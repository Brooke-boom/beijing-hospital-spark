#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二轮口径同步：主表同名合并（9,789 → 9,678）之后的文档对齐。

## 与第一轮（sync_docs_metrics.py）的分工

第一轮同步的是「稀疏字段三路补全 + 等级适用范围纠偏」的产物
（电话 570→823、等级 922→942、应参评 955→967 等）。
本轮是**同一机构多写法合并**的产物，它把总数与各口径又推进了一步：

    机构总数   9,789 → 9,678
    应参评      967 → 874     （不适用 8,822 → 8,804）
    等级(适用)  942 → 849     （一级 505→480 / 二级 214→189 / 三级 223→180 / 未定级 25 不变）
    等级覆盖率 97.4% → 97.1%
    等次        255 → 223
    电话        823 → 815
    地址      8,762 → 8,706
    多来源机构 3,139 → 3,133

## ⚠️ 两条铁律

1. **「当前态描述」要改，「历史工作记录」不改。**
   「主表 9,789 家」「应参评 967 家」是当前态 → 改。
   「电话 570 → **823**」「等级 922 → **942**」是上一轮补全工作的**产出记录**
   → 保留原文，另起一段追加本轮变化。抹掉它们等于抹掉那轮工作的证据。

2. **时点文档一律不改正文**（`毕业论文_2026-09-06.md` 已标完成日期、
   `项目最终整改报告.md` 完成于 2026-09-20、`开发日志.md` 是追加式流水），
   只在末尾追加**带日期的更新块**。

用法：
    python3 etl/sync_docs_metrics_r2.py            # 预演，打印每处替换次数
    python3 etl/sync_docs_metrics_r2.py --apply    # 落盘
