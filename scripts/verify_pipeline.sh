#!/usr/bin/env bash
# =============================================================================
#  真实链路贯通校验（不重跑跑批，只证明「已产出的东西真的通」）
# -----------------------------------------------------------------------------
#  与 run_pipeline.sh 的分工：
#    run_pipeline.sh        从零到可演示：跑批 + 构建产物 + 产物一致性
#    verify_pipeline.sh     跑批之后/答辩之前：证明**跨组件**真的接上了
#
#  四段：
#    1/4 容器     —— hdfs-namenode / spark-master / hospital-mysql 三件套在跑
#    2/4 HDFS+Spark —— 分层表逐张可读 + 行数 + 清单对账 + Maven 坐标 + JDBC
#                      （复用 spark/jobs/check_deps.py，避免第二份表清单）
#    3/4 MySQL    —— 业务库表数、关键表行数、跨层关系一致
#    4/4 Flask API —— 服务起得来，接口返回的是**库里的真数据**而不是兜底快照
#
#  ⚠️ 断言一律锚在「关系」上（HDFS 行数 == MySQL 行数 == 接口返回的 total），
#     不写死绝对值 —— 数据口径一变，写死的期望值就变成假报警。
#
#  用法：
#    bash scripts/verify_pipeline.sh                # 全跑（会临时起一个 Flask）
#    bash scripts/verify_pipeline.sh --skip-flask   # 不起服务，只查数据链路
#    bash scripts/verify_pipeline.sh --keep-flask   # 查完不关服务（接着手工演示）
# =============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DOCKER="${DOCKER:-/usr/local/bin/docker}"
PY="${PY:-/Users/brooke/.workbuddy/binaries/python/envs/default/bin/python}"
PORT="${PORT:-5001}"

SKIP_FLASK=0
KEEP_FLASK=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-flask) SKIP_FLASK=1 ;;
    --keep-flask) KEEP_FLASK=1 ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

FAILED=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

