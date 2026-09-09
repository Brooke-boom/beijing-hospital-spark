#!/usr/bin/env python3
# 第三批等级修正：七三一医院重复记录 1185 二级->三级（与 A类2026 一致）
import csv, os, pymysql, io

MASTER = 'data/processed/master_institutions.csv'
WIDE = 'data/processed/hospital_wide.csv'

def fix_csv(path, idcol, lvcol, fixes):
    rows = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    cols = rows[0].keys()
    n = 0
    for r in rows:
        if r[idcol] in fixes:
            r[lvcol] = fixes[r[idcol]]
            n += 1
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return n

fixes = {'1185': '三级'}
n1 = fix_csv(MASTER, 'id', 'level', fixes)
n2 = fix_csv(WIDE, 'id', 'level', fixes)
print('master 修正行:', n1, '| wide 修正行:', n2)

# MySQL
try:
    conn = pymysql.connect(host='127.0.0.1', port=3307, user='root',
                          password='hospital123', database='hospital', charset='utf8mb4')
    cur = conn.cursor()
    cur.execute('UPDATE ads_inst_search SET level_norm=%s WHERE id=%s', ('三级', '1185'))
    print('MySQL 1185 -> 三级 affected=', cur.rowcount)
    conn.commit(); conn.close()
except Exception as e:
    print('MySQL 更新失败(可稍后手动):', e)
