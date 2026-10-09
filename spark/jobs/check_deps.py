# -*- coding: utf-8 -*-
"""
依赖与环境自检（答辩现场可用）
================================================================================
验证三件事（外加一项覆盖对账）：
  1. Maven 坐标（--packages）能否解析到 MySQL 驱动 → JDBC 连通性
  2. HDFS 数仓各分层目录是否可读、行数是否符合预期
     —— 逐张读 LAYERS 里登记的表，**再拿 HDFS 实际目录与清单对账**：
        实存但未登记的表会报红（漏登记 = 那张表坏了也不报警），
        登记了但 HDFS 上没有的也报红。
  3. Spark 运行模式（单机 local[*] 或 Standalone 集群，两者均合法）

运行：
  bash spark/run_all.sh --only deps     # 走 run_all 的封装
  或容器内直接（单机模式，默认）：
  spark-submit --master 'local[*]' \
    --conf spark.jars.ivy=/opt/workspace/jobs/.ivy2 \
    --packages com.mysql:mysql-connector-j:8.4.0 \
    /opt/workspace/jobs/jobs/check_deps.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    DWD, DWS, MYSQL_PROPS, MYSQL_URL, ODS, get_spark, print_section,
)

# (目录, 层名, 该层应存在的表)
#
# ⚠️ 这份清单是**自检的覆盖范围**，不是文档。少列一张表 = 那张表坏了也不会报红。
#    2026-09-24 修：原清单只列 23 张，而 HDFS 实际有 28 张 —— DWS 的
#    dws_coord_coverage / dws_level_category / dws_dept_strength /
#    dws_network_district / dws_time_hour 五张从未被自检覆盖。
#    现在第 2 节末会拿 HDFS 实际目录与这份清单对账，**漏列即报红**，不会再悄悄腐烂。
LAYERS = [
    (ODS, "ODS 层·原始数据列式化", [
        "ods_institution", "ods_dept_relation", "ods_dept_dict",
        "ods_specialty", "ods_geocode", "ods_disease_dept"]),
    (DWD, "DWD 层·清洗与坐标关联", [
        "dwd_institution_clean", "dwd_dept_relation_clean", "dwd_specialty_clean"]),
    (DWS + "/space", "DWS·空间维度", [
        "dws_inst_by_district", "dws_district_center", "dws_district_distance",
        "dws_coord_coverage"]),
    (DWS + "/category", "DWS·类型与等级维度", [
        "dws_inst_by_level", "dws_inst_by_category", "dws_inst_by_ownership",
        "dws_level_category"]),
    (DWS + "/dept", "DWS·科室维度", [
        "dws_dept_coverage", "dws_dept_by_district", "dws_dept_density",
        "dws_dept_strength"]),
    (DWS + "/network", "DWS·协作网络维度", [
        "dws_network_summary", "dws_network_members", "dws_network_district"]),
    (DWS + "/time", "DWS·时间维度", [
        "dws_time_daily", "dws_time_event", "dws_time_feature", "dws_time_hour"]),
]


def hdfs_subdirs(spark, path):
    """列出 HDFS 目录下的一级子目录名（用来跟 LAYERS 清单对账）。"""
    jvm = spark._jvm
    hpath = jvm.org.apache.hadoop.fs.Path(path)
    fs = jvm.org.apache.hadoop.fs.FileSystem.get(hpath.toUri(), spark._jsc.hadoopConfiguration())
    return sorted(s.getPath().getName() for s in fs.listStatus(hpath) if s.isDirectory())


def main(spark=None):
    own = spark is None
    spark = spark or get_spark("HospitalDW-DepCheck")
    ok = True

    print_section("1. Spark 运行模式")
    master = spark.sparkContext.master
    print("  master = %s" % master)
    if master.startswith("spark://"):
        print("  ✓ Standalone 集群模式")
    elif master.startswith("local"):
        print("  ✓ 单机模式 local[*]（复盘标准④：Maven 单机模式，依赖同样由 Maven 坐标解析）")
    else:
        ok = False
        print("  ⚠️  未识别的运行模式（应为 local[*] 或 spark://host:port）")

    print_section("2. HDFS 数仓分层可读性与行数")
    n_total = 0
    for base, label, tables in LAYERS:
        print("  【%s】%s" % (label, base.replace("hdfs://namenode:8020", "")))
        for t in tables:
            n_total += 1
            try:
                n = spark.read.parquet("%s/%s" % (base, t)).count()
                print("    ✓ %-46s %7d 行" % (t, n))
            except Exception as e:
                ok = False
                print("    ✗ %-46s 读取失败: %s" % (t, str(e)[:80]))
    print("  —— 清单覆盖 %d 张表" % n_total)

    # 覆盖对账：HDFS 上实际存在的表，若不在上面清单里 → 报红。
    # 只加「逐张读」是不够的：新加一张表而忘了登记，自检会照样全绿。
    print("  · 与 HDFS 实际目录对账（漏列即报红）")
    for base, label, tables in LAYERS:
        try:
            actual = hdfs_subdirs(spark, base)
        except Exception as e:
            ok = False
            print("    ✗ %s 目录列举失败，无法证明覆盖完整: %s" % (label, str(e)[:80]))
            continue
        extra = [x for x in actual if x not in tables]
        missing = [x for x in tables if x not in actual]
        if extra or missing:
            ok = False
            if extra:
                print("    ✗ %s 有 %d 张表未纳入自检: %s" % (label, len(extra), ", ".join(extra)))
            if missing:
                print("    ✗ %s 清单里有、HDFS 上不存在: %s" % (label, ", ".join(missing)))
        else:
            print("    ✓ %s 实存 %d 张，清单一致" % (label, len(actual)))

    print_section("3. Maven 依赖 + MySQL 连通性")
    try:
        df = spark.read.jdbc(MYSQL_URL, "ads_inst_search", properties=MYSQL_PROPS)
        print("  ✓ jdbc 驱动可用，ads_inst_search = %d 行" % df.count())
    except Exception as e:
        ok = False
        print("  ✗ JDBC 失败（检查 --packages 坐标）: %s" % str(e)[:160])

    if own:
        spark.stop()
    print("\n%s" % ("✅ 自检全部通过" if ok else "❌ 存在未通过项，见上方 ✗ 标记"))
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
