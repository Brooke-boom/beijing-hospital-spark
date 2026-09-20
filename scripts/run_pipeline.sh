#!/usr/bin/env bash
# =============================================================================
#  全链路一键跑批：容器 → 入湖 → 数仓 → 落库 → 索引 → 前端产物 → 校验
# -----------------------------------------------------------------------------
#  这条脚本把"从零到可演示"的每一步串起来，顺序即依赖顺序。
#  每一步都可以用开关跳过，便于只重跑变化的那一段。
#
#  用法：
#    bash scripts/run_pipeline.sh                 # 全流程
#    bash scripts/run_pipeline.sh --from dwd       # 只重跑 DWD 及之后（改清洗规则时用）
#    bash scripts/run_pipeline.sh --only ads       # 只重跑 ADS 落库
#    bash scripts/run_pipeline.sh --skip-ingest    # 跳过数据入湖（HDFS 上已是最新）
#    bash scripts/run_pipeline.sh --skip-front     # 只跑数据链路，不动前端产物
#    SPARK_MASTER=spark://spark-master:7077 bash scripts/run_pipeline.sh   # 集群模式
#
#  前置：Docker 已启动，本机 Node/受管 Python 可用（web/vue/node_modules 已链接）
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DOCKER="${DOCKER:-/usr/local/bin/docker}"
PY="${PY:-/Users/brooke/.workbuddy/binaries/python/envs/default/bin/python}"
SKIP_INGEST=0
SKIP_FRONT=0
SKIP_VERIFY=0
PASS_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-ingest) SKIP_INGEST=1 ;;
    --skip-front)  SKIP_FRONT=1 ;;
    --skip-verify) SKIP_VERIFY=1 ;;
    --from|--only)  PASS_ARGS+=("$1" "$2"); shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\n\033[1m▶ %s\033[0m\n' "$1"; }
ok()   { printf '  ✓ %s\n' "$1"; }

# ---------------------------------------------------------------------------
step "0/6 启动容器（HDFS / Spark / MySQL）"
"$DOCKER" compose up -d >/dev/null
for i in $(seq 1 60); do
  ready=$("$DOCKER" ps --format '{{.Names}}\t{{.Status}}' \
          | grep -E '^(hdfs-namenode|spark-master|hospital-mysql)\b' \
          | grep -c 'Up' || true)
  [[ "$ready" == "3" ]] && break
  sleep 2
done
[[ "$ready" == "3" ]] || { echo "❌ 容器未全部就绪（$ready/3），请检查 docker compose logs" >&2; exit 1; }
ok "hdfs-namenode / spark-master / hospital-mysql 均已运行"

for i in $(seq 1 30); do
  if "$DOCKER" exec hdfs-namenode hdfs dfs -ls / >/dev/null 2>&1; then break; fi
  sleep 2
done
"$DOCKER" exec hdfs-namenode hdfs dfs -ls / >/dev/null 2>&1 \
  || { echo "❌ HDFS 未就绪" >&2; exit 1; }
ok "HDFS 可访问（NameNode: http://localhost:9870）"

# ---------------------------------------------------------------------------
if [[ "$SKIP_INGEST" == "1" ]]; then
  step "1/6 数据入湖（已跳过）"
else
  step "1/6 数据入湖：本地治理结果 + 行为日志 → HDFS /hospital/ods/raw"
  "$PY" etl/upload_to_hdfs.py
fi

# ---------------------------------------------------------------------------
step "2/6 数仓跑批：ODS → DWD → DWS(5 维度) → ADS"
bash spark/run_all.sh "${PASS_ARGS[@]+"${PASS_ARGS[@]}"}"

# ---------------------------------------------------------------------------
step "3/6 业务库索引（ADS overwrite 会丢索引，必须重建）"
"$PY" etl/create_indexes.py

# ---------------------------------------------------------------------------
if [[ "$SKIP_FRONT" == "1" ]]; then
  step "4/6 前端产物（已跳过）"
else
  step "4/6 前端产物：快照 + 词表 + 单文件大屏 + Vue 构建"
  bash web/build_spa.sh
  bash web/vue/build.sh
fi

# ---------------------------------------------------------------------------
if [[ "$SKIP_VERIFY" == "1" ]]; then
  step "5/6 校验（已跳过）"
else
  step "5/6 校验：产物完整性 + 双端一致性"
  "$PY" etl/verify_artifacts.py
  "$PY" etl/verify_offline_nlq.py
fi

step "6/6 完成"
cat <<'EOF'
  启动服务后可访问：
    在线（Vue + Flask）： http://127.0.0.1:5001/spa/
    单文件大屏：         http://127.0.0.1:5001/
    启动命令：           bash web/start.sh
  想确认真实链路是否贯通，再跑： bash scripts/verify_pipeline.sh
EOF
