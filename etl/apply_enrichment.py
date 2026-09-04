# -*- coding: utf-8 -*-
"""将高置信证据应用到 master_institutions.csv（并同步 hospital_wide.csv 两列，保持展示一致）。
策略:
  A. level_suggest 中 action=apply 且 (旧空 或 新旧level不同)  -> 补/改 level
     - 若 new_sub 为空且旧有 sub，保留旧 sub（不误删等次）
  B. bed_suggest 全部 -> 只填当前 beds 为空的行
  C. 纯等次补全(150) 与冲突/无证据 一律不动，留 review
备份: data/归档_旧版命名/processed_backup/master_institutions_<ts>.csv
审计: data/processed/enrichment/apply_log_<ts>.csv
用法: python apply_enrichment.py
"""
import os, sys, csv, shutil, datetime, collections

BASE = os.path.expanduser("~/Desktop/毕设")
MASTER = os.path.join(BASE, 'data/processed/master_institutions.csv')
WIDE = os.path.join(BASE, 'data/processed/hospital_wide.csv')
BAKDIR = os.path.join(BASE, 'data/归档_旧版命名/processed_backup')
AUDIT_DIR = os.path.join(BASE, 'data/processed/enrichment')
SRC = '/tmp/enrich'
ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
os.makedirs(BAKDIR, exist_ok=True)
os.makedirs(AUDIT_DIR, exist_ok=True)

with open(MASTER, encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
fn = list(rows[0].keys())

lv_sugg = list(csv.DictReader(open(os.path.join(SRC, 'level_suggest.csv'), encoding='utf-8-sig')))
bed_sugg = list(csv.DictReader(open(os.path.join(SRC, 'bed_suggest.csv'), encoding='utf-8-sig')))

# 目标集合
apply_lv = [r for r in lv_sugg if r['action'] == 'apply' and (not r['old_level'] or r['old_level'] != r['new_level'])]
by_id = {r['id']: r for r in rows}
audit = []
n_lv = n_bed = 0

for s in apply_lv:
    r = by_id.get(s['id'])
    if r is None:
        continue
    new_sub = s['new_sub']
    if not new_sub and r.get('level_sub'):
        new_sub = r['level_sub']  # 保留原等次
    if r['level'] != s['new_level'] or (new_sub and r['level_sub'] != new_sub):
        audit.append(dict(id=r['id'], name=r['name'], field='level',
                          old=f"{r['level']}{r['level_sub']}", new=f"{s['new_level']}{new_sub}",
                          src=s['srcs'][:200]))
        r['level'] = s['new_level']
        r['level_sub'] = new_sub
        n_lv += 1

for s in bed_sugg:
    r = by_id.get(s['id'])
    if r is None:
        continue
    if not (r.get('beds') or '').strip() or float(r['beds']) <= 0:
        audit.append(dict(id=r['id'], name=r['name'], field='beds',
                          old=r['beds'], new=str(int(float(s['new_beds']))), src=s['src']))
        r['beds'] = str(int(float(s['new_beds'])))
        n_bed += 1

# 备份 + 写回 master
shutil.copy2(MASTER, os.path.join(BAKDIR, 'master_institutions_' + ts + '.csv'))
with open(MASTER, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=fn)
    w.writeheader(); w.writerows(rows)

# 同步 wide 两列（仅改这些行，避免重跑 merge 前页面/分析暂时一致）
if os.path.exists(WIDE):
    with open(WIDE, encoding='utf-8-sig') as f:
        wrows = list(csv.DictReader(f))
    wfn = list(wrows[0].keys())
    wby = {r['id']: r for r in wrows}
    for a in audit:
        if a['id'] in wby:
            wby[a['id']]['level'] = by_id[a['id']]['level']
            wby[a['id']]['level_sub'] = by_id[a['id']]['level_sub']
            if a['field'] == 'beds':
                wby[a['id']]['beds'] = by_id[a['id']]['beds']
    with open(WIDE, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=wfn)
        w.writeheader(); w.writerows(wrows)

# 审计
with open(os.path.join(AUDIT_DIR, 'apply_log_' + ts + '.csv'), 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'name', 'field', 'old', 'new', 'src'])
    w.writeheader(); w.writerows(audit)

print(f'已应用: 等级变更 {n_lv} 条, 床位回填 {n_bed} 条')
print('备份:', os.path.join(BAKDIR, 'master_institutions_' + ts + '.csv'))
print('审计:', os.path.join(AUDIT_DIR, 'apply_log_' + ts + '.csv'))
# 汇总
import collections
with open(MASTER, encoding='utf-8-sig') as f:
    rows2 = list(csv.DictReader(f))
hosp = [r for r in rows2 if r['category'] in ('医院', '中医医院', '妇幼保健院')]
print('医院类有等级:', sum(1 for r in hosp if (r['level'] or '').strip()), '/', len(hosp))
print('床位有值:', sum(1 for r in rows2 if (r.get('beds') or '').strip() and float(r['beds']) > 0))
