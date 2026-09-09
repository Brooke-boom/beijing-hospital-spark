# -*- coding: utf-8 -*-
"""第一批联网核实等级修正（2026-09-09）。
依据：北京市医保A类定点医疗机构名单(2023) + 北京市卫健委互联网医院名单(2022)。
修正 3 家明确冲突：
  1193 北京丰台医院          二级 -> 三级   (A类名单明确三级)
  1534 北京市石景山医院      三级 -> 二级   (A类名单明确二级，纠正 09-04 旧网验错误)
  1488 北京三诺健恒糖尿病医院 二级 -> 一级   (互联网医院名单明确一级)
"""
import csv, shutil, datetime, pymysql, os

BASE = os.path.expanduser("~/Desktop/毕设")
MASTER = os.path.join(BASE, 'data/processed/master_institutions.csv')
WIDE = os.path.join(BASE, 'data/processed/hospital_wide.csv')
NET = os.path.join(BASE, 'data/processed/enrichment/net/apply_net_level.csv')

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
fixes = {
    '1193': ('三级', '', '北京医保A类定点医疗机构名单(2023)明确为三级'),
    '1534': ('二级', '', '北京医保A类定点医疗机构名单(2023)明确为二级，纠正09-04旧网验结论'),
    '1488': ('一级', '', '北京市卫健委互联网医院名单(2022)明确为一级'),
}

def apply_csv(path, ts):
    rows = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    fn = list(rows[0].keys())
    bak = path + '.' + ts + '.bak'
    shutil.copy2(path, bak)
    n = 0
    for r in rows:
        if r['id'] in fixes:
            nl, ns, _ = fixes[r['id']]
            if r['level'] != nl or r.get('level_sub', '') != ns:
                r['level'] = nl
                r['level_sub'] = ns
                n += 1
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fn)
        w.writeheader(); w.writerows(rows)
    return n, bak

n1, b1 = apply_csv(MASTER, ts)
n2, b2 = apply_csv(WIDE, ts)
print(f'master 修正 {n1} 行 (备份 {b1})')
print(f'wide   修正 {n2} 行 (备份 {b2})')

# MySQL
conn = pymysql.connect(host='127.0.0.1', port=3307, user='root', password='hospital123',
                       database='hospital', charset='utf-8')
cur = conn.cursor()
for i, (lv, sub, _) in fixes.items():
    cur.execute('UPDATE ads_inst_search SET level_norm=%s WHERE id=%s', (lv, i))
    print(f'MySQL ads_inst_search id={i} -> {lv}  affected={cur.rowcount}')
conn.commit(); conn.close()

# 修正网验审计文件 1534 的旧结论（二级->三级 改为 三级->二级）
if os.path.exists(NET):
    rows = list(csv.DictReader(open(NET, encoding='utf-8-sig')))
    fn = list(rows[0].keys())
    for r in rows:
        if r['id'] == '1534':
            r['new_level'] = '二级'
            r['old_level'] = '三级'
            r['action'] = 'downgrade'
            r['basis'] = '北京医保A类定点医疗机构名单(2023)明确为二级，纠正09-04旧网验结论'
    with open(NET, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fn); w.writeheader(); w.writerows(rows)
    print('已修正网验审计文件 apply_net_level.csv 中 1534 结论')

print('第一批等级修正完成')
