#!/usr/bin/env bash
# 大屏故障一键诊断：检查文件、CDN、Python/Flask 端口、JSON 解析
set -e
WEB=/Users/brooke/Desktop/毕设/web
cd "$WEB" || { echo "❌ 找不到 web 目录"; exit 1; }

echo "=== 1. 文件检查 ==="
for f in dashboard_offline.html dashboard_standalone.html dashboard.html snapshot_data.json app.py vendor/echarts.min.js; do
  if [ -f "$f" ]; then
    sz=$(du -h "$f" | cut -f1)
    echo "  ✅ $f ($sz)"
  else
    echo "  ❌ $f 缺失"
  fi
done

echo ""
echo "=== 2. HTML 关键内容校验 ==="
if grep -q "window.__SNAPSHOT__" dashboard_offline.html; then
  echo "  ✅ 离线版含内嵌数据 (window.__SNAPSHOT__)"
else
  echo "  ❌ 离线版缺内嵌数据"
fi
if grep -q "echarts.init" dashboard_offline.html; then
  echo "  ✅ 离线版已内嵌 ECharts"
else
  echo "  ❌ 离线版缺 ECharts"
fi
if grep -q "cdn.jsdelivr.net" dashboard_offline.html; then
  echo "  ⚠️ 离线版仍引用 jsdelivr CDN"
else
  echo "  ✅ 离线版无外部 CDN 依赖"
fi

echo ""
echo "=== 3. JSON 解析校验 ==="
/Users/brooke/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -c "
import json, re
with open('dashboard_offline.html','r',encoding='utf-8') as f:
    html = f.read()
m = re.search(r'window\.__SNAPSHOT__\s*=\s', html)
if m:
    end = html.find('</script>', m.end())
    d = json.loads(html[m.end():end].rstrip().rstrip(';').rstrip())
    print(f'  ✅ JSON 解析成功: {len(d[\"institutions\"])} 家医院 (snapshot_time={d.get(\"snapshot_time\")})')
else:
    print('  ❌ 未找到内嵌数据')
"

echo ""
echo "=== 4. Flask 端口检查 ==="
for p in 5000 5001; do
  if lsof -nP -iTCP:$p -sTCP:LISTEN 2>/dev/null | head -1 | grep -q LISTEN; then
    echo "  ⚠️ 端口 $p 已被占用:"
    lsof -nP -iTCP:$p -sTCP:LISTEN | head -2 | tail -1
  else
    echo "  ✅ 端口 $p 空闲"
  fi
done

echo ""
echo "=== 5. CDN 可达性（仅离线版用不到，留作诊断） ==="
for url in https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js https://geo.datav.aliyun.com/areas_v3/bound/110000_full.json; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "TIMEOUT")
  echo "  $url -> $code"
done

echo ""
echo "=== 6. 浏览器打开方式（自动） ==="
echo "正在用默认浏览器打开 dashboard_offline.html..."
open dashboard_offline.html 2>&1 && echo "  ✅ open 命令已发出" || echo "  ❌ open 失败"

echo ""
echo "=== 诊断完成 ==="
echo "如果浏览器仍打不开，请提供以下信息："
echo "  1) 浏览器名称和版本（Safari / Chrome / Edge / Firefox）"
echo "  2) 现象：白屏 / 转圈 / 报错 / 乱码 / 其它"
echo "  3) 浏览器开发者工具 Console 标签页的第一条红色错误"
