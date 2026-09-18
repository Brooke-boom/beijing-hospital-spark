#!/usr/bin/env bash
# 一键启动 Flask 大屏服务
# 用法: bash web/start.sh
# 默认端口 5001（macOS 5000 被 AirPlay 占用），可用 PORT=8000 bash web/start.sh 覆盖
set -e
cd "$(dirname "$0")/.."
PORT=${PORT:-5001}

# 检查端口
if lsof -nP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
  echo "⚠️  端口 $PORT 已被占用："
  lsof -nP -iTCP:$PORT -sTCP:LISTEN | head -2 | tail -1
  echo ""
  echo "可用以下命令换端口：PORT=8000 bash web/start.sh"
  exit 1
fi

# 检查数据库
if ! nc -z 127.0.0.1 3307 2>/dev/null; then
  echo "⚠️  MySQL 未监听 3307 端口，Flask API 会连不上数据库"
  echo "请先启动 MySQL 容器：docker compose up -d mysql"
  echo ""
fi

# 启动 Flask
echo "=== 启动 Flask 服务（端口 $PORT）==="
echo "  Vue 在线形态（前后端分离）: http://localhost:$PORT/spa/"
echo "  单文件离线兜底大屏:         http://localhost:$PORT/"
if [ -d web/vue/dist ]; then
  echo "  ✓ 检测到 Vue 构建产物 web/vue/dist（/spa/ 可用）"
else
  echo "  ⚠️  未找到 web/vue/dist，/spa/ 会返回 503。"
  echo "     如需 Vue 形态请先构建：bash web/vue/build.sh"
fi
echo "  注意：定位功能需要 http:// 协议，file:// 协议下浏览器拒绝授权"
echo "  停止服务: Ctrl+C"
echo ""
exec /Users/brooke/.workbuddy/binaries/python/envs/default/bin/python web/app.py
