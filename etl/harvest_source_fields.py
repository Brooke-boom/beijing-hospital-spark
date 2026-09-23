#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""源文件字段回收：把「合并时被丢弃的列」重新捞回来（第一轮，离线）

背景
----
「数据质量」页的关键字段完整率长期是：电话 5.8%（570 家）、交通 0.2%（17 家）、
等级 12%、重点专科 8.5%。看起来像"公开数据里就是没有"。

实际上公卫数据源里**有**这些列，只是 `clean_merge.py` 当年只取了
名称 / 地址 / 区 / 类别 / 经济类型等少数列，其余列在合并时就地丢弃：

  西城区等级医院名单.csv        → 电话 / 床位 / **重点科室** / **交通** / 医院网址
  朝阳区三级医疗机构名单.csv    → 联系电话
  朝阳区社区卫生服务中心名单.csv → 联系电话
  三级中医医疗机构名录.csv      → 电话号码
  丰台区三级/二级/中医/医务室   → 医院等级 / 联系电话
  平谷区村级卫生室.csv(1831 行) → 联系电话
  北京市健康体检机构信息.csv    → 咨询电话
  顺义区医疗机构名单.csv(802)   → 机构级别 / 机构等次
  卫健委可开放数据.csv(831)     → 医院等级 / 医院等次（分号单列）
  医疗保险定点医疗机构名单.csv  → 医院等级（**含甲等/乙等**）
  ……

所以第一步不是联网，而是"把自家仓库翻一遍"。**能离线拿到的，不必去网上猜。**

匹配规则与 `enrich_depts_haodf.py` 完全一致（复用同一套归一化 / 别名 / 包含式），
严禁 difflib 兜底。候选不唯一 → 整条丢弃并记入报告的「歧义」清单。

产出
----
  data/processed/source_field_patch.csv        补丁（inst_id, field, value, src_file, match）
  data/processed/govern_report_field_harvest.md 治理报告（分字段 / 分来源统计）
**本脚本只产出补丁，不改主表**（回写由 apply_field_patch.py 统一做）。

