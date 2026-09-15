# -*- coding: utf-8 -*-
"""
维度五：时间维度分析（time）
================================================================================
分析对象：
  A. 用户行为时间趋势 —— 数据源 /hospital/ods/raw/fact_user_event.csv（业务埋点日志入湖）
     日粒度事件量、活跃会话、事件类型结构、活跃时段分布
  B. 数据批次时效性 —— 每次 ETL 跑批写入一条快照（机构总量/等级结构/坐标覆盖），
     累积后可分析数据增量与时效性趋势

输入：HDFS /hospital/ods/raw/fact_user_event.csv（CSV）
      HDFS /hospital/dwd/dwd_institution_clean（Parquet，供批次快照取数）
输出：HDFS /hospital/dws/time/*
      HDFS /hospital/meta/snapshots/（追加，Parquet）

运行（单独）：
  spark-submit --master spark://spark-master:7077 jobs/dim_time.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    DWD, DWS, META, ODS_RAW, get_spark, print_section, write_parquet,
)

from pyspark.sql import functions as F  # noqa: E402

OUT = DWS + "/time"


def behavior_analysis(spark):
    """A. 用户行为时间趋势"""
    print("\n  ── A. 用户行为时间趋势（埋点日志）──")
    raw = spark.read.csv("%s/fact_user_event.csv" % ODS_RAW, header=True, encoding="utf-8")
    ev = (
        raw.filter(F.col("ev").isNotNull())
        .withColumn("ts", F.to_timestamp("created_at"))
        .filter(F.col("ts").isNotNull())
        .withColumn("dt", F.to_date("ts"))
        .withColumn("hour", F.hour("ts"))
        .cache()
    )
    n = ev.count()
    print("     行为事件总量: %d 条" % n)

    # A1. 日粒度趋势
    daily = (
        ev.groupBy("dt")
        .agg(
            F.count("id").alias("event_count"),
            F.countDistinct("sid").alias("session_count"),
            F.countDistinct("ev").alias("event_type_count"),
        )
        .orderBy("dt")
    )
    write_parquet(daily, "%s/dws_time_daily" % OUT)
    print("     ✓ dws_time_daily: %d 天" % daily.count())

    # A2. 事件类型结构（含首末次出现时间，反映功能使用节奏）
    by_event = (
        ev.groupBy("ev")
        .agg(
            F.count("id").alias("event_count"),
            F.min("dt").alias("first_date"),
            F.max("dt").alias("last_date"),
            F.countDistinct("sid").alias("session_count"),
        )
        .orderBy(F.desc("event_count"))
    )
    write_parquet(by_event, "%s/dws_time_event" % OUT)
    print("     ✓ dws_time_event: %d 类事件（首位 %s %d 次）"
          % (by_event.count(), by_event.first()["ev"], by_event.first()["event_count"]))

    # A3. 活跃时段分布
    by_hour = (
        ev.groupBy("hour")
        .agg(F.count("id").alias("event_count"))
        .orderBy("hour")
    )
    write_parquet(by_hour, "%s/dws_time_hour" % OUT)
    print("     ✓ dws_time_hour: %d 个时段" % by_hour.count())

    # A4. 功能使用结构（检索/导诊/详情/对比/筛选/定位）
    feat = (
        ev.withColumn(
            "feature",
            F.when(F.col("ev").isin("search", "nlq", "filter", "filter_district", "filter_level"),
                   F.lit("多维筛选检索"))
            .when(F.col("ev") == "triage", F.lit("智能导诊"))
            .when(F.col("ev").isin("detail", "drawer"), F.lit("机构详情"))
            .when(F.col("ev") == "compare", F.lit("医院对比"))
            .when(F.col("ev") == "locate", F.lit("空间定位"))
            .otherwise(F.lit("其他"))
        )
        .groupBy("feature")
        .agg(F.count("id").alias("event_count"),
             F.countDistinct("sid").alias("session_count"))
        .orderBy(F.desc("event_count"))
    )
    write_parquet(feat, "%s/dws_time_feature" % OUT)
    print("     ✓ dws_time_feature: %d 类功能" % feat.count())
    return daily, n


def snapshot(spark, inst):
    """B. 批次快照（数据时效性维度）"""
    print("\n  ── B. 数据批次快照（时效性维度）──")
    d = inst.agg(
        F.count("id").alias("inst_count"),
        F.sum(F.when(F.col("level_norm") == "三级", 1).otherwise(0)).alias("level_3"),
        F.sum(F.when(F.col("level_norm") == "二级", 1).otherwise(0)).alias("level_2"),
        F.sum(F.when(F.col("level_norm") == "一级", 1).otherwise(0)).alias("level_1"),
        F.sum(F.when(F.col("level_norm") == "未定级", 1).otherwise(0)).alias("level_none"),
        F.countDistinct("district").alias("district_count"),
        F.sum(F.when(F.col("lng").isNotNull(), 1).otherwise(0)).alias("coord_ok"),
    ).first()
    row = spark.createDataFrame(
        [(int(d["inst_count"]), int(d["level_3"]), int(d["level_2"]), int(d["level_1"]),
          int(d["level_none"]), int(d["district_count"]), int(d["coord_ok"]))],
        "inst_count long, level_3 long, level_2 long, level_1 long, "
        "level_none long, district_count long, coord_ok long",
    )
    snap = (
        row.withColumn("batch_ts", F.date_format(F.current_timestamp(), "yyyy-MM-dd HH:mm:ss"))
        .withColumn("batch_date", F.date_format(F.current_timestamp(), "yyyy-MM-dd"))
        .select("batch_ts", "batch_date", "inst_count", "level_3", "level_2",
                "level_1", "level_none", "district_count", "coord_ok")
    )
    write_parquet(snap, "%s/snapshots" % META, mode="append")
    print("     ✓ 批次快照已追加: %s（机构 %d 家，三级 %d / 二级 %d / 一级 %d）"
          % (snap.first()["batch_ts"], d["inst_count"], d["level_3"], d["level_2"], d["level_1"]))
    return snap


def main(spark):
    print_section("时间维度：行为趋势 + 数据批次时效性")
    behavior_analysis(spark)
    inst = spark.read.parquet("%s/dwd_institution_clean" % DWD)
    snapshot(spark, inst)


if __name__ == "__main__":
    s = get_spark("HospitalDW-DimTime")
    try:
        main(s)
    finally:
        s.stop()
