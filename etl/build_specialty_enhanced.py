# -*- coding: utf-8 -*-
"""联网完善重点专科（重点科室）数据 — 多源整合 → 增强版数据集

数据源（均为联网核实/官方公开）：
  1. 《"十二五+"国家临床重点专科名单.csv》(GBK)   — 20 家中医/中西医，52 条，含单位地址
  2. 国家卫生计生委临床重点专科建设项目（西医类）— 54 个专科分类，230 个项目
  3. 国家卫生计生委临床重点专科建设项目（中医类）— 24 个专科分类
  4. 北京市中医管理局 2012 公示名单              — 8 条，含专科负责人
  5. 国家临床重点专科北京 13 家详细清单           — 交叉验证/补充

产出：
  data/processed/specialty_enhanced.csv    增强版重点专科明细（每院每专科一行）
  data/processed/specialty_hospital.csv    按院汇总（专科数、专科清单、级别）
  /tmp/specialty_unmatched.txt             未能与主表匹配的医院名（供人工确认）

用法: python build_specialty_enhanced.py
"""
import csv, os, re, unicodedata
from collections import defaultdict

ROOT = os.path.expanduser('~/Desktop/毕设/data/processed')
MASTER = os.path.join(ROOT, 'master_institutions.csv')
OUT_DETAIL = os.path.join(ROOT, 'specialty_enhanced.csv')
OUT_HOSP = os.path.join(ROOT, 'specialty_hospital.csv')
UNMATCHED = '/tmp/specialty_unmatched.txt'

# ============================================================ 主表
with open(MASTER, encoding='utf-8-sig') as f:
    master = list(csv.DictReader(f))
by_name = {r['name']: r for r in master}
print(f'[master] {len(master)} 家')

# ============================================================ 名称标准化 + 别名
def norm(s):
    s = unicodedata.normalize('NFKC', s or '')
    s = re.sub(r'[\s\u3000（）()]+', '', s)
    return s.lower()

# 人工确认的别名映射（源名 -> 主表标准名）
ALIAS = {
    '卫生部北京医院': '北京医院',
    '首都医科大学北京宣武医院': '首都医科大学宣武医院',
    '首都医科大学附属宣武医院': '首都医科大学宣武医院',
    '首都医科大学宣武医院': '首都医科大学宣武医院',
    '首都医科大学附属地坛医院': '首都医科大学附属北京地坛医院',
    '北京地坛医院': '首都医科大学附属北京地坛医院',
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
    '宣武医院': '首都医科大学宣武医院',
    '阜外心血管病医院': '中国医学科学院阜外医院',
    '医科院肿瘤医院': '中国医学科学院肿瘤医院',
    '整形外科医院': '中国医学科学院整形外科医院',
    '北京军区总医院': '中国人民解放军总医院第七医学中心',
    '北京三博脑科医院': '首都医科大学三博脑科医院',
    '北京市道培医院': '北京陆道培血液病医院',
    '北京潞河医院': '首都医科大学附属北京潞河医院',
    '北京胸科医院': '首都医科大学附属北京胸科医院',
    '北京肿瘤医院': '北京大学肿瘤医院',
}

# 主表规范化索引
master_norm = {}
for r in master:
    master_norm.setdefault(norm(r['name']), r)


def match_inst(name):
    """返回主表行 or None：精确 → 别名 → 规范化 → 包含匹配"""
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
    # 包含匹配（谨慎：要求长度 >= 6 且唯一）
    if len(n) >= 6:
        cands = [r for k, r in master_norm.items() if n in k or k in n]
        if len(cands) == 1:
            return cands[0], 'fuzzy'
    return None, ''


# ============================================================ 数据源 1：GBK 国家临床重点专科名单
src1 = []
gbk_path = os.path.expanduser('~/Desktop/毕设/data/“十二五+”国家临床重点专科名单.csv')
with open(gbk_path, encoding='gbk') as f:
    rows = list(csv.reader(f))
cur_hosp, cur_addr = '', ''
for r in rows[2:]:
    if len(r) < 4:
        continue
    no, hosp, addr, spec = r[0], r[1], r[2], r[3]
    if hosp.strip():
        cur_hosp = hosp.strip()
    if addr.strip():
        cur_addr = addr.strip()
    if spec.strip() and cur_hosp:
        src1.append({'hospital': cur_hosp, 'addr': cur_addr, 'specialty': spec.strip()})
print(f'[源1] GBK 名单 {len(src1)} 条（20 家，含地址）')

