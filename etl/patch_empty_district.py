# -*- coding: utf-8 -*-
"""P0 治理：自动补 master_institutions.csv 中空 district 字段
- 输入: data/processed/master_institutions.csv (9,789 行)
- 输出: data/processed/master_institutions_patched.csv (新增 district 列修正后的副本)
- 不直接覆盖原文件 (原文件备份到 data/processed/backup/)
- 不可推断的 9 家写入 /tmp/uninferable_district.txt 供人工核对

用法:
    python patch_empty_district.py
"""
import csv, os, shutil

ROOT = os.path.expanduser('~/Desktop/毕设/data/processed')
MASTER = os.path.join(ROOT, 'master_institutions.csv')
BACKUP = os.path.join(ROOT, 'backup/master_institutions.before_district_patch.csv')
OUT = os.path.join(ROOT, 'master_institutions_patched.csv')
UNINFERABLE = '/tmp/uninferable_district.txt'

DISTRICTS = ['东城区','西城区','朝阳区','海淀区','丰台区','石景山区','门头沟区',
             '房山区','通州区','顺义区','昌平区','大兴区','怀柔区','平谷区','密云区','延庆区']
# 别名（崇文/宣武 是东城/西城旧称）
ALIAS = {'崇文区':'东城区','宣武区':'西城区','崇文':'东城区','宣武':'西城区'}

def infer(addr, name=''):
    text = (addr or '') + ' ' + (name or '')
    for d in DISTRICTS:
        if d in text:
            return d
    for k, v in ALIAS.items():
        if k in text:
            return v
    return ''

# 1. 备份原文件（不覆盖）
os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
if not os.path.exists(BACKUP):
    shutil.copy2(MASTER, BACKUP)
    print(f'[backup] {BACKUP}')
else:
    print(f'[backup exists, skip] {BACKUP}')

# 2. 读 + 推断 + 写
fixed = 0
uninferable_rows = []
with open(MASTER, encoding='utf-8-sig') as f, \
     open(OUT, 'w', encoding='utf-8', newline='') as fo:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    writer = csv.DictWriter(fo, fieldnames=fieldnames)
    writer.writeheader()
    for row in reader:
        if not row.get('district', '').strip():
            d = infer(row.get('addr', ''), row.get('name', ''))
            if d:
                row['district'] = d
                fixed += 1
            else:
                uninferable_rows.append({
                    'id': row.get('id', ''),
                    'name': row.get('name', ''),
                    'addr': row.get('addr', ''),
                    'category': row.get('category', ''),
                    'level': row.get('level', ''),
                })
        writer.writerow(row)

print(f'[fixed] {fixed} 行 district 已自动补全')
print(f'[uninferable] {len(uninferable_rows)} 行待人工处理 -> {UNINFERABLE}')

# 3. 输出不可推断清单
with open(UNINFERABLE, 'w', encoding='utf-8') as f:
    f.write('# 待人工补 district 的医院清单（已按归属建议标注）\n')
    f.write('# 建议判读：按地址归属至对应区\n\n')
    for r in uninferable_rows:
        f.write(f"id={r['id']:>5s} | {r['name'][:40]:40s} | addr={r['addr']} | cat={r['category']} | lvl={r['level']}\n")

print(f'[done] patched file -> {OUT}')
print(f'       backup         -> {BACKUP}')
print(f'       human review   -> {UNINFERABLE}')