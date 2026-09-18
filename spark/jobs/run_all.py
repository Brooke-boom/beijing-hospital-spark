# -*- coding: utf-8 -*-
"""
数仓全链路编排入口
================================================================================
一次 SparkSession 串起 8 个阶段，避免反复启停 JVM：

  ods      原始数据列式化      HDFS CSV      → HDFS Parquet
  dwd      清洗 + 坐标关联     HDFS Parquet  → HDFS Parquet
  space    空间维度分析        DWD → DWS/space
  category 类型等级维度分析    DWD → DWS/category
  dept     科室维度分析        DWD+科室 → DWS/dept
  network  协作网络维度分析    DWD → DWS/network
  time     时间维度分析        行为日志+DWD → DWS/time（含批次快照）
  ads      服务层落库          HDFS 结果 → MySQL（业务库）

用法（容器内，单机模式）：
  spark-submit --master 'local[*]' \
    --conf spark.jars.ivy=/opt/workspace/jobs/.ivy2 \
    --packages com.mysql:mysql-connector-j:8.4.0 \
    /opt/workspace/jobs/jobs/run_all.py [--only ads] [--from space]

宿主机封装：bash spark/run_all.sh [同上参数]
  （默认单机 local[*]；SPARK_MASTER=spark://spark-master:7077 可切集群模式）
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common  # noqa: E402
import check_deps  # noqa: E402
import dim_category  # noqa: E402
import dim_dept  # noqa: E402
import dim_network  # noqa: E402
import dim_space  # noqa: E402
import dim_time  # noqa: E402
import layer_ads  # noqa: E402
import layer_dwd  # noqa: E402
import layer_ods  # noqa: E402

# 阶段定义：(标识, 名称, 执行函数, 是否需要 DWD 已产出)
STAGES = [
    ("ods",      "ODS 层·原始数据列式化",   layer_ods.main,      False),
    ("dwd",      "DWD 层·清洗与坐标关联",   layer_dwd.main,      False),
    ("space",    "空间维度分析",            dim_space.main,      True),
    ("category", "类型与等级维度分析",      dim_category.main,   True),
    ("dept",     "科室维度分析",            dim_dept.main,       True),
    ("network",  "协作网络维度分析",        dim_network.main,    True),
    ("time",     "时间维度分析",            dim_time.main,       True),
    ("ads",      "ADS 服务层·结果落业务库", layer_ads.main,      False),
    ("deps",     "环境自检·HDFS+依赖+JDBC", check_deps.main,     False),
]
ORDER = [s[0] for s in STAGES]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只执行指定阶段")
    ap.add_argument("--from", dest="start", default="ods", help="从指定阶段开始执行")
    args = ap.parse_args()

    if args.only:
        todo = [s for s in STAGES if s[0] == args.only]
        if not todo:
            print("未知阶段: %s（可选：%s）" % (args.only, ", ".join(ORDER)))
            return 1
    else:
        idx = ORDER.index(args.start) if args.start in ORDER else 0
        todo = STAGES[idx:]

    common.print_section("数仓全链路编排：%d 个阶段" % len(todo))
    print("  阶段顺序: %s" % " → ".join(s[0] for s in todo))
    print("  HDFS 根: %s" % common.HDFS_ROOT)

    spark = common.get_spark("HospitalDW-Pipeline")
    print("  ✅ Spark %s 已启动（运行模式 master=%s）"
          % (spark.version, spark.sparkContext.master))

    timings = []
    try:
        for key, name, fn, _ in todo:
            t0 = time.time()
            print("\n" + "█" * 66)
            print("█ 阶段 [%s] %s" % (key, name))
            print("█" * 66)
            fn(spark)
            dt = time.time() - t0
            timings.append((key, name, dt))
            print("\n  ⏱  阶段 [%s] 完成，用时 %.1f 秒" % (key, dt))
    finally:
        spark.stop()

    common.print_section("执行汇总")
    total = 0.0
    for key, name, dt in timings:
        total += dt
        print("  %-9s %-24s %7.1f s" % (key, name, dt))
    print("  %-9s %-24s %7.1f s" % ("合计", "%d 个阶段" % len(timings), total))
    print("\n✅ 数仓全链路执行完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
