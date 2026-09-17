# -*- coding: utf-8 -*-
"""办别 / 医院等级在线核实合并（幂等）：
baike_ownership.jsonl（百科信息栏：医院性质/经济类型/经营性质/主管部门/医院等级）
+ 内置名称规则引擎（军队系/国企职工/大学附属/社区/区属直称）
→ 主表新列
  ownership_online  在线核实办别（公立/民营）
  ownership_src     来源：baike_nature / baike_econ / baike_profit / baike_regulator / rule_military / rule_soe / rule_affiliated / rule_community / rule_district
  level_online      在线核实等级（三级/二级/一级/未定级）
  level_sub_online  在线核实等次（甲等/乙等/丙等）
  level_src         来源：baike_level
覆盖策略：只填空、不覆盖已有值；等级仅当原值为「不适用医院分级/未定级/空」时回填。
产出：data/processed/govern_report_ownership_online.md
"""
import csv
import json
import re
import sys

sys.path.insert(0, 'etl')
from build_specialty_online import ALIAS, norm  # noqa: E402

MASTER = 'data/processed/master_institutions.csv'
JSONL = 'data/processed/baike_ownership.jsonl'
REPORT = 'data/processed/govern_report_ownership_online.md'

LEVEL_GAP = ('不适用医院分级', '未定级', '', None)

# ---------- 名称规则引擎（只处理办别未标注的医院类机构，可解释） ----------
RULES = [
    ('rule_military', '公立',
     re.compile(r'中国人民解放军|武警|武装警察|军医大学|陆军总医院|海军总医院|空军总医院|火箭军')),
    ('rule_soe', '公立',
     re.compile(r'职工医院|航空总医院|航天|铁路|首钢|燕山石化|煤矿|矿务局|冶金|兵器|核工业')),
    ('rule_affiliated', '公立', re.compile(r'附属|附院')),
    ('rule_community', '公立', re.compile(r'社区卫生服务中心|社区卫生服务站')),
    ('rule_district', '公立',
     re.compile(r'^北京市?[市区]?.{0,6}(区|县)(中医医院|中西医结合医院|医院|妇幼保健院)$')),
    ('rule_district', '公立', re.compile(r'^北京中医医院')),
]

# ---------- 百科信息栏 → 办别（按证据强度排序） ----------
# 注意：主管部门=卫健委不能作为公立依据——民营医院的监管单位同样登记为卫健委
# （实测：北京京科银康/仲博/红旗/西京等民营中医院均如此），故不设 baike_regulator。
def _clean(v):
    return re.sub(r'\s*\[[^\]]{1,8}\]', '', v or '').split('；')[0].strip()


def baike_ownership(info):
    nature = _clean(info.get('医院性质', ''))
    econ = _clean(info.get('经济类型', ''))
    profit = _clean(info.get('经营性质', ''))
    # 注意「非公立（非营利性）」是民营办医口径，必须先于「公立」判断（子串包含陷阱）
    if '非公立' in nature or '民营' in nature or '私立' in nature or '私人' in nature:
        return '民营', 'baike_nature'
    if '公立' in nature or '政府办' in nature or '国有' in nature:
        return '公立', 'baike_nature'
    # 部分词条「医院性质」直接写营利性/非营利性（营利性医院必为民营办医）
    if '营利性' in nature and '非营利' not in nature:
        return '民营', 'baike_profit'
    if '国有全资' in econ or '集体全资' in econ or '全民所有制' in econ:
        return '公立', 'baike_econ'
    if '私有' in econ or '私人' in econ or '个人独资' in econ:
        return '民营', 'baike_econ'
    if '营利性' in profit and '非营利' not in profit:
        return '民营', 'baike_profit'
    return None, None


def baike_level(info):
    v = _clean(info.get('医院等级', ''))
    if not v:
        return None, None
    if '未定级' in v or '未评' in v:
        return '未定级', ''
    m = re.search(r'(三级|二级|一级)', v)
    if not m:
        return None, None
    lv = m.group(1)
    sub = ''
    ms = re.search(r'(甲等|乙等|丙等)', v)
    if ms:
        sub = ms.group(1)
    return lv, sub


