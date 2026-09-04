# -*- coding: utf-8 -*-
"""等级/床位真实证据池构建 + 主表匹配建议（预览模式，默认不写回主表）。
产出(默认 /tmp):
  pool_stats.txt           各源证据规模与命中统计
  level_suggest.csv        建议回填/校正的等级记录 (含冲突标记)
  bed_suggest.csv          建议回填的真实床位记录
  review_uncertain.csv     名称模糊/多候选/等级冲突，需人工复核
用法: python enrich_level_beds.py [--apply]
"""
import os, sys, csv, re, unicodedata
from collections import defaultdict, Counter

ROOT = os.path.expanduser("~/Desktop/毕设/data")
MASTER = os.path.join(ROOT, 'processed/hospital_wide.csv')
OUT = '/tmp/enrich'
os.makedirs(OUT, exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_tables as rt

APPEND = '--apply' in sys.argv

# ---------------------------------------------------------------- norm
def norm_full(s):
    s = unicodedata.normalize('NFKC', s or '')
    s = re.sub(r'[\s\u3000]+', '', s)
    return s.lower()

def strip_paren(s):
    s = re.sub(r'[（(【\[][^）)】\]]*[）)】\]]', '', s or '')
    return s

PREFIXES = ['北京市朝阳区','北京市海淀区','北京市丰台区','北京市石景山区','北京市门头沟区',
            '北京市房山区','北京市通州区','北京市顺义区','北京市昌平区','北京市大兴区',
            '北京市怀柔区','北京市平谷区','北京市密云区','北京市延庆区','北京市东城区',
            '北京市西城区','北京市','北京']
def strip_prefix(s):
    s = s or ''
    for p in PREFIXES:
        if s.startswith(p) and len(s) > len(p):
            return s[len(p):]
    return s

def variants(name):
    """返回一组候选 key（从精确到宽松）"""
    n = norm_full(name)
    core = norm_full(strip_paren(name))
    out = [n, core]
    # 去掉前缀的版本
    sn = norm_full(strip_prefix(strip_paren(name)))
    out.append(sn)
    seen = []
    for x in out:
        if x and x not in seen:
            seen.append(x)
    return seen

# ---------------------------------------------------------------- 证据源定义
# 每源: (文件, 名称列, 等级列[, 等次列, 区列, 优先级, 备注, 附加字段提取器])
def grade_of(raw, sub=None):
    """解析原始等级文本 -> (level, level_sub)。text 如 '三级甲等','一级合格','三级','未定级','无等级','二级无等'"""
    raw = (raw or '').strip()
    m = re.search(r'[一二三]级', raw)
    lv = m.group(0) if m else None
    if not lv:
        if any(k in raw for k in ('未定', '未评', '无等级', '无等', '未评级')):
            return '', ''
        return None, None
    sub = ''
    if '甲等' in raw or raw.endswith('甲'): sub = '甲等'
    elif '乙等' in raw or raw.endswith('乙'): sub = '乙等'
    elif '合格' in raw: sub = '合格'
    elif re.search(r'无等|未评', raw): sub = '未评'
    return lv, sub

def grade_hosp_code(s):
    """医院.csv 等级列形如 '3-三级'/'1-一级' 或 '2-甲等'"""
    m = re.search(r'[一二三]级', s or '')
    return m.group(0) if m else None

SOURCES = [
    # 官方执业登记：诊疗科目+级别（级别权威，不细分等次）
    dict(file='医疗机构（基本信息）.csv', name='机构名称', level='机构级别',
         district='', extra='诊疗科目名称', prio=10, tag='卫健委执业登记', trust_sub=False),
    dict(file='卫健委可开放数据.csv', name='机构名称', level='医院等级', sub='医院等次',
         district='区县名称', extra='卫生机构类别', prio=9, tag='卫健委开放数据', trust_sub=True),
    dict(file='顺义区医疗机构名单.csv', name='机构名称', level='机构级别', sub='机构等次',
         district='', extra='机构类别', prio=8, tag='顺义区名单', trust_sub=True),
    dict(file='医院.csv', name='机构名称', level='医院等级级', sub='医院等级等',
         district='', extra='地址', prio=8, tag='机构代码库', trust_sub=True),
    dict(file='归档_旧版命名/医疗机构基本信息.csv', name='医疗机构名称', level='医院等级',
         district='', extra='专科类型', prio=7, tag='医保-怀柔', trust_sub=False),
    dict(file='区医保局定点医疗机构情况.csv', name='医疗机构名称', level='医院等级',
         district='', extra='类型', prio=6, tag='医保局-怀柔', trust_sub=False),
    dict(file='区医保局定点医疗机构情况 (1).csv', name='定点医疗机构名称', level='医院等级',
         district='', extra='', prio=6, tag='医保局-怀柔2', trust_sub=False),
    dict(file='市医保局-区属二三级定点医疗机构.csv', name='医院名称', level='医院等级',
         district='区属名称', extra='', prio=6, tag='医保局-区属', trust_sub=False),
    dict(file='定点医疗机构信息.csv', name='定点医疗机构名称', level='医院等级',
         district='所属辖区', extra='', prio=6, tag='医保局-密云', trust_sub=True),
    dict(file='医疗保险定点医疗机构名单.csv', name='医院名称', level='医院等级',
         district='区县', extra='', prio=5, tag='医保局名单', trust_sub=False),  # 甲等口径粗，只取级别
    dict(file='东城区定点医疗机构信息.csv', name='医疗机构全称', level='机构等级',
         district='所属区', extra='', prio=6, tag='医保局-东城', trust_sub=False),
    dict(file='北京市区属二级、三级医院名单.csv', name='医疗机构名称', level='等级',
         district='区名称', extra='', prio=5, tag='区属二三级', trust_sub=False),
]

def find_header_row(header, rows, name_kw, level_kw):
    """部分文件前几行是标题/说明行，向下找真正表头行。返回 (header, data_rows)"""
    if any(name_kw in h for h in header) and any(level_kw in h for h in header):
        return header, rows
    for i, r in enumerate(rows[:8]):
        if any(name_kw in (c or '') for c in r) and any(level_kw in (c or '') for c in r):
            return r, rows[i+1:]
    return header, rows

def col(header, kw_list):
    for kw in kw_list:
        for i, h in enumerate(header):
            if kw in h:
                return i
    return None

def load_source(s):
    path = os.path.join(ROOT, s['file'])
    res = rt.load(path)
    if res is None:
        return None
    header, rows = res
    header, rows = find_header_row(header, rows, s['name'], s['level'])
    ni = col(header, [s['name']])
    li = col(header, [s['level']])
    if ni is None or li is None:
        return None
    di = col(header, [s['district']]) if s.get('district') else None
    si = col(header, [s['sub']]) if s.get('sub') else None
    ei = col(header, [s['extra']]) if s.get('extra') else None
    return header, rows, ni, li, di, si, ei

def parse_level_cell(cell):
    """返回 (level, level_sub, ok)"""
    c = (cell or '').strip()
    lv = re.search(r'[一二三]级', c)
    if not lv:
        if any(k in c for k in ('未定', '未评', '无等级', '无等', '未评级')):
            return '', '', True
        return None, None, False
    lv = lv.group(0)
    sub = ''
    if re.search(r'甲等|甲$', c): sub = '甲等'
    elif re.search(r'乙等|乙$', c): sub = '乙等'
    elif '合格' in c: sub = '合格'
    elif re.search(r'无等|未评', c): sub = '未评'
    return lv, sub, True

# ---------------------------------------------------------------- 构建证据池
evidence = defaultdict(list)   # norm_key -> list of dict
raw_src_stats = {}

def add_evidence(src_cfg, key, district, level, sub, raw, extra):
    evidence[key].append(dict(src=src_cfg['tag'], district=district or '', level=level,
                              sub=sub, raw=raw, extra=extra or '', prio=src_cfg['prio'],
                              trust_sub=src_cfg.get('trust_sub', False)))

for s in SOURCES:
    got = load_source(s)
    if got is None:
        raw_src_stats[s['file']] = 'LOAD_FAIL'
        continue
    header, rows, ni, li, di, si, ei = got
    cnt = 0
    for r in rows:
        name = (r[ni] if ni < len(r) else '').strip()
        if not name:
            continue
        lv_raw = (r[li] if li < len(r) else '').strip()
        if s.get('sub') and si is not None and si < len(r):
            sub_raw = (r[si] if si < len(r) else '').strip()
            lv_text = lv_raw + sub_raw
        else:
            sub_raw = ''
            lv_text = lv_raw
        level, sub, ok = parse_level_cell(lv_text if lv_text else lv_raw)
        if not ok:
            continue
        if not s.get('trust_sub', False):
            sub = ''  # 粗口径源不贡献等次细分
        district = ''
        if di is not None and di < len(r):
            district = (r[di] or '').strip()
        extra = ''
        if ei is not None and ei < len(r):
            extra = (r[ei] or '').strip()
        for key in variants(name):
            add_evidence(s, key, district, level, sub, lv_raw, extra)
            cnt += 1
        # 用含 district 的完整 key 再挂一次（精确优先）
        if district:
            add_evidence(s, district + '|' + norm_full(name), district, level, sub, lv_raw, extra)
    raw_src_stats[s['file']] = cnt

# ---------------------------------------------------------------- 主表读取
with open(MASTER, encoding='utf-8-sig') as f:
    master = list(csv.DictReader(f))
fieldnames = list(master[0].keys())

def decide(cands, cur_level=''):
    """依据证据决定 level/sub。返回 (level, sub, status, detail)
    status: 'unanimous' | 'conflict' | 'no-grade-evidence'
    level 仅当证据一致才返回；conflict 时返回多数派，但需人工。
    sub   只采纳 trust_sub 源。
    """
    graded = [c for c in cands if c['level']]
    if not graded:
        return None, None, 'no-grade-evidence', ''
    lv_opinions = set(c['level'] for c in graded)
    lv_cnt = Counter(c['level'] for c in graded)
    top_lv = lv_cnt.most_common(1)[0][0]
    unanimous = len(lv_opinions) == 1
    if unanimous:
        lv = top_lv
    else:
        # 高 prio 源的多数意见作为建议（人工核）
        ps = sorted(graded, key=lambda c: -c['prio'])
        lv = Counter(c['level'] for c in ps if c['prio'] == ps[0]['prio']).most_common(1)[0][0]
    # 等次细分：仅 trust_sub 源
    tsub = [c['sub'] for c in cands if c.get('trust_sub') and c['sub']]
    sub = Counter(tsub).most_common(1)[0][0] if tsub else ''
    detail = '一致' if unanimous else ('多数%d/%d 意见:%s' % (lv_cnt[top_lv], len(graded), sorted(lv_opinions)))
    return lv, sub, ('unanimous' if unanimous else 'conflict'), detail

def lookup(row):
    """返回该行所有可能命中的证据 (list of evidence dicts) 带匹配强度"""
    out = []
    name = row['name'].strip()
    district = row.get('district') or ''
    keys = variants(name)
    # 1) 区限定精确
    for key in keys:
        out += [dict(c, match='district+name') for c in evidence.get(district + '|' + norm_full(name), [])]
    # 2) 名字变体精确
    for key in keys:
        out += [dict(c, match='name') for c in evidence.get(key, [])]
    return out

level_sugg = []
bed_sugg = []
review = []
stats = Counter()

# 顺义/西城真实床位候选源
BED_SOURCES = [
    dict(file='北京市顺义区医疗机构床位数（截止2024年5月3日）.csv', name='机构名称', bed='床位数', level='机构级别', tag='顺义区床位(2024-05)'),
    dict(file='西城区等级医院名单.csv', name='名称', bed='床位', level='分类级别', tag='西城区等级医院名单'),
]

def load_beds():
    beds = defaultdict(list)  # key -> [dict(bed, level, src, district)]
    for s in BED_SOURCES:
        path = os.path.join(ROOT, s['file'])
        res = rt.load(path)
        if res is None:
            continue
        header, rows = res
        header, rows = find_header_row(header, rows, s['name'], s['level'] or s['bed'])
        ni = col(header, [s['name']]); bi = col(header, [s['bed']])
        if ni is None or bi is None:
            continue
        for r in rows:
            name = (r[ni] if ni < len(r) else '').strip()
            b = (r[bi] if bi < len(r) else '').strip().replace(',', '')
            if not name or not b:
                continue
            try:
                bv = float(b)
            except ValueError:
                continue
            if bv <= 0:
                continue
            for k in variants(name):
                beds[k].append(dict(bed=bv, src=s['tag']))
    return beds

beds_pool = load_beds()

for row in master:
    cat = row['category']
    name = row['name'].strip()
    cur_level = (row.get('level') or '').strip()
    cur_sub = (row.get('level_sub') or '').strip()
    cur_beds = (row.get('beds') or '').strip()
    is_hosp = cat in ('医院', '中医医院', '妇幼保健院')

    # ---- 等级
    if is_hosp:
        cands = lookup(row)
        if not cands:
            if not cur_level:
                stats['hospital-no-evidence'] += 1
                review.append(dict(kind='no-evidence', id=row['id'], name=name, district=row.get('district'),
                                   category=cat, level='', note='医院类无等级且无本地证据'))
            continue
        level, sub, status, detail = decide(cands, cur_level)
        if level is None:
            if not cur_level:
                review.append(dict(kind='only-ungraded', id=row['id'], name=name, district=row.get('district'),
                                   category=cat, level='', note='证据仅标未定级/无等级: ' + ';'.join(set(c['raw'] for c in cands))))
            continue
        # 强冲突(改大级)不进自动，转人工
        conflict_level_change = (status == 'conflict' and cur_level and cur_level != level)
        if status == 'conflict' and not cur_level:
            # 补空但有冲突：建议值，需人工
            review.append(dict(kind='conflict-new', id=row['id'], name=name, district=row.get('district'),
                               category=cat, level=level + sub, note='补等级多源冲突, 建议 ' + level + sub + ' | ' + detail))
            continue
        if conflict_level_change:
            review.append(dict(kind='conflict-change', id=row['id'], name=name, district=row.get('district'),
                               category=cat, level=cur_level + '->' + level, note='拟改级与现不同, 多数建议 ' + level + sub + ' | ' + detail))
            continue
        # 可自动：一致 或 冲突但与原一致(仅等次补全)/补空一致
        changed = (cur_level == '' and (level or sub)) or (cur_level and cur_level != level) or (sub and sub != cur_sub)
        if changed:
            level_sugg.append(dict(id=row['id'], name=name, district=row.get('district'), category=cat,
                                   old_level=cur_level, old_sub=cur_sub, new_level=level, new_sub=sub,
                                   status=status, action='apply',
                                   srcs=';'.join(sorted(set(c['src'] for c in cands)))[:300]))
        else:
            stats['hospital-ok'] += 1

    # ---- 床位（对有空床位且命中真实源的任何机构）
    if not cur_beds or float(cur_beds) <= 0:
        hits = []
        for k in variants(name):
            hits += beds_pool.get(k, [])
        if hits:
            best = max(hits, key=lambda x: x['bed'])
            bed_sugg.append(dict(id=row['id'], name=name, district=row.get('district'), category=cat,
                                 old_beds=cur_beds or '', new_beds=best['bed'], src=best['src']))

# ---------------------------------------------------------------- 输出
print('=== 等级/床位 证据池规模 ===')
for k, v in raw_src_stats.items():
    print(f'  {k:<44} {v}')
print()
print(f'医院/中医/妇幼 缺等级建议: {sum(1 for r in level_sugg if not r["old_level"])}')
print(f'已有等级疑似校正建议: {sum(1 for r in level_sugg if r["old_level"])}')
print(f'真实床位建议回填: {len(bed_sugg)}')
print(f'需人工复核: {len(review)}')
print(f'已有等级且本地证据一致(未列出): {stats["hospital-ok"]}')

with open(os.path.join(OUT, 'level_suggest.csv'), 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'name', 'district', 'category', 'old_level', 'old_sub', 'new_level', 'new_sub', 'status', 'action', 'srcs'])
    w.writeheader(); w.writerows(level_sugg)
with open(os.path.join(OUT, 'bed_suggest.csv'), 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'name', 'district', 'category', 'old_beds', 'new_beds', 'src'])
    w.writeheader(); w.writerows(bed_sugg)
with open(os.path.join(OUT, 'review_uncertain.csv'), 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['kind', 'id', 'name', 'district', 'category', 'level', 'note'])
    w.writeheader(); w.writerows(review)
print('\n输出目录:', OUT)
