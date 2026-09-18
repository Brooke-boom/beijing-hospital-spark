# -*- coding: utf-8 -*-
"""
ADS 层（服务层）：HDFS 分析结果 → MySQL 业务库
================================================================================
定位：HDFS 存数仓分层（ODS/DWD/DWS），MySQL 只保存"面向业务系统的服务层结果"
（复盘标准④：分析结果保存到业务数据库）。

输入：HDFS /hospital/dwd/*、/hospital/dws/*（Parquet）
输出：MySQL hospital 库

服务层表：
  ① 服务副本（Flask 检索/详情直接查询）
     dwd_institution_clean / dwd_dept_relation_clean / dwd_specialty_clean
     dws_inst_by_district / dws_inst_by_level / dws_inst_by_category / dws_dept_coverage
  ② 应用宽表（大屏检索与图表）
     ads_inst_search / ads_district_overview / ads_level_overview / ads_specialty_hospital
  ③ 新增分析结果
     ads_network_summary（协作网络）/ ads_time_trend（行为趋势）
     ads_time_feature（功能使用结构）/ ads_etl_snapshot（批次时效性）

运行（单独）：
  spark-submit --master 'local[*]' --packages com.mysql:mysql-connector-j:8.4.0 jobs/layer_ads.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    DWD, DWS, META, get_spark, print_section, write_mysql,
)

from pyspark.sql import functions as F  # noqa: E402

SPACE = DWS + "/space"
CATEGORY = DWS + "/category"
DEPT = DWS + "/dept"
NETWORK = DWS + "/network"
TIME = DWS + "/time"

SERVING_COPIES = [
    ("%s/dwd_institution_clean" % DWD, "dwd_institution_clean"),
    ("%s/dwd_dept_relation_clean" % DWD, "dwd_dept_relation_clean"),
    ("%s/dwd_specialty_clean" % DWD, "dwd_specialty_clean"),
    ("%s/dws_inst_by_district" % SPACE, "dws_inst_by_district"),
    ("%s/dws_inst_by_level" % CATEGORY, "dws_inst_by_level"),
    ("%s/dws_inst_by_category" % CATEGORY, "dws_inst_by_category"),
    ("%s/dws_dept_coverage" % DEPT, "dws_dept_coverage"),
]


def build_ads_inst_search(inst_dwd, depts_dwd):
    """ADS1：筛选排序主表（Flask 检索用）——口径与原实现一致"""
    inst_with_dept_count = (
        depts_dwd.groupBy("hospital_id")
        .agg(
            F.count("dept_name").alias("dept_count"),
            F.sum(F.when(F.col("is_key_specialty") == "1", 1).otherwise(0)).alias("key_specialty_count"),
        )
    )
    # 重点专科数权威口径 = feature 三级分级中的 L1（重点专科/重点科室）科系数
    # 注意：feature 源数据混用半角「;」与全角「；」，切分需两者兼容
    inst_feature_cnt = (
        inst_dwd.select("id", "feature", "feature_level")
        .withColumn("fk_cnt",
                    F.when(F.col("feature_level") == "1", F.size(F.split(F.col("feature"), "[;；]")))
                    .otherwise(0))
        .select("id", "fk_cnt")
    )
    # dept_count 口径：在线核实值（dept_count_online，官网口径）优先，
    # 无在线值沿用源条目数（dwd_dept_relation_clean 计数）——见 govern_report_deptcount_online.md
    return (
        inst_dwd
        .join(inst_with_dept_count, inst_dwd["id"] == inst_with_dept_count["hospital_id"], "left")
        .drop("hospital_id")
        .join(inst_feature_cnt, "id", "left")
        .withColumn("key_specialty_count",
                    F.when(F.col("fk_cnt").isNotNull() & (F.col("fk_cnt") > 0), F.col("fk_cnt"))
                    .otherwise(F.col("key_specialty_count")))
        .withColumn("dept_count",
                    F.when(F.col("dept_count_online").isNotNull(), F.col("dept_count_online"))
                    .otherwise(F.col("dept_count")))
        .drop("fk_cnt", "dept_count_online",
              "ownership_online", "level_online", "level_sub_online")
        # 保留 *_src / dept_count_src / ownership_src / level_src 落库（前端标注在线核实口径）
        .na.fill({"dept_count": 0, "key_specialty_count": 0})
    )


def build_specialty_hospital(inst_dwd):
    """ADS4：专科找医院（feature L1 权威口径，分段展开科室名）"""

    def _clean_spec(seg):
        seg = F.trim(F.regexp_replace(seg, r"[（(][^（）()]{0,80}[)）]", ""))
        seg = F.trim(F.regexp_replace(seg, r"^(另有|另设|另|含|包括|国家|省|市|院级|首都区域|其中)\s*", ""))
        seg = F.trim(F.regexp_replace(seg, r"[;；、,，\s]+$", ""))
        return seg

    return (
        inst_dwd
        .filter(F.col("feature_level") == "1")
        .filter(F.col("feature").isNotNull() & (F.length(F.col("feature")) > 0))
        .withColumn("seg", F.explode(F.split(F.col("feature"), "[;；]")))
        .withColumn("seg", _clean_spec(F.col("seg")))
        .filter(F.length(F.col("seg")) >= 2)
        .filter(F.length(F.col("seg")) <= 14)
        .select(
            F.col("id").alias("hospital_id"),
            "name", "district", "level_norm", "lng", "lat",
            F.col("seg").alias("dept_name"),
            F.lit("feature_l1").alias("source"),
        )
    )


def main(spark):
    print_section("ADS 层：HDFS 分析结果 → MySQL 业务库（服务层）")

    inst_dwd = spark.read.parquet("%s/dwd_institution_clean" % DWD).cache()
    depts_dwd = spark.read.parquet("%s/dwd_dept_relation_clean" % DWD).cache()

    # ---------- ① 服务副本 ----------
    print("\n  ① 服务副本（Flask 直接查询）")
    for src, table in SERVING_COPIES:
        df = spark.read.parquet(src)
        write_mysql(df, table)

    # ---------- ② 应用宽表 ----------
    print("\n  ② 应用宽表（大屏检索与图表）")
    ads_inst = build_ads_inst_search(inst_dwd, depts_dwd)
    write_mysql(ads_inst, "ads_inst_search")
    print("     ads_inst_search: %d 行（筛选主表）" % ads_inst.count())

    ads_district = spark.read.parquet("%s/dws_inst_by_district" % SPACE).select(
        "district", "inst_count", "category_diversity",
        "level_3_count", "level_2_count",
        "coord_high_count", "coord_rough_count", "coord_missing_count",
        "public_count", "private_count", "ownership_unknown_count",
    )
    write_mysql(ads_district, "ads_district_overview")
    print("     ads_district_overview: %d 行" % ads_district.count())

    ads_level = spark.read.parquet("%s/dws_inst_by_level" % CATEGORY) \
        .select("level_norm", "inst_count", "district_count", "category_count")
    write_mysql(ads_level, "ads_level_overview")
    print("     ads_level_overview: %d 行" % ads_level.count())

    spec = build_specialty_hospital(inst_dwd)
    write_mysql(spec, "ads_specialty_hospital")
    print("     ads_specialty_hospital: %d 行（专科找医院）" % spec.count())

    # ---------- ③ 新增分析结果 ----------
    print("\n  ③ 新增分析结果（维度分析落库）")
    net = spark.read.parquet("%s/dws_network_summary" % NETWORK) \
        .select("network_key", "network_name", "member_count", "core_count",
                "district_count", "level_3_count")
    write_mysql(net, "ads_network_summary")
    print("     ads_network_summary: %d 行" % net.count())

    trend = spark.read.parquet("%s/dws_time_daily" % TIME)
    write_mysql(trend, "ads_time_trend")
    print("     ads_time_trend: %d 行（行为日趋势）" % trend.count())

    feat = spark.read.parquet("%s/dws_time_feature" % TIME)
    write_mysql(feat, "ads_time_feature")
    print("     ads_time_feature: %d 行（功能使用结构）" % feat.count())

    snap = spark.read.parquet("%s/snapshots" % META)
    write_mysql(snap, "ads_etl_snapshot")
    print("     ads_etl_snapshot: %d 行（数据批次时效性）" % snap.count())

    # ---------- 校验 ----------
    print_section("服务层校验（MySQL 回读）")
    for t in ["ads_inst_search", "ads_district_overview", "ads_level_overview",
              "ads_specialty_hospital", "ads_network_summary", "ads_time_trend",
              "ads_etl_snapshot"]:
        from common import MYSQL_PROPS, MYSQL_URL
        df = spark.read.jdbc(MYSQL_URL, t, properties=MYSQL_PROPS)
        print("  %-26s %6d 行" % (t, df.count()))


if __name__ == "__main__":
    s = get_spark("HospitalDW-ADS")
    try:
        main(s)
    finally:
        s.stop()