def main():
    rows = list(csv.DictReader(open(MASTER, encoding='utf-8-sig')))
    by_name = {r['name']: r for r in rows}
    by_norm = {}
    for r in rows:
        by_norm.setdefault(norm(r['name']), r)

    EXTRA_ALIAS = {
        '中国人民解放军总医院': '中国人民解放军总医院(301医院)',
    }

    def resolve(name):
        n = EXTRA_ALIAS.get(name.strip(), ALIAS.get(name.strip(), name.strip()))
        return by_name.get(n) or by_norm.get(norm(n))

    # ---------- 1. 百科证据 ----------
    recs = [json.loads(l) for l in open(JSONL, encoding='utf-8')]
    own_upd, lvl_upd, unmatched = {}, {}, []
    for rec in recs:
        if not rec.get('found'):
            continue
        info = rec.get('infobox') or {}
        r = resolve(rec['query'])
        if not r:
            unmatched.append(rec['query'])
            continue
        o, osrc = baike_ownership(info)
        if o and r['ownership'] == '未标注' and r['id'] not in own_upd:
            own_upd[r['id']] = (o, osrc)
        lv, lsub = baike_level(info)
        if lv and r['level'] in LEVEL_GAP and r['id'] not in lvl_upd:
            lvl_upd[r['id']] = (lv, lsub)

    # ---------- 2. 规则引擎兜底（百科未覆盖的未标注医院） ----------
    rule_cnt = {}
    for r in rows:
        if r['ownership'] != '未标注' or r['id'] in own_upd:
            continue
        n = r['name']
        if '医院' not in n or re.search(r'村卫生室|村卫生所', n):
            continue
        for src, label, pat in RULES:
            if pat.search(n):
                own_upd[r['id']] = (label, src)
                rule_cnt[src] = rule_cnt.get(src, 0) + 1
                break

    # ---------- 3. 写回主表（新列追加，幂等） ----------
    hdr = list(rows[0].keys())
    for c in ('ownership_online', 'ownership_src', 'level_online', 'level_sub_online', 'level_src'):
        if c not in hdr:
            hdr.append(c)
    for r in rows:
        u = own_upd.get(r['id'])
        r['ownership_online'] = u[0] if u else ''
        r['ownership_src'] = u[1] if u else ''
        v = lvl_upd.get(r['id'])
        r['level_online'] = v[0] if v else ''
        r['level_sub_online'] = v[1] if v else ''
        r['level_src'] = 'baike_level' if v else ''
        # 等级在线修正后同步升级 grade_scope（真实医院不应留在 not_applicable 桶）；
        # 只升级不降级，未定级也属「适用医院等级评审」口径
        if v and r.get('grade_scope') == 'not_applicable':
            r['grade_scope'] = 'applicable'

    with open(MASTER, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        w.writerows(rows)

    # ---------- 4. 报告 ----------
    from collections import Counter
    own_now = Counter(r['ownership_online'] and (r['ownership'] if r['ownership'] != '未标注' else r['ownership_online']) or r['ownership'] for r in rows)
    lvl_now = Counter(r['level_online'] and r['level_online'] or r['level'] for r in rows)
    n_own = len(own_upd)
    n_lvl = len(lvl_upd)
    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write('# 办别/等级在线核实报告（百度百科信息栏 + 名称规则引擎）\n\n')
        f.write('- 抓取词条 %d，成功命中 %d；办别补全 %d（百科 %d + 规则 %d），等级补全 %d\n' %
                (len(recs), sum(1 for x in recs if x.get('found')), n_own,
                 n_own - sum(rule_cnt.values()), sum(rule_cnt.values()), n_lvl))
        f.write('- 主表新增列：ownership_online / ownership_src / level_online / level_sub_online / level_src\n')
        f.write('- ADS 层：ownership = COALESCE(ownership_online, ownership)；level = COALESCE(level_online, level)\n')
        f.write('- 规则命中分布：%s\n' % json.dumps(rule_cnt, ensure_ascii=False))
        f.write('- 合并后办别分布（原值⊕在线值）：%s\n' % json.dumps(own_now, ensure_ascii=False))
        f.write('- 合并后等级分布：%s\n' % json.dumps(lvl_now, ensure_ascii=False))
        f.write('- 未匹配词条 %d 个：%s\n\n' % (len(unmatched), unmatched[:20]))
        f.write('## 规则补全样例\n\n| 医院 | 办别 | 规则 |\n|---|---|---|\n')
        shown = 0
        for r in rows:
            if r['ownership_src'] and r['ownership_src'].startswith('rule_'):
                f.write('| %s | %s | %s |\n' % (r['name'], r['ownership_online'], r['ownership_src']))
                shown += 1
                if shown >= 40:
                    break
    print('ownership updated=%d rule=%s | level updated=%d | unmatched=%d' %
          (n_own, json.dumps(rule_cnt, ensure_ascii=False), n_lvl, len(unmatched)))


if __name__ == '__main__':
    main()
