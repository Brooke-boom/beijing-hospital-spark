# -*- coding: utf-8 -*-
"""
ODS 层：原始数据列式化
================================================================================
输入：HDFS /hospital/ods/raw/*.csv（由 etl/upload_to_hdfs.py 入湖）
输出：HDFS /hospital/ods/parquet/<表名>（Parquet）

ODS 只做"搬运 + 列式化"，不做任何清洗：schema 与源文件一致，
保证原始数据可回溯（数据血缘最低层）。

运行（单独）：
  spark-submit --master 'local[*]' jobs/layer_ods.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    ODS, ODS_RAW, get_spark, print_section, write_parquet, read_parquet,
)

# 源文件 → ODS 表名（与源系统一致，保留原始语义）
SOURCES = [
    ("master_institutions.csv", "ods_institution", dict(multiLine=True)),
    ("hospital_depts.csv", "ods_dept_relation", dict(multiLine=True)),
    ("dept_dict.csv", "ods_dept_dict", dict(multiLine=False)),
    ("specialty_departments.csv", "ods_specialty", dict(multiLine=False)),
    ("geocode_cache.csv", "ods_geocode", dict(multiLine=True)),
    ("disease_dept_map.csv", "ods_disease_dept", dict(multiLine=False)),
]


def main(spark):
    print_section("ODS 层：HDFS CSV → HDFS Parquet（原始数据列式化）")
    for fname, table, opt in SOURCES:
        src = "%s/%s" % (ODS_RAW, fname)
        df = spark.read.csv(src, header=True, encoding="utf-8",
                            multiLine=opt.get("multiLine", False))
        n = df.count()
        print("  %-24s ← %-28s %6d 行 × %d 列" % (table, fname, n, len(df.columns)))
        write_parquet(df, "%s/%s" % (ODS, table))

    print("\n  ODS 产出校验：")
    for _, table, _ in SOURCES:
        n = read_parquet(spark, "%s/%s" % (ODS, table)).count()
        print("    %-24s %6d 行" % (table, n))


if __name__ == "__main__":
    s = get_spark("HospitalDW-ODS")
    try:
        main(s)
    finally:
        s.stop()
