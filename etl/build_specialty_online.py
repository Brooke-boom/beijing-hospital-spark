#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网补全重点专科/重点科室 → 合并写回主表 master_institutions.csv

数据源：
  A. 权威名单（2026-09-17 联网核实，官网/卫健委通知原文，内置于 AUTH_NATIONAL / AUTH_MUNICIPAL）
     - 国家临床重点专科（卫健委西医）：协和/朝阳/北医三院/中日/安贞/北京医院/积水潭/肿瘤医院/北大第一
     - 北京市临床重点专科：市卫健委 2018/2020 年度通知、2021/2022 重大疫情专项、2024/2025 单项公布
  B. 百度百科抓取 data/processed/baike_depts.jsonl（etl/scrape_baike_depts.py 产出）

主表变更（原地更新，保留历史值，只增不改不删）：
  - national_specialty(_count)：并入 A 的国家临床重点专科（原值多为中医药重点专科，保留）
  - municipal_specialty(_count)：并入 A 的北京市临床重点专科（原值为中医管理局名单，保留）
  - 新列 baike_key_depts / baike_src：百科「重点专科」章节科室
  - 新列 specialty_src：本次补全的来源注记
  - feature/feature_level：仅当原 feature_level≠1 且百科给出明确重点专科章节时 升级 L1，
    feature 保留原 L1 值（若有）并在尾部并入百科科室

产出：
  data/processed/specialty_online.csv            每院每专科明细（level=national/municipal/baike）
  data/processed/govern_report_specialty_online.md  治理报告
