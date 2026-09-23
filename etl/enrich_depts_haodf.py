#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在线核实科室数 → 主表回写（第三轮，数据源：好大夫在线）

问题：主表 9,789 家机构里只有 34 家有在线核实的科室数（前两轮走百度百科），
      机构列表因此 99.6% 显示「科室资料待补全」。百科对一级/二级医院覆盖极差，
      好大夫在线对**北京全体医院**有成体系的科室数据，且页头直接给出官方口径
      「N个科室」，正好补上这个窟窿。

匹配（严禁"差不多就认"）：
  1) 归一化后全等
  2) 去掉括号后缀后全等
  3) 别名字典（haodf 用简称：北京朝阳医院 / 北医三院 / 医科院肿瘤医院）
  4) **包含式**：一方是另一方的子串，且短名 ≥4 字、长度差 ≤12 字、
     同名候选唯一。取"长度差最小"的那家。
     ⚠️ 绝不用 difflib 相似度兜底：实测 "北京朝阳医院" 与 "北京医院" 相似度 0.80，
        "北京安贞医院" 与 "北京安达医院" 0.83 —— 会张冠李戴，比没有数据更糟。
  5) 候选不唯一 → 整条丢弃，记进报告的「歧义」清单待人工确认

回写主表（只增不改不删，且**不覆盖**已有的在线核实值）：
  dept_count_online  在线核实科室数
  dept_count_src     'haodf'（好大夫在线 · 在线核实）

产出：
  data/processed/haodf_match.csv                 匹配结果（供 build_dept_dict.py 消费）
  data/processed/govern_report_depts_haodf.md    治理报告

