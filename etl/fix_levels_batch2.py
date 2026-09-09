# -*- coding: utf-8 -*-
"""第二批联网核实等级修正（2026-09-09）。
权威基准：北京市医保 A 类定点医疗机构名单（2026-08-08 更新，北京市医保局发布）。
该名单 59 家医院中 57 家为三级。据此：

1) 回滚第一批误判：1534 北京市石景山医院 —— A类(2026)明确三级，第一批据旧版误降为二级，本次纠正回三级。
2) 升级 8 家：系统与 A类(2026)冲突、系统偏低（二级/一级）且确为该医院本体（非社区站/诊所分支）：
   1165 北京市第六医院        二级->三级
   1163 北京市普仁医院        二级->三级
   1164 北京市普仁医院(四院)  二级->三级
   1258 北京市仁和医院        二级->三级
   1566 北京市健宫医院        二级->三级
   1504 北京市中关村医院      二级->三级
   3936 北京市中关村医院(社区) 二级->三级
   1313 朝阳医院怀柔医院      二级->三级

注：系统=三级但官方单源/旧源建议更低者（1421和睦家、1186七三一、1526三博脑科）
暂不改，留待用户确认更权威来源。
"""
import csv, shutil, datetime, pymysql, os

BASE = os.path.expanduser("~/Desktop/毕设")
MASTER = os.path.join(BASE, 'data/processed/master_institutions.csv')
WIDE = os.path.join(BASE, 'data/processed/hospital_wide.csv')
NET = os.path.join(BASE, 'data/processed/enrichment/net/apply_net_level.csv')

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
BASIS = '北京市医保A类定点医疗机构名单(2026-08-08)明确为三级'
fixes = {
    '1534': ('三级', '', 'A类定点名单(2026-08-08)明确三级，纠正第一批据旧版误降为二级'),
    '1165': ('三级', '', BASIS),
    '1163': ('三级', '', BASIS),
    '1164': ('三级', '', BASIS),
    '1258': ('三级', '', BASIS),
    '1566': ('三级', '', BASIS),
    '1504': ('三级', '', BASIS),
    '3936': ('三级', '', BASIS),
    '1313': ('三级', '', BASIS),
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
        w = csv.DictWriter(f, fieldnames=fn); w.writeheader(); w.writerows(rows)
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
    print(f'MySQL id={i} -> {lv}  affected={cur.rowcount}')
conn.commit(); conn.close()

# 更新网验审计文件 apply_net_level.csv
if os.path.exists(NET):
    rows = list(csv.DictReader(open(NET, encoding='utf-8-sig')))
    fn = list(rows[0].keys())
    have = {r['id'] for r in rows}
    for r in rows:
        if r['id'] == '1534':
            r['old_level'] = r.get('old_level') or '二级'
            r['new_level'] = '三级'
            r['action'] = 'upgrade'
            r['basis'] = 'A类定点名单(2026-08-08)明确三级，纠正第一批据旧版误降'
    for i, (lv, _, basis) in fixes.items():
        if i == '1534':
            continue
        if i not in have:
            rows.append({'id': i, 'name': '', 'district': '', 'old_level': '二级',
                         'old_sub': '', 'new_level': lv, 'new_sub': '',
                         'is_hospital': '是', 'action': 'upgrade', 'basis': basis})
    with open(NET, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fn); w.writeheader(); w.writerows(rows)
    print(f'已更新网验审计文件 apply_net_level.csv（含 1534 回滚 + {len(fixes)-1} 家升级）')

print('第二批等级修正完成')
