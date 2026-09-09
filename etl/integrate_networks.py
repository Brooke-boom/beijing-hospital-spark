# -*- coding: utf-8 -*-
# 医疗协作网络整合：儿科医联体 / 卒中中心 / 危重新生儿救治 / 危重孕产妇救治
# 给 master_institutions.csv + hospital_wide.csv + MySQL(ads_inst_search) 增加 4 个网络字段
import csv, os, re, sys, pymysql
from networks_data import (PEDIATRIC_CORE, PEDIATRIC_MEMBER, STROKE,
                           NEONATAL_CITY, MATERNAL_CITY)

BASE = "/Users/brooke/Desktop/毕设"
MASTER = os.path.join(BASE, "data/processed/master_institutions.csv")
WIDE   = os.path.join(BASE, "data/processed/hospital_wide.csv")

# ---------- 自动匹配器 ----------
def norm(s):
    s = re.sub(r'[（(].*?[)）]', '', str(s))
    return re.sub(r'\s+', '', s)
REJECT = ['体检','社区','分院','院区','干部','亦庄','回龙观','南区','西院','东院','门诊部']
PREFIX_OK = ['首都医科大学附属','首都医科大学','中国医学科学院','中国中医科学院','北京大学',
             '北京','附属','清华大学附属','清华大学','北京清华','北京市','中国人民解放军',
             '解放军','陆军','海军','空军','武警','北京首都']
EXTRA_OK = ['研究所','儿科研究所','铁路总医院','京中医疗区','北区','南部','西部','中心',
            '总','第一','第二','第三','儿童','妇女','妇幼']

def match_method(O, Mname):
    nO, nM = norm(O), norm(Mname)
    if nO == nM: return 'exact'
    if nO in nM:
        extra = re.sub(r'[（）()\s]', '', nM.replace(nO, ''))
        if len(nO)/len(nM) >= 0.5 and (extra == '' or extra in EXTRA_OK or any(extra.startswith(p) for p in PREFIX_OK)):
            return 'contain'
    if nM in nO:
        extra = re.sub(r'[（）()\s]', '', nO.replace(nM, ''))
        if len(nM)/len(nO) >= 0.5 and (extra == '' or extra in EXTRA_OK or any(extra.startswith(p) for p in PREFIX_OK)):
            return 'contain'
    return None

def branch_guard(mname, oname):
    for mk in REJECT:
        if mk in mname and mk not in oname:
            return False
    return True

# ---------- 手动别名映射（自动匹配无法覆盖的同名/异名机构）----------
MANUAL = {
    "复兴医院": ["1597"],
    "海淀区妇幼保健院": ["3937"],
    "北京首儿窦店儿童医院": [],          # 主表无此机构（私立，不在9789范围内），如实跳过
    "首都医科大学附属北京积水潭医院": ["1587","1588"],
    "怀柔区医院": ["1311"],
    "丰台区妇幼保健院": ["1653"],
    "门头沟妇幼保健院": ["1675"],
    "煤炭总医院": ["1469"],              # 应急管理部应急总医院(原煤炭总医院)
    "中国中医研究院西苑医院": ["155","156"],
    "中国武警总医院": ["1479"],
    "北京世纪坛医院": ["1527","1528","1529"],
    "北京电力医院": ["1241"],
    "北京丰台区南苑医院": ["1220"],
    "中国人民解放军陆军总医院二六三临床部": ["1598"],
    "解放军总医院第五医学中心": ["1181"],
    "解放军总医院第七医学中心": ["1148"],
}

# ---------- 构建 官方名 -> [master_id] ----------
rows = list(csv.DictReader(open(MASTER, encoding='utf-8-sig')))
idmap = {r['id']: r for r in rows}

def resolve(names):
    out = {}
    for O in names:
        ids = MANUAL.get(O)
        if ids is None:
            ids = [r['id'] for r in rows if match_method(O, r['name']) and branch_guard(r['name'], O)]
        out[O] = ids
    return out

