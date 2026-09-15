#!/bin/bash
# HDFS 容器入口：按 HDFS_ROLE 启动 namenode / datanode
# NameNode 首次启动自动格式化（目录为空时）
set -e

ROLE="${HDFS_ROLE:-namenode}"

case "$ROLE" in
  namenode)
    if [ ! -f /data/dfs/name/current/VERSION ]; then
      echo "[hdfs] 检测到 NameNode 未格式化，执行 hdfs namenode -format ..."
      hdfs namenode -format -force -nonInteractive
    fi
    echo "[hdfs] 启动 NameNode（RPC 8020 / Web UI 9870）"
    exec hdfs namenode
    ;;
  datanode)
    echo "[hdfs] 启动 DataNode（Web UI 9864）"
    exec hdfs datanode
    ;;
  *)
    exec "$@"
    ;;
esac