用法: python3 etl/build_specialty_online.py
"""
import csv, json, os, re, unicodedata
from collections import defaultdict

ROOT = os.path.expanduser('~/Desktop/毕设/data/processed')
MASTER = os.path.join(ROOT, 'master_institutions.csv')
BAIKE = os.path.join(ROOT, 'baike_depts.jsonl')
OUT_DETAIL = os.path.join(ROOT, 'specialty_online.csv')
REPORT = os.path.join(ROOT, 'govern_report_specialty_online.md')

# ============================================================ 权威名单（2026-09-17 联网核实）
# 国家临床重点专科（含建设项目）——来源：各院官网简介/市卫健委转发通知
AUTH_NATIONAL = {
    '中国医学科学院北京协和医院': ('官网词条核验（国家临床重点专科29个）', [
        '儿科', '神经科', '心内科', '感染内科', '基本外科', '骨科', '放射治疗科',
        '物理医学康复科', '皮肤科', '中医科', '血液内科', '临床营养科', '心理医学科']),
    '首都医科大学附属北京朝阳医院': ('朝阳医院官网简介/2024喜报（8重点+2建设）', [
        '呼吸与危重症医学科', '心脏内科', '急诊医学科', '重症医学科', '麻醉科',
        '职业病科', '临床护理专业', '检验科', '心脏大血管外科', '心脏内科(冠心病"1+N"学科群)']),
    '北京大学第三医院': ('北医三院官网简介（27个/37批次）', [
        '骨科', '药剂科(临床药学)', '病理科', '专科护理', '检验科', '消化科', '妇科', '产科',
        '职业病科', '耳鼻喉科', '心血管分子生物学与调节肽重点实验室', '呼吸内科', '神经内科',
        '普通外科', '泌尿外科', '眼科', '麻醉科', '康复医学科', '成形科(整形外科)',
        '运动医学科', '心血管内科', '肿瘤放疗科(放射治疗专业)', '急诊科', '神经外科',
        '内分泌科', '生殖医学科', '血液内科']),
    '中日友好医院': ('医院官网/百科（19个科室及专业）', [
        '内分泌科', '呼吸与危重症医学科', '风湿免疫科', '急诊医学科', '老年病科', '胸外科',
        '疼痛科', '中医风湿病科', '中西医结合肿瘤内科', '肛肠科', '中医肺病科', '临床护理',
        '肾病科', '神经外科', '泌尿外科', '皮肤科', '心脏科']),
    '首都医科大学附属北京安贞医院': ('安贞医院官网简介（国家重点学科1+国家临床重点专科5）', [
        '心血管内科', '心脏大血管外科', '老年病科', '妇科', '重症医学科']),
    '北京医院': ('北京医院官网概况（23个专业获批及建设项目）', [
        '心血管内科', '呼吸内科', '神经内科', '泌尿外科', '中医科', '老年医学', '医学影像科',
        '临床药学', '临床检验', '临床护理', '风湿免疫', '肿瘤', '内分泌', '消化科',
        '放射治疗科', '心脏大血管外科', '普通外科', '神经外科', '皮肤科', '血液科',
        '胸外科', '重症医学科']),
    '北京积水潭医院': ('积水潭医院2025喜报（4重点+3建设）', [
        '骨科', '手外科', '烧伤整形与创面修复科', '运动医学科', '急诊科', '重症医学科', '心血管内科']),
    '中国医学科学院肿瘤医院': ('肿瘤医院官网（8学科11项）', [
        '肿瘤学', '胸外科', '医学影像科', '放疗科', '结直肠外科', '病理科', '泌尿外科', '妇科']),
    '北京大学第一医院': ('北大医院官网历年名单（2010-2025）', [
        '妇科', '产科', '儿科', '专科护理', '心血管内科', '内分泌科', '中医科', '老年病科',
        '呼吸与危重症医学科', '肾脏内科', '普通外科', '泌尿外科', '麻醉科', '皮肤性病科',
        '消化内科', '神经内科', '感染疾病科', '临床药学', '风湿免疫科', '胸外科',
        '放射治疗科', '重症医学科', '神经外科', '骨科', '健康管理科', '生殖医学科']),
    '首都医科大学附属北京天坛医院': ('百科词条/官网（神经专科国家队+临床重点学科）', [
        '神经内科', '神经外科', '眼科', '耳鼻咽喉科', '变态反应科']),
}

# 北京市临床重点专科（含重大疫情防治专项）——来源：市卫健委通知原文（2018/2020/2022）
# 结构: (年度, 类别, 专科, [医院别名...])；医院别名经 ALIAS 归一
MUNICIPAL_NOTICES = [
    ('2018', '培育', '心内科', ['大兴区人民医院', '潞河医院', '平谷区医院']),
    ('2018', '培育', '呼吸内科', ['房山区良乡医院', '潞河医院', '密云区医院']),
    ('2018', '培育', '神经内科', ['房山区良乡医院', '房山区第一医院', '潞河医院']),
    ('2018', '培育', '普通外科', ['垂杨柳医院', '海淀医院', '房山区良乡医院', '潞河医院', '平谷区医院']),
    ('2018', '培育', '儿科', ['房山区良乡医院', '潞河医院', '怀柔医院', '延庆区医院']),
    ('2018', '建设', '心血管', ['友谊医院', '宣武医院', '天坛医院']),
    ('2018', '建设', '肿瘤科', ['友谊医院', '朝阳医院', '世纪坛医院']),
    ('2018', '建设', '妇科', ['北京医院', '友谊医院', '宣武医院']),
    ('2018', '建设', '儿科', ['协和医院', '人民医院', '友谊医院', '安贞医院']),
    ('2018', '建设', '老年医学', ['朝阳医院', '天坛医院', '北京老年医院']),
    ('2018', '建设', '精神科', ['朝阳医院', '天坛医院']),
    ('2018', '卓越', '心血管', ['阜外医院', '安贞医院']),
    ('2018', '卓越', '呼吸内科', ['北大第一医院', '朝阳医院']),
    ('2018', '卓越', '神经内科', ['宣武医院', '天坛医院']),
    ('2018', '卓越', '普外科', ['协和医院', '友谊医院']),
    ('2020', '培育', '呼吸内科', ['海淀医院', '延庆区医院', '垂杨柳医院']),
    ('2020', '培育', '感染性疾病科', ['海淀医院', '潞河医院', '平谷区医院']),
    ('2020', '培育', '检验科', ['垂杨柳医院', '复兴医院', '密云区医院']),
    ('2020', '建设', '呼吸内科', ['世纪坛医院', '友谊医院', '天坛医院']),
    ('2020', '建设', '感染性疾病科', ['胸科医院', '友谊医院', '北医三院']),
    ('2020', '建设', '检验科', ['宣武医院', '中日友好医院', '世纪坛医院']),
    ('2020', '卓越', '重症医学科', ['朝阳医院', '协和医院', '友谊医院']),
    ('2020', '卓越', '感染性疾病科', ['协和医院', '佑安医院', '人民医院']),
    ('2020', '卓越', '检验科', ['协和医院', '朝阳医院', '北医三院']),
    ('2021', '卓越', '儿科(重症医学专业)', ['北大第一医院']),
    ('2021', '建设', '整形烧伤外科(烧伤专业)', ['北大第一医院']),
    ('2022', '培育', '感染性疾病科', ['密云区医院', '怀柔医院']),
    ('2022', '培育', '医学检验科', ['怀柔医院', '石景山医院']),
    ('2022', '培育', '医学影像科', ['航天中心医院', '延庆区医院']),
    ('2022', '培育', '重症医学科', ['复兴医院', '潞河医院']),
    ('2022', '培育', '中医科', ['复兴医院', '潞河医院']),
    ('2022', '建设', '重症医学科', ['世纪坛医院', '地坛医院', '中日友好医院']),
    ('2022', '建设', '医学影像科', ['朝阳医院', '阜外医院', '北医三院']),
    ('2022', '建设', '感染性疾病科', ['清华长庚医院', '儿童医院']),
    ('2022', '建设', '医学检验科', ['北大第一医院', '安贞医院']),
    ('2022', '建设', '呼吸内科', ['清华长庚医院', '宣武医院']),
    ('2022', '建设', '流行病学', ['安贞医院', '朝阳医院']),
    ('2022', '建设', '创伤科', ['人民医院', '朝阳医院']),
    ('2022', '建设', '中医科', ['北京中医医院', '人民医院']),
    ('2022', '卓越', '感染性疾病科', ['北大第一医院']),
    ('2022', '卓越', '医学检验科', ['人民医院']),
    ('2022', '卓越', '中医科', ['地坛医院', '西苑医院(肺病科)']),
    ('2024', '建设', '生殖医学科', ['北医三院']),
    ('2024', '建设', '神经外科', ['北医三院']),
    ('2024', '建设', '胸外科', ['朝阳医院']),
    ('2024', '建设', '心脏内科(冠心病"1+N"学科群)', ['朝阳医院']),
    ('2025', '建设', '妇科', ['清华长庚医院']),
    ('2025', '建设', '护理学科', ['积水潭医院']),
]

# 通知/权威源常用院名 → 主表标准名（沿用既有治理脚本的别名集并扩展）
ALIAS = {
    '协和医院': '中国医学科学院北京协和医院',
    '儿童医院': '首都医科大学附属北京儿童医院',
    '安贞医院': '首都医科大学附属北京安贞医院',
    '朝阳医院': '首都医科大学附属北京朝阳医院',
    '友谊医院': '首都医科大学附属北京友谊医院',
    '同仁医院': '首都医科大学附属北京同仁医院',
    '天坛医院': '首都医科大学附属北京天坛医院',
    '佑安医院': '首都医科大学附属北京佑安医院',
    '世纪坛医院': '首都医科大学附属北京世纪坛医院',
    '胸科医院': '首都医科大学附属北京胸科医院',
    '地坛医院': '首都医科大学附属北京地坛医院',
    '宣武医院': '首都医科大学宣武医院',
    '阜外医院': '中国医学科学院阜外医院',
    '人民医院': '北京大学人民医院',
    '北大第一医院': '北京大学第一医院',
    '北医三院': '北京大学第三医院',
    '积水潭医院': '北京积水潭医院',
    '中日友好医院': '中日友好医院',
    '北京医院': '北京医院',
    '北京老年医院': '北京老年医院',
    '清华长庚医院': '北京清华长庚医院',
    '复兴医院': '首都医科大学附属复兴医院',
    '潞河医院': '首都医科大学附属北京潞河医院',
    '垂杨柳医院': '北京市垂杨柳医院',
    '海淀医院': '北京市海淀医院',
    '平谷区医院': '北京市平谷区医院',
    '密云区医院': '北京市密云区医院',
    '延庆区医院': '北京市延庆区医院',
    '怀柔医院': '北京怀柔医院',
    '房山区良乡医院': '北京市房山区良乡医院',
    '房山区第一医院': '北京市房山区第一医院',
    '大兴区人民医院': '北京市大兴区人民医院',
    '石景山医院': '北京市石景山医院',
    '航天中心医院': '航天中心医院',
    '北京中医医院': '首都医科大学附属北京中医医院',
    '西苑医院(肺病科)': '中国中医科学院西苑医院',
    '西苑医院': '中国中医科学院西苑医院',
}

GENERIC_DEPTS = {'临床科室', '医技科室', '重点专科', '特色科室', '科室设置', '重点科室',
                 '其他科室', '科室介绍', '国家临床重点专科', '国家重点学科', '医疗科室'}


def norm(s):
    s = unicodedata.normalize('NFKC', s or '')
    s = re.sub(r'[\s\u3000（）()]+', '', s)
    return s.lower()


def split_depts(s):
    return [x.strip() for x in re.split(r'[;；]', s or '') if x.strip()]


def split_ann(s):
    """与 web/app.py _split_ann 同口径：全套分隔符切分（保括号注释）"""
    return [x.strip() for x in re.split(r'[;；、,，/]+', s or '') if len(x.strip()) >= 2]


def main():
    with open(MASTER, encoding='utf-8-sig') as f:
        master = list(csv.DictReader(f))
    by_name = {r['name']: r for r in master}
    by_norm = {}
    for r in master:
        by_norm.setdefault(norm(r['name']), r)
    print(f'[master] {len(master)} 家')

    def resolve(name):
        n = ALIAS.get(name.strip(), name.strip())
        r = by_name.get(n) or by_norm.get(norm(n))
        return r

    detail = []          # 明细行
    nat_new, mun_new, baike_new = defaultdict(set), defaultdict(set), defaultdict(set)
    src_note = defaultdict(list)
    unmatched = defaultdict(list)

    # ---------- A1 权威国家级 ----------
    for hname, (src, depts) in AUTH_NATIONAL.items():
        r = resolve(hname)
        if not r:
            unmatched['national'].append(hname)
            continue
        for d in depts:
            nat_new[r['id']].add(d)
            detail.append({'hospital_id': r['id'], 'hospital': r['name'],
                           'level': 'national', 'dept': d, 'year': '', 'grade': '',
                           'source': src})
        src_note[r['id']].append('国家临床重点专科:' + src)

    # ---------- A2 权威市级 ----------
    for year, grade, dept, hosp in MUNICIPAL_NOTICES:
        for h in hosp:
            r = resolve(h)
            if not r:
                unmatched['municipal'].append(f'{year}/{dept}/{h}')
                continue
            mun_new[r['id']].add(dept)
            detail.append({'hospital_id': r['id'], 'hospital': r['name'],
                           'level': 'municipal', 'dept': dept, 'year': year,
                           'grade': grade, 'source': f'北京市卫健委{year}年度通知'})
            src_note[r['id']].append(f'北京市临床重点专科{year}({grade})')

    # ---------- B 百度百科重点专科章节 ----------
    baike_rows = []
    if os.path.exists(BAIKE):
        for ln in open(BAIKE, encoding='utf-8'):
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            if not rec.get('found'):
                continue
            baike_rows.append(rec)

    def clean_section(secs):
        out = []
        for s in secs:
            s = s.strip()
            if not s or s in GENERIC_DEPTS or len(s) > 16:
                continue
            if re.match(r'^[\d\[（(播放▪]', s):
                continue
            out.append(s)
        return list(dict.fromkeys(out))

    def infobox_depts(text):
        """从信息栏「重点专科」字段抢救科室名（含截断列表/注释，逐 token 过滤）"""
        t = re.sub(r'\[\d+(?:-\d+)*\]', '', text or '')
        t = re.sub(r'播报|编辑|目录', '；', t)
        out = []
        for tok in re.split(r'[;；、，。：:]', t):
            tok = tok.strip()
            if not tok or tok in GENERIC_DEPTS or len(tok) > 14 or len(tok) < 2:
                continue
            if not re.search(r'(科|中心|部|所|室)$', tok):
                continue
            if re.search(r'历史|沿革|荣誉|地址|院区|奖项|教学|简介', tok):
                continue
            if '等' in tok:
                tok = tok.split('等')[0]
                if not tok.endswith(('科', '中心', '部', '所', '室')) or len(tok) < 2:
                    continue
            out.append(tok)
        return list(dict.fromkeys(out))[:15]

    baike_hit = 0
    for rec in baike_rows:
        r = resolve(rec['name'] if rec['name'] in by_name else rec['query'])
        if not r:
            unmatched['baike'].append(rec['query'])
            continue
        depts = clean_section(rec.get('key_depts_section', []))
        src_kind = '重点专科章节'
        if not depts:
            depts = infobox_depts(rec.get('infobox', {}).get('重点专科', ''))
            src_kind = '信息栏·重点专科'
        if not depts:
            continue
        baike_new[r['id']].update(depts)
        baike_hit += 1
        src_note[r['id']].append(f'百度百科({src_kind}): ' + rec.get('url', ''))
        for d in depts:
            detail.append({'hospital_id': r['id'], 'hospital': r['name'],
                           'level': 'baike', 'dept': d, 'year': '', 'grade': '',
                           'source': '百度百科' + src_kind + ' ' + rec.get('url', '')})
    print(f'[baike] 有重点专科章节 {baike_hit}/{len(baike_rows)}')

    # ---------- 写回主表 ----------
    new_cols = ['baike_key_depts', 'baike_src', 'specialty_src']
    for r in master:
        for c in new_cols:
            if c not in r:
                r[c] = ''
        iid = r['id']
        # national / municipal 并集（保留原值）
        old_nat = split_ann(r.get('national_specialty'))
        old_mun = split_ann(r.get('municipal_specialty'))
        nat = list(dict.fromkeys(old_nat + sorted(nat_new.get(iid, set()))))
        mun = list(dict.fromkeys(old_mun + sorted(mun_new.get(iid, set()))))
        if nat != old_nat or mun != old_mun or baike_new.get(iid):
            changed = True
        else:
            changed = False
        if nat_new.get(iid):
            r['national_specialty'] = ';'.join(nat)
            r['national_specialty_count'] = str(len(nat))
        if mun_new.get(iid):
            r['municipal_specialty'] = ';'.join(mun)
            r['municipal_specialty_count'] = str(len(mun))
        if baike_new.get(iid):
            r['baike_key_depts'] = ';'.join(sorted(baike_new[iid]))
            r['baike_src'] = next((s for s in src_note[iid] if s.startswith('百度百科')), '')
        if src_note.get(iid):
            r['specialty_src'] = ' | '.join(list(dict.fromkeys(src_note[iid]))[:3])
        # feature 升级：原非 L1 且百科给出明确重点专科章节
        if baike_new.get(iid) and r.get('feature_level') != '1':
            r['feature'] = ';'.join(dict.fromkeys(
                split_depts(r.get('feature')) + sorted(baike_new[iid])))
            r['feature_level'] = '1'
        _ = changed

    # ---------- 落盘 ----------
    fields = list(master[0].keys())
    for c in new_cols:
        if c not in fields:
            fields.append(c)
    with open(MASTER, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(master)
    with open(OUT_DETAIL, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['hospital_id', 'hospital', 'level', 'dept',
                                          'year', 'grade', 'source'])
        w.writeheader()
        w.writerows(detail)

    # ---------- 报告 ----------
    nat_cnt = sum(1 for r in master if (r.get('national_specialty') or '').strip())
    mun_cnt = sum(1 for r in master if (r.get('municipal_specialty') or '').strip())
    l1 = sum(1 for r in master if r.get('feature_level') == '1')
    baike_cnt = sum(1 for r in master if (r.get('baike_key_depts') or '').strip())
    rep = []
    rep.append('# 重点专科/重点科室 联网补全治理报告\n')
    rep.append('- 执行时间：2026-09-17')
    rep.append('- 数据源：A 权威名单（市卫健委 2018/2020/2021/2022/2024/2025 通知原文 + 9 家医院官网简介）；'
               'B 百度百科词条（etl/scrape_baike_depts.py，212 家三级医院）')
    rep.append(f'- 国家临床重点专科（含建设项目）有值：{nat_cnt} 家（补全前 42 家）')
    rep.append(f'- 北京市临床重点专科有值：{mun_cnt} 家（补全前 77 家）')
    rep.append(f'- 百科重点专科章节入库：{baike_cnt} 家（命中章节 {baike_hit}）')
    rep.append(f'- feature L1（重点专科/重点科室）：{l1} 家')
    rep.append(f'- 明细行：{len(detail)} 条 → specialty_online.csv')
    if unmatched:
        rep.append('\n## 未匹配（人工确认）\n')
        for k, v in unmatched.items():
            rep.append(f'- {k}: {v[:20]}')
    open(REPORT, 'w', encoding='utf-8').write('\n'.join(rep) + '\n')
    print('\n'.join(rep))


if __name__ == '__main__':
    main()
