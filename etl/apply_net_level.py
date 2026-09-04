# -*- coding: utf-8 -*-
"""将联网核验的高置信等级结论(apply_net_level.csv)写回 master_institutions.csv，
并同步 hospital_wide.csv 的 level/level_sub 列，保持展示一致。

与 apply_enrichment.py 的区别: 本脚本来自联网逐家核验(grade_A1/B/C1/C2)，
new_level/new_sub 为核验后的确定值，直接覆盖(不保留旧等次，避免"三级+旧合格"式错配)。

策略:
  - 仅处理 action in (fill, upgrade) 的行
  - new_level 非空 -> 覆盖 level; 同时覆盖 level_sub (可能为空)
  - 备份: data/归档_旧版命名/processed_backup/master_institutions_<ts>.csv
  - 审计: data/processed/enrichment/apply_net_log_<ts>.csv

用法: python apply_net_level.py
"""
import os, csv, shutil, datetime

BASE = os.path.expanduser("~/Desktop/毕设")
MASTER = os.path.join(BASE, 'data/processed/master_institutions.csv')
WIDE = os.path.join(BASE, 'data/processed/hospital_wide.csv')
BAKDIR = os.path.join(BASE, 'data/归档_旧版命名/processed_backup')
SRC = os.path.join(BASE, 'data/processed/enrichment/net/apply_net_level.csv')
AUDIT_DIR = os.path.join(BASE, 'data/processed/enrichment')
ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
os.makedirs(BAKDIR, exist_ok=True)
os.makedirs(AUDIT_DIR, exist_ok=True)

with open(MASTER, encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
fn = list(rows[0].keys())

sugg = [r for r in csv.DictReader(open(SRC, encoding='utf-8-sig')) if r['action'] in ('fill', 'upgrade')]
by_id = {r['id']: r for r in rows}
audit = []
n = 0
for s in sugg:
    r = by_id.get(s['id'])
    if r is None:
        continue
    new_level = (s['new_level'] or '').strip()
    new_sub = (s['new_sub'] or '').strip()
    if not new_level:
        continue
    old = f"{r['level'] or ''}{r['level_sub'] or ''}"
    new = new_level + new_sub
    if old == new:
        continue
    audit.append(dict(id=r['id'], name=r['name'], field='level',
                      old=old, new=new, src=('联网核验:' + (s['basis'] or '')[:100])))
    r['level'] = new_level
    r['level_sub'] = new_sub
    n += 1

# 备份 + 写回 master
shutil.copy2(MASTER, os.path.join(BAKDIR, 'master_institutions_' + ts + '.csv'))
with open(MASTER, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=fn)
    w.writeheader()
    w.writerows(rows)

# 同步 wide level/level_sub
if os.path.exists(WIDE):
    with open(WIDE, encoding='utf-8-sig') as f:
        wrows = list(csv.DictReader(f))
    wfn = list(wrows[0].keys())
    wby = {r['id']: r for r in wrows}
    for a in audit:
        if a['id'] in wby:
            wby[a['id']]['level'] = by_id[a['id']]['level']
            wby[a['id']]['level_sub'] = by_id[a['id']]['level_sub']
    with open(WIDE, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=wfn)
        w.writeheader()
        w.writerows(wrows)

# 审计
with open(os.path.join(AUDIT_DIR, 'apply_net_log_' + ts + '.csv'), 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'name', 'field', 'old', 'new', 'src'])
    w.writeheader()
    w.writerows(audit)

print(f'已应用联网等级变更 {n} 条')
print('备份:', os.path.join(BAKDIR, 'master_institutions_' + ts + '.csv'))
print('审计:', os.path.join(AUDIT_DIR, 'apply_net_log_' + ts + '.csv'))

import collections
with open(MASTER, encoding='utf-8-sig') as f:
    rows2 = list(csv.DictReader(f))
hosp = [r for r in rows2 if r['category'] in ('医院', '中医医院', '妇幼保健院')]
print('医院类有等级:', sum(1 for r in hosp if (r['level'] or '').strip()), '/', len(hosp))
