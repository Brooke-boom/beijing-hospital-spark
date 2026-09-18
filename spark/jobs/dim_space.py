# -*- coding: utf-8 -*-
"""
维度一：空间维度分析（admin/spatial）
================================================================================
分析对象：医疗机构的地理分布与空间可达性
输入：HDFS /hospital/dwd/dwd_institution_clean
输出：HDFS /hospital/dws/space/*

产出：
  1. dws_inst_by_district   16 区机构数量与结构（含公立/民营、等级、坐标精度）
  2. dws_coord_coverage     坐标覆盖精度分布（门址/兴趣点=high，其余=rough，缺失=missing）
  3. dws_district_center    各区坐标重心（由机构经纬度均值求得）
  4. dws_district_distance  16×16 区间 Haversine 球面距离矩阵（空间可达性基础）

运行（单独）：
  spark-submit --master 'local[*]' jobs/dim_space.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DWD, DWS, get_spark, print_section, write_parquet  # noqa: E402

from pyspark.sql import functions as F  # noqa: E402

OUT = DWS + "/space"


def main(spark):
    print_section("空间维度：机构地理分布与空间可达性")
    inst = spark.read.parquet("%s/dwd_institution_clean" % DWD).cache()
    print("  输入 dwd_institution_clean: %d 行" % inst.count())

    # ---------- 1. 区县分布 ----------
    dws_district = (
        inst.groupBy("district")
        .agg(
            F.count("id").alias("inst_count"),
            F.countDistinct("category_norm").alias("category_diversity"),
            F.sum(F.when(F.col("level_norm") == "三级", 1).otherwise(0)).alias("level_3_count"),
            F.sum(F.when(F.col("level_norm") == "二级", 1).otherwise(0)).alias("level_2_count"),
            F.sum(F.when(F.col("coord_precision") == "high", 1).otherwise(0)).alias("coord_high_count"),
            F.sum(F.when(F.col("coord_precision") == "rough", 1).otherwise(0)).alias("coord_rough_count"),
            F.sum(F.when(F.col("coord_precision") == "missing", 1).otherwise(0)).alias("coord_missing_count"),
            F.sum(F.when(F.col("ownership") == "公立", 1).otherwise(0)).alias("public_count"),
            F.sum(F.when(F.col("ownership") == "民营", 1).otherwise(0)).alias("private_count"),
            F.sum(F.when(F.col("ownership") == "未标注", 1).otherwise(0)).alias("ownership_unknown_count"),
        )
        .filter(F.col("district").isNotNull() & (F.length(F.col("district")) > 0))
        .orderBy(F.desc("inst_count"))
    )
    write_parquet(dws_district, "%s/dws_inst_by_district" % OUT)
    print("  ✓ dws_inst_by_district: %d 个区（首位 %s %d 家）"
          % (dws_district.count(), dws_district.first()["district"], dws_district.first()["inst_count"]))

    # ---------- 2. 坐标覆盖精度 ----------
    total = inst.count()
    dws_coord = (
        inst.groupBy("coord_precision")
        .agg(F.count("id").alias("inst_count"))
        .withColumn("ratio", F.round(F.col("inst_count") / F.lit(total), 6))
        .orderBy(F.desc("inst_count"))
    )
    write_parquet(dws_coord, "%s/dws_coord_coverage" % OUT)
    cov = {r["coord_precision"]: r["inst_count"] for r in dws_coord.collect()}
    print("  ✓ dws_coord_coverage: 高精度 %d / 粗略 %d / 缺失 %d（覆盖 %.2f%%）"
          % (cov.get("high", 0), cov.get("rough", 0), cov.get("missing", 0),
             100.0 * (total - cov.get("missing", 0)) / total))

    # ---------- 3. 各区坐标重心 ----------
    centers = (
        inst.filter(F.col("lng").isNotNull() & F.col("lat").isNotNull())
        .groupBy("district")
        .agg(F.avg("lng").alias("center_lng"), F.avg("lat").alias("center_lat"),
             F.count("id").alias("sample_count"))
        .filter(F.col("district").isNotNull() & (F.length(F.col("district")) > 0))
        .withColumn("center_lng", F.round(F.col("center_lng"), 6))
        .withColumn("center_lat", F.round(F.col("center_lat"), 6))
    )
    write_parquet(centers, "%s/dws_district_center" % OUT)
    print("  ✓ dws_district_center: %d 个区的空间重心" % centers.count())

    # ---------- 4. 区间 Haversine 距离矩阵 ----------
    a = centers.select(F.col("district").alias("from_district"),
                       F.col("center_lng").alias("a_lng"), F.col("center_lat").alias("a_lat"))
    b = centers.select(F.col("district").alias("to_district"),
                       F.col("center_lng").alias("b_lng"), F.col("center_lat").alias("b_lat"))
    dist = (
        a.crossJoin(b)
        .withColumn(
            "distance_km",
            F.round(
                F.expr("""
                  2 * 6371.0088 * asin(least(1.0, sqrt(
                      pow(sin(radians(b_lat - a_lat) / 2), 2) +
                      cos(radians(a_lat)) * cos(radians(b_lat)) *
                      pow(sin(radians(b_lng - a_lng) / 2), 2)
                  )))
                """), 3)
        )
        .select("from_district", "to_district", "distance_km")
    )
    write_parquet(dist, "%s/dws_district_distance" % OUT)
    n_dist = dist.count()
    mx = dist.orderBy(F.desc("distance_km")).first()
    print("  ✓ dws_district_distance: %d 条区间距离（最远 %s → %s %.2f km）"
          % (n_dist, mx["from_district"], mx["to_district"], mx["distance_km"]))


if __name__ == "__main__":
    s = get_spark("HospitalDW-DimSpace")
    try:
        main(s)
    finally:
        s.stop()