step() { printf '\n\033[1m▶ %s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; FAILED=$((FAILED + 1)); }
info() { printf '    %s\n' "$1"; }

# ---------------------------------------------------------------------------
step "1/4 容器：HDFS / Spark / MySQL"
names=$("$DOCKER" ps --format '{{.Names}}' 2>/dev/null || true)
for c in hdfs-namenode spark-master hospital-mysql; do
  if grep -qx "$c" <<<"$names"; then ok "$c 在运行"; else bad "$c 未运行（docker compose up -d）"; fi
done
[[ "$FAILED" == "0" ]] || { echo; echo "❌ 容器不全，后续无法校验" >&2; exit 1; }

# ---------------------------------------------------------------------------
step "2/4 HDFS + Spark：分层表可读性 / 清单对账 / Maven 坐标 / JDBC"
# 走 check_deps.py —— 表清单只有它一份，避免这里再写第二份（两份必然走偏）
if bash spark/run_all.sh --only deps >"$TMP/deps.log" 2>&1; then
  ok "环境自检通过（HDFS 逐张可读 + 清单对账一致 + Maven 坐标解析 + JDBC 连通）"
else
  bad "环境自检未通过，明细："
  grep -E '(✓|✗)' "$TMP/deps.log" | sed 's/^/      /' | tail -40
fi
info "$(grep -c '✓ ' "$TMP/deps.log" || true) 项 ✓ / $(grep -c '✗ ' "$TMP/deps.log" || true) 项 ✗"
# 从自检输出里取两张关键表的行数，第 3 段用来跟 MySQL 对账
hdfs_rows() { grep -E "✓ ${1} " "$TMP/deps.log" | head -1 | awk '{print $(NF-1)}'; }
HDFS_INST="$(hdfs_rows ods_institution)"
HDFS_REL="$(hdfs_rows dwd_dept_relation_clean)"
info "HDFS ods_institution=${HDFS_INST:-?}  dwd_dept_relation_clean=${HDFS_REL:-?}"

# ---------------------------------------------------------------------------
step "3/4 MySQL 业务库：表数 / 关键表行数 / 跨层关系一致"
"$PY" - "$HDFS_INST" "$HDFS_REL" <<'PY' >"$TMP/db.log" 2>&1
import os, sys, pymysql
hdfs_inst = sys.argv[1] or None
hdfs_rel = sys.argv[2] or None
cfg = dict(host=os.environ.get("DB_HOST", "127.0.0.1"),
           port=int(os.environ.get("DB_PORT", 3307)),
           user=os.environ.get("DB_USER", "app"),
           password=os.environ.get("DB_PASS", "app123"),
           database="hospital", charset="utf8mb4",
           cursorclass=pymysql.cursors.DictCursor)
try:
    c = pymysql.connect(**cfg)
except Exception as e:
    print("FAIL 连不上业务库：%s" % e); sys.exit(0)

def one(sql):
    cur = c.cursor(); cur.execute(sql); r = cur.fetchone()
    return list(r.values())[0] if r else None

tables = []
cur = c.cursor()
cur.execute("SHOW TABLES")
for r in cur.fetchall():
    tables.append(list(r.values())[0])
tables.sort()
print("tables=%d" % len(tables))
if len(tables) < 20:
    print("FAIL 业务库表数 %d < 20，疑似落库不完整" % len(tables))
else:
    print("OK  业务库 %d 张表" % len(tables))

inst = one("SELECT COUNT(*) FROM ads_inst_search")
rel = one("SELECT COUNT(*) FROM dwd_dept_relation_clean")
snap = one("SELECT COUNT(*) FROM ads_etl_snapshot")
print("mysql_inst=%s mysql_rel=%s snapshots=%s" % (inst, rel, snap))

if not inst:
    print("FAIL ads_inst_search 为空")
elif hdfs_inst and str(inst) != str(hdfs_inst):
    print("FAIL 跨层不一致：HDFS ods_institution=%s ≠ MySQL ads_inst_search=%s（改过清洗口径后要重跑 ads 阶段）"
          % (hdfs_inst, inst))
else:
    print("OK  HDFS ods_institution == MySQL ads_inst_search == %s" % inst)

if not rel:
    print("FAIL dwd_dept_relation_clean 为空（科室筛选会全空）")
elif hdfs_rel and str(rel) != str(hdfs_rel):
    print("FAIL 跨层不一致：HDFS dwd_dept_relation_clean=%s ≠ MySQL %s" % (hdfs_rel, rel))
else:
    print("OK  HDFS dwd_dept_relation_clean == MySQL dwd_dept_relation_clean == %s" % rel)

if not snap:
    print("FAIL ads_etl_snapshot 为空（前端「快照日期」无来源）")
else:
    print("OK  批次快照 %s 条" % snap)
c.close()
PY
while IFS= read -r line; do
  case "$line" in
    OK*)   ok "${line#OK  }" ;;
    FAIL*) bad "${line#FAIL }" ;;
    *)     info "$line" ;;
  esac
done < "$TMP/db.log"

# ---------------------------------------------------------------------------
if [[ "$SKIP_FLASK" == "1" ]]; then
  step "4/4 Flask API（已跳过）"
else
  step "4/4 Flask API：接口返回的是库里的真数据"
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    info "端口 $PORT 已有服务在跑，直接复用它"
    FLASK_PID=""
  else
    "$PY" web/app.py >"$TMP/flask.log" 2>&1 &
    FLASK_PID=$!
    disown "$FLASK_PID" 2>/dev/null || true   # 免得收尾 kill 时打印 "Terminated"
    for _ in $(seq 1 30); do
      lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && break
      sleep 1
    done
  fi
  if ! lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    bad "服务未起来，看 $TMP/flask.log"
    tail -15 "$TMP/flask.log" 2>/dev/null | sed 's/^/      /'
  else
    # 沙箱/代理环境里发往 127.0.0.1 的请求会被 HTTP_PROXY 劫持 → 显式绕开代理
    "$PY" - "$PORT" <<'PY' >"$TMP/api.log" 2>&1
