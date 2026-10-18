# -*- coding: utf-8 -*-
"""
区县医疗资源 KMeans 聚类（Spark MLlib）
================================================================================
目的：对北京市 16 个区按医疗资源结构做无监督聚类，为论文第 5 章
「大数据处理过程」与需求 3.2.4「数据挖掘应用」提供真实结果背书。

输入（只读，不写 HDFS，不影响贯通校验的表清单对账）：
  /hospital/dwd/dwd_institution_clean   机构明细（9,678 行）
  /hospital/dwd/dwd_dept_relation_clean 机构-科室映射（11,419 行）

特征（每区 6 维，均为现算统计量）：
  机构总数 / 医院数 / 三级数 / 二级数 / 重点专科数（国家级+市级）/
  科室覆盖机构数（来自科室映射表）。取口径跨来源稳定、覆盖率高的 6 维，
  （办别字段各区数据源写法不一，不入选，避免口径噪声污染聚类）

依赖：spark-master 容器内需 numpy（pyspark.ml 硬依赖）。
  docker exec -u root spark-master pip3 install -q --no-cache-dir numpy
  （容器重建后需重装；根治可在 Spark 镜像 Dockerfile 里加同一行）

用法（宿主机）：
  docker exec spark-master /opt/spark/bin/spark-submit --master "local[*]" \
      /opt/workspace/jobs/jobs/cluster_district.py
"""
from pyspark.sql import SparkSession, functions as F
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import ClusteringEvaluator

S = SparkSession.builder.appName("district_kmeans").getOrCreate()
S.sparkContext.setLogLevel("WARN")

inst = S.read.parquet("hdfs://namenode:8020/hospital/dwd/dwd_institution_clean")
rel = S.read.parquet("hdfs://namenode:8020/hospital/dwd/dwd_dept_relation_clean")

base = inst.groupBy("district").agg(
    F.count("*").alias("total_cnt"),
    F.sum(F.when(F.col("category_norm") == "医院", 1).otherwise(0)).alias("hospital_cnt"),
    F.sum(F.when(F.col("level_norm") == "三级", 1).otherwise(0)).alias("lv3_cnt"),
    F.sum(F.when(F.col("level_norm") == "二级", 1).otherwise(0)).alias("lv2_cnt"),
    F.coalesce(F.sum(F.col("national_specialty_count") + F.col("municipal_specialty_count")),
                F.lit(0)).alias("specialty_cnt"),
)
cover = rel.select("hospital_id").distinct() \
    .join(inst.select(F.col("id").alias("hospital_id"), "district"), on="hospital_id") \
    .groupBy("district").agg(F.count("*").alias("dept_cover_cnt"))

feat = base.join(cover, on="district", how="left").fillna(0, subset=["dept_cover_cnt"])
FEATURES = ["total_cnt", "hospital_cnt", "lv3_cnt", "lv2_cnt",
            "specialty_cnt", "dept_cover_cnt"]

assembled = VectorAssembler(inputCols=FEATURES, outputCol="raw_vec").transform(feat)
scaler = StandardScaler(inputCol="raw_vec", outputCol="features",
                        withMean=True, withStd=True).fit(assembled)
data = scaler.transform(assembled).cache()

print("\n===== 各区特征（原始值） =====")
feat.orderBy(F.desc("total_cnt")).show(20, truncate=False)

print("===== 选 k：轮廓系数（k=2..5） =====")
best_k, best_s = None, -1.0
for k in (2, 3, 4, 5):
    m = KMeans(k=k, seed=42, maxIter=50).fit(data)
    s = ClusteringEvaluator().evaluate(m.transform(data))
    print("k=%d  silhouette=%.4f" % (k, s))
    if s > best_s:
        best_k, best_s = k, s
print("chosen k = %d (silhouette=%.4f)" % (best_k, best_s))

model = KMeans(k=best_k, seed=42, maxIter=50).fit(data)
out = model.transform(data)
print("\n===== 聚类结果（k=%d, silhouette=%.4f） =====" % (best_k, best_s))
out.select("district", "total_cnt", "hospital_cnt", "lv3_cnt", "lv2_cnt",
           "specialty_cnt", "dept_cover_cnt", "prediction").orderBy("prediction", F.desc("total_cnt")).show(20, truncate=False)

print("===== 聚类中心（标准化空间） =====")
centers = model.clusterCenters()
for i, c in enumerate(centers):
    print("cluster %d: %s" % (i, ["%.2f" % v for v in c]))

print("\n===== 各簇规模与均值（原始空间，用于论文描述） =====")
out.groupBy("prediction").agg(
    F.count("*").alias("districts"),
    F.round(F.avg("total_cnt"), 1).alias("avg_total"),
    F.round(F.avg("hospital_cnt"), 1).alias("avg_hospital"),
    F.round(F.avg("lv3_cnt"), 1).alias("avg_lv3"),
    F.round(F.avg("specialty_cnt"), 1).alias("avg_specialty"),
).orderBy("prediction").show(truncate=False)

S.stop()