# ============================================================ 数据源 2+3：230 个建设项目（西医类/中医类）
WEST_230 = [
    ('心血管内科', ['北京医院', '北京协和医院', '中国医学科学院阜外医院', '北京大学第一医院', '北京大学人民医院', '北京朝阳医院', '北京安贞医院']),
    ('呼吸内科', ['北京医院', '中日友好医院', '北京协和医院', '北京大学第一医院', '北京大学人民医院', '北京大学第三医院', '北京朝阳医院']),
    ('专科护理专业', ['北京协和医院', '北京大学第一医院', '北京大学人民医院', '宣武医院', '北京大学第三医院', '中日友好医院']),
    ('神经内科', ['北京医院', '北京协和医院', '北京大学第三医院', '宣武医院', '北京天坛医院', '北京大学第一医院']),
    ('临床护理专业', ['北京医院', '北京友谊医院', '中国医学科学院阜外医院', '北京朝阳医院', '北京天坛医院', '北京儿童医院']),
    ('检验科', ['北京协和医院', '北京大学人民医院', '北京大学第三医院', '北京友谊医院', '北京朝阳医院']),
    ('老年病科', ['北京医院', '中日友好医院', '北京大学第一医院', '宣武医院', '北京友谊医院', '北京安贞医院']),
    ('普通外科', ['北京协和医院', '北京大学第一医院', '北京大学人民医院', '北京大学第三医院', '北京友谊医院']),
    ('泌尿外科', ['北京医院', '北京协和医院', '北京大学第一医院', '北京大学人民医院', '北京大学第三医院']),
    ('妇科', ['北京协和医院', '北京大学第一医院', '北京大学人民医院', '北京大学第三医院', '北京妇产医院']),
    ('重症医学科', ['北京协和医院', '北京大学人民医院', '北京朝阳医院', '宣武医院', '北京友谊医院']),
    ('重点实验室', ['中国医学科学院阜外医院', '北京大学第三医院', '北京大学第一医院', '北京大学第六医院', '北京医院']),
    ('感染性疾病科', ['北京协和医院', '北京大学第一医院', '北京大学人民医院', '北京地坛医院', '北京佑安医院']),
    ('骨科', ['北京协和医院', '北京大学人民医院', '北京大学第三医院', '北京积水潭医院']),
    ('内分泌科', ['北京协和医院', '中日友好医院', '北京大学第一医院', '北京大学人民医院']),
    ('产科', ['北京协和医院', '北京大学第一医院', '北京大学第三医院', '北京妇产医院']),
    ('麻醉科', ['北京协和医院', '北京朝阳医院', '北京大学第一医院', '北京大学第三医院']),
    ('消化内科', ['北京协和医院', '北京大学第三医院', '北京友谊医院', '北京大学第一医院']),
    ('神经外科', ['首都医科大学宣武医院', '北京天坛医院', '北京三博脑科医院', '北京协和医院']),
    ('眼科', ['北京协和医院', '北京大学人民医院', '北京大学第三医院', '北京同仁医院']),
    ('急诊医学科', ['北京协和医院', '北京大学人民医院', '北京朝阳医院', '中日友好医院']),
    ('病理科', ['北京协和医院', '北京大学第三医院', '北京大学肿瘤医院', '北京友谊医院']),
    ('药学部', ['北京大学第三医院', '北京医院', '北京协和医院', '北京大学第一医院']),
    ('肿瘤科', ['北京协和医院', '中国医学科学院肿瘤医院', '北京大学人民医院', '北京肿瘤医院']),
    ('血液科', ['北京市道培医院', '北京协和医院', '北京大学人民医院']),
    ('胸外科', ['中日友好医院', '北京大学人民医院']),
    ('儿科重症', ['北京大学第一医院', '北京儿童医院', '首都儿科研究所附属儿童医院']),
    ('耳鼻咽喉科', ['北京协和医院', '北京大学第三医院', '北京同仁医院']),
    ('风湿免疫科', ['北京协和医院', '中日友好医院', '北京大学人民医院']),
    ('整形外科', ['北京协和医院', '整形外科医院', '北京大学第三医院']),
    ('变态反应科', ['北京协和医院', '北京同仁医院', '北京世纪坛医院']),
    ('医学影像科', ['北京医院', '北京协和医院', '中国医学科学院肿瘤医院']),
    ('肾病科', ['北京协和医院', '北京大学第一医院']),
    ('心脏大血管外科', ['中国医学科学院阜外医院', '北京安贞医院']),
    ('儿科呼吸专业', ['北京儿童医院', '首都儿科研究所附属儿童医院']),
    ('口腔科-牙体牙髓', ['北京大学口腔医院', '北京口腔医院']),
    ('口腔颌面外科专业', ['北京大学口腔医院', '北京口腔医院']),
    ('口腔修复专业', ['北京大学口腔医院', '北京口腔医院']),
    ('皮肤科', ['北京大学第一医院', '北京大学人民医院']),
    ('精神病科', ['北京安定医院', '北京回龙观医院']),
    ('职业病科', ['北京大学第三医院', '北京朝阳医院']),
    ('运动医学科', ['北京大学第三医院', '北京积水潭医院']),
    ('口腔正畸专业', ['北京大学口腔医院', '北京口腔医院']),
    ('康复医学科', ['北京大学第三医院', '北京博爱医院']),
    ('手外科', ['北京积水潭医院']),
    ('口腔科-牙周病', ['北京大学口腔医院']),
    ('地方病科', ['北京友谊医院']),
    ('烧伤科', ['北京积水潭医院']),
    ('口腔种植专业', ['北京大学口腔医院']),
    ('儿童口腔专业', ['北京大学口腔医院']),
    ('口腔黏膜专业', ['北京大学口腔医院']),
    ('疼痛科', ['中日友好医院']),
    ('小儿外科', ['北京儿童医院']),
]

