# -*- coding: utf-8 -*-
"""联网采集北京市头部医院权威床位，按 id 精确回填主表。
数据来源：卫健委直属医院规模排名(今日头条/多源交叉)、医院官网、百度百科。
产出：
  /tmp/beds_audit.csv   回填审计记录
  data/processed/master_institutions.csv  更新后主表
  data/processed/backup/before_beds_online.csv  备份
用法: python etl/enrich_beds_online.py
"""
import os, csv, shutil

ROOT = os.path.expanduser('~/Desktop/毕设/data')
MASTER = os.path.join(ROOT, 'processed', 'master_institutions.csv')
BACKUP = os.path.join(ROOT, 'processed', 'backup', 'before_beds_online.csv')
os.makedirs(os.path.dirname(BACKUP), exist_ok=True)

# --------------------------------------------------------- 权威床位表（id -> (床位, 来源, 口径)）
# 综合医院（全院/编制床位口径，多源交叉）
BEDS = {
    1150: (2000,  '卫生健康委直属医院规模排名', '开放床位'),   # 中国医学科学院北京协和医院
    1151: (2000,  '卫生健康委直属医院规模排名', '开放床位'),   # 协和（东院区）
    1547: (2000,  '卫生健康委直属医院规模排名', '开放床位'),   # 协和（西院区）
    1476: (10000, '解放军总医院规模盘点',       '全院开放床位'),  # 中国人民解放军总医院(301)
    1498: (2300,  '卫生健康委直属医院规模排名', '开放床位'),   # 北京大学第三医院
    1499: (2300,  '卫生健康委直属医院规模排名', '开放床位'),   # 北医三院、北大第三临床医学院
    1595: (3306,  '北京友谊医院三院区编制',     '全院编制床位'),  # 首都医科大学附属北京友谊医院
    1559: (2500,  '北京大学人民医院开放床位',   '全员开放床位'),  # 北京大学人民医院
    1560: (2500,  '北京大学人民医院开放床位',   '全员开放床位'),  # 北大人民医院（北大第二临床医学院）
    1561: (2259,  '北京大学第一医院开放床位',   '全院开放床位'),  # 北京大学第一医院
    1562: (2259,  '北京大学第一医院开放床位',   '全院开放床位'),  # 北大第一医院(北大医院)
    1587: (2203,  '北京积水潭医院三院区床位',   '全院床位'),   # 北京积水潭医院
    1588: (2203,  '北京积水潭医院三院区床位',   '全院床位'),   # 积水潭（北大第四临床医学院）
    1475: (2500,  '北京朝阳医院三院区编制',     '全院编制床位'),  # 首都医科大学附属北京朝阳医院
    1542: (2500,  '北京朝阳医院三院区编制',     '全院编制床位'),  # 朝阳（西院区）
    1178: (1500,  '北京同仁医院床位',          '全院床位'),    # 首都医科大学附属北京同仁医院
    1179: (1500,  '北京同仁医院床位',          '全院床位'),    # 同仁（东院区）
    1281: (1500,  '北京同仁医院床位',          '全院床位'),    # 同仁(南区)
    1282: (1500,  '北京同仁医院床位',          '全院床位'),    # 同仁（南院区）
    1245: (1500,  '北京天坛医院床位',          '全院床位'),    # 首都医科大学附属北京天坛医院
    1474: (2200,  '北京安贞医院两院区编制',     '全院编制床位'),  # 首都医科大学附属北京安贞医院
    1403: (2100,  '中日友好医院官网',          '开放床位'),    # 中日友好医院
    1401: (2200,  '中国医学科学院肿瘤医院开放',  '全院开放床位'),  # 中国医学科学院肿瘤医院
    1548: (1403,  '中国医学科学院阜外医院',     '开放床位'),    # 中国医学科学院阜外医院
    1549: (1403,  '中国医学科学院阜外医院',     '开放床位'),    # 阜外心血管病医院
    1152: (1328,  '北京医院(国家老年医学中心)', '床位规模'),    # 北京医院
    1527: (1100,  '北京世纪坛医院编制',        '全院编制床位'),  # 首都医科大学附属北京世纪坛医院
    1528: (1100,  '北京世纪坛医院编制',        '全院编制床位'),  # 世纪坛（北京铁路总医院）
    1529: (1100,  '北京世纪坛医院编制',        '全院编制床位'),  # 世纪坛（社区）
    1351: (1369,  '北京回龙观医院编制',        '全院编制床位'),  # 北京回龙观医院
    1352: (1369,  '北京回龙观医院编制',        '全院编制床位'),  # 回龙观（精神病专科）
    1614: (1042,  '北京潞河医院开放床位',      '全院开放床位'),  # 首都医科大学附属北京潞河医院
    1592: (1643,  '首都医科大学宣武医院官网',   '全院开放床位'),  # 首都医科大学宣武医院
    # 专科医院
    1180: (660,   '北京妇产医院官网/百科',     '全院编制床位'),  # 首都医科大学附属北京妇产医院
    1553: (970,   '北京儿童医院官网床位表',     '全院编制床位'),  # 北京儿童医院
    1593: (970,   '北京儿童医院官网床位表',     '全院编制床位'),  # 首都医科大学附属北京儿童医院
    1594: (970,   '北京儿童医院官网床位表',     '全院编制床位'),  # 儿童医院(北京市儿科研究所)
    1624: (200,   '顺义区床位文件',           '院区床位'),     # 北京儿童医院顺义院区（保留）
}

# 读取主表
shutil.copy2(MASTER, BACKUP)
with open(MASTER, encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
fieldnames = list(rows[0].keys())

# 回填
audit = []
updated = 0
new_filled = 0
for r in rows:
    rid = r['id'].strip()
    key = int(rid) if rid.isdigit() else -1
    if key in BEDS:
        bed, src, calibre = BEDS[key]
        old = r.get('beds', '').strip()
        if not old or old == '0':
            action = '新增'
            new_filled += 1
        else:
            action = '更新'
            updated += 1
        r['beds'] = str(int(bed))
        audit.append(dict(id=rid, name=r['name'][:32], old=old, new=str(int(bed)),
                          src=src, calibre=calibre, action=action,
                          district=r.get('district', ''), level=r.get('level', '')))

# 写回主表
with open(MASTER, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)

# 审计输出
with open('/tmp/beds_audit.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'name', 'old', 'new', 'src', 'calibre', 'action', 'district', 'level'])
    w.writeheader()
    w.writerows(audit)

print(f'回填完成：共 {len(audit)} 家医院，其中 新增 {new_filled} 家 / 更新 {updated} 家')
print('\n=== 回填明细（按目标床位降序） ===')
for a in sorted(audit, key=lambda x: -int(x['new'])):
    print(f"  {a['action']:2s} {a['name'][:30]:30s} {a['old']:>6s}→{a['new']:>5s}  {a['calibre']}  [{a['src']}]")
print('\n备份:', BACKUP)
print('审计:', '/tmp/beds_audit.csv')
