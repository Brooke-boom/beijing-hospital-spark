# -*- coding: utf-8 -*-
"""科室数量在线核实合并（幂等）：
baike_deptcount.jsonl（百科「主要科室/科室设置」章节）→ 主表新列
  dept_count_online  在线核实科室数（claims 官网口径优先，否则科室表计数）
  dept_count_src     来源标注：baike_claim（官网口径转述）/ baike_table（词条科室表计数）
覆盖策略：在线值非空即覆盖（报告列出变小案例人工复核）；无在线值保持源口径。
产出：data/processed/govern_report_deptcount_online.md
"""
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict

sys.path.insert(0, 'etl')
from build_specialty_online import ALIAS, norm  # noqa: E402  复用别名归一（import 副作用安全：有 __main__ 保护）

MASTER = 'data/processed/master_institutions.csv'
JSONL = 'data/processed/baike_deptcount.jsonl'
REPORT = 'data/processed/govern_report_deptcount_online.md'


def main():
    rows = list(csv.DictReader(open(MASTER, encoding='utf-8-sig')))
    # 源口径 dept_count 基准：取最近一次构建的快照（与 MySQL ads_inst_search 一致）
    old_by_id = {}
    try:
        snap = json.load(open('web/snapshot_data.json', encoding='utf-8'))
        old_by_id = {r['id']: (r.get('dept_count') or 0) for r in snap['institutions']}
    except Exception as e:
        print('⚠️ 快照读取失败，源口径对比将按 0 处理：', e)
    by_name = {r['name']: r for r in rows}
    by_norm = {}
    for r in rows:
        by_norm.setdefault(norm(r['name']), r)

    # 本脚本专属别名（词条名 → 主表名），不改公共 ALIAS
    EXTRA_ALIAS = {
        '中国人民解放军总医院': '中国人民解放军总医院(301医院)',
        '北京市延庆区医院': '北京市延庆区医院（北京大学第三医院延庆医院）',
        '北京市中关村医院': '北京市中关村医院（中国科学院中关村医院）',
    }

    def resolve(name):
        n = EXTRA_ALIAS.get(name.strip(), ALIAS.get(name.strip(), name.strip()))
        return by_name.get(n) or by_norm.get(norm(n))

    recs = [json.loads(l) for l in open(JSONL, encoding='utf-8')]
    upd, unmatched, smaller = {}, [], []
    hit_claim = hit_table = 0
    for rec in recs:
        if not rec.get('found'):
            continue
        claims = rec.get('claims') or []
        online, src = None, None
        if claims:
            online = max(c['n'] for c in claims)
            src = 'baike_claim'
        elif rec.get('table_count'):
            online = int(rec['table_count'])
            src = 'baike_table'
        if not online:
            continue
        r = resolve(rec['query'])
        if not r:
            unmatched.append(rec['query'])
            continue
        old_n = int(old_by_id.get(r['id']) or 0)
        if online == old_n:
            continue
        # 同一机构多词条（主名+分院区变体）时取更大值
        if r['id'] in upd and upd[r['id']]['n'] >= online:
            continue
        if online < old_n:
            smaller.append((r['name'], old_n, online, src))
        upd[r['id']] = {'n': online, 'src': src}
        if src == 'baike_claim':
            hit_claim += 1
        else:
            hit_table += 1

    # 写回主表（新增两列，幂等）
    hdr = list(rows[0].keys())
    for c in ('dept_count_online', 'dept_count_src'):
        if c not in hdr:
            hdr.append(c)
    for r in rows:
        u = upd.get(r['id'])
        r['dept_count_online'] = str(u['n']) if u else ''
        r['dept_count_src'] = u['src'] if u else ''
    with open(MASTER, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        w.writerows(rows)

        bigger = sum(1 for r in rows if r.get('dept_count_online'))
        with open(REPORT, 'w', encoding='utf-8') as f:
            f.write('# 科室数量在线核实报告（百度百科「主要科室/科室设置」，官网口径转述优先）\n\n')
            f.write('- 抓取词条 %d，成功解析在线值 %d（声明口径 %d + 科室表计数 %d）\n' %
                    (len(recs), len(upd), hit_claim, hit_table))
            f.write('- 主表新增列：dept_count_online / dept_count_src；ADS 层 dept_count = COALESCE(online, 源条目数)\n')
            f.write('- 未匹配词条 %d 个：%s\n\n' % (len(unmatched), unmatched[:20]))
            f.write('## 覆盖后变小的案例（人工复核）\n\n')
            f.write('| 医院 | 源口径 | 在线核实 | 来源 |\n|---|---|---|---|\n')
            for n, o, v, s in sorted(smaller, key=lambda x: x[1] - x[2])[:40]:
                f.write('| %s | %d | %d | %s |\n' % (n, o, v, s))
            f.write('\n## 头部机构对照（top 修正幅度）\n\n| 医院 | 源口径 | 在线核实 | 来源 |\n|---|---|---|---|\n')
            delta = []
            for r in rows:
                if r.get('dept_count_online'):
                    old_n = int(old_by_id.get(r['id']) or 0)
                    delta.append((int(r['dept_count_online']) - old_n, r['name'], old_n,
                                  r['dept_count_online'], r['dept_count_src']))
            for d, n, o, v, s in sorted(delta, reverse=True)[:30]:
                f.write('| %s | %d | %s | %s |\n' % (n, o, v, s))
    print('updated=%d (claim=%d table=%d) unmatched=%d smaller=%d' %
          (len(upd), hit_claim, hit_table, len(unmatched), len(smaller)))


if __name__ == '__main__':
    main()
