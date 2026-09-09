#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第二批等级核实：以官方名单为权威基准，交叉核对系统 202 家“三级”机构。
优先级：北京市医保 A 类定点名单(2026-08-08) > 互联网医院名单(2022) > 发热门诊名单(2020)。
目标：找出“系统=三级 但官方=二级/一级/未定级”的硬冲突（系统错标为过高等级）。
"""
import json, re

SNAP = 'web/snapshot_data.json'
d = json.load(open(SNAP, encoding='utf-8'))
inst = d['institutions']
by_name = inst

# ---------- 官方权威等级基准 ----------
# A类定点(2026-08-08)：59家，绝大多数为三级，2家二级
A_CLASS = {
    '三级': ['同仁医院','协和医院','北京医院','北京市第六医院','北京中医医院','普仁医院','积水潭','北京大学人民医院',
            '北京大学第一医院','复兴医院','阜外','宣武','友谊医院','健宫医院','广安门','中日友好','地坛','朝阳医院',
            '安贞','华信医院','垂杨柳','航空总医院','民航总','世纪坛','空军特色医学中心','航天中心医院',
            '北京大学第三医院','海淀医院','中关村医院','西苑医院','北京老年医院','天坛医院','电力医院','丰台医院',
            '通用航天医院','航天总医院','丰台右安门医院','佑安','博爱医院','首钢医院','石景山医院','昌平区医院',
            '小汤山医院','清华长庚','北大国际医院','燕化医院','良乡医院','潞河医院','顺义区医院','大兴区人民医院',
            '仁和医院','京煤集团总医院','平谷区医院','怀柔医院','密云区医院','延庆区医院'],
    '二级': ['北京市第二医院','北京市门头沟区医院'],
}
# 互联网医院名单(2022)：明确的非三级项（三级项已由A类覆盖或单独标注）
INTERNET = {
    '二级': ['北京航天总医院','高博博仁','京顺医院','丰台区中医医院'],
    '一级': ['三诺健恒'],
    '未定级': ['三博脑科'],
}
# 发热门诊名单(2020)中明确的二级项（A类未覆盖者）
FEVER = {
    '二级': ['监狱管理局清河分局医院','双桥医院','朝阳区中医医院','和睦家','四季青','上地医院','化工职业病',
            '清华大学医院','社会福利医院','水利医院','南苑医院','铁营医院','七三一医院'],
}

def match_level(name, kw_list):
    for kw in kw_list:
        if kw in name:
            return kw
    return None

# 建立 系统三级 -> 官方等级 映射（取最高优先级命中）
conflicts = []   # 系统三级 但官方更低
all_hits = []
for r in inst:
    if r['level'] != '三级':
        continue
    nm = r['name']
    off = None; src = None; kw = None
    # 1) A类优先
    for lv in ['三级','二级']:
        k = match_level(nm, A_CLASS[lv])
        if k:
            off, src, kw = lv, 'A类(2026)', k
            break
    # 2) 未命中A类 -> 互联网医院名单
    if off is None:
        for lv in ['二级','一级','未定级']:
            k = match_level(nm, INTERNET[lv])
            if k:
                off, src, kw = lv, '互联网医院(2022)', k
                break
    # 3) 未命中 -> 发热门诊名单
    if off is None:
        for lv in ['二级']:
            k = match_level(nm, FEVER[lv])
            if k:
                off, src, kw = lv, '发热门诊(2020)', k
                break
    if off is None:
        continue
    all_hits.append((r['id'], nm, r['district'], off, src, kw))
    if off != '三级':
        conflicts.append((r['id'], nm, r['district'], off, src, kw))

print('=== 系统三级 在官方名单中的命中（含一致项）===')
for (i, nm, dist, off, src, kw) in all_hits:
    print(f'  {off:<4} [{src:<14}] kw={kw:<14} {nm} (id={i})')
print()
print(f'=== 硬冲突：系统=三级 但官方=更低等级 ({len(conflicts)} 家) ===')
for (i, nm, dist, off, src, kw) in conflicts:
    print(f'  >>> 应改为【{off}】 [{src}] kw={kw} | {nm} (id={i}) [{dist}]')

# 反向：系统非三级 但 A类明确=三级（遗漏/低估）
print()
print('=== 反向：系统<三级 但 A类=三级（应升为三级）===')
for r in inst:
    if r['level'] == '三级':
        continue
    for kw in A_CLASS['三级']:
        if kw in r['name']:
            print(f'  >>> 系统={r["level"]} 应升【三级】[A类] kw={kw} | {r["name"]} (id={r["id"]})')
            break
