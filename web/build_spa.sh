#!/usr/bin/env bash
# 重新生成大屏快照数据 + 单文件 HTML
# 用法：bash web/build_spa.sh
set -e
cd "$(dirname "$0")/.."
echo "=== 1. 拉 MySQL 全量精简数据 ==="
/Users/brooke/.workbuddy/binaries/python/envs/default/bin/python << 'PYEOF'
import json, pymysql
from pathlib import Path
conn = pymysql.connect(host='127.0.0.1', port=3307, user='root', password='hospital123',
                      database='hospital', charset='utf8mb4',
                      cursorclass=pymysql.cursors.DictCursor)
def q(sql):
    with conn.cursor() as cur:
        cur.execute(sql); return cur.fetchall()
rows = q("""SELECT id, name, district, level_norm AS level, category_norm AS category,
    dept_count, beds, key_specialty_count, lng, lat, coord_precision, key_depts
    FROM ads_inst_search""")
for r in rows:
    r['id'] = str(r['id']).strip()
    for k in ('name','district','level','category','coord_precision','key_depts'):
        v = r.get(k); r[k] = ('' if v is None else v.strip() if isinstance(v, str) else v)
    for k in ('dept_count','beds','key_specialty_count','lng','lat'):
        r[k] = None if r.get(k) in (None, '') else r[k]
overviews = {
    'districts':  q("SELECT district, inst_count, coord_high_count FROM ads_district_overview ORDER BY inst_count DESC"),
    'levels':     q("SELECT level_norm AS level, inst_count FROM ads_level_overview ORDER BY inst_count DESC"),
    'categories': q("SELECT category_norm AS category, inst_count, level_3_count FROM dws_inst_by_category ORDER BY inst_count DESC"),
    'depts':      q("SELECT dept_name, hospital_count, key_specialty_count FROM dws_dept_coverage ORDER BY hospital_count DESC LIMIT 20"),
}
spec = q("SELECT dept_name, name AS hospital, district, level_norm AS level, hospital_id FROM ads_specialty_hospital ORDER BY dept_name, hospital")
groups = {}
for r in spec:
    d = r.pop('dept_name'); r['id'] = str(r.pop('hospital_id')).strip()
    if d not in groups:
        groups[d] = {'dept_name': d, 'hospital_count': 0, 'top_hospitals': []}
    groups[d]['hospital_count'] += 1
    if len(groups[d]['top_hospitals']) < 3:
        groups[d]['top_hospitals'].append({'id': r['id'], 'name': r['hospital'], 'district': r['district'], 'level': r['level']})
spec_out = sorted(groups.values(), key=lambda x: -x['hospital_count'])
meta = {
    'districts': overviews['districts'], 'levels': overviews['levels'],
    'categories': overviews['categories'],
    'depts': q("SELECT dept_name, hospital_count FROM dws_dept_coverage ORDER BY hospital_count DESC"),
}
geo = json.load(open('web/static/json/beijing.json', encoding='utf-8'))
out = {'institutions': rows, 'overviews': overviews, 'specialty_groups': spec_out,
       'meta': meta, 'geojson': geo, 'snapshot_time': '2026-09-04', 'total': len(rows)}
out_path = Path('web/snapshot_data.json')
out_path.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(f'  ✓ {out_path} | {out_path.stat().st_size/1024/1024:.2f} MB')
conn.close()
PYEOF

echo "=== 2. 拼装单文件 HTML ==="
/Users/brooke/.workbuddy/binaries/python/envs/default/bin/python << 'PYEOF'
from pathlib import Path
data = open('web/snapshot_data.json', encoding='utf-8').read()
html = open('web/dashboard.html', encoding='utf-8').read()
js = open('web/app.js', encoding='utf-8').read()
js = js.replace(
"async function loadData() {\n  try {\n    const resp = await fetch('snapshot_data.json');\n    if (!resp.ok) throw new Error('HTTP ' + resp.status);\n    DATA = await resp.json();\n    console.log('数据加载完成:', DATA.total, '家');\n    init();\n  } catch (e) {\n    document.getElementById('loading').innerHTML =\n      '❌ 数据加载失败：' + e.message + '<br>请确保 <code>snapshot_data.json</code> 与 HTML 在同一目录';\n  }\n}",
"function loadData() {\n  try {\n    if (!window.__SNAPSHOT__) throw new Error('未找到内嵌数据快照');\n    DATA = window.__SNAPSHOT__;\n    console.log('数据加载完成:', DATA.total, '家');\n    init();\n  } catch (e) {\n    document.getElementById('loading').innerHTML =\n      '❌ 数据加载失败：' + e.message;\n  }\n}")
html = html.replace('<script src="app.js"></script>', f'<script>\n{js}\n</script>')
html = html.replace('</body>', f'<script>window.__SNAPSHOT__ = {data};</script>\n</body>')
out = Path('web/dashboard_standalone.html')
out.write_text(html, encoding='utf-8')
print(f'  ✓ {out} | {out.stat().st_size/1024/1024:.2f} MB')
# 同步到 Flask 模板
import shutil
shutil.copy(out, 'web/templates/index.html')
print('  ✓ web/templates/index.html 已同步')
PYEOF
echo "=== 完成 ==="
