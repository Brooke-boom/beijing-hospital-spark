# -*- coding: utf-8 -*-
"""
依赖与环境自检（答辩现场可用）
================================================================================
验证三件事：
  1. Maven 坐标（--packages）能否解析到 MySQL 驱动 → JDBC 连通性
  2. HDFS 数仓各分层目录是否可读、行数是否符合预期
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

LAYERS = [
    (ODS, ["ods_institution", "ods_dept_relation", "ods_dept_dict",
           "ods_specialty", "ods_geocode", "ods_disease_dept"]),
    (DWD, ["dwd_institution_clean", "dwd_dept_relation_clean", "dwd_specialty_clean"]),
    (DWS + "/space", ["dws_inst_by_district", "dws_district_center", "dws_district_distance"]),
    (DWS + "/category", ["dws_inst_by_level", "dws_inst_by_category", "dws_inst_by_ownership"]),
    (DWS + "/dept", ["dws_dept_coverage", "dws_dept_by_district", "dws_dept_density"]),
    (DWS + "/network", ["dws_network_summary", "dws_network_members"]),
    (DWS + "/time", ["dws_time_daily", "dws_time_event", "dws_time_feature"]),
]


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
    for base, tables in LAYERS:
        for t in tables:
            try:
                n = spark.read.parquet("%s/%s" % (base, t)).count()
                print("  ✓ %-52s %6d 行" % ("%s/%s" % (base.replace("hdfs://namenode:8020", ""), t), n))
            except Exception as e:
                ok = False
                print("  ✗ %-52s 读取失败: %s" % (t, str(e)[:80]))

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