用法: python etl/enrich_depts_haodf.py
"""
import csv
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime

BASE = os.path.expanduser('~/Desktop/毕设')
PROC = os.path.join(BASE, 'data/processed')
MASTER = os.path.join(PROC, 'master_institutions.csv')
JSONL = os.path.join(PROC, 'haodf_depts.jsonl')
MATCH = os.path.join(PROC, 'haodf_match.csv')
REPORT = os.path.join(PROC, 'govern_report_depts_haodf.md')
BAKDIR = os.path.join(BASE, 'data/归档_旧版命名/processed_backup')

sys.path.insert(0, os.path.join(BASE, 'etl'))
from build_specialty_online import ALIAS, norm  # noqa: E402  复用已有的别名与归一

# haodf 用简称，主表用官方全称。这份表只收**人工核对过**的对应关系；
# 凡不能一眼确认的（如"北京东区儿童医院"归属）一律不写，宁可留在未匹配清单里。
HAODF_ALIAS = {
    '医科院肿瘤医院': '中国医学科学院肿瘤医院',
    '北大口腔医院': '北京大学口腔医院',
    '北医六院': '北京大学第六医院',
    '北大肿瘤医院': '北京肿瘤医院、北京大学肿瘤医院',
    '解放军总医院第九医学中心': '中国人民解放军总医院第九医学中心',
    '解放军总医院第六医学中心': '中国人民解放军总医院第六医学中心',
    '解放军总医院第八医学中心': '中国人民解放军总医院第八医学中心',
    '解放军总医院第五医学中心': '中国人民解放军总医院第五医学中心',
    '中国人民解放军总医院第三医学中心': '中国人民解放军总医院第三医学中心',
    '北大第一医院': '北京大学第一医院',
    '北大人民医院': '北京大学人民医院',
    '首儿所': '首都儿科研究所附属儿童医院',
    '首都儿科研究所附属儿童医院': '首都儿科研究所附属儿童医院',
    '中国中医科学院望京医院': '中国中医科学院望京医院',
    '北京中医医院': '首都医科大学附属北京中医医院',
    '广安门医院': '中国中医科学院广安门医院',
    '北京儿童医院': '首都医科大学附属北京儿童医院',
    '北京口腔医院': '首都医科大学附属北京口腔医院',
    '北京胸科医院': '首都医科大学附属北京胸科医院',
}

# 短名/全称混排：这些 haodf 条目指向院内门诊部/分院，不是主院，禁止匹配到主院
SATELLITE = re.compile(r'(门诊部|门诊|分院|院区|诊所|卫生服务站|社区服务站)')
# 长度差上限：超过这个差值说明候选名与本名不是同一家的两种写法
MAXEXTRA = 12
MINCORE = 4
# 主表的「医院类」类型：只有当 haodf 名里含"医院/中心/保健院"时，才优先在这些类型里找
HOSP_CATS = ('医院', '中医医院', '妇幼保健院')


def core(s):
    """去掉括号补充说明后的核心名"""
    return re.sub(r'\([^()]*\)', '', norm(s))


def load_master():
    with open(MASTER, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def load_haodf():
    out = []
    for line in open(JSONL, encoding='utf-8'):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def build_match(insts, haodf):
    by_full, by_core, by_name = {}, {}, {}
    for r in insts:
        by_full.setdefault(norm(r['name']), []).append(r)
        by_core.setdefault(core(r['name']), []).append(r)
        by_name.setdefault(norm(r['name']), r)

    rows, ambiguity, miss = [], [], []
    for o in haodf:
        hn = norm(o.get('name') or '')
        if not hn:
            continue
        tgt, how = None, ''
        # 1) 全等
        if hn in by_full:
            tgt, how = by_full[hn][0], 'exact'
        # 2) 去括号全等
        if tgt is None and core(hn) in by_core:
            tgt, how = by_core[core(hn)][0], 'core'
        # 3) 别名字典（先 haodf 专用表，再复用已有的院名别名表）
        if tgt is None:
            for src, dst in list(HAODF_ALIAS.items()) + list(ALIAS.items()):
                if hn != norm(src):
                    continue
                d = norm(dst)
                if d in by_full:
                    tgt, how = by_full[d][0], 'alias'
                elif d in by_core:
                    tgt, how = by_core[d][0], 'alias'
                if tgt is not None:
                    break
        # 4) 包含式（严格：短名≥4、长度差≤12、候选唯一）
        if tgt is None and not SATELLITE.search(hn) and hn not in ('', ):
            cands = []
            for r in insts:
                mn = norm(r['name'])
                for a, b in ((hn, mn), (mn, hn)):
                    if len(a) >= MINCORE and a in b and (len(b) - len(a)) <= MAXEXTRA:
                        cands.append((len(b) - len(a), r))
            if cands:
                cands.sort(key=lambda x: x[0])
                best = cands[0][0]
                tops = [r for e, r in cands if e == best]
                # 同名多家时，优先「医院类」——haodf 目录是医院目录，不会指向某某门诊部
                hosp = [r for r in tops if r.get('category') in HOSP_CATS]
                pick = hosp if len(hosp) == 1 else (tops if len(tops) == 1 else [])
                if len(pick) == 1:
                    tgt, how = pick[0], 'contain+%d' % best
                else:
                    ambiguity.append((o.get('name'), [r['name'] for r in tops][:4]))
        if tgt is None:
            miss.append(o.get('name'))
            continue
        rows.append({
            'inst_id': tgt['id'], 'inst_name': tgt['name'], 'hid': str(o['hid']),
            'haodf_name': o.get('name') or '', 'match': how,
            'dept_count': o.get('dept_count') or 0,
            'dept_list_count': len(o.get('depts') or []),
        })
    return rows, ambiguity, miss


def main():
    insts = load_master()
    haodf = load_haodf()
    rows, ambiguity, miss = build_match(insts, haodf)
    print('  好大夫条目 %d | 匹配上 %d | 歧义 %d | 未匹配 %d'
          % (len(haodf), len(rows), len(ambiguity), len(miss)))

    # 一家机构被多条 haodf 命中时保留信息量最大的那条（科室名更多）
    dedup = {}
    for r in rows:
        k = r['inst_id']
        if k not in dedup or (r['dept_list_count'], r['dept_count']) > \
                (dedup[k]['dept_list_count'], dedup[k]['dept_count']):
            dedup[k] = r
    uniq = list(dedup.values())
    print('  去重后覆盖机构 %d 家' % len(uniq))

    with open(MATCH, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['inst_id', 'inst_name', 'hid', 'haodf_name',
                                          'match', 'dept_count', 'dept_list_count'])
        w.writeheader()
        w.writerows(sorted(uniq, key=lambda r: int(r['inst_id'])))

    # ---- 回写主表 ----
    by_id = {r['id']: r for r in insts}
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs(BAKDIR, exist_ok=True)
    shutil.copy2(MASTER, os.path.join(BAKDIR, 'master_institutions_%s.csv' % ts))

    applied, skipped_have = [], []
    for r in uniq:
        m = by_id.get(r['inst_id'])
        if m is None:
            continue
        n = int(r['dept_count'] or r['dept_list_count'] or 0)
        if n <= 0:
            continue
        if (m.get('dept_count_src') or '').strip():
            skipped_have.append((r, m.get('dept_count_src'), m.get('dept_count_online')))
            continue
        # 好大夫页头口径优先；页头没有时退回科室列表条数（报告里分别标注）
        m['dept_count_online'] = str(n)
        m['dept_count_src'] = 'haodf_claim' if r['dept_count'] else 'haodf_list'
        applied.append((r, n))

    with open(MASTER, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(insts[0].keys()))
        w.writeheader()
        w.writerows(insts)
    print('  主表回写 %d 家（跳过已有在线核实值 %d 家）' % (len(applied), len(skipped_have)))

    # ---- 报告 ----
    by_cat, by_src = {}, {}
    for r, n in applied:
        c = by_id[r['inst_id']]['category']
        by_cat[c] = by_cat.get(c, 0) + 1
        s = by_id[r['inst_id']]['dept_count_src']
        by_src[s] = by_src.get(s, 0) + 1
    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write('# 科室数在线核实（好大夫在线）治理报告\n\n')
        f.write('- 生成时间：%s\n' % ts)
        f.write('- 数据源：好大夫在线 北京医院目录 `hospital/list-11.html` + 各院科室列表页\n')
        f.write('- 抓取产出：`data/processed/haodf_depts.jsonl`（%d 家）\n' % len(haodf))
        f.write('- 匹配结果：`data/processed/haodf_match.csv`（%d 家，去重后）\n\n' % len(uniq))
        f.write('## 一、匹配口径\n\n')
        f.write('全等 → 去括号全等 → 别名字典 → **包含式**（短名≥4 字、长度差≤12 字、候选唯一，'
                '同名多家时优先「医院类」）。\n')
        f.write('不使用相似度兜底：实测「北京朝阳医院↔北京医院」相似度 0.80、'
                '「北京安贞医院↔北京安达医院」0.83，会张冠李戴。\n')
        f.write('名含「门诊部/分院/院区」的条目不做包含式匹配，避免把院内门诊部认成主院。\n\n')
        f.write('## 二、回写结果\n\n')
        f.write('- 新增在线核实值：**%d 家**\n' % len(applied))
        f.write('- 跳过（已有百科核实值，不覆盖）：%d 家\n' % len(skipped_have))
        f.write('- 来源标注：%s\n\n' % ' / '.join('%s %d' % kv for kv in sorted(by_src.items())))
        f.write('按机构类型分布：\n\n')
        for k, v in sorted(by_cat.items(), key=lambda x: -x[1]):
            f.write('- %s：%d 家\n' % (k, v))
        f.write('\n## 三、未匹配 %d 家（保持原状）\n\n' % len(miss))
        f.write('多为口腔门诊部 / 诊所 / 美容医院等主表未收录的机构。前 40 条：\n\n')
        for m in miss[:40]:
            f.write('- %s\n' % m)
        f.write('\n## 四、歧义 %d 条（未回写，待人工确认）\n\n' % len(ambiguity))
        for n, ts_ in ambiguity:
            f.write('- %s → 候选：%s\n' % (n, ' / '.join(ts_)))
    print('  报告 → %s' % REPORT)


if __name__ == '__main__':
    main()
