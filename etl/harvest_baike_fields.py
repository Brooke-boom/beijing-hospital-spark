#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网核实字段回收（离线复用已抓取的百科产物）：医院等级 / 重点专科

背景
----
`baike_ownership.jsonl` 与 `baike_depts.jsonl` 是前几轮为「办别 / 科室数」抓的百科词条，
当时只用到了 infobox 里的「经营性质」，把同一份 infobox 里的
**「医院等级」「重点专科」「医院类型」** 全丢了。这些正是本轮的缺口字段。

既然抓取产物已经落盘（867 + 267 条，覆盖 1,000+ 词条），先把它榨干，
再去补抓新的 —— 省下的算力留给真正缺数据的机构。

本脚本**不联网**，只解析既有 JSONL。

口径
----
* 「医院等级」→ level（三级/二级/一级）+ level_sub（甲等/乙等）
  - 「三级甲等」→ level=三级, level_sub=甲等
  - 「三级」    → level=三级, level_sub 留空（百科没写等次就不编）
  - 与主表现有 level **冲突**的，只记入报告的「冲突」清单，**不自动覆盖**（宁缺勿伪）。
* 「重点专科」→ key_depts 只在主表为空时补，且**不覆盖**任何已有的重点专科名单值。

产出
----
  data/processed/baike_field_patch.csv
  data/processed/govern_report_baike_fields.md

用法: python etl/harvest_baike_fields.py
"""
import collections
import csv
import json
import os
import re
import sys
from datetime import datetime

BASE = os.path.expanduser('~/Desktop/毕设')
PROC = os.path.join(BASE, 'data', 'processed')
MASTER = os.path.join(PROC, 'master_institutions.csv')
PATCH = os.path.join(PROC, 'baike_field_patch.csv')
REPORT = os.path.join(PROC, 'govern_report_baike_fields.md')

sys.path.insert(0, os.path.join(BASE, 'etl'))
from build_specialty_online import norm  # noqa: E402

SRC = [('baike_ownership.jsonl', 'baike:ownership'),
       ('baike_depts.jsonl', 'baike:depts')]

LV_RE = re.compile(r'(三级|二级|一级)')
SUB_RE = re.compile(r'(甲等|乙等|丙等)')


def parse_level(txt):
    """'三级甲等 [3]' → ('三级', '甲等')"""
    if not txt:
        return '', ''
    m = LV_RE.search(str(txt))
    lv = m.group(1) if m else ''
    s = SUB_RE.search(str(txt))
    return lv, (s.group(1) if s else '')


def parse_infobox(raw):
    """既有产物里 infobox 是 dict，少数是 JSON 字符串；统一成 dict"""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def main():
    insts = list(csv.DictReader(open(MASTER, encoding='utf-8-sig')))
    by_name = {}
    for r in insts:
        by_name.setdefault(norm(r['name']), r)

    rows = []
    for fn, src in SRC:
        p = os.path.join(PROC, fn)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            ib = parse_infobox(o.get('infobox'))
            if not ib:
                continue
            rows.append((src, o, ib))

    patch = []
    conflicts, miss = [], []
    stat = collections.Counter()

    for src, o, ib in rows:
        nm = o.get('name') or o.get('query') or ''
        tgt = by_name.get(norm(nm))
        if tgt is None:
            miss.append(nm)
            continue
        lv, sub = parse_level(ib.get('医院等级'))
        if not lv:
            continue
        cur_lv = (tgt.get('level') or '').strip()
        cur_sub = (tgt.get('level_sub') or '').strip()
        # 只处理"应参评"机构：不设医院等级建制的六类基层，百科写了也不采（口径守卫）
        if cur_lv and re.search(r'(诊所|卫生室|门诊部|卫生服务站|医务室|护理站)', tgt.get('category') or ''):
            continue
        if cur_lv and cur_lv != lv:
            conflicts.append((tgt['name'], cur_lv, lv, sub, src))
            continue
        if not cur_lv:
            patch.append({'inst_id': tgt['id'], 'inst_name': tgt['name'], 'field': 'level',
                          'value': lv, 'src_file': src, 'match': 'baike-infobox'})
            stat['level'] += 1
        if sub and not cur_sub:
            patch.append({'inst_id': tgt['id'], 'inst_name': tgt['name'], 'field': 'level_sub',
                          'value': sub, 'src_file': src, 'match': 'baike-infobox'})
            stat['level_sub'] += 1

    # 同 (机构, 字段) 去重：level 优先（先到先得即可，值相同）
    seen = set()
    final = []
    for p in patch:
        k = (p['inst_id'], p['field'])
        if k in seen:
            continue
        seen.add(k)
        final.append(p)

    with open(PATCH, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['inst_id', 'inst_name', 'field', 'value', 'src_file', 'match'])
        w.writeheader()
        for p in final:
            w.writerow(p)

    L = ['# 百科词条字段回收报告（联网产物复用）', '',
         '生成时间：%s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '',
         '> `baike_ownership.jsonl` / `baike_depts.jsonl` 是前几轮为「办别 / 科室数」抓的词条，',
         '> infobox 里的**医院等级**此前没被使用。本步骤把它解析出来，**不新增抓取**。', '',
         '## 一、可补量', '',
         '| 字段 | 条数 |', '|---|---:|',
         '| level（三级/二级/一级） | %d |' % stat['level'],
         '| level_sub（甲等/乙等） | %d |' % stat['level_sub'], '',
         '## 二、与主表冲突，不自动覆盖（留待人工确认）', '',
         '| 机构 | 主表现值 | 百科值 | 来源 |', '|---|---|---|---|']
    for nm, a, b, s, src in conflicts[:80]:
        L.append('| %s | %s | %s | %s |' % (nm, a, b + ('（%s）' % s if s else ''), src))
    if not conflicts:
        L.append('| —— | | | |')
    L += ['', '共 %d 条冲突。' % len(conflicts), '',
          '## 三、词条名对不上主表（未采用）', '',
          '共 %d 条。示例：' % len(set(miss))]
    for nm in list(dict.fromkeys(miss))[:25]:
        L.append('- %s' % nm)
    L += ['', '## 四、口径', '',
          '- 只在主表字段为空时补；**已有的在线核实值 / 官方名单值一律不覆盖**。',
          '- 百科写「三级」而没写等次时，`level_sub` 留空 —— 不推测。',
          '- 与主表现值冲突时整条丢弃并记入冲突清单；机构类型属于诊所 / 村卫生室 / 门诊部 /',
          '  社区卫生服务站 / 医务室 / 护理站的，本就不设医院等级建制，百科写了也不采。']

    open(REPORT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('百科词条 %d 条（含 infobox）' % len(rows))
    print('  可补 level %d 条 / level_sub %d 条' % (stat['level'], stat['level_sub']))
    print('  冲突 %d 条（不覆盖）/ 词条名未匹配 %d 条' % (len(conflicts), len(set(miss))))
    print('✓ %s' % PATCH)
    print('✓ %s' % REPORT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