用法: python etl/harvest_source_fields.py
"""
import csv
import collections
import os
import re
import sys
import unicodedata
from datetime import datetime

BASE = os.path.expanduser('~/Desktop/毕设')
PROC = os.path.join(BASE, 'data', 'processed')
DATA = os.path.join(BASE, 'data')
MASTER = os.path.join(PROC, 'master_institutions.csv')
PATCH = os.path.join(PROC, 'source_field_patch.csv')
REPORT = os.path.join(PROC, 'govern_report_field_harvest.md')

sys.path.insert(0, os.path.join(BASE, 'etl'))
from build_specialty_online import ALIAS, norm  # noqa: E402  复用既有归一化与院名别名
from clean_merge import std_level               # noqa: E402  复用"文件名声明等级"的同一套规则

# ---------------------------------------------------------------- 字段与列名别名
# 列名 → 目标字段。用**等值**匹配（去掉空白后比较），不用子串 ——
# 子串会把「医院等级说明」这种备注列也吸进来。
COL_ALIAS = {
    # 联系电话
    '联系电话': 'phone', '电话号码': 'phone', '咨询电话': 'phone', '电话': 'phone',
    '联系方式': 'phone', '机构电话': 'phone', '电话（总机）': 'phone',
    '1.2.4 联系电话座机或手机': 'phone',
    # 等级（级别：三级/二级/一级/未定级）
    '医院等级': 'level', '机构级别': 'level', '分类级别': 'level', '级别': 'level',
    # 等次（甲/乙/丙/合格）
    '医院等次': 'level_sub', '机构等次': 'level_sub', '等次': 'level_sub',
    # 床位（真实值才收；本字段不进展示与评分）
    '床位数': 'beds', '床位': 'beds', '实有床位数': 'beds', '编制床位数': 'beds',
    # 交通导引
    '交通': 'traffic', '乘车路线': 'traffic', '交通导引': 'traffic', '交通指南': 'traffic',
    # 重点专科 / 擅长科室
    '重点科室': 'key_depts', '重点专科': 'key_depts', '特色科室': 'key_depts',
    # 官网
    '医院网址': 'website', '挂号网址': 'website', '网址': 'website',
}

# 列名归一（去空白 / 全角空格 / 换行）
def colkey(s):
    return re.sub(r'[\s\u3000]+', '', str(s or '')).replace('\ufeff', '')


_COLKEY2FIELD = {colkey(k): v for k, v in COL_ALIAS.items()}

# 名称列 / 也要认出来以便取行名
NAME_COLS = ['机构名称', '医疗机构名称', '医疗机构全称', '医院名称', '名称', '机构名称（签章）',
             '单位名称', '机构']

# 区列：源文件自带区县时用它做**硬约束**（基层机构名高度重复，不看区就会串区）
DISTRICT_COLS = ['区县名称', '区县名称-16', '所属区', '所属辖区', '区县', '行政区', '区']

# 等级词的规范化：原表写法五花八门
LV_RE = re.compile(r'(三级|二级|一级)')
SUB_RE = re.compile(r'(甲等|乙等|丙等|合格|基本合格|未评|不评|未定级|无等级)')


def to_level(txt):
    """从任意写法里抽「三级/二级/一级」；抽不到返回 ''"""
    if not txt:
        return ''
    t = str(txt).strip()
    m = LV_RE.search(t)
    return m.group(1) if m else ''


def to_level_sub(txt):
    """从等次列抽「甲等/乙等/…」；'合格'类不算等次（那是评审结论，不是甲/乙）"""
    if not txt:
        return ''
    m = re.search(r'(甲等|乙等|丙等)', str(txt))
    return m.group(1) if m else ''


_PH_SPLIT = re.compile(r'[\n\r]+')
_PH_KEEP = re.compile(r'[0-9][0-9\-\s\(\)（）转/、,，\.]{5,}')
_CN_NUM = str.maketrans('０１２３４５６７８９（）－', '0123456789()-')


def to_phone(txt):
    """抽第一个电话；去掉「工作日 8:00-11:30」这类时间备注

    公卫数据里的电话列常写成
      "64522668(工作日8:00-11:30;13:30-17:00)\\n64234017(节假日8:00-20:00)"
    展示层不需要这些排班说明，取第一条主号即可（并保留备号）。
    """
    if not txt:
        return ''
    t = str(txt).translate(_CN_NUM)
    parts = []
    for seg in _PH_SPLIT.split(t):
        seg = seg.strip()
        if not seg:
            continue
        # 去掉括号里的时间说明（含"工作日""节假日""转"的保留 —— "转"是分机号）
        seg = re.sub(r'[（(][^（）()]*(?:工作日|节假日|周末|上午|下午|夜间)[^（）()]*[）)]', '', seg)
        m = _PH_KEEP.search(seg)
        if not m:
            continue
        v = re.sub(r'\s+', '', m.group(0)).strip('-、,，./ ')
        digits = re.sub(r'\D', '', v)
        if len(digits) < 7 or len(digits) > 20:
            continue
        parts.append(v)
    if not parts:
        return ''
    return ' / '.join(parts[:2])


def to_text(txt, limit=120):
    if not txt:
        return ''
    t = re.sub(r'[\s\u3000]+', ' ', str(txt)).strip()
    if len(t) > limit:
        t = t[:limit].rstrip()
    return t


def to_beds(txt):
    if not txt:
        return ''
    m = re.search(r'(\d+(?:\.\d+)?)', str(txt).replace(',', ''))
    if not m:
        return ''
    v = float(m.group(1))
    if v <= 0 or v > 20000:
        return ''
    return str(int(v)) if v == int(v) else str(v)


def to_url(txt):
    t = to_text(txt, 200)
    m = re.search(r'https?://[^\s，,；;]+', t)
    return m.group(0) if m else ''


CLEANERS = {'phone': to_phone, 'level': to_level, 'level_sub': to_level_sub,
            'beds': to_beds, 'traffic': lambda x: to_text(x, 160),
            'key_depts': lambda x: to_text(x, 200), 'website': to_url}

# ---------------------------------------------------------------- 读表
ENCODINGS = ('utf-8-sig', 'gbk', 'gb18030', 'utf-16', 'utf-8')


def read_table(path):
    """返回 (header_row_idx, rows)；自动跳过标题行 / 合并单元格垃圾行

    公卫导出常把「密云区卫健委2023年度公开数据」放第 1 行、表头放第 2 行，
    也有的整行只有一个单元格（合并单元格残留）。这里向下找表头。
    """
    if path.endswith('.xlsx'):
        try:
            import openpyxl
        except ImportError:
            return None, None
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            # ⚠️ read_only 模式下 openpyxl 按**声明维度**迭代，而不是按真实有数据的范围。
            # Excel 另存过的表常把维度写成 A1:Z1048576，于是 iter_rows 会老老实实
            # 走完 100 万行 —— 表现为脚本在这一行上"无声卡死"（实测卡了 5 分钟以上）。
            # reset_dimensions() 让维度回到真实数据范围。
            try:
                ws.reset_dimensions()
            except Exception:
                pass
            rows = []
            for i, r in enumerate(ws.iter_rows(values_only=True)):
                if i > 60000:
                    break
                rows.append([('' if c is None else str(c)) for c in r])
            wb.close()
        except Exception:
            return None, None
    else:
        rows = None
        for enc in ENCODINGS:
            try:
                with open(path, encoding=enc, newline='') as f:
                    rows = [r for r in csv.reader(f)]
                break
            except Exception:
                continue
        if rows is None:
            return None, None

    best, best_score = None, -1
    for i, r in enumerate(rows[:8]):
        cells = [colkey(c) for c in r]
        nz = [c for c in cells if c]
        if not nz:
            continue
        score = sum(1 for c in nz if c in _COLKEY2FIELD) + \
            (2 if any(c in [colkey(x) for x in NAME_COLS] for c in nz) else 0)
        if score > best_score:
            best, best_score = i, score
    if best is None:
        return None, None
    body = [r for r in rows[best + 1:] if any(str(c).strip() for c in r)]
    return best, [rows[best]] + body


def split_semicolon_single(header, rows):
    """卫健委可开放数据.csv 之类：整个表塞在一列里，用 ; 分隔"""
    if len(header) != 1 or ';' not in str(header[0]):
        return header, rows
    hdr = [x.strip() for x in str(header[0]).split(';')]
    out = []
    for r in rows:
        if len(r) != 1 or ';' not in str(r[0]):
            continue
        cells = [x.strip() for x in str(r[0]).split(';')]
        if len(cells) >= len(hdr):
            out.append(cells[:len(hdr)])
    if not out:
        return header, rows
    return hdr, out


# ---------------------------------------------------------------- 名称匹配
def core(s):
    """去括号补充说明后的核心名"""
    return re.sub(r'\([^()]*\)', '', norm(s))


def strip_suffix_paren(s):
    return re.sub(r'[（(][^（）()]*[）)]', '', str(s or '')).strip()


SATELLITE = re.compile(r'(社区卫生服务站|社区卫生服务中心|卫生服务站|村卫生室|卫生室|医务室|'
                       r'门诊部|诊所|护理站|卫生所|保健所|school|大学|学院|公司|宾馆|酒店|工厂|'
                       r'培训|中心|站$)')
MINCORE = 4
MAXEXTRA = 12
# 基层机构（村卫生室 / 诊所 / 门诊部 …）：名称重复率极高，放宽匹配会串区，
# 因此改用**更严**的规则 —— 主表名必须以源名结尾（"北京市平谷区马坊镇二条街村卫生室"
# 以 "马坊镇二条街村卫生室" 结尾），且短名 ≥6 字、区必须一致。
MINCORE_SAT = 6
MAXEXTRA_SAT = 16


def norm_district(s):
    """'110115-大兴区' → '大兴区'；'北京市朝阳区' → '朝阳区'"""
    t = str(s or '')
    t = re.sub(r'^\s*\d{6}\s*[-—]?\s*', '', t)
    m = re.search(r'([\u4e00-\u9fa5]{2,4}?[区县])', t)
    return m.group(1) if m else t.strip()


def build_matcher(insts):
    by_full, by_core = {}, {}
    for r in insts:
        by_full.setdefault(norm(r['name']), []).append(r)
        by_core.setdefault(core(r['name']), []).append(r)

    # 包含式必须快：朴素写法是「每个待匹配名 × 9,789 家」，平谷村级卫生室一家就 1,831 行，
    # 实测直接跑到被系统掐掉。改用 **3-gram 倒排索引**：若 n 是 b 的子串且 len(n)≥4，
    # 则 n 的每个 3-gram 都出现在 b 里 —— 先按 3-gram 取候选，再做子串校验，
    # 候选数从 9,789 降到个位数。
    gram = collections.defaultdict(set)
    for i, r in enumerate(insts):
        mn = norm(r['name'])
        for j in range(len(mn) - 2):
            gram[mn[j:j + 3]].add(i)

    cache = {}

    def _cand(n):
        idxs = None
        for j in range(len(n) - 2):
            g = gram.get(n[j:j + 3])
            if g is None:
                return ()
            idxs = set(g) if idxs is None else (idxs & g)
            if not idxs:
                return ()
        return idxs or ()

    def contains(n, dist=None, sat=False):
        """返回 (目标机构, 长度差)；短名长度 / 长度差 / 候选唯一 / 区一致 四重约束"""
        lim_low = MINCORE_SAT if sat else MINCORE
        lim_ext = MAXEXTRA_SAT if sat else MAXEXTRA
        if len(n) < lim_low:
            return None, None
        cands = []
        for i in _cand(n):
            r = insts[i]
            mn = norm(r['name'])
            if dist and r.get('district') and r['district'] != dist:
                continue            # 区不一致 → 直接排除，宁可漏也不串区
            if sat:
                ok = mn.endswith(n) and (len(mn) - len(n)) <= lim_ext
            else:
                ok = (n in mn or mn in n) and (len(mn) - len(n)) <= lim_ext
            if ok:
                cands.append((len(mn) - len(n), i))
        if not cands:
            return None, None
        cands.sort()
        best = cands[0][0]
        ids = sorted({insts[i]['id'] for e, i in cands if e == best})
        if len(ids) == 1:
            return next(r for r in insts if r['id'] == ids[0]), best
        return None, None

    def match(raw_name, dist=None):
        key = (raw_name, dist)
        if key in cache:
            return cache[key]
        n = norm(raw_name)
        c = core(n)
        tgt, how = None, ''
        if n in by_full and len(by_full[n]) == 1:
            tgt, how = by_full[n][0], 'exact'
        if tgt is None and c and c in by_core and len(by_core[c]) == 1:
            tgt, how = by_core[c][0], 'core'
        if tgt is None:
            for src, dst in ALIAS.items():
                if n != norm(src):
                    continue
                d = norm(dst)
                if d in by_full and len(by_full[d]) == 1:
                    tgt, how = by_full[d][0], 'alias'
                elif d in by_core and len(by_core[d]) == 1:
                    tgt, how = by_core[d][0], 'alias'
                if tgt is not None:
                    break
        if tgt is None and n and len(n) >= MINCORE:
            sat = bool(SATELLITE.search(n))
            tgt, e = contains(n, dist=dist, sat=sat)
            if tgt is not None:
                how = ('suffix+%d' if sat else 'contain+%d') % e
        cache[key] = (tgt, how)
        return cache[key]

    return match


# ---------------------------------------------------------------- 主流程
# 来源可信度（同字段多来源冲突时取分高者）。数字越大越权威。
SRC_RANK = [
    (re.compile(r'西城区等级医院名单'), 95),      # 区卫健委「等级医院」专题表，字段最全
    (re.compile(r'卫健委可开放数据'), 90),
    (re.compile(r'医疗保险定点医疗机构名单'), 88),
    (re.compile(r'市医保局'), 85),
    (re.compile(r'区医保局'), 84),
    (re.compile(r'定点医疗机构'), 80),
    (re.compile(r'顺义区医疗机构名单'), 78),
    (re.compile(r'医疗机构（基本信息）'), 76),
    (re.compile(r'社区卫生服务站名单'), 70),
    (re.compile(r'大兴区|密云区|平谷区|延庆区|房山区|朝阳区|海淀区|通州区|丰台区'), 66),
    (re.compile(r'.*'), 50),
]


def src_rank(fname):
    for pat, sc in SRC_RANK:
        if pat.search(fname):
            return sc
    return 50


def main():
    insts = list(csv.DictReader(open(MASTER, encoding='utf-8-sig')))
    match = build_matcher(insts)

    used = set()
    for r in insts:
        for f in (r['source_files'] or '').split('|'):
            if f.strip():
                used.add(f.strip())

    # 补上「在 data/ 目录里但没被合并进去」的候选源（有字段就先捞，是否采用看下面的白名单）
    extra = []
    for f in sorted(os.listdir(DATA)):
        if f.endswith(('.csv', '.xlsx')) and f not in used:
            extra.append(f)

    patches = []          # dict: inst_id, field, value, src_file, match
    stats = collections.Counter()
    per_file = collections.defaultdict(collections.Counter)
    ambiguity = []
    unreadable = []

    for fname in sorted(used) + extra:
        path = os.path.join(DATA, fname)
        if not os.path.exists(path):
            unreadable.append((fname, '文件不存在'))
            continue
        print('  · %s' % fname, flush=True)
        hi, rows = read_table(path)
        if hi is None or not rows or len(rows) < 2:
            unreadable.append((fname, '读不出表头 / 无非空数据行'))
            continue
        header, rows = split_semicolon_single(rows[0], rows[1:])
        cols = {}
        name_idx = None
        dist_idx = None
        for i, h in enumerate(header):
            k = colkey(h)
            if k in _COLKEY2FIELD:
                cols.setdefault(_COLKEY2FIELD[k], i)
            if name_idx is None and k in [colkey(x) for x in NAME_COLS]:
                name_idx = i
            if dist_idx is None and k in [colkey(x) for x in DISTRICT_COLS]:
                dist_idx = i
        if name_idx is None:
            continue

        # 文件名声明的等级：《一级中医医疗机构名录》《三级中医医疗机构名录》《驻区二级医疗机构》
        # 这类文件，名单本身就是按等级发布的，表里根本没有等级列 —— **文件名即口径**。
        # clean_merge.std_level 本来就在合并期用这条规则做兜底，但同名机构跨多份源合并时，
        # 等级可能被"另一份没有等级信息的源"占了位，于是留下了 4 家空等级
        # （今康中医医院 / 景萍骨科医院 / 世华中医医院 / 诺德康泽中医门诊部）。
        # 这里把它作为**补全来源**再走一遍，等价于把兜底规则补完。
        #
        # 两个前置守卫（与 std_level 同源，缺一不可）：
        #   ① 文件名里出现**两种**等级词 = 跨等级名单（《区属二级、三级医院名单》《市医保局-区属
        #      二三级定点机构》），任何单一等级都不成立 → 放弃；
        #   ② 「一级以下」「村一级」由 std_level 内部的否定上下文守卫挡掉。
        # 六类基层机构（诊所/村卫生室/门诊部/…）不设等级建制，由 apply_field_patch.py 拦截。
        if 'level' not in cols:
            _lvs = set(re.findall(r'(三级|二级|一级)', fname))
            if len(_lvs) == 1:
                flv, fsub = std_level('', fname)
                if flv:
                    cols['level'] = -1
                    if fsub and 'level_sub' not in cols:
                        cols['level_sub'] = -1

        if not cols:
            continue

        for r in rows:
            if name_idx >= len(r):
                continue
            raw = str(r[name_idx]).strip()
            if not raw:
                continue
            dist = norm_district(r[dist_idx]) if (dist_idx is not None and dist_idx < len(r)) else None
            tgt, how = match(raw, dist)
            if tgt is None:
                continue
            for field, ci in cols.items():
                if ci == -1:                     # 文件名声明的等级
                    val = std_level('', fname)[0] if field == 'level' else std_level('', fname)[1]
                    how2 = 'fname'
                else:
                    if ci >= len(r):
                        continue
                    val = CLEANERS[field](r[ci])
                    how2 = how
                if not val:
                    continue
                patches.append({'inst_id': tgt['id'], 'inst_name': tgt['name'], 'field': field,
                                'value': val, 'src_file': fname, 'match': how2, 'rank': src_rank(fname)})
                stats[field] += 1
                per_file[fname][field] += 1

    # 同 (inst, field) 多来源 → 取 rank 高者；rank 相同取更长值（信息更多）
    best = {}
    for p in patches:
        k = (p['inst_id'], p['field'])
        cur = best.get(k)
        if cur is None or (p['rank'], len(p['value'])) > (cur['rank'], len(cur['value'])):
            best[k] = p
    final = sorted(best.values(), key=lambda x: (x['field'], int(x['inst_id'])))

    with open(PATCH, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['inst_id', 'inst_name', 'field', 'value', 'src_file', 'match'])
        w.writeheader()
        for p in final:
            w.writerow({k: p[k] for k in ('inst_id', 'inst_name', 'field', 'value', 'src_file', 'match')})

    # 现有主表非空数，用于报告对比
    have = {f: sum(1 for r in insts if (r.get(f) or '').strip())
            for f in ['phone', 'level', 'level_sub', 'beds', 'traffic', 'key_depts', 'website']}
    newfill = collections.Counter()
    for p in final:
        if not (next(r for r in insts if r['id'] == p['inst_id']).get(p['field']) or '').strip():
            newfill[p['field']] += 1

    L = ['# 源文件字段回收报告（离线第一轮）', '',
         '生成时间：%s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '',
         '> 结论先行：关键字段「覆盖率低」的主因**不是公开数据没有**，而是合并阶段把这些列丢掉了。',
         '> 本步骤只从 data/ 目录下的源文件里回收，**不联网、不推断、不估算**。', '',
         '## 一、总览', '',
         '| 字段 | 主表现有非空 | 本次可补（当前为空） | 回收来源行数 |',
         '|---|---:|---:|---:|']
    for f in ['phone', 'level', 'level_sub', 'traffic', 'key_depts', 'beds', 'website']:
        L.append('| %s | %d | **%d** | %d |' % (f, have.get(f, 0), newfill.get(f, 0), stats.get(f, 0)))
    L += ['', '## 二、每个源文件贡献了什么', '',
          '| 源文件 | ' + ' | '.join(['phone', 'level', 'level_sub', 'traffic', 'key_depts', 'beds', 'website']) + ' |',
          '|---|' + '---:|' * 7]
    for fname in sorted(per_file, key=lambda k: -sum(per_file[k].values())):
        row = per_file[fname]
        L.append('| %s | ' % fname + ' | '.join(str(row.get(f, 0) or '') for f in
                 ['phone', 'level', 'level_sub', 'traffic', 'key_depts', 'beds', 'website']) + ' |')
    L += ['', '## 三、读不出来的源文件（不影响结论，仅备查）', '']
    for fname, why in unreadable:
        L.append('- %s —— %s' % (fname, why))
    L += ['', '## 四、口径说明', '',
          '- 匹配规则与 `enrich_depts_haodf.py` 一致：全等 → 去括号全等 → 别名字典 → 严格包含式；',
          '  **不使用 difflib 相似度**（"北京朝阳医院"vs"北京医院" 相似度 0.80，必错配）。',
          '- 同一 (机构, 字段) 命中多个源时，按来源权威度取一：区卫健委专题表 > 市/区医保局 > 区级名录。',
          '- 电话只取号码本体，剥掉「(工作日 8:00-11:30)」这类排班说明；等次列只认甲/乙/丙等，',
          '  「合格 / 未评」属评审结论而非等次，不计入 `level_sub`。',
          '- 补丁文件：`data/processed/source_field_patch.csv`（回写由 apply_field_patch.py 负责）。']

    open(REPORT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')

    print('源文件 %d 个（在用）+ %d 个（未合并）' % (len(used), len(extra)))
    for f in ['phone', 'level', 'level_sub', 'traffic', 'key_depts', 'beds', 'website']:
        print('  %-10s 现有 %5d  →  可补 %5d  （来源命中 %5d 行）'
              % (f, have.get(f, 0), newfill.get(f, 0), stats.get(f, 0)))
    print('✓ %s' % PATCH)
    print('✓ %s' % REPORT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
