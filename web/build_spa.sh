#!/usr/bin/env bash
# 重新生成大屏快照数据 + 单文件 HTML
# 用法：bash web/build_spa.sh
set -e
cd "$(dirname "$0")/.."
echo "=== 1. 拉 MySQL 全量精简数据 ==="
/Users/brooke/.workbuddy/binaries/python/envs/default/bin/python << 'PYEOF'
import json, pymysql, datetime
from pathlib import Path
conn = pymysql.connect(host='127.0.0.1', port=3307, user='root', password='hospital123',
                      database='hospital', charset='utf8mb4',
                      cursorclass=pymysql.cursors.DictCursor)
def q(sql):
    with conn.cursor() as cur:
        cur.execute(sql); return cur.fetchall()
rows = q("""SELECT a.id, a.name, a.district, a.level_norm AS level, a.category_norm AS category,
    a.category_sub, a.ownership, a.feature, a.feature_level,
    a.addr, a.phone,
    a.dept_count, a.key_specialty_count, a.lng, a.lat, a.coord_precision, a.key_depts, a.grade_scope,
    a.dept_count_src,
    a.ownership_src, a.level_src,
    a.national_specialty, a.national_specialty_count,
    a.municipal_specialty, a.municipal_specialty_count,
    a.net_pediatric, a.net_stroke, a.net_neonatal, a.net_maternal,
    COALESCE(rc.rule_dept_count, 0) AS rule_dept_count
    FROM ads_inst_search a
    LEFT JOIN (SELECT hospital_id, COUNT(*) AS rule_dept_count FROM dwd_dept_relation_clean
               WHERE source = 'rule' GROUP BY hospital_id) rc ON rc.hospital_id = a.id""")
for r in rows:
    r['id'] = str(r['id']).strip()
    for k in ('name','district','level','category','category_sub','ownership',
              'feature','feature_level','coord_precision','key_depts','grade_scope',
              'addr','phone',
              'national_specialty','municipal_specialty',
              'net_pediatric','net_stroke','net_neonatal','net_maternal','dept_count_src'):
        v = r.get(k); r[k] = ('' if v is None else v.strip() if isinstance(v, str) else v)
    for k in ('dept_count','key_specialty_count','lng','lat','national_specialty_count','municipal_specialty_count'):
        r[k] = None if r.get(k) in (None, '') else r[k]