"""
import argparse
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

# ---------------------------------------------------------------------------
# 本轮定版口径（真源 = data/processed/master_institutions.csv 现算）
# ---------------------------------------------------------------------------
N_TOTAL = '9,678'
N_APPLIC = '874'
N_NONAPPLIC = '8,804'
LV1, LV2, LV3, LV0 = '480', '189', '180', '25'
N_LEVEL_OK = '849'
N_LEVELSUB = '223'
N_PHONE = '815'
N_ADDR = '8,706'
PCT = '97.1%'
PCT_HIGH = '54.9%'
PCT_MID = '21.6%'
PCT_LOW = '20.6%'
PCT_NONE = '2.9%'
N_APPLIC_PCT = '9.0%'
N_MULTISRC = '3,133'

# 活文档：正文里的「当前态」数字需要跟着走
LIVE = ['README.md', 'docs/毕业论文.md', 'docs/项目说明书.md',
        'docs/功能点-代码对应表.md', 'docs/项目文件说明与系统演示指南.md',
        'docs/答辩与简历讲解手册.md', 'docs/毕业答辩问题库.md',
        'docs/数据联网核实报告.md', 'docs/论文大纲.md', 'docs/系统运行流程.md']
# 时点文档 / 追加式流水：只追加，不改正文
FROZEN = ['docs/毕业论文_2026-09-06.md', 'docs/项目最终整改报告.md',
          'docs/开发日志.md']

# ---------------------------------------------------------------------------
# 替换表：(相对路径 或 '*', 旧文本, 新文本)
#   path='*' 表示对全部 LIVE 生效；替换**不做正则**，逐字面匹配。
# ---------------------------------------------------------------------------
PAIRS = [
    # ---- 机构总数（当前态） ----
    ('*', '9,789', N_TOTAL),
    ('*', '9789', N_TOTAL.replace(',', '')),
    # ---- 等级适用范围口径（当前态） ----
    ('*', '8,822', N_NONAPPLIC),
    ('*', '应参评 967 家', f'应参评 {N_APPLIC} 家'),
    ('*', '应参评 **967**', f'应参评 **{N_APPLIC}**'),
    ('*', '（应参评 967', f'（应参评 {N_APPLIC}'),
    ('*', '**967 家（9.9%）属应参评机构**', f'**{N_APPLIC} 家（{N_APPLIC_PCT}）属应参评机构**'),
    ('*', '应参评机构 955 家', f'应参评机构 {N_APPLIC} 家'),
    ('*', '应参评机构（967 家）', f'应参评机构（{N_APPLIC} 家）'),
    # ---- 等级分布（当前态） ----
    ('*', f'一级 505 家（52.2%）、二级 214 家（22.1%）、三级 223 家（23.1%）、未定级 25 家（2.6%）',
     f'一级 {LV1} 家（{PCT_HIGH}）、二级 {LV2} 家（{PCT_MID}）、三级 {LV3} 家（{PCT_LOW}）、未定级 {LV0} 家（{PCT_NONE}）'),
    ('*', f'一级 505 家、二级 214 家、三级 223 家、未定级 25 家',
     f'一级 {LV1} 家、二级 {LV2} 家、三级 {LV3} 家、未定级 {LV0} 家'),
    ('*', f'一级 480 家、二级 189 家、三级 180 家、未定级 25 家',
     f'一级 {LV1} 家、二级 {LV2} 家、三级 {LV3} 家、未定级 {LV0} 家'),
    ('*', f'一级 **505** / 二级 **214** / 三级 **223** / 未定级 **25**',
     f'一级 **{LV1}** / 二级 **{LV2}** / 三级 **{LV3}** / 未定级 **{LV0}**'),
    ('*', f'一级 **505** / 二级 **214** / 三级 **223**',
     f'一级 **{LV1}** / 二级 **{LV2}** / 三级 **{LV3}**'),
    ('*', f'三级 223 / 二级 214 / 一级 505 / 未定级 25',
     f'三级 {LV3} / 二级 {LV2} / 一级 {LV1} / 未定级 {LV0}'),
    ('*', f'三级 223 / 二级 214 / 一级 505',
     f'三级 {LV3} / 二级 {LV2} / 一级 {LV1}'),
    ('*', f'一级 505 / 二级 214 / 三级 223', f'一级 {LV1} / 二级 {LV2} / 三级 {LV3}'),
    ('*', f'一级 498 家（52.1%）', f'一级 {LV1} 家（{PCT_HIGH}）'),
    ('*', f'三级 212 家（22.2%）', f'三级 {LV3} 家（{PCT_LOW}）'),
    ('*', f'二级 212 家（22.2%）', f'二级 {LV2} 家（{PCT_MID}）'),
    # ---- 覆盖率 / 补全数（当前态） ----
    ('*', '97.4%', PCT),
    ('*', '等级非空 942 家', f'等级非空 {N_LEVEL_OK} 家'),
    ('*', '**942**', f'**{N_LEVEL_OK}**'),
    ('*', '3,139', N_MULTISRC),
]

# 上一轮补全工作的产出记录：出现在这些上下文里的数字属**历史**，不动
HISTORY_GUARD = ['570（5.8%）', '570 → ', '922 | **', '| 922 ', '175 → ', '| 175 ',
                 '→ **823', '→ **942', '→ **255']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    files = {}
    for p in LIVE:
        if os.path.exists(p):
            files[p] = io.open(p, encoding='utf-8').read()
        else:
            print(f'  ！缺失：{p}')

    stat = {}
    for path, old, new in PAIRS:
        if old == new:
            continue
        targets = LIVE if path == '*' else [path]
        for p in targets:
            if p not in files:
                continue
            text = files[p]
            n = text.count(old)
            if not n:
                continue
            # 历史记录保护：本文件中该片段若只出现在历史上下文里则跳过
            if any(g in text and old in g for g in HISTORY_GUARD):
                stat.setdefault(p, []).append(f'跳过(历史) {old[:26]}')
                continue
            files[p] = text.replace(old, new)
            stat.setdefault(p, []).append(f'{old[:30]} → {new[:30]} ×{n}')
            if args.apply:
                io.open(p, 'w', encoding='utf-8').write(files[p])

    total = sum(len(v) for v in stat.values())
    print(f'\n=== 命中 {len(stat)} 个文件 / {total} 类替换 ===')
    for p in sorted(stat):
        print(f'\n{p}')
        for line in stat[p]:
            print(f'    {line}')

    if not args.apply:
        print('\n[预演] 未写入。加 --apply 落盘。')
    else:
        print(f'\n[落盘] 已更新 {len(stat)} 个文件。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
