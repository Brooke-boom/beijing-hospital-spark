#!/usr/bin/env bash
# ============================================================================
# Vue 前端一键构建 —— 前后端分离形态
#   产出：web/vue/dist/  → 由 Flask 挂载在 /spa/（见 web/app.py 的 spa 路由）
#   依赖：Node.js（本地 node_modules 已软链到受管工作区，无需联网）
#
# 用法：
#   bash web/vue/build.sh          # 构建生产产物
#   bash web/vue/build.sh --dev    # 启动 Vite 开发服务器（5173，/api 代理到 Flask）
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

NODE="${NODE_BIN:-node}"

if [ ! -d node_modules ]; then
  cat <<'EOF'
✗ 未找到 node_modules。
  请在 Vue 工程目录安装依赖：
    cd web/vue && npm install --registry=https://registry.npmmirror.com
EOF
  exit 1
fi

if [ "${1:-}" = "--dev" ]; then
  echo "▶ 启动 Vite 开发服务器（http://127.0.0.1:5173/spa/），/api 代理到 Flask 5001"
  exec "$NODE" node_modules/vite/bin/vite.js
fi

echo "▶ 同步地图边界数据 → web/vue/geo/"
# 智能筛选页的结果地图需要北京 16 区边界。权威副本在 web/vendor/beijing_geo.json，
# 仓库里同时保留一份 geo/ 副本（clone 后不装 Node 也能构建），这里做一次覆盖同步，
# 避免两处各改一份导致边界漂移。
if [ -f "$HERE/../vendor/beijing_geo.json" ]; then
  mkdir -p "$HERE/geo"
  cp "$HERE/../vendor/beijing_geo.json" "$HERE/geo/beijing_geo.json"
  echo "  ✓ 已从 web/vendor/beijing_geo.json 同步"
else
  echo "  ! 未找到 web/vendor/beijing_geo.json，沿用 geo/ 内既有副本"
fi

echo "▶ 构建 Vue 前端 → web/vue/dist/"
"$NODE" node_modules/vite/bin/vite.js build

echo
echo "✓ 构建完成。访问方式："
echo "    在线（Vue + Flask）：  http://127.0.0.1:5001/spa/"
echo "    离线兜底（单文件）：   http://127.0.0.1:5001/    或直接双击 web/dashboard_offline.html"
