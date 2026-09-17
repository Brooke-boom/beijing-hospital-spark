# -*- coding: utf-8 -*-
"""
DWD 层：清洗 + 坐标关联
================================================================================
输入：HDFS /hospital/ods/parquet/*
输出：HDFS /hospital/dwd/*（Parquet，复盘标准②：预处理结果回写 HDFS）

清洗规则（与原 etl_hospital.py 完全一致，保证口径不漂移）：
  1. 机构主表：id 纯数字防御、按 id 去重、区名去"北京"前缀
  2. 等级归一化 level_norm（含 grade_scope=not_applicable → 不适用医院分级）
  3. 类型归一化 category_norm
  4. 关联 geocode 坐标缓存（按 id 去重防 join 膨胀）+ 坐标精度分桶

运行（单独）：
  spark-submit --master spark://spark-master:7077 jobs/layer_dwd.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DWD, ODS, get_spark, print_section, write_parquet  # noqa: E402

from pyspark.sql import functions as F  # noqa: E402
from pyspark.sql.types import DoubleType  # noqa: E402


def build_institution_dwd(inst_ods, geo_ods):
    """机构主表清洗 + 坐标关联（保持原口径）"""
    return (
        inst_ods
        .filter(F.col("id").isNotNull() & (F.length(F.col("id")) > 0))
        .filter(F.col("id").rlike("^\\d+$") & (F.length(F.col("id")) <= 6))
        .filter(F.col("name").isNotNull() & (F.length(F.col("name")) > 0))
        .dropDuplicates(["id"])
        .withColumn(
            "district_clean",
            F.when(F.col("district").startswith("北京"), F.substring(F.col("district"), 3, 20))
            .when(F.col("district").endswith("县"), F.concat(F.col("district"), F.lit("")))
            .otherwise(F.col("district"))
        )
        .withColumn(
            "level_norm",
            # 诊所/村卫生室/门诊部等不参加医院等级评审 → 单独归类，避免混入"未定级"
            F.when(F.col("grade_scope") == "not_applicable", F.lit("不适用医院分级"))
            .when(F.col("level").isin("三级", "三级甲等", "三级乙等", "三级丙等"), F.lit("三级"))
            .when(F.col("level").isin("二级", "二级甲等", "二级乙等", "二级丙等"), F.lit("二级"))
            .when(F.col("level").isin("一级", "一级甲等", "一级乙等", "一级丙等"), F.lit("一级"))
            .when(F.col("level_sub").isin("甲等", "甲"), F.lit("甲"))
            .otherwise(F.lit("未定级"))
        )
        .withColumn(
            "category_norm",
            F.when(F.col("category").contains("医院"), F.lit("医院"))
            .when(F.col("category").contains("诊所"), F.lit("诊所"))
            .when(F.col("category").contains("门诊"), F.lit("门诊部"))
            .when(F.col("category").contains("疾控"), F.lit("疾控中心"))
            .when(F.col("category").contains("妇幼"), F.lit("妇幼保健"))
            .when(F.col("category").contains("急救"), F.lit("急救中心"))
            .when(F.col("category").contains("血液"), F.lit("血站"))
            .when(F.col("category").contains("体检"), F.lit("体检中心"))
            .otherwise(F.lit("其他机构"))
        )
        .join(
            geo_ods.select("id", "lng", "lat", "level", "formatted", "src")
                   .dropDuplicates(["id"])
                   .withColumnRenamed("level", "coord_level")
                   .withColumnRenamed("formatted", "coord_formatted")
                   .withColumnRenamed("src", "coord_source"),
            on="id", how="left"
        )
        .withColumn("lng_d", F.col("lng").cast(DoubleType()))
        .withColumn("lat_d", F.col("lat").cast(DoubleType()))
        .withColumn(
            "coord_precision",
            F.when(F.col("lng_d").isNull(), F.lit("missing"))
            .when(F.col("coord_level").isin("门址", "兴趣点"), F.lit("high"))
            .otherwise(F.lit("rough"))
        )
        .withColumn("src_count_int", F.col("src_count").cast("int"))
        .select(
            "id", "name", "district_clean", "category", "category_norm",
            "category_sub",
            "level", "level_sub", "level_norm", "grade_scope",
            "addr", "phone", "postal", "key_depts",
            "feature", "feature_level",
            "national_specialty", "national_specialty_count",
            "municipal_specialty", "municipal_specialty_count",
            "ownership", "ownership_basis",
            # 医疗协作网络维度（integrate_networks.py 写入主表，此处透传）
            "net_pediatric", "net_stroke", "net_neonatal", "net_maternal",
            "lng_d", "lat_d", "coord_formatted", "coord_level", "coord_source", "coord_precision",
            "econ", "profit", "category_raw", "src_count_int", "source_files",
            # 科室数量在线核实（build_deptcount_online.py 写入主表；空值=沿用源条目数口径）
            "dept_count_online", "dept_count_src",
        )
        .withColumnRenamed("district_clean", "district")
        .withColumnRenamed("lng_d", "lng")
        .withColumnRenamed("lat_d", "lat")
        # CSV 读入的计数字段为 string，转 int 避免按字典序排序（"9" > "28"）
        .withColumn("national_specialty_count",
                    F.coalesce(F.col("national_specialty_count").cast("int"), F.lit(0)))
        .withColumn("municipal_specialty_count",
                    F.coalesce(F.col("municipal_specialty_count").cast("int"), F.lit(0)))
        .withColumn("dept_count_online",
                    F.coalesce(F.col("dept_count_online").cast("int")))
    )


def main(spark):
    print_section("DWD 层：清洗 + 坐标关联 → HDFS Parquet")
    inst_ods = spark.read.parquet("%s/ods_institution" % ODS)
    geo_ods = spark.read.parquet("%s/ods_geocode" % ODS)
    depts_ods = spark.read.parquet("%s/ods_dept_relation" % ODS)
    specialty_ods = spark.read.parquet("%s/ods_specialty" % ODS)

    # 1. 机构主表
    inst_dwd = build_institution_dwd(inst_ods, geo_ods)
    n = inst_dwd.count()
    print("  dwd_institution_clean: %d 行（清洗后）" % n)
    write_parquet(inst_dwd, "%s/dwd_institution_clean" % DWD)

    # 2. 机构-科室关系
    depts_dwd = (
        depts_ods
        .filter(F.col("hospital_id").isNotNull())
        .filter(F.col("dept_name").isNotNull())
        .select("hospital_id", "dept_name", "source", "is_key_specialty")
    )
    print("  dwd_dept_relation_clean: %d 行" % depts_dwd.count())
    write_parquet(depts_dwd, "%s/dwd_dept_relation_clean" % DWD)

    # 3. 重点专科名单
    specialty_dwd = (
        specialty_ods
        .filter(F.col("hospital").isNotNull())
        .select("hospital", "specialties")
        .withColumnRenamed("hospital", "hospital_name")
        .withColumnRenamed("specialties", "specialty_name")
    )
    print("  dwd_specialty_clean: %d 行" % specialty_dwd.count())
    write_parquet(specialty_dwd, "%s/dwd_specialty_clean" % DWD)

    print("\n  DWD 口径自检：")
    for r in sorted(inst_dwd.groupBy("level_norm").count().collect(),
                    key=lambda x: -x["count"]):
        print("    level_norm=%-10s %6d" % (r["level_norm"], r["count"]))


if __name__ == "__main__":
    s = get_spark("HospitalDW-DWD")
    try:
        main(s)
    finally:
        s.stop()