overviews = {
    'districts':  q("SELECT district, inst_count, coord_high_count FROM ads_district_overview ORDER BY inst_count DESC"),
    # 等级分布仅统计"应参评医院等级评审"的机构；
    # level_norm='不适用医院分级'（诊所/村卫生室/门诊部/社区卫生服务站/医务室/急救/疾控/体检等）
    # 不参加医院评审，计入会形成 87% 的假性"未定级"，故在此口径剔除。
    'levels':     q("SELECT level_norm AS level, inst_count FROM ads_level_overview"
                    " WHERE level_norm <> '不适用医院分级' ORDER BY inst_count DESC"),
    'categories': q("SELECT category_norm AS category, inst_count, level_3_count FROM dws_inst_by_category ORDER BY inst_count DESC"),
    'depts':      q("SELECT dept_name, hospital_count, key_specialty_count FROM dws_dept_coverage ORDER BY hospital_count DESC LIMIT 20"),
    # 协作网络汇总（ads_network_summary）→ 协作网络独立页
    'networks':   q("SELECT network_key, network_name, member_count, core_count,"
                    " district_count, level_3_count FROM ads_network_summary ORDER BY member_count DESC"),
    # 功能使用结构（ads_time_feature）→ 运营后台「功能使用结构」图
    'time_feature': q("SELECT feature, event_count, session_count FROM ads_time_feature"
                      " ORDER BY event_count DESC LIMIT 12"),
    # ETL 批次时效（ads_etl_snapshot）→ 运营后台「数据批次时效」区块
    'etl_snapshots': q("SELECT CAST(batch_date AS CHAR) AS batch_date, batch_ts, inst_count, level_3, level_2, level_1,"
                       " level_none, district_count, coord_ok FROM ads_etl_snapshot"
                       " ORDER BY batch_ts DESC LIMIT 6"),
    # 数据整合 / 数据质量页口径：来自 etl 治理脚本真实输出
    # （data/processed/data_quality_report.md，70 个源文件 → 13,803 条 → 去重 9,791 家），
    # 不依赖额外 ETL 表，随快照分发；前端 dqv() 优先读此对象。
    'data_quality': {
        'source_files': 70, 'raw_records': 13803, 'final_inst': 9791,
        'dup_names': 3139, 'dup_max_sources': 9, 'cross_verified': 657, 'key_dept_inst': 20,
        'sources': [
            {'name': '市 / 区医保局定点医疗机构名单', 'count': 4876,
             'desc': '市医保局及东城、平谷、延庆、顺义等区定点医药机构文件'},
            {'name': '社区卫生服务机构名录', 'count': 1972,
             'desc': '社区卫生服务中心与社区卫生服务站名单'},
            {'name': '区级卫健委及专题公开数据', 'count': 6955,
             'desc': '密云 / 通州 / 房山 / 朝阳 / 怀柔等区医疗机构名录、重点专科与协作网络公示、业务统计表'},
        ],
        'fields': [
            {'field': 'district', 'label': '行政区', 'nonnull': 9749, 'pct': 99.6},
            {'field': 'addr', 'label': '地址', 'nonnull': 8762, 'pct': 89.5},
            {'field': 'profit', 'label': '经济类型（办别）', 'nonnull': 8328, 'pct': 85.1},
            {'field': 'key_depts', 'label': '重点专科 / 擅长科室', 'nonnull': 831, 'pct': 8.5},
            {'field': 'level', 'label': '医院等级', 'nonnull': 1172, 'pct': 12.0},
            {'field': 'phone', 'label': '联系电话', 'nonnull': 570, 'pct': 5.8},
            {'field': 'beds', 'label': '床位数', 'nonnull': 35, 'pct': 0.4},
            {'field': 'traffic', 'label': '交通导引', 'nonnull': 17, 'pct': 0.2},
        ],
    },
    # 注：ads_time_trend 目前仅 5 行测试数据，待行为日志积累后接入「行为日趋势」
}
meta = {
    'districts': overviews['districts'], 'levels': overviews['levels'],
    'categories': overviews['categories'],
    'depts': q("SELECT dept_name, hospital_count FROM dws_dept_coverage ORDER BY hospital_count DESC"),
}
geo = json.load(open('web/static/json/beijing.json', encoding='utf-8'))
# 快照日期 = 最近一次 ETL 批次日期（反映数据实际新鲜度），不再硬编码；
# 批次表为空时退回构建当天。前端「快照 <日期>」标签读的就是这个字段。
_etl = overviews.get('etl_snapshots') or []
_snap_date = (_etl[0].get('batch_date') if _etl else None) or datetime.date.today().isoformat()
out = {'institutions': rows, 'overviews': overviews,
       'meta': meta, 'geojson': geo, 'snapshot_time': str(_snap_date), 'total': len(rows)}
out_path = Path('web/snapshot_data.json')
out_path.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(f'  ✓ {out_path} | {out_path.stat().st_size/1024/1024:.2f} MB')
conn.close()
PYEOF

echo "=== 2. 刷新离线就医决策数据包 ==="
# 必须与 app.py 的判科/打分常量、ads_dept_strength 同步；
# 漏跑会让单文件形态与后端 /api/plan 漂移（etl/verify_offline_plan.py 能查出来），
# 所以放在构建链路里自动跑，而不是靠人记得。
/Users/brooke/.workbuddy/binaries/python/envs/default/bin/python etl/export_offline_plan_data.py

echo "=== 3. 拼装单文件 HTML ==="
/Users/brooke/.workbuddy/binaries/python/envs/default/bin/python << 'PYEOF'
from pathlib import Path
data = open('web/snapshot_data.json', encoding='utf-8').read()
html = open('web/dashboard.html', encoding='utf-8').read()
js = open('web/app.js', encoding='utf-8').read()

# 就医决策主线的离线数据包与两段脚本。
# 单文件形态原本只带查阅能力，主线要跳 /spa/（在线形态）——在 GitHub Pages 上那是 404。
# 内联这三样之后，单文件自身即可走完「说需求 → 分诊 → 对比 → 拿方案」。
plan_path = Path('web/offline_plan_data.json')
if not plan_path.exists():
    raise SystemExit('缺少 web/offline_plan_data.json，请先运行：'
                     'python etl/export_offline_plan_data.py')
