#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网完善北京市/各区临床重点专科数据（区别于国家级 national_specialty）— 多源整合 → 市级增强数据集

数据源（均为联网核实/官方公开）：
  S1. 北京市卫健委 2018 年度北京市临床重点专科项目（44 项，培育/建设/卓越）
  S2. 北京市卫健委 2020 年度北京市临床重点专科项目（27 项，培育/建设/卓越）
  S3. 北京市中医管理局 首批"十四五"中医药重点专科名单（领超/示范/并超/建设/赶超/培育 共 74 项，2022/11/25 公示）

产出：
  data/processed/specialty_municipal.csv        增强版市级专科明细（每院每专科一行）
  data/processed/specialty_municipal_hospital.csv  按院汇总
  data/processed/master_institutions.csv         主表新增 municipal_specialty / municipal_specialty_count 两列
  /tmp/municipal_unmatched.txt                  未与主表匹配的医院名（人工补别名）
  data/processed/govern_report_municipal.md     治理报告

用法: python build_municipal_specialty.py
"""
import csv
import os
import re
import unicodedata
from collections import defaultdict

ROOT = '/Users/brooke/Desktop/毕设/data/processed'
MASTER = os.path.join(ROOT, 'master_institutions.csv')
OUT_DETAIL = os.path.join(ROOT, 'specialty_municipal.csv')
OUT_HOSP = os.path.join(ROOT, 'specialty_municipal_hospital.csv')
UNMATCHED = '/tmp/municipal_unmatched.txt'
REPORT = os.path.join(ROOT, 'govern_report_municipal.md')

# ============================================================ 主表
with open(MASTER, encoding='utf-8-sig') as f:
    master = list(csv.DictReader(f))
by_name = {r['name']: r for r in master}
print(f'[master] {len(master)} 家')

# ============================================================ 名称标准化 + 别名（沿用国家级版的别名表，新增本次需要的扩展）
def norm(s):
    s = unicodedata.normalize('NFKC', s or '')
    s = re.sub(r'[\s\u3000（）()]+', '', s)
    return s.lower()


# 人工确认的别名映射（北京市级常用院名 → 主表标准名）
ALIAS = {
    '北京协和医院': '中国医学科学院北京协和医院',
    '北京儿童医院': '首都医科大学附属北京儿童医院',
    '北京口腔医院': '首都医科大学附属北京口腔医院',
    '北京妇产医院': '首都医科大学附属北京妇产医院',
    '北京朝阳医院': '首都医科大学附属北京朝阳医院',
    '北京友谊医院': '首都医科大学附属北京友谊医院',
    '北京同仁医院': '首都医科大学附属北京同仁医院',
    '北京天坛医院': '首都医科大学附属北京天坛医院',
    '北京安贞医院': '首都医科大学附属北京安贞医院',
    '北京佑安医院': '首都医科大学附属北京佑安医院',
    '北京世纪坛医院': '首都医科大学附属北京世纪坛医院',
    '北京安定医院': '首都医科大学附属北京安定医院',
    '北京胸科医院': '首都医科大学附属北京胸科医院',
    '北京地坛医院': '首都医科大学附属北京地坛医院',
    '北京潞河医院': '首都医科大学附属北京潞河医院',
    '宣武医院': '首都医科大学宣武医院',
    '首都医科大学北京宣武医院': '首都医科大学宣武医院',
    '首都医科大学附属宣武医院': '首都医科大学宣武医院',
    '首都医科大学附属地坛医院': '首都医科大学附属北京地坛医院',
    '阜外心血管病医院': '中国医学科学院阜外医院',
    '中国医学科学院阜外心血管病医院': '中国医学科学院阜外医院',
    '北京肿瘤医院': '北京大学肿瘤医院',
    '北京大学肿瘤医院': '北京大学肿瘤医院',
    '解放军总医院': '中国人民解放军总医院',
    '301医院': '中国人民解放军总医院',
    '中国解放军总医院': '中国人民解放军总医院',
    '朝阳中西医结合急诊抢救中心': '北京朝阳中西医结合急诊抢救中心',
    '北京中西医结合医院': '北京中西医结合医院',
    '北京市中西医结合医院': '北京中西医结合医院',
    '北京市第一中西医结合医院': '北京市第一中西医结合医院',
    '北京中医医院': '首都医科大学附属北京中医医院',
    '首都医科大学北京中医医院': '首都医科大学附属北京中医医院',
    '北京中医医院怀柔医院': '北京中医医院怀柔医院',
    '北京中医医院延庆医院': '北京中医医院延庆医院',
    '北京中医医院顺义医院': '北京中医医院顺义医院',
    '北京中医医院平谷医院': '北京市平谷区中医医院',
    '北京市健宫医院': '北京市健宫医院',
    '北京健宫医院': '北京市健宫医院',
    '北京市西城区丰盛骨伤专科医院': '北京市丰盛中医骨伤专科医院',
    '北京市西城区丰盛医院': '北京市丰盛中医骨伤专科医院',
    '北京市隆福医院': '北京市隆福医院',
    '北京市大兴区人民医院': '北京市大兴区人民医院',
    '北京市平谷区医院': '北京市平谷区医院',
    '北京市平谷区中医医院': '北京市平谷区中医医院',
    '北京市房山区良乡医院': '北京市房山区良乡医院',
    '北京市房山区第一医院': '北京市房山区第一医院',
    '北京市房山中医院': '北京市房山区中医医院',
    '北京市房山区中医医院': '北京市房山区中医医院',
    '北京中医药大学房山医院': '北京市房山区中医医院',
    '北京市密云区医院': '北京市密云区医院',
    '北京市海淀区医院': '北京市海淀医院',
    '北京怀柔医院': '北京怀柔医院',
    '北京市延庆区医院': '北京市延庆区医院',
    '北京市垂杨柳医院': '北京市垂杨柳医院',
    '北京大学人民医院': '北京大学人民医院',
    '北京大学第一医院': '北京大学第一医院',
    '北京大学第三医院': '北京大学第三医院',
    '北京老年医院': '北京老年医院',
    '北京市小汤山医院': '北京市小汤山医院',
    '北京中医药大学东直门医院': '北京中医药大学东直门医院',
    '北京中医药大学东方医院': '北京中医药大学东方医院',
    '北京中医药大学第三附属医院': '北京中医药大学第三附属医院',
    '中国中医科学院望京医院': '中国中医科学院望京医院',
    '中国中医科学院广安门医院': '中国中医科学院广安门医院',
    '中国中医科学院西苑医院': '中国中医科学院西苑医院',
    '中国中医科学院眼科医院': '中国中医科学院眼科医院',
    '首都医科大学附属北京宣武医院': '首都医科大学宣武医院',
    '北京市小汤山医院': '北京小汤山医院',
    '北京市隆福医院': '北京市隆福医院（北京中西医结合老年医院）',
}

# 主表规范化索引
master_norm = {}
for r in master:
    master_norm.setdefault(norm(r['name']), r)


def match_inst(name):
    """返回 (主表行 or None, 命中方式)"""
    if name in by_name:
        return by_name[name], 'exact'
    std = ALIAS.get(name)
    if std and std in by_name:
        return by_name[std], 'alias'
    n = norm(name)
    if n in master_norm:
        return master_norm[n], 'norm'
    std_n = norm(std) if std else None
    if std_n and std_n in master_norm:
        return master_norm[std_n], 'alias-norm'
    # 包含匹配（要求长度 >= 6 且唯一）
    if len(n) >= 6:
        cands = [r for k, r in master_norm.items() if n in k or k in n]
        if len(cands) == 1:
            return cands[0], 'fuzzy'
    return None, ''


# ============================================================ 数据源 S1：北京市卫健委 2018 年度市级重点专科（44 项）
S1 = [
    # 培育项目（5 专科 × 多家医院）
    ('心内科', '培育', ['北京市大兴区人民医院', '首都医科大学附属北京潞河医院', '北京市平谷区医院']),
    ('呼吸内科', '培育', ['北京市房山区良乡医院', '首都医科大学附属北京潞河医院', '北京市密云区医院']),
    ('神经内科', '培育', ['北京市房山区良乡医院', '北京市房山区第一医院', '首都医科大学附属北京潞河医院']),
    ('普通外科', '培育', ['北京市垂杨柳医院', '北京市海淀医院', '北京市房山区良乡医院', '首都医科大学附属北京潞河医院', '北京市平谷区医院']),
    ('儿科', '培育', ['北京市房山区良乡医院', '首都医科大学附属北京潞河医院', '北京怀柔医院', '北京市延庆区医院']),
    # 建设项目（6 专科 × 多家医院）
    ('心血管', '建设', ['首都医科大学附属北京友谊医院', '首都医科大学宣武医院', '首都医科大学附属北京天坛医院']),
    ('肿瘤科', '建设', ['首都医科大学附属北京友谊医院', '首都医科大学附属北京朝阳医院', '首都医科大学附属北京世纪坛医院']),
    ('妇科', '建设', ['北京医院', '首都医科大学附属北京友谊医院', '首都医科大学宣武医院']),
    ('儿科', '建设', ['中国医学科学院北京协和医院', '北京大学人民医院', '首都医科大学附属北京友谊医院', '首都医科大学附属北京安贞医院']),
    ('老年医学', '建设', ['首都医科大学附属北京朝阳医院', '首都医科大学附属北京天坛医院', '北京老年医院']),
    ('精神科', '建设', ['首都医科大学附属北京朝阳医院', '首都医科大学附属北京天坛医院']),
    # 卓越项目（4 专科 × 多家医院）
    ('心血管', '卓越', ['中国医学科学院阜外医院', '首都医科大学附属北京安贞医院']),
    ('呼吸内科', '卓越', ['北京大学第一医院', '首都医科大学附属北京朝阳医院']),
    ('神经内科', '卓越', ['首都医科大学宣武医院', '首都医科大学附属北京天坛医院']),
    ('普外科', '卓越', ['中国医学科学院北京协和医院', '首都医科大学附属北京友谊医院']),
]

# ============================================================ 数据源 S2：北京市卫健委 2020 年度市级重点专科（27 项）
S2 = [
    ('呼吸内科', '培育', ['北京市海淀医院', '北京市延庆区医院', '北京市垂杨柳医院']),
    ('感染性疾病科', '培育', ['北京市海淀医院', '首都医科大学附属北京潞河医院', '北京市平谷区医院']),
    ('检验科', '培育', ['北京市垂杨柳医院', '首都医科大学附属复兴医院', '北京市密云区医院']),
    ('呼吸内科', '建设', ['首都医科大学附属北京世纪坛医院', '首都医科大学附属北京友谊医院', '首都医科大学附属北京天坛医院']),
    ('感染性疾病科', '建设', ['首都医科大学附属北京胸科医院', '首都医科大学附属北京友谊医院', '北京大学第三医院']),
    ('检验科', '建设', ['首都医科大学附属北京宣武医院', '中日友好医院', '首都医科大学附属北京世纪坛医院']),
    ('重症医学科', '卓越', ['首都医科大学附属北京朝阳医院', '中国医学科学院北京协和医院', '首都医科大学附属北京友谊医院']),
    ('感染性疾病科', '卓越', ['中国医学科学院北京协和医院', '首都医科大学附属北京佑安医院', '北京大学人民医院']),
    ('检验科', '卓越', ['中国医学科学院北京协和医院', '首都医科大学附属北京朝阳医院', '北京大学第三医院']),
]

# ============================================================ 数据源 S3：北京市中医管理局 首批"十四五"中医药重点专科（74 项目 — 全部已抓）
# 完整列表（2022/11/25 公示）：领超 10 项 + 示范 3 项 + 并超 20 项 + 建设 12 项 + 赶超 20 项 + 培育 9 项
S3 = [
    # === 领超类 10 项（BJZKLC0001~0010）===
    ('领超', '中国中医科学院西苑医院', '心血管科'),
    ('领超', '中国中医科学院广安门医院', '肿瘤科'),
    ('领超', '北京中医药大学东直门医院', '肾病科'),
    ('领超', '中国中医科学院望京医院', '骨伤科'),
    ('领超', '首都医科大学附属北京儿童医院', '儿科'),
    ('领超', '北京中医药大学东方医院', '妇科'),
    ('领超', '北京中医药大学东直门医院', '妇科'),
    ('领超', '首都医科大学附属北京中医医院', '针灸科'),
    ('领超', '首都医科大学附属北京中医医院', '皮肤科'),
    ('领超', '中国中医科学院广安门医院', '肛肠科'),
    # === 示范类 3 项（BJZKLC0011~0013）===
    ('示范', '首都医科大学附属北京中医医院', '心血管科'),
    ('示范', '首都医科大学附属北京中医医院', '肿瘤科'),
    ('示范', '中日友好医院', '肿瘤科'),
    # === 并超类 20 项（BJZKBC0001~0020）===
    ('并超', '中国中医科学院广安门医院', '心血管科'),
    ('并超', '北京中医药大学东直门医院', '心血管科'),
    ('并超', '北京中医药大学东方医院', '肿瘤科'),
    ('并超', '中国中医科学院西苑医院', '肿瘤科'),
    ('并超', '首都医科大学附属北京中医医院', '肾病科'),
    ('并超', '中国中医科学院西苑医院', '肾病科'),
    ('并超', '北京中医药大学东直门医院', '骨伤科'),
    ('并超', '北京市鼓楼中医医院', '骨伤科'),
    ('并超', '首都医科大学附属北京中医医院', '儿科'),
    ('并超', '北京中医药大学东方医院', '儿科'),
    ('并超', '北京大学第三医院', '妇科'),
    ('并超', '北京中医药大学第三附属医院', '妇科'),
    ('并超', '中国中医科学院广安门医院', '针灸科'),
    ('并超', '中国中医科学院眼科医院', '针灸科'),
    ('并超', '北京中医药大学东方医院', '皮肤科'),
    ('并超', '北京市鼓楼中医医院', '皮肤科'),
    ('并超', '中国中医科学院望京医院', '肛肠科'),
    ('并超', '北京市肛肠医院', '肛肠科'),
    ('并超', '北京按摩医院', '推拿科'),
    ('并超', '北京中医医院平谷医院', '推拿科'),
    # === 建设类 12 项（BJZKBC0021~0032）===
    ('建设', '北京中医药大学东方医院', '心血管科'),
    ('建设', '北京中医药大学第三附属医院', '肿瘤科'),
    ('建设', '首都医科大学附属北京世纪坛医院', '肿瘤科'),
    ('建设', '北京中医药大学第三附属医院', '骨伤科'),
    ('建设', '首都医科大学附属北京中医医院', '妇科'),
    ('建设', '中国中医科学院西苑医院', '妇科'),
    ('建设', '北京中医药大学附属护国寺中医医院', '针灸科'),
    ('建设', '北京中医药大学东直门医院', '针灸科'),
    ('建设', '首都医科大学附属北京同仁医院', '针灸科'),
    ('建设', '中日友好医院', '肛肠科'),
    ('建设', '中国中医科学院西苑医院', '肛肠科'),
    ('建设', '首都医科大学附属北京中医医院', '肛肠科'),
    # === 赶超类 20 项（BJZKGC0001~0020）===
    ('赶超', '北京中医药大学房山医院', '心血管科'),
    ('赶超', '北京市隆福医院', '心血管科'),
    ('赶超', '北京市第一中西医结合医院', '心血管科'),
    ('赶超', '北京中医医院顺义医院', '肿瘤科'),
    ('赶超', '北京市鼓楼中医医院', '肿瘤科'),
    ('赶超', '清华大学玉泉医院', '肿瘤科'),
    ('赶超', '北京中医药大学房山医院', '肾病科'),
    ('赶超', '北京中医医院顺义医院', '肾病科'),
    ('赶超', '北京市宣武中医医院', '骨伤科'),
    ('赶超', '北京市门头沟区中医医院', '骨伤科'),
    ('赶超', '北京市西城区丰盛骨伤专科医院', '骨伤科'),
    ('赶超', '北京市和平里医院', '儿科'),
    ('赶超', '北京市丰台区中医医院', '妇科'),
    ('赶超', '北京中西医结合医院', '妇科'),
    ('赶超', '北京市昌平区南口医院', '针灸科'),
    ('赶超', '北京中医医院平谷医院', '针灸科'),
    ('赶超', '北京中西医结合医院', '针灸科'),
    ('赶超', '北京市丰台区中医医院', '皮肤科'),
    ('赶超', '北京市门头沟区中医医院', '肛肠科'),
    ('赶超', '北京市密云区中医医院', '肛肠科'),
    # === 培育类 9 项（BJZKGC0021~0029）===
    ('培育', '北京中医医院怀柔医院', '心血管科'),
    ('培育', '北京健宫医院', '心血管科'),
    ('培育', '北京朝阳中西医结合急诊抢救医院', '肿瘤科'),
    ('培育', '北京市通州区中西医结合医院', '骨伤科'),
    ('培育', '北京市大兴区中西医结合医院', '骨伤科'),
    ('培育', '北京中医医院延庆医院', '骨伤科'),
    ('培育', '北京王府中西医结合医院', '妇科'),
    ('培育', '北京市朝阳区中医医院', '针灸科'),
    ('培育', '北京市小汤山医院', '针灸科'),
]


# ============================================================ 合并去重
# 专科名规范化（沿用国家级版）
SPEC_NORM = {
    '老年病': '老年病科', '血液病': '血液病科', '脾胃病': '脾胃病科',
    '专科护理专业': '专科护理', '临床护理专业': '临床护理',
    '心血管': '心血管科',  # 北京市级版用"心血管"，统一为"心血管科"便于与国家级并列
    '肿瘤': '肿瘤科',
    '儿科(建设)': '儿科', '普外科': '普通外科',
}


def spec_std(s):
    s = (s or '').strip()
    return SPEC_NORM.get(s, s)


records = []
seen = set()


def add(hospital, specialty, batch='', program='', source=''):
    inst, how = match_inst(hospital)
    std_hosp = inst['name'] if inst else hospital
    specialty = spec_std(specialty)
    key = (norm(std_hosp), norm(specialty))
    if key in seen:
        for r in records:
            if (norm(r['hospital']), norm(r['specialty'])) == key:
                if batch and not r.get('batch'):
                    r['batch'] = batch
                if program and not r.get('program'):
                    r['program'] = program
                break
        return False
    seen.add(key)
    records.append({
        'hospital_raw': hospital,
        'hospital': std_hosp,
        'inst_id': inst['id'] if inst else '',
        'district': inst.get('district', '') if inst else '',
        'inst_level': inst.get('level', '') if inst else '',
        'match_type': how,
        'specialty': specialty,
        'level': '市级',
        'batch': batch,
        'program': program,
        'source': source,
    })
    return True


# S1
for spec, tier, hosps in S1:
    for h in hosps:
        add(h, spec, batch=f'2018-{tier}', program='北京市临床重点专科',
            source='北京市卫健委 2018 年度北京市临床重点专科项目')
# S2
for spec, tier, hosps in S2:
    for h in hosps:
        add(h, spec, batch=f'2020-{tier}', program='北京市临床重点专科',
            source='北京市卫健委 2020 年度北京市临床重点专科项目')
# S3
for tier, h, spec in S3:
    add(h, spec, batch=f'十四五-{tier}', program='北京市中医管理局中医药重点专科',
        source='北京市中医管理局 首批"十四五"中医药重点专科')

print(f'\n[merge] 合并后 {len(records)} 条市级专科记录')

# ============================================================ 写明细
fields = ['inst_id', 'hospital', 'hospital_raw', 'district', 'inst_level', 'specialty',
          'level', 'program', 'batch', 'match_type', 'source']
with open(OUT_DETAIL, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for r in sorted(records, key=lambda x: (x['district'], x['hospital'], x['specialty'])):
        w.writerow(r)
print(f'[out] {OUT_DETAIL}')

# ============================================================ 按院汇总
hosp_map = defaultdict(list)
for r in records:
    hosp_map[r['hospital']].append(r)

with open(OUT_HOSP, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['inst_id', 'hospital', 'district', 'inst_level', 'specialty_count',
                'specialties', 'batches', 'programs'])
    for h, rs in sorted(hosp_map.items(), key=lambda x: -len(x[1])):
        inst_id = rs[0]['inst_id']
        specs = [x['specialty'] for x in rs]
        batches = sorted({x['batch'] for x in rs if x['batch']})
        programs = sorted({x['program'] for x in rs if x['program']})
        w.writerow([inst_id, h, rs[0]['district'], rs[0]['inst_level'], len(rs),
                    ';'.join(specs), '|'.join(batches), '|'.join(programs)])
print(f'[out] {OUT_HOSP}')

# ============================================================ 未匹配清单
unmatched = sorted({r['hospital_raw'] for r in records if not r['inst_id']})
with open(UNMATCHED, 'w', encoding='utf-8') as f:
    f.write('# 未能与主表匹配的医院名（需人工确认别名）\n\n')
    for h in unmatched:
        n = sum(1 for r in records if r['hospital_raw'] == h)
        f.write(f'{h}  ({n} 条专科)\n')

# ============================================================ 统计
matched_n = sum(1 for r in records if r['inst_id'])
print(f'\n===== 统计 =====')
print(f'专科记录总数: {len(records)}')
print(f'已匹配主表 id: {matched_n} ({matched_n/len(records)*100:.1f}%)')
print(f'未匹配: {len(records)-matched_n}')
print(f'涉及医院: {len(hosp_map)} 家')
print(f'  其中已匹配: {sum(1 for h,rs in hosp_map.items() if rs[0]["inst_id"])} 家')
print(f'未匹配医院名 {len(unmatched)} 个 -> {UNMATCHED}')

# ============================================================ 主表写 municipal_specialty / municipal_specialty_count
# 仅给匹配上的医院回写
SPEC_SEP = ';'  # 与 feature 字段一致

hosp_specs = {}
for h, rs in hosp_map.items():
    if rs[0]['inst_id']:
        specs = sorted({spec_std(x['specialty']) for x in rs})
        hosp_specs[h] = ';'.join(specs)

# 备份
import shutil
BACKUP = os.path.join(ROOT, 'backup', 'master_institutions.before_municipal.csv')
if not os.path.exists(BACKUP):
    shutil.copy2(MASTER, BACKUP)
    print(f'\n[backup] {BACKUP}')

# 读所有行 → 写回（含新增 2 列）
with open(MASTER, encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    fieldnames = list(reader.fieldnames)
    # 新增两列（如已存在不重复加）
    for c in ('municipal_specialty', 'municipal_specialty_count'):
        if c not in fieldnames:
            fieldnames.append(c)
    rows = list(reader)

filled = 0
for r in rows:
    nm = r['name']
    if nm in hosp_specs:
        r['municipal_specialty'] = hosp_specs[nm]
        r['municipal_specialty_count'] = str(hosp_specs[nm].count(SPEC_SEP) + 1)
        filled += 1
    else:
        r.setdefault('municipal_specialty', '')
        r.setdefault('municipal_specialty_count', '0')

with open(MASTER, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)
print(f'[master] 已写入 municipal_specialty: {filled} 行（新增 2 列）')

# ============================================================ 治理报告
report = []
report.append('# 北京市级临床重点专科治理报告（2026-09-06）\n')
report.append('## 数据来源\n')
report.append('- **S1**：北京市卫健委 [2018 年度北京市临床重点专科项目名单](https://wjw.beijing.gov.cn/zwgk_20040/ylws/201912/t20191216_1242434.html)（44 项，培育/建设/卓越）')
report.append('- **S2**：北京市卫健委 [2020 年度北京市临床重点专科项目名单](https://wjw.beijing.gov.cn/zwgk_20040/ylws/202012/t20201215_2165001.html)（27 项）')
report.append('- **S3**：北京市中医管理局 [首批"十四五"中医药重点专科名单](https://zyj.beijing.gov.cn/sy/tzgg/202211/t20221128_2867580.html)（74 项 — 本次入库 28 项）')
report.append('')
report.append('## 关键统计\n')
report.append(f'- 专科记录总数：{len(records)} 条')
report.append(f'- 已匹配主表：{matched_n} 条（{matched_n/len(records)*100:.1f}%）')
report.append(f'- 涉及医院：{len(hosp_map)} 家（已匹配 {sum(1 for h,rs in hosp_map.items() if rs[0]["inst_id"])} 家）')
report.append(f'- 主表 municipal_specialty 字段新增：{filled} 家')
report.append(f'- 未匹配（待人工补别名）：{len(unmatched)} 个')
report.append('')
report.append('## 与国家临床重点专科的差异\n')
report.append('- **国家级**（national_specialty）：由国家卫健委直接评定（项目数较多，门槛高）')
report.append('- **市级**（municipal_specialty）：北京市/各区卫健委评定（培育/建设/卓越三档；中医药单列领超/示范/并超/建设/赶超/培育六档）')
report.append('- 同一医院可能同时有国家级 + 市级专科，本数据集独立入库不合并，避免重复')
report.append('')
report.append('## TODO\n')
report.append('- [ ] 补齐 S3 中医十四五剩余 ~46 项（领超/示范/并超/建设/赶超/培育 各类未抓全部分）')
report.append('- [ ] 抓取 2022/2024 年度北京市临床重点专科新批次（北医三院/朝阳/友谊/北大医院 2024 已部分收录于个别新闻）')

with open(REPORT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(report))
print(f'[report] {REPORT}')
