# -*- coding: utf-8 -*-
"""
维度四：医疗协作网络维度分析（network）
================================================================================
分析对象：北京市四类医疗协作网络的空间与等级构成
  - 儿科医联体（net_pediatric：核心 / 成员）
  - 卒中中心网络（net_stroke）
  - 危重新生儿救治中心（net_neonatal）
  - 危重孕产妇救治中心（net_maternal）

输入：HDFS /hospital/dwd/dwd_institution_clean
输出：HDFS /hospital/dws/network/*

运行（单独）：
  spark-submit --master spark://spark-master:7077 jobs/dim_network.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DWD, DWS, get_spark, print_section, write_parquet  # noqa: E402

from pyspark.sql import functions as F  # noqa: E402

OUT = DWS + "/network"

# 维度定义：源字段 → 网络标识 / 中文名
NETWORKS = [
    ("net_pediatric", "pediatric", "儿科医联体"),
    ("net_stroke", "stroke", "卒中中心网络"),
    ("net_neonatal", "neonatal", "危重新生儿救治中心"),
    ("net_maternal", "maternal", "危重孕产妇救治中心"),
]


def main(spark):
    print_section("协作网络维度：四类医疗协作网络构成分析")
    inst = spark.read.parquet("%s/dwd_institution_clean" % DWD).cache()

    # ---------- 1. 网络成员明细（四列竖表化） ----------
    members = None
    for col, key, name in NETWORKS:
        raw = F.col(col)
        part = (
            inst.filter(raw.isNotNull() & (F.length(raw) > 0))
            .select(
                F.lit(key).alias("network_key"),
                F.lit(name).alias("network_name"),
                F.col("id").alias("hospital_id"),
                "name", "district", "level_norm", "category_norm",
                raw.alias("role_raw"),
                # 角色归一化：儿科医联体区分"核心/成员"，其余网络源值（1/市级）统一为"成员"
                F.when(raw == "核心", F.lit("核心")).otherwise(F.lit("成员")).alias("role"),
            )
        )
        members = part if members is None else members.unionByName(part)
    members = members.cache()
    write_parquet(members, "%s/dws_network_members" % OUT)
    print("  ✓ dws_network_members: %d 条网络成员记录" % members.count())

    # ---------- 2. 网络规模汇总 ----------
    summary = (
        members.groupBy("network_key", "network_name")
        .agg(
            F.count("hospital_id").alias("member_count"),
            F.sum(F.when(F.col("role") == "核心", 1).otherwise(0)).alias("core_count"),
            F.countDistinct("district").alias("district_count"),
            F.sum(F.when(F.col("level_norm") == "三级", 1).otherwise(0)).alias("level_3_count"),
        )
        .withColumn("member_count", F.col("member_count").cast("int"))
        .withColumn("core_count", F.col("core_count").cast("int"))
        .orderBy(F.desc("member_count"))
    )
    write_parquet(summary, "%s/dws_network_summary" % OUT)
    print("  ✓ dws_network_summary:")
    for r in summary.collect():
        extra = "，核心 %d" % r["core_count"] if r["core_count"] else ""
        print("      %-16s %3d 家%s（覆盖 %d 个区，三级 %d 家）"
              % (r["network_name"], r["member_count"], extra,
                 r["district_count"], r["level_3_count"]))

    # ---------- 3. 网络 × 区 空间分布 ----------
    net_district = (
        members.groupBy("network_key", "network_name", "district")
        .agg(F.count("hospital_id").alias("member_count"))
        .orderBy("network_key", F.desc("member_count"))
    )
    write_parquet(net_district, "%s/dws_network_district" % OUT)
    print("  ✓ dws_network_district: %d 条（网络 × 区）" % net_district.count())


if __name__ == "__main__":
    s = get_spark("HospitalDW-DimNetwork")
    try:
        main(s)
    finally:
        s.stop()
