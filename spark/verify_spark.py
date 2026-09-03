# -*- coding: utf-8 -*-
"""
Spark 环境验证脚本：读取医院主表，做一次真实的分布式计算
=========================================================
在容器内提交：
  docker compose exec spark-master /opt/spark/bin/spark-submit \
      --master spark://spark-master:7077 /opt/workspace/jobs/verify_spark.py

验证点：
  1. SparkSession 能创建（集群连通）
  2. 能读 CSV（挂载数据卷正常）
  3. 分布式聚合计算（groupBy + count + orderBy）
  4. collect 回 driver 正常
"""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = (SparkSession.builder
         .appName("hospital-verify")
         .getOrCreate())

DATA = "/opt/workspace/data/processed/master_institutions.csv"

df = (spark.read
      .option("header", True)
      .option("encoding", "UTF-8")
      .csv(DATA))

total = df.count()
print("=" * 50)
print("PySpark 环境验证")
print("=" * 50)
print("机构总数: %d" % total)

print("\n各区机构数（Top 10）:")
(df.filter(F.col("district") != "")
   .groupBy("district")
   .count()
   .orderBy(F.desc("count"))
   .show(10, truncate=False))

print("各类型机构数:")
df.groupBy("category").count().orderBy(F.desc("count")).show(20, truncate=False)

print("Spark 版本: %s" % spark.version)
print("验证通过 ✓")
spark.stop()
