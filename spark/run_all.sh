#!/usr/bin/env bash
# 数仓全链路一键跑批（宿主机执行）
# =============================================================================
#  前置：docker compose up -d （HDFS + Spark + MySQL 全部就绪）
#        python3 etl/upload_to_hdfs.py （治理后数据入湖到 HDFS）
#
#  用法：
#    bash spark/run_all.sh                  # 全链路：ODS→DWD→5 维度→ADS
#    bash spark/run_all.sh --only ads       # 只跑服务层落库
#    bash spark/run_all.sh --from space     # 从空间维度开始
# =============================================================================
set -euo pipefail

DOCKER="${DOCKER:-/usr/local/bin/docker}"
CONTAINER="spark-master"
JOB_DIR="/opt/workspace/jobs/jobs"
# Maven 依赖缓存落在已挂载的 jobs 目录（宿主 ./spark/.ivy2），
# 首次联网解析后本地留存，答辩现场无网也能复用。
IVY_DIR="/opt/workspace/jobs/.ivy2"
# Maven 坐标（复盘标准③：依赖用 Maven 声明，不再手工挂 --jars）
PACKAGES="com.mysql:mysql-connector-j:8.4.0"

if ! "$DOCKER" ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "❌ 容器 ${CONTAINER} 未运行，请先执行：docker compose up -d" >&2
  exit 1
fi

if ! "$DOCKER" exec hdfs-namenode hdfs dfs -ls / >/dev/null 2>&1; then
  echo "❌ HDFS 不可用，请先执行：docker compose up -d namenode datanode" >&2
  exit 1
fi

echo "▶ 提交数仓作业到 Spark 集群（$CONTAINER）"
"$DOCKER" exec "$CONTAINER" /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --conf spark.jars.ivy="$IVY_DIR" \
  --packages "$PACKAGES" \
  "$JOB_DIR/run_all.py" "$@"
