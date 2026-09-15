# -*- coding: utf-8 -*-
"""
维度二：类型与等级维度分析（category / level / ownership）
================================================================================
分析对象：医疗机构的分类结构（等级、类型、主办方）
输入：HDFS /hospital/dwd/dwd_institution_clean
输出：HDFS /hospital/dws/category/*

产出：
  1. dws_inst_by_level      等级结构（三级/二级/一级/未定级/不适用医院分级）
  2. dws_inst_by_category   机构类型结构（医院/诊所/门诊部/…）
  3. dws_inst_by_ownership  主办方结构（公立/民营/未标注）
  4. dws_level_category     等级 × 类型 交叉表（结构分析的二维视角）

运行（单独）：
  spark-submit --master spark://spark-master:7077 jobs/dim_category.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DWD, DWS, get_spark, print_section, write_parquet  # noqa: E402

from pyspark.sql import functions as F  # noqa: E402

OUT = DWS + "/category"


def main(spark):
    print_section("类型维度：等级 / 类型 / 主办方结构分析")
    inst = spark.read.parquet("%s/dwd_institution_clean" % DWD).cache()

    # ---------- 1. 等级结构 ----------
    dws_level = (
        inst.groupBy("level_norm")
        .agg(
            F.count("id").alias("inst_count"),
            F.countDistinct("district").alias("district_count"),
            F.countDistinct("category_norm").alias("category_count"),
        )
        .orderBy(F.desc("inst_count"))
    )
    write_parquet(dws_level, "%s/dws_inst_by_level" % OUT)
    lv = {r["level_norm"]: r["inst_count"] for r in dws_level.collect()}
    print("  ✓ dws_inst_by_level: 三级 %d / 二级 %d / 一级 %d / 未定级 %d / 不适用 %d"
          % (lv.get("三级", 0), lv.get("二级", 0), lv.get("一级", 0),
             lv.get("未定级", 0), lv.get("不适用医院分级", 0)))

    # ---------- 2. 类型结构 ----------
    dws_category = (
        inst.groupBy("category_norm")
        .agg(
            F.count("id").alias("inst_count"),
            F.countDistinct("district").alias("district_count"),
            F.sum(F.when(F.col("level_norm") == "三级", 1).otherwise(0)).alias("level_3_count"),
        )
        .orderBy(F.desc("inst_count"))
    )
    write_parquet(dws_category, "%s/dws_inst_by_category" % OUT)
    print("  ✓ dws_inst_by_category: %d 类（首位 %s %d 家）"
          % (dws_category.count(), dws_category.first()["category_norm"],
             dws_category.first()["inst_count"]))

    # ---------- 3. 主办方结构 ----------
    dws_owner = (
        inst.groupBy("ownership")
        .agg(
            F.count("id").alias("inst_count"),
            F.countDistinct("district").alias("district_count"),
            F.sum(F.when(F.col("level_norm") == "三级", 1).otherwise(0)).alias("level_3_count"),
        )
        .orderBy(F.desc("inst_count"))
    )
    write_parquet(dws_owner, "%s/dws_inst_by_ownership" % OUT)
    print("  ✓ dws_inst_by_ownership: %d 类（公立 %d / 民营 %d）"
          % (dws_owner.count(),
             sum(r["inst_count"] for r in dws_owner.collect() if r["ownership"] == "公立"),
             sum(r["inst_count"] for r in dws_owner.collect() if r["ownership"] == "民营")))

    # ---------- 4. 等级 × 类型 交叉 ----------
    cross = (
        inst.groupBy("level_norm", "category_norm")
        .agg(F.count("id").alias("inst_count"))
        .orderBy(F.desc("inst_count"))
    )
    write_parquet(cross, "%s/dws_level_category" % OUT)
    print("  ✓ dws_level_category: %d 个交叉组合" % cross.count())


if __name__ == "__main__":
    s = get_spark("HospitalDW-DimCategory")
    try:
        main(s)
    finally:
        s.stop()