ped_core_map = resolve(PEDIATRIC_CORE)
ped_mem_map  = resolve(PEDIATRIC_MEMBER)
stroke_map   = resolve(STROKE)
neo_map      = resolve(NEONATAL_CITY)
mat_map      = resolve(MATERNAL_CITY)

# ---------- 聚合到每个 id 的网络标签 ----------
tag = {r['id']: {'net_pediatric':'','net_stroke':'','net_neonatal':'','net_maternal':''} for r in rows}
def apply(mapdict, field, value):
    for O, ids in mapdict.items():
        for i in ids:
            if i in tag:
                tag[i][field] = value
apply(ped_core_map, 'net_pediatric', '核心')
apply(ped_mem_map,  'net_pediatric', '成员')   # 若同机构既是核心又是成员，成员覆盖（成员不应盖核心）
# 修正：核心优先
for O, ids in ped_core_map.items():
    for i in ids:
        if i in tag: tag[i]['net_pediatric'] = '核心'
apply(stroke_map, 'net_stroke', '1')
apply(neo_map,    'net_neonatal', '市级')
apply(mat_map,    'net_maternal', '市级')

# ---------- 写回 master & wide ----------
def write_csv(path, newcols):
    r = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    cols = list(r[0].keys())
    for c in newcols:
        if c not in cols: cols.append(c)
    for row in r:
        t = tag.get(row['id'])
        for c in newcols:
            row[c] = t[c] if t else ''
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(r)
    return len(r)
n1 = write_csv(MASTER, ['net_pediatric','net_stroke','net_neonatal','net_maternal'])
n2 = write_csv(WIDE,   ['net_pediatric','net_stroke','net_neonatal','net_maternal'])
print("master 写入行:", n1, "| wide 写入行:", n2)

# ---------- 汇总 ----------
def count(field, val): return sum(1 for t in tag.values() if t[field]==val)
print("\n=== 整合结果统计 ===")
print("儿科医联体 核心:", count('net_pediatric','核心'), "| 成员:", count('net_pediatric','成员'),
      "| 合计:", count('net_pediatric','核心')+count('net_pediatric','成员'))
print("卒中中心:", count('net_stroke','1'))
print("危重新生儿救治(市级):", count('net_neonatal','市级'))
print("危重孕产妇救治(市级):", count('net_maternal','市级'))

# 未匹配报告
def unmatched(mapdict, label):
    miss = [O for O,ids in mapdict.items() if not ids]
    if miss: print(f"  [注意] {label} 未匹配: {miss}")
unmatched(ped_core_map, "儿科核心"); unmatched(ped_mem_map, "儿科成员")
unmatched(stroke_map, "卒中"); unmatched(neo_map, "新生儿"); unmatched(mat_map, "孕产妇")

# ---------- 落 MySQL ----------
try:
    conn = pymysql.connect(host='127.0.0.1', port=3307, user='root',
                          password='hospital123', database='hospital', charset='utf8mb4')
    cur = conn.cursor()
    for col in ['net_pediatric','net_stroke','net_neonatal','net_maternal']:
        cur.execute(f"SELECT COUNT(*) FROM information_schema.columns "
                    f"WHERE table_schema='hospital' AND table_name='ads_inst_search' AND column_name='{col}'")
        if cur.fetchone()[0] == 0:
            cur.execute(f"ALTER TABLE ads_inst_search ADD COLUMN {col} VARCHAR(20) DEFAULT ''")
            print(f"MySQL 新增列 {col}")
    cur.execute("UPDATE ads_inst_search SET net_pediatric='',net_stroke='',net_neonatal='',net_maternal=''")
    nup=0
    for i, t in tag.items():
        if any(t[c] for c in ['net_pediatric','net_stroke','net_neonatal','net_maternal']):
            cur.execute("UPDATE ads_inst_search SET net_pediatric=%s,net_stroke=%s,net_neonatal=%s,net_maternal=%s WHERE id=%s",
                        (t['net_pediatric'],t['net_stroke'],t['net_neonatal'],t['net_maternal'],i))
            nup+=1
    conn.commit(); conn.close()
    print("MySQL 更新行:", nup)
except Exception as e:
    print("MySQL 更新失败(稍后手动):", e)