TCM_230 = [
    ('传染病科', ['北京地坛医院']),
    ('儿科', ['首都医科大学附属北京儿童医院']),
    ('肺病科', ['中日友好医院', '中国中医科学院西苑医院', '北京中医药大学东方医院']),
    ('风湿病科', ['中日友好医院', '中国中医科学院广安门医院']),
    ('妇科', ['北京中医药大学东方医院', '北京中医药大学东直门医院']),
    ('肝病科', ['首都医科大学附属北京佑安医院', '中日友好医院', '北京马应龙长青肛肠医院']),
    ('骨伤科', ['北京中医药大学第三附属医院', '中国中医科学院望京医院']),
    ('护理学', ['首都医科大学附属北京中医医院', '中国中医科学院广安门医院', '北京中医药大学东方医院']),
    ('急诊科', ['北京中医药大学东直门医院', '首都医科大学附属北京中医医院']),
    ('康复科', ['中国中医科学院望京医院']),
    ('老年病科', ['北京大学第一医院', '北京医院', '中国中医科学院西苑医院']),
    ('临床药学', ['北京中医药大学东直门医院']),
    ('内分泌科', ['北京协和医院', '首都医科大学附属北京世纪坛医院', '中国中医科学院广安门医院']),
    ('脑病科', ['北京中医药大学东方医院', '北京中医药大学东直门医院', '首都医科大学北京宣武医院', '北京中医药大学第三附属医院']),
    ('皮肤科', ['首都医科大学附属北京中医医院', '中国中医科学院广安门医院']),
    ('脾胃病科', ['首都医科大学附属北京中医医院', '中国中医科学院西苑医院', '中国中医科学院望京医院',
                  '北京中医药大学东直门医院', '北京中医药大学东方医院', '北京中医药大学第三附属医院']),
    ('神志病科', ['首都医科大学附属北京安定医院']),
    ('肾病科', ['中国中医科学院望京医院', '北京中医药大学东直门医院']),
    ('外科', ['首都医科大学附属北京中医医院']),
    ('心血管科', ['中国中医科学院广安门医院', '中国中医科学院西苑医院', '北京中医药大学东方医院', '首都医科大学附属北京中医医院']),
    ('血液病科', ['中国中医科学院西苑医院']),
    ('眼科', ['中国中医科学院眼科医院']),
    ('针灸科', ['首都医科大学附属北京中医医院', '北京中医药大学附属护国寺中医医院']),
    ('肿瘤科', ['中日友好医院', '中国中医科学院广安门医院', '首都医科大学附属北京中医医院']),
]

src2 = []
for spec, hosps in WEST_230:
    for h in hosps:
        src2.append({'hospital': h, 'specialty': spec, 'system': '西医'})
src3 = []
for spec, hosps in TCM_230:
    for h in hosps:
        src3.append({'hospital': h, 'specialty': spec, 'system': '中医'})
print(f'[源2] 230 名单西医类 {len(src2)} 条 / {len(WEST_230)} 专科')
print(f'[源3] 230 名单中医类 {len(src3)} 条 / {len(TCM_230)} 专科')

