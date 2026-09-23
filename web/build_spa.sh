#!/usr/bin/env bash
# 重新生成大屏快照数据 + 单文件 HTML
# 用法：bash web/build_spa.sh [--no-db]
#   --no-db  跳过「拉 MySQL」这一步，直接复用已有的 web/snapshot_data.json。
#            适用场景：本机没起 MySQL / 只改了前端想重新拼装产物。
#            注意：源数据变了必须带库重跑（--no-db 不会更新快照内容）。
set -e
cd "$(dirname "$0")/.."

NO_DB=0
for a in "$@"; do [ "$a" = "--no-db" ] && NO_DB=1; done

if [ "$NO_DB" = "1" ]; then
  echo "=== 1. 跳过 MySQL（--no-db），复用 web/snapshot_data.json ==="
  [ -s web/snapshot_data.json ] || { echo "✗ web/snapshot_data.json 不存在或为空，请先带库运行一次"; exit 1; }
  /Users/brooke/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -c "
import json, os
d = json.load(open('web/snapshot_data.json', encoding='utf-8'))
n = len(d.get('institutions') or [])
print('  OK 复用快照 %d 家机构 | 快照日期 %s | %.2f MB' % (
    n, d.get('snapshot_time') or '?', os.path.getsize('web/snapshot_data.json') / 1024 / 1024))
inst = (d.get('institutions') or [{}])[0]
# 数据来源字段：带库构建产出 src_count_int / source_files；
# 由 etl/export_inst_source.py 回填的历史快照叫 src_count（app.nlq.js 两者都认）。
have_src = any(k in inst for k in ('src_count_int', 'src_count'))
print(('  OK 数据来源字段存在（%s）' % (', '.join(k for k in ('src_count_int', 'src_count') if k in inst))
       if have_src else '  WARN 缺少数据来源计数字段（按来源筛选会失效，请带库重跑）'))
print(('  OK 字段 source_files 存在' if 'source_files' in inst
       else '  WARN 缺少 source_files（按来源筛选会失效，请重跑 etl/export_inst_source.py）'))
print(('  OK 字段 depts 存在（离线可按科室筛选）' if 'depts' in inst
       else '  WARN 缺少 depts（离线按科室筛选会失效，请带库重跑 build_spa.sh）'))
