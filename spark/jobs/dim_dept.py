# -*- coding: utf-8 -*-
"""
维度三：科室维度分析（department）
================================================================================
分析对象：科室资源的供给广度与空间分布
输入：HDFS /hospital/dwd/dwd_institution_clean + dwd_dept_relation_clean
输出：HDFS /hospital/dws/dept/*

产出：
  1. dws_dept_coverage      科室覆盖度（开设该科室的机构数 + 重点专科标记数）
  2. dws_dept_by_district   科室 × 区 分布（哪些区缺哪些科室）
  3. dws_dept_density       每区科室种类密度（区级科室丰富度）

运行（单独）：
  spark-submit --master spark://spark-master:7077 jobs/dim_dept.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DWD, DWS, get_spark, print_section, write_parquet  # noqa: E402

from pyspark.sql import functions as F  # noqa: E402

OUT = DWS + "/dept"


def main(spark):
    print_section("科室维度：科室资源供给广度与空间分布")
    inst = spark.read.parquet("%s/dwd_institution_clean" % DWD)
    depts = spark.read.parquet("%s/dwd_dept_relation_clean" % DWD).cache()

    # ---------- 1. 科室覆盖度 ----------
    dws_dept_cov = (
        depts.groupBy("dept_name")
        .agg(
            F.countDistinct("hospital_id").alias("hospital_count"),
            F.sum(F.when(F.col("is_key_specialty") == "1", 1).otherwise(0)).alias("key_specialty_count"),
        )
        .orderBy(F.desc("hospital_count"))
    )
    write_parquet(dws_dept_cov, "%s/dws_dept_coverage" % OUT)
    print("  ✓ dws_dept_coverage: %d 个科室（首位 %s，%d 家机构开设）"
          % (dws_dept_cov.count(), dws_dept_cov.first()["dept_name"],
             dws_dept_cov.first()["hospital_count"]))

    # ---------- 2. 科室 × 区 分布（空间维度交叉） ----------
    inst_key = inst.select(F.col("id").alias("hospital_id"),
                           F.col("district"), F.col("level_norm"))
    dept_district = (
        depts.join(inst_key, on="hospital_id", how="inner")
        .filter(F.col("district").isNotNull() & (F.length(F.col("district")) > 0))
        .groupBy("dept_name", "district")
        .agg(F.countDistinct("hospital_id").alias("hospital_count"))
        .orderBy(F.desc("hospital_count"))
    )
    write_parquet(dept_district, "%s/dws_dept_by_district" % OUT)
    print("  ✓ dws_dept_by_district: %d 条（科室 × 区）" % dept_district.count())

    # ---------- 3. 各区科室种类密度 ----------
    density = (
        depts.join(inst_key, on="hospital_id", how="inner")
        .filter(F.col("district").isNotNull() & (F.length(F.col("district")) > 0))
        .groupBy("district")
        .agg(
            F.countDistinct("dept_name").alias("dept_variety"),
            F.countDistinct("hospital_id").alias("hospital_count"),
            F.count("dept_name").alias("dept_relation_count"),
        )
        .withColumn("dept_per_hospital",
                    F.round(F.col("dept_relation_count") / F.col("hospital_count"), 3))
        .orderBy(F.desc("dept_variety"))
    )
    write_parquet(density, "%s/dws_dept_density" % OUT)
    top = density.first()
    print("  ✓ dws_dept_density: %d 个区（科室种类最多：%s %d 种）"
          % (density.count(), top["district"], top["dept_variety"]))

    print("    科室关系总量: %d 条" % depts.count())


if __name__ == "__main__":
    s = get_spark("HospitalDW-DimDept")
    try:
        main(s)
    finally:
        s.stop()
