#!/usr/bin/env bash
# 一键启动 Flask 大屏服务
# 用法: bash web/start.sh
# 默认端口 5001（macOS 5000 被 AirPlay 占用），可用 PORT=8000 bash web/start.sh 覆盖
set -e
cd "$(dirname "$0")/.."
PORT=${PORT:-5001}

# 端口占用由 app.py 启动自愈处理：本项目旧实例自动结束重启，
# 其他程序占用才报错退出（可用 PORT=8000 覆盖）

# 检查数据库
if ! nc -z 127.0.0.1 3307 2>/dev/null; then
  echo "⚠️  MySQL 未监听 3307 端口，Flask API 会连不上数据库"
  echo "请先启动 MySQL 容器：docker compose up -d mysql"
  echo ""
fi

# 启动 Flask
echo "=== 启动 Flask 服务（端口 $PORT）==="
echo "  单文件离线大屏（唯一入口）: http://localhost:$PORT/"
echo "  旧 /spa/ 路径已下线，会自动 302 跳转回 /"
echo "  注意：定位功能需要 http:// 协议，file:// 协议下浏览器拒绝授权"
echo "  停止服务: Ctrl+C"
echo ""
exec /Users/brooke/.workbuddy/binaries/python/envs/default/bin/python web/app.py
