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
    category_sub, ownership, feature, feature_level,
    dept_count, beds, key_specialty_count, lng, lat, coord_precision, key_depts, grade_scope
    FROM ads_inst_search""")
for r in rows:
    r['id'] = str(r['id']).strip()
    for k in ('name','district','level','category','category_sub','ownership',
              'feature','feature_level','coord_precision','key_depts','grade_scope'):
        v = r.get(k); r[k] = ('' if v is None else v.strip() if isinstance(v, str) else v)
    for k in ('dept_count','beds','key_specialty_count','lng','lat'):
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
}
spec = q("SELECT dept_name, name AS hospital, district, level_norm AS level, hospital_id FROM ads_specialty_hospital ORDER BY dept_name, hospital")
import re as _re
# —— 专科名清洗：去括号注解/噪声词 + 同义症候归并，得到可读的标准科室名 ——
_DEPT_SYN = {
 '心血管科':'心血管内科','心内科':'心血管内科','高血压科':'心血管内科',
 '脾胃科':'脾胃病科','脾胃病':'脾胃病科','消化科':'消化内科',
 '呼吸科':'呼吸内科','肺病科':'呼吸内科','肺病':'呼吸内科',
 '康复科':'康复医学科','中西医结合康复医学科':'康复医学科','中西结合康复医学科':'康复医学科',
 '肾内科':'肾病科','肾病':'肾病科','肾脏病科':'肾病科',
 '风湿病科':'风湿免疫科','风湿':'风湿免疫科',
 '针灸科':'针灸推拿科','推拿科':'针灸推拿科',
 '普外科':'普通外科','外科':'普通外科',
 '神经病科':'神经内科','脑病科':'神经内科',
 '肛肠科':'肛肠外科','肛肠':'肛肠外科','眼病科':'眼科',
 '肿瘤':'肿瘤科','骨质疏松科':'骨科','骨伤科':'骨科',
 '急症科':'急诊科','急救医学部':'急诊科','急诊医学科':'急诊科',
 '重症医学':'重症医学科','心脏外科':'心外科','皮肤病科':'皮肤科','泌外科':'泌尿外科',
 '内分泌':'内分泌科','老年医学科':'老年病科','脑外科':'神经外科','血液科':'血液内科',
 '甲状腺科':'乳腺外科','疼痛医学部':'疼痛科','儿科(儿科学)':'儿科',
}
_DEPT_NOISE = _re.compile(r'(口径|建设单位|官网|平台|特色|重点专科等|重点专科$|重点专科\s|另有|另设|暂无|未公开|公开|名单|博采|百科|项目|科室情况|科室设置|为特色|设有|包含|主要|为准|查询|参考|来源|信息)')
def _cdept(dept):
    if not dept: return None
    s = _re.sub(r'[（(][^（）()]{0,80}[)）]', '', dept).strip()
    s = _re.sub(r'^(另有|另设|另|含|包括|国家|省|市|院级|首都区域|其中|北京市|首都|国家级|北京市级|区级|全国|北京)', '', s)
    s = _re.sub(r'[;；、,，\s]+$', '', s).strip('（()）· ')
    if not s or len(s) < 2 or len(s) > 12: return None
    if _DEPT_NOISE.search(s): return None
    if _re.search(r'[0-9"，。、＝=]', s): return None
    if not _re.search(r'(科|室|学|病|痛|免疫|风湿|内|外|儿|妇|口腔|眼|耳鼻|肛|骨|脑|心|呼吸|消化|神经|内分泌|肿瘤|皮肤|泌尿|血液|康复|针灸|放射|超声|影像|营养|麻醉|急诊|感染|传染|老年|护理|检验|病理|变态)', s): return None
    return _DEPT_SYN.get(s, s)
def _norm(hospital, district):
    # 医院镜像归并（同一物理医院的多条名称变体）：
    #   1) 截断到首个“（”前的机构主体名（如“北京市隆福医院（北京中西医结合老年医院）”）
    #   2) 截断到空格分隔的并列别名（“北京中医药大学附属…医院/第一临床医学院”）
    #   3) 去掉机构挂靠前缀 + 同址共同体后缀
    n = _re.sub(r'[（(].*$', '', hospital).strip()
    n = _re.sub(r'\s+(附属|北京|中国|首都|北京中医药|第一|第二).*$', '', n)
    n = _re.sub(r'(中国中医研究院|中国中医科学院|北京中医药大学附属?|首都医科大学附属?|北京大学附属?|中国医学科学院)', '', n)
    n = _re.sub(r'(第一临床医学院|第二临床医学院|第一临床医药研究所|第二临床医药研究所)', '', n)
    n = _re.sub(r'(社区卫生服务中心|社区卫生服务站|卫生服务站|门诊部|诊所|卫生服务中心|南区|北区)', '', n)
    n = _re.sub(r'[、\s，,。]', '', n)
    return (n, district)
groups = {}
for r in spec:
    d = _cdept(r.pop('dept_name'))
    if not d: continue
    r['id'] = str(r.pop('hospital_id')).strip()
    if d not in groups:
        groups[d] = {'dept_name': d, 'hospital_count': 0, 'top_hospitals': [], '_seen': set()}
    # 镜像实体（同一物理医院名称变体）在同一专科内只计一次
    core = _norm(r['hospital'], r['district'])
    if core in groups[d]['_seen']:
        continue
    groups[d]['_seen'].add(core)
    groups[d]['hospital_count'] += 1
    if len(groups[d]['top_hospitals']) < 3:
        groups[d]['top_hospitals'].append({'id': r['id'], 'name': r['hospital'], 'district': r['district'], 'level': r['level']})
spec_out = sorted(groups.values(), key=lambda x: -x['hospital_count'])
for g in spec_out:
    g.pop('_seen', None)
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
# 关键：window.__SNAPSHOT__ 必须先定义，再执行 app.js，否则 loadData() 会报"未找到内嵌数据快照"
html = html.replace('<script src="app.js"></script>',
                    f'<script>window.__SNAPSHOT__ = {data};</script>\n<script>\n{js}\n</script>')
out = Path('web/dashboard_standalone.html')
out.write_text(html, encoding='utf-8')
print(f'  ✓ {out} | {out.stat().st_size/1024/1024:.2f} MB')
# 同步到 Flask 模板
import shutil
shutil.copy(out, 'web/templates/index.html')
print('  ✓ web/templates/index.html 已同步')

# === 2.5 生成完全离线版：内嵌 ECharts 库，去掉所有 CDN 依赖 ===
import urllib.request, os
vendor_dir = Path('web/vendor'); vendor_dir.mkdir(exist_ok=True)
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
html2 = html2.replace('<title>北京市医院医疗资源整合与智能筛选可视化系统</title>',
                    '<title>北京市医院医疗资源整合与智能筛选可视化系统 - 离线版</title>', 1)
offline = Path('web/dashboard_offline.html')
offline.write_text(html2, encoding='utf-8')
print(f'  ✓ {offline} | {offline.stat().st_size/1024/1024:.2f} MB (完全离线，无需 CDN)')
PYEOF
echo "=== 完成 ==="