import json, sys, urllib.request
port = sys.argv[1]
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
BASE = "http://127.0.0.1:%s" % port

def get(path):
    with op.open(BASE + path, timeout=30) as r:
        return r.status, json.loads(r.read().decode("utf-8"))

def size(obj):
    """接口返回可能是 list / dict / 带包装的 dict，统一取「条目数」。"""
    if isinstance(obj, list):
        return len(obj)
    if isinstance(obj, dict):
        if "items" in obj and isinstance(obj["items"], list):
            return len(obj["items"])
        for v in obj.values():
            if isinstance(v, list):
                return len(v)
        return len(obj)
    return 1

try:
    st, h = get("/api/health")
except Exception as e:
    print("FAIL /api/health 不可达：%s" % e); sys.exit(0)

if st != 200 or h.get("status") != "ok":
    print("FAIL /api/health 异常：%s %s" % (st, h))
else:
    print("OK  /api/health 200，institutions=%s" % h.get("institutions"))

st, body = get("/api/institutions?page_size=1")
total = body.get("total")
items = body.get("items") or []
if st != 200 or not items:
    print("FAIL /api/institutions 无数据：%s total=%s items=%s" % (st, total, len(items)))
elif h.get("institutions") != total:
    print("FAIL 两接口口径不一致：/api/health=%s ≠ /api/institutions.total=%s"
          % (h.get("institutions"), total))
else:
    print("OK  /api/institutions.total == /api/health.institutions == %s" % total)

# 维度接口抽样：每个都必须返回非空，否则前端对应页面就是空板
for path in ("/api/overview/districts", "/api/overview/levels",
             "/api/overview/depts", "/api/meta/filters"):
    try:
        st, b = get(path)
        n = size(b)
        print(("OK  " if n else "FAIL ") + "%s 返回 %d 项" % (path, n))
    except Exception as e:
        print("FAIL %s 不可达：%s" % (path, e))

# 筛选真的收窄结果（不是「换个说法返回全量」）
st, b = get("/api/institutions?district=%E6%B5%B7%E6%B7%80%E5%8C%BA&page_size=1")
sub = b.get("total")
if sub is None or sub == 0 or sub >= (total or 0):
    print("FAIL 区域筛选没生效：全量=%s 海淀区=%s" % (total, sub))
else:
    print("OK  筛选生效：全量 %s → 海淀区 %s" % (total, sub))
PY
    while IFS= read -r line; do
      case "$line" in
        OK*)   ok "${line#OK  }" ;;
        FAIL*) bad "${line#FAIL }" ;;
        *)     info "$line" ;;
      esac
    done < "$TMP/api.log"
  fi
  if [[ -n "${FLASK_PID:-}" && "$KEEP_FLASK" != "1" ]]; then
    kill "$FLASK_PID" 2>/dev/null || true
    info "已关闭临时服务"
  fi
fi

# ---------------------------------------------------------------------------
step "附：三份前端产物一致性"
if "$PY" etl/verify_artifacts.py >"$TMP/art.log" 2>&1; then
  ok "产物校验通过（内联快照哈希一致 + 图表容器均有 JS 初始化）"
else
  bad "产物校验未通过："
  tail -25 "$TMP/art.log" | sed 's/^/      /'
fi

# ---------------------------------------------------------------------------
echo
if [[ "$FAILED" == "0" ]]; then
  printf '\033[32m✅ 真实链路贯通：容器 → HDFS/Spark → MySQL → Flask API → 前端产物\033[0m\n'
  echo "   演示入口： http://127.0.0.1:$PORT/spa/   （Vue + Flask）"
  echo "              http://127.0.0.1:$PORT/       （单文件大屏）"
  exit 0
else
  printf '\033[31m❌ 有 %d 项未通过，见上方 ✗\033[0m\n' "$FAILED"
  exit 1
fi