# ============================================================ 数据源 4：北京市中医管理局 2012 公示（含负责人）
src4 = [
    ('首都医科大学附属北京中医医院', '外科', '董建勋'),
    ('首都医科大学附属北京中医医院', '心血管科', '刘红旭'),
    ('首都医科大学附属北京佑安医院', '传染病', '李宁'),
    ('首都医科大学附属北京地坛医院', '肝病科', '王宪波'),
    ('首都医科大学北京宣武医院', '脑病科', '高利'),
    ('中日友好医院', '脾胃病科', '符思'),
    ('中日友好医院', '心血管科', '黄力'),
    ('中日友好医院', '肛肠科', '安阿玥'),
]
leader_map = {(h, s): l for h, s, l in src4}
print(f'[源4] 2012 公示（含负责人）{len(src4)} 条')

# ============================================================ 合并去重
# 专科名规范化：统一补"科"后缀，消除"老年病"/"老年病科"这类重复
SPEC_NORM = {
    '老年病': '老年病科', '血液病': '血液病科', '脾胃病': '脾胃病科',
    '临床药学': '临床药学', '专科护理专业': '专科护理', '临床护理专业': '临床护理',
}


def spec_std(s):
    s = (s or '').strip()
    return SPEC_NORM.get(s, s)


records = []
seen = set()


def add(hospital, specialty, system='', program='', batch='', addr='', leader='', source=''):
    # 用"匹配后的标准院名"去重，避免别名（北京协和医院 / 中国医学科学院北京协和医院）
    # 各插一条相同专科造成重复
    inst, how = match_inst(hospital)
    std_hosp = inst['name'] if inst else hospital
    specialty = spec_std(specialty)
    key = (norm(std_hosp), norm(specialty))
    if key in seen:
        # 已存在则补字段（负责人/地址）
        for r in records:
            if (norm(r['hospital']), norm(r['specialty'])) == key:
                if leader and not r['leader']:
                    r['leader'] = leader
                if addr and not r['addr']:
                    r['addr'] = addr
                if system and not r['system']:
                    r['system'] = system
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
        'system': system,
        'program': program,
        'batch': batch,
        'level': '国家级',
        'addr': addr,
        'leader': leader,
        'source': source,
    })
    return True


# 源1（含地址，中医）
for r in src1:
    add(r['hospital'], r['specialty'], system='中医',
        program='国家临床重点专科', batch='十二五', addr=r['addr'],
        source='《"十二五+"国家临床重点专科名单》(GBK,含地址)')
# 源2（西医类 230）
for r in src2:
    add(r['hospital'], r['specialty'], system=r['system'],
        program='国家临床重点专科建设项目', batch='国家卫生计生委',
        source='国家卫生计生委临床重点专科建设项目(西医类,230项)')
# 源3（中医类 230）
for r in src3:
    add(r['hospital'], r['specialty'], system=r['system'],
        program='国家临床重点专科建设项目', batch='国家卫生计生委',
        source='国家卫生计生委临床重点专科建设项目(中医类)')
# 源4（负责人）—— 按标准院名匹配，避免别名重复命中
for h, s, l in src4:
    inst4, _ = match_inst(h)
    std4 = inst4['name'] if inst4 else h
    s4 = spec_std(s)
    key4 = (norm(std4), norm(s4))
    found = False
    for r in records:
        if (norm(r['hospital']), norm(r['specialty'])) == key4:
            r['leader'] = l
            found = True
            break
    if not found:
        add(h, s, system='中医', program='国家临床重点专科建设项目(中医专业)',
            batch='2012', leader=l, source='北京市中医管理局2012公示(含负责人)')

print(f'\n[merge] 合并后 {len(records)} 条专科记录')

# ============================================================ 写明细
fields = ['inst_id', 'hospital', 'hospital_raw', 'district', 'inst_level', 'specialty',
          'system', 'program', 'batch', 'level', 'leader', 'addr', 'match_type', 'source']
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
                'specialties', 'leaders', 'programs', 'sample_addr'])
    for h, rs in sorted(hosp_map.items(), key=lambda x: -len(x[1])):
        inst_id = rs[0]['inst_id']
        specs = [x['specialty'] for x in rs]
        leaders = [f"{x['specialty']}:{x['leader']}" for x in rs if x['leader']]
        programs = sorted({x['program'] for x in rs if x['program']})
        addrs = [x['addr'] for x in rs if x['addr']]
        w.writerow([inst_id, h, rs[0]['district'], rs[0]['inst_level'], len(rs),
                    '、'.join(specs), '；'.join(leaders), '|'.join(programs),
                    addrs[0] if addrs else ''])
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
print(f'有负责人: {sum(1 for r in records if r["leader"])} 条')
print(f'有地址: {sum(1 for r in records if r["addr"])} 条')
print(f'未匹配医院名 {len(unmatched)} 个 -> {UNMATCHED}')