"
else
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
    -- category_fine：主表的**细粒度**机构类型（医务室 / 护理站 / 中医医院 …）。
    -- 展示层按 10 类粗口径（category_norm）会把这些并进"其他机构 / 医院"，
    -- 而「科室数」这一项的展示口径需要区分 医务室 / 护理站（它们按诊疗科目执业、
    -- 不设科室建制，写"科室资料待补全"属于口径错误）。只加一个展示字段，
    -- 不动 category_norm —— 那套 10 类是 nlq.CATEGORIES 声明的筛选口径。
    a.category AS category_fine,
    a.category_sub, a.ownership, a.feature, a.feature_level,
    a.addr, a.phone,
    a.dept_count, a.key_specialty_count, a.lng, a.lat, a.coord_precision, a.key_depts, a.grade_scope,
    a.dept_count_src,
    a.ownership_src, a.level_src,
    a.national_specialty, a.national_specialty_count,
    a.municipal_specialty, a.municipal_specialty_count,
    a.net_pediatric, a.net_stroke, a.net_neonatal, a.net_maternal,
    a.src_count_int, a.source_files,
    COALESCE(rc.rule_dept_count, 0) AS rule_dept_count
    FROM ads_inst_search a
    LEFT JOIN (SELECT hospital_id, COUNT(*) AS rule_dept_count FROM dwd_dept_relation_clean
               WHERE source = 'rule' GROUP BY hospital_id) rc ON rc.hospital_id = a.id""")
for r in rows:
    r['id'] = str(r['id']).strip()
    for k in ('name','district','level','category','category_fine','category_sub','ownership',
              'feature','feature_level','coord_precision','key_depts','grade_scope',
              'addr','phone',
              'national_specialty','municipal_specialty',
              'net_pediatric','net_stroke','net_neonatal','net_maternal','dept_count_src',
              'source_files'):
        v = r.get(k); r[k] = ('' if v is None else v.strip() if isinstance(v, str) else v)
    for k in ('dept_count','key_specialty_count','lng','lat','national_specialty_count',
              'municipal_specialty_count','src_count_int'):
        r[k] = None if r.get(k) in (None, '') else r[k]

# 科室隶属关系：快照原先只有科室「词表」（meta.depts，来自 dws_dept_coverage），
# 没有「哪家机构有哪些科室」的隶属关系 —— 于是离线形态能认出"骨科"这个词、
# 也把它解析成了筛选条件，却查不出来（只得 0 家，并提示"离线形态不支持按科室筛选"）。
# 这里把 dwd_dept_relation_clean（29 类科室 / 16,251 条隶属 / 覆盖 9,335 家，
# 约 200KB）一并内嵌，单文件形态即可与后端按同一张表、同一种语义筛选科室。
# 命名用 depts，与已有的 key_depts（重点专科挂牌）区分开。
_dept_rows = q("SELECT hospital_id, dept_name FROM dwd_dept_relation_clean")
_dmap = {}
for _r in _dept_rows:
    _dmap.setdefault(str(_r['hospital_id']).strip(), []).append(_r['dept_name'])
_n_dept = 0
for r in rows:
    _ds = _dmap.get(r['id'])
    r['depts'] = ';'.join(sorted(_ds)) if _ds else ''
    if _ds:
        _n_dept += 1
print('  OK 科室隶属(dwd_dept_relation_clean): %d 条 / %d 家有明细 / 快照已带 depts 字段'
      % (len(_dept_rows), _n_dept))

# ---------------------------------------------------------------------------
# 数据质量指标：从主表现算（不再手写字面量）
#
# 分母分两种口径，前端表格会并列展示：
#   · 全量口径   —— 主表 9,684 家；适用于 行政区 / 地址 / 办别 / 电话 / 床位 / 交通 / 官网
#   · 适用口径   —— 字段本身有适用范围的，用"该字段谈得上的机构数"当分母：
#        level       应参评 880 家（其余 8,804 家为诊所/村卫生室/门诊部/社区卫生服务站/
#                    医务室/护理站/社区卫生服务中心/急救/疾控/体检等——按各自《基本标准》
#                    以诊疗科目执业，不设医院等级建制）
#        key_depts   设诊疗科目的机构（该字段真源是《医疗机构（基本信息）》的诊疗科目列）
#   pct 一律是**全量口径**的百分比（便于横向比较"这一列到底有多稀"），
#   bpct 是适用口径的百分比（回答"在谈得上的机构里补全到什么程度"）。
# ---------------------------------------------------------------------------
import csv as _csv
_master = list(_csv.DictReader(open('data/processed/master_institutions.csv', encoding='utf-8-sig')))
_n = len(_master)


def _nn(col):
    return sum(1 for r in _master if (r.get(col) or '').strip())


# ⚠️ 应参评集合以**主表 grade_scope 列**为唯一真源（由 etl/build_grade_scope.py 派生，
#    判据函数与 clean_merge.py / DWD level_norm 同源）。这里曾用一份更窄的本地表复算，
#    漏掉「社区卫生服务中心 / 急救机构 / 公共卫生机构 / 体检机构 / 其他医疗机构」
#    五类同样不设等级建制的机构，分母因此从 880 虚增到 1,405 ——
#    等级覆盖率被显示成 62.4%，而真实值是 97.2%（855/880）。
#    口径漂移一次就会在页面上放大成 30 个百分点的假象，故直接读列、不再本地复算。
_applic = [r for r in _master if (r.get('grade_scope') or '') == 'applicable']
_applic_n = len(_applic)
# 应参评里"等级非空"的家数（口径与 ads_level_overview 的 level_norm 一致：不适用不入表）
_level_ok = sum(1 for r in _applic if (r.get('level') or '').strip())
# 重点专科（国家 / 市级挂牌）—— 与 key_depts（诊疗科目）区分开
_spec_ok = sum(1 for r in _master
               if (r.get('national_specialty') or '').strip() or (r.get('municipal_specialty') or '').strip())
_kd_ok = _nn('key_depts')


def _f(col, label, basis=None, basis_label='主表全量', note=''):
    k = _nn(col)
    b = _n if basis is None else basis
    return {'field': col, 'label': label, 'nonnull': k,
            'pct': round(k / _n * 100, 1) if _n else 0.0,
            'basis': b, 'basis_label': basis_label,
            'bpct': round(k / b * 100, 1) if b else 0.0, 'note': note}


_dq = {
    'source_files': 70, 'raw_records': 13803, 'final_inst': _n,
    # merged_inst 是 clean_merge.py 的 groupby 输出行数（**治理前**）。它不随主表
    # 变化 —— 它是"合并前"的基线，页面用「9,791 → 9,678」表达治理环节又收拢了
    # 113 条同名/多牌子记录（其中 2026-09-22 同名合并治理贡献 111 条）。重跑
    # clean_merge.py 后此值需同步。
    'merged_inst': 9791,
    # 多来源机构数 / 最大来源数 / 多源交叉验证数一律现算：
    # 它们随主表行数走，写死会在每次治理后变成"说不清来历的旧数"
    # （cross_verified 曾写死 657，治理后真实值 677 却没人发现）。
    'dup_names': sum(1 for r in _master if int(r.get('src_count') or 0) > 1),
    'dup_max_sources': max([int(r.get('src_count') or 0) for r in _master] or [0]),
    'cross_verified': sum(1 for r in _master if int(r.get('src_count') or 0) >= 3),
    'key_dept_inst': _spec_ok,
    'sources': [
        {'name': '市 / 区医保局定点医疗机构名单', 'count': 4876,
         'desc': '市医保局及东城、平谷、延庆、顺义等区定点医药机构文件'},
        {'name': '社区卫生服务机构名录', 'count': 1972,
         'desc': '社区卫生服务中心与社区卫生服务站名单'},
        {'name': '区级卫健委及专题公开数据', 'count': 6955,
         'desc': '密云 / 通州 / 房山 / 朝阳 / 怀柔等区医疗机构名录、重点专科与协作网络公示、业务统计表'},
    ],
    'fields': [
        _f('district', '行政区'),
        _f('addr', '地址'),
        _f('profit', '经济类型（办别）'),
        _f('level', '医院等级', _applic_n, '应参评机构',
           '住院医院类参加等级评审；诊所/村卫生室等按「不适用分级」展示'),
        _f('phone', '联系电话'),
        _f('key_depts', '诊疗科目（执业登记）'),
        _f('beds', '床位数'),
        _f('traffic', '交通导引'),
        _f('website', '机构官网'),
    ],
    'specialty': {'label': '重点专科挂牌（国家 / 市级）', 'nonnull': _spec_ok,
                  'pct': round(_spec_ok / _n * 100, 1) if _n else 0.0,
                  'basis': _applic_n, 'basis_label': '应参评机构',
                  'bpct': round(_spec_ok / _applic_n * 100, 1) if _applic_n else 0.0},
    'level_applic': _applic_n, 'level_ok': _level_ok,
    'dept_nonnull': _kd_ok,
}
print('  OK 数据质量指标现算：主表 %d 家 | 应参评 %d 家 | 等级非空 %d | 电话 %d | 交通 %d'
      % (_n, _applic_n, _level_ok, _nn('phone'), _nn('traffic')))

# 机构行补三个展示字段：beds / traffic / website。
# ⚠️ 这三列在 MySQL 的 ads_inst_search 里**没有**（建表时就没选），但它们主表里是有的。
#    直接从主表按 id 回填到快照行上，省掉一次 schema 变更 + 全链路重跑；
#    机构详情页因此可以展示「交通导引 / 机构官网」，完整率也不再是无人认领的数字。
_by_id = {r['id']: r for r in _master}
_n_fill = 0
for _r in rows:
    _m = _by_id.get(_r['id'])
    if _m:
        _r['beds'] = (_m.get('beds') or '').strip()
        _r['traffic'] = (_m.get('traffic') or '').strip()
        _r['website'] = (_m.get('website') or '').strip()
        _r['profit'] = (_m.get('profit') or '').strip()
        if _r['traffic'] or _r['website']:
            _n_fill += 1
print('  OK 快照行补展示字段 beds/traffic/website：%d 家带交通导引或官网' % _n_fill)

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
    # 数据整合 / 数据质量页口径：**全部由主表实时计算**。
    # ⚠️ 这里原本是一串手写字面量（level 1,172 / beds 35 / traffic 17 / final_inst 9,791），
    #    数据治理过后它们不会跟着变 —— 结果就是页面上的完整率与真实主表对不上，
    #    而且没有任何迹象表明它是旧的（用户看到「等级 12.0%」却查不到这一千多家是谁）。
    #    改成从 data/processed/master_institutions.csv 现算：单一真源，改数据即改口径。
    #    同时补上 basis（适用分母）—— 等级的合理分母是"应参评机构"（967 家），
    #    而不是全部 9,684 家：另外 8,804 家是诊所/村卫生室等不设医院等级建制的类别，
    #    用全量当分母会把 97.2% 的覆盖率显示成 9.6%，属于口径错误。
    'data_quality': _dq,
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
fi

echo "=== 2. 刷新自然语言筛选词表 ==="
# 词表只有一份真源：web/nlq.py。这里把它导出成 web/nlq_lexicon.json，
# 再内联进单文件产物 —— 单文件形态的解析结果因此与后端逐字段一致
# （etl/verify_offline_nlq.py 会逐条比对，漂移立刻暴露）。
# 放在构建链路里自动跑，而不是靠人记得手抄。
/Users/brooke/.workbuddy/binaries/python/versions/3.13.12/bin/python3 etl/export_nlq_lexicon.py

echo "=== 3. 拼装单文件 HTML ==="
/Users/brooke/.workbuddy/binaries/python/versions/3.13.12/bin/python3 << 'PYEOF'
from pathlib import Path
data = open('web/snapshot_data.json', encoding='utf-8').read()
html = open('web/dashboard.html', encoding='utf-8').read()
js = open('web/app.js', encoding='utf-8').read()

# 智能筛选页的词表 + 解析引擎 + 界面层。
# 单文件形态原本只带查阅能力，智能筛选要跳 /spa/（在线形态）——在 GitHub Pages 上那是 404。
# 内联这三样之后，单文件自身即可走完「说一句话 → 解析成筛选条件 → 查真实数据 → 看分布」。
lex_path = Path('web/nlq_lexicon.json')
if not lex_path.exists():
    raise SystemExit('缺少 web/nlq_lexicon.json，请先运行：'
                     'python etl/export_nlq_lexicon.py')
lex_json = lex_path.read_text(encoding='utf-8')
nlq_js = open('web/app.nlq.js', encoding='utf-8').read()
nlq_ui_js = open('web/app.nlq.ui.js', encoding='utf-8').read()


def inline(s):
    """内联进 <script> 前必须转义 </script>：数据或代码里出现该串会提前闭合脚本，
    页面从那一行起全部变成文本（症状是「页面没报错但白屏」），排查起来很费时间。"""
    return s.replace('</script>', '<\\/script>')


# 关键：window.__SNAPSHOT__ / window.__NLQ_LEX__ 必须先定义，再执行 app.js / app.nlq.js，
# 否则 loadData() 会报"未找到内嵌数据快照"，离线解析引擎也拿不到词表。
assert '<script src="app.js"></script>' in html, '产物拼装失败：未找到 app.js 锚点'
html = html.replace('<script src="app.js"></script>',
                    f'<script>window.__SNAPSHOT__ = {inline(data)};</script>\n'
                    f'<script>window.__NLQ_LEX__ = {inline(lex_json)};</script>\n'
                    f'<script>\n{inline(js)}\n</script>')
# 词表装载脚本（开发形态回退读 nlq_lexicon.json）在产物里已由 __NLQ_LEX__ 覆盖，原样保留即可
for tag, code in (('<script src="app.nlq.js"></script>', nlq_js),
                  ('<script src="app.nlq.ui.js"></script>', nlq_ui_js)):
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