plan_data = plan_path.read_text(encoding='utf-8')
plan_js = open('web/app.plan.js', encoding='utf-8').read()
plan_ui_js = open('web/app.plan.ui.js', encoding='utf-8').read()


def inline(s):
    """内联进 <script> 前必须转义 </script>：数据或代码里出现该串会提前闭合脚本，
    页面从那一行起全部变成文本（症状是「页面没报错但白屏」），排查起来很费时间。"""
    return s.replace('</script>', '<\\/script>')


js = js.replace(
"async function loadData() {\n  try {\n    const resp = await fetch('snapshot_data.json');\n    if (!resp.ok) throw new Error('HTTP ' + resp.status);\n    DATA = await resp.json();\n    console.log('数据加载完成:', DATA.total, '家');\n    init();\n  } catch (e) {\n    document.getElementById('loading').innerHTML =\n      '❌ 数据加载失败：' + e.message + '<br>请确保 <code>snapshot_data.json</code> 与 HTML 在同一目录';\n  }\n}",
"function loadData() {\n  try {\n    if (!window.__SNAPSHOT__) throw new Error('未找到内嵌数据快照');\n    DATA = window.__SNAPSHOT__;\n    console.log('数据加载完成:', DATA.total, '家');\n    init();\n  } catch (e) {\n    document.getElementById('loading').innerHTML =\n      '❌ 数据加载失败：' + e.message;\n  }\n}")
# 关键：window.__SNAPSHOT__ / window.__PLAN_DATA__ 必须先定义，再执行 app.js，否则 loadData() 会报"未找到内嵌数据快照"
html = html.replace('<script src="app.js"></script>',
                    f'<script>window.__SNAPSHOT__ = {inline(data)};</script>\n'
                    f'<script>window.__PLAN_DATA__ = {inline(plan_data)};</script>\n'
                    f'<script>\n{inline(js)}\n</script>')
for tag, code in (('<script src="app.plan.js"></script>', plan_js),
                  ('<script src="app.plan.ui.js"></script>', plan_ui_js)):
    if html.count(tag) != 1:
        raise SystemExit(f'产物拼装失败：锚点 {tag} 出现 {html.count(tag)} 次（应为 1 次）')
    html = html.replace(tag, f'<script>\n{inline(code)}\n</script>')
out = Path('web/dashboard_standalone.html')
out.write_text(html, encoding='utf-8')
print(f'  ✓ {out} | {out.stat().st_size/1024/1024:.2f} MB')
# 同步到 Flask 模板
import shutil
shutil.copy(out, 'web/templates/index.html')
print('  ✓ web/templates/index.html 已同步')

# === 2.5 生成完全离线版：内嵌 ECharts 库，去掉所有 CDN 依赖 ===
import urllib.request, os
vendor_dir = Path('web/vendor')
try:
    vendor_dir.mkdir(exist_ok=True)
except Exception:
    pass  # 目录已存在（部分沙盒环境对已存在目录也会抛错）
echarts_js = vendor_dir / 'echarts.min.js'
if not echarts_js.exists():
    print('  · 下载 ECharts 5.5.1 到 vendor/ ...')
    try:
        urllib.request.urlretrieve('https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js', echarts_js)
    except Exception as e:
        print(f'  ⚠️ 下载失败: {e}，跳过离线版生成')
        raise SystemExit(0)
echarts_inline = echarts_js.read_text(encoding='utf-8')
html2 = out.read_text(encoding='utf-8')
html2 = html2.replace(
    '<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>',
    f'<script>\n/* ECharts 5.5.1 - inlined for offline use */\n{echarts_inline}\n</script>',
    1
)
html2 = html2.replace('<title>北京市医疗机构资源整合与多维筛选可视化系统</title>',
                    '<title>北京市医疗机构资源整合与多维筛选可视化系统 - 离线版</title>', 1)
offline = Path('web/dashboard_offline.html')
offline.write_text(html2, encoding='utf-8')
print(f'  ✓ {offline} | {offline.stat().st_size/1024/1024:.2f} MB (完全离线，无需 CDN)')
PYEOF
echo "=== 完成 ==="
