# -*- coding: utf-8 -*-
"""
数仓公共模块：SparkSession / HDFS 路径常量 / 读写工具
================================================================================
存储分层（复盘标准①②：数据从 HDFS 来、预处理结果回写 HDFS）
  /hospital/ods/raw      原始文本（CSV，入湖时落盘）
  /hospital/ods/parquet  ODS 层 Parquet（原始数据列式化）
  /hospital/dwd          DWD 层 Parquet（清洗 + 坐标关联）
  /hospital/dws           DWS 层 Parquet（按分析维度轻度汇总）
  /hospital/meta         批次快照等元数据
  MySQL（业务库）        仅存 ADS 服务层结果，供 Flask 查询（复盘标准④）
"""

import os
import sys

from pyspark.sql import SparkSession

# ---------------- HDFS 路径 ----------------
HDFS_NS = "hdfs://namenode:8020"
HDFS_ROOT = HDFS_NS + "/hospital"
ODS_RAW = HDFS_ROOT + "/ods/raw"          # 原始 CSV
ODS = HDFS_ROOT + "/ods/parquet"          # ODS 层 Parquet
DWD = HDFS_ROOT + "/dwd"                  # DWD 层 Parquet
DWS = HDFS_ROOT + "/dws"                  # DWS 层 Parquet（按维度）
ADS = HDFS_ROOT + "/ads"                  # ADS 层 Parquet
META = HDFS_ROOT + "/meta"                # 元数据（批次快照）

# ---------------- MySQL（业务库，仅存服务层结果） ----------------
MYSQL_HOST = os.environ.get("MYSQL_HOST", "hospital-mysql")
MYSQL_DB = "hospital"
MYSQL_URL = ("jdbc:mysql://%s:3306/%s?useSSL=false&allowPublicKeyRetrieval=true"
             "&serverTimezone=Asia/Shanghai&characterEncoding=utf8" % (MYSQL_HOST, MYSQL_DB))
MYSQL_PROPS = {
    "user": "root",
    "password": "hospital123",
    "driver": "com.mysql.cj.jdbc.Driver",
    "rewriteBatchedStatements": "true",
}

MYSQL_LOCAL_URL = ("jdbc:mysql://127.0.0.1:3307/%s?useSSL=false&allowPublicKeyRetrieval=true"
                   "&serverTimezone=Asia/Shanghai&characterEncoding=utf8" % MYSQL_DB)


def get_spark(app_name):
    """构建 SparkSession（Standalone 集群模式由 spark-submit --master 指定）"""
    spark = (
        SparkSession.builder
        .appName(app_name)
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.driver.memory", "1g")
        # HDFS 客户端：以超级用户写入（容器内 Spark 进程 uid=185）
        .config("spark.hadoop.fs.defaultFS", HDFS_NS)
        .config("spark.hadoop.dfs.client.use.datanode.hostname", "true")
        .config("spark.hadoop.dfs.replication", "1")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# ---------------- 读写封装 ----------------
def write_parquet(df, path, mode="overwrite", partitions=None):
    """DataFrame → HDFS Parquet（回写 HDFS，复盘标准②）"""
    w = df.write.mode(mode).option("compression", "snappy")
    if partitions:
        w = w.partitionBy(*partitions)
    w.parquet(path)
    print("    ✓ 已写入 HDFS: %s" % path)
    return path


def read_parquet(spark, path):
    return spark.read.parquet(path)


def write_mysql(df, table, mode="overwrite"):
    """DataFrame → MySQL 业务库（复盘标准④：分析结果落业务数据库）"""
    df.write.jdbc(url=MYSQL_URL, table=table, mode=mode, properties=MYSQL_PROPS)
    print("    ✓ 已写入 MySQL: %s" % table)


def print_section(title):
    print("\n" + "=" * 66)
    print("  %s" % title)
    print("=" * 66)


def ensure_local_path():
    """允许单独 spark-submit 某个维度模块时 import 本文件"""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
