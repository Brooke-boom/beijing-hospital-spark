#!/usr/bin/env python3
"""用 national_specialty 反向校验并补全 feature 字段

背景：feature_level=1 的 68 家重点专科医院中，部分综合医院 feature 字段
内容稀疏（如北京医院只写"老年病科"，但国家临床重点专科实际有 9 个）。
本次用 build_specialty_enhanced.py 联网补充的 national_specialty 字段
反向校验，将 national 中存在但 feature 中缺失的专科自动追加到 feature。

策略：只对 L1 重点专科（feature_level=1）+ national_specialty>0 的医院执行；
按专科名归一化后做集合差，差集里的专科追加到 feature（用 "；" 分隔符），
去重后保留原有顺序的扩展。

输出：
- /Users/brooke/Desktop/毕设/data/processed/backup/master_institutions.before_feat_backfill.csv
- /Users/brooke/Desktop/毕设/data/processed/master_institutions.csv（覆盖）
- /Users/brooke/Desktop/毕设/data/processed/govern_report_feat_backfill.md
"""
import csv
import os
import re
from collections import Counter

ROOT = '/Users/brooke/Desktop/毕设/data/processed'
MASTER = os.path.join(ROOT, 'master_institutions.csv')
BACKUP = os.path.join(ROOT, 'backup', 'master_institutions.before_feat_backfill.csv')
REPORT = os.path.join(ROOT, 'govern_report_feat_backfill.md')

# 专科名归一化：去括号、去尾部"中心/诊疗中心"，保留尾部"科"以区分分类
NOISE_PATTERNS = [
    r'（[^）]*）',  # 全角括号
    r'\([^)]*\)',   # 半角括号
    r'\s+',
]


def norm_spec(s: str) -> str:
    if not s:
        return ''
    s = s.strip()
    for p in NOISE_PATTERNS:
        s = re.sub(p, '', s)
    # 去尾部"诊疗中心"再"中心"
    for suf in ['诊疗中心', '中心']:
        if s.endswith(suf):
            s = s[:-len(suf)]
            break
    return s.strip()


def is_equiv(a: str, b: str) -> bool:
    """两个归一化专科名是否等价（含子串包含以处理"心血管科" vs "心血管内科"）"""
    if not a or not b:
        return False
    if a == b:
        return True
    # 子串包含：至少一方包含另一方（最短长度>=2 防止单字误判）
    if len(min(a, b, key=len)) >= 2 and (a in b or b in a):
        return True
    return False


def any_equiv(s: str, group) -> bool:
    return any(is_equiv(s, x) for x in group)


def split_specs(s: str) -> list:
    """分号/中文逗号/英文逗号/中文顿号/斜杠 拆分"""
    if not s:
        return []
    parts = re.split(r'[；;,，、/／；]', s)
    return [p.strip() for p in parts if p.strip()]


def main():
    # 备份
    if not os.path.exists(BACKUP):
        import shutil
        shutil.copy2(MASTER, BACKUP)
        print(f'[backup] {BACKUP}')

    with open(MASTER, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys())

    # 仅处理 L1 + national_specialty>0 的医院
    target = [r for r in rows
              if r.get('feature_level') == '1'
              and int(r.get('national_specialty_count', '0') or '0') > 0]

    print(f'目标医院: {len(target)} 家（L1 + national>0）')

    filled_count = 0
    new_specs_total = 0
    sample_log = []

    for r in target:
        old_feat = r.get('feature', '').strip()
        nat = r.get('national_specialty', '').strip()
        if not nat:
            continue
        old_specs = split_specs(old_feat)
        new_specs = split_specs(nat)
        old_keys = [norm_spec(s) for s in old_specs if norm_spec(s)]
        new_keys = [norm_spec(s) for s in new_specs if norm_spec(s)]

        # 求差集：national 中有且 feature 中等价的都不算
        diff_ordered = []
        for s, k in zip(new_specs, new_keys):
            if not k or len(k) < 2:
                continue
            if any_equiv(k, old_keys):
                continue
            # 已在 diff 中？
            if any(is_equiv(k, dd) for dd, _ in diff_ordered):
                continue
            diff_ordered.append((k, s))
        if not diff_ordered:
            continue

        # 按 national 原顺序追加（已按上一步保持）
        appended = [s for _, s in diff_ordered]
        merged = old_specs + appended

        # 去重：按归一化键做等价去重，保留先出现者
        seen_keys = []
        uniq = []
        for s in merged:
            k = norm_spec(s)
            if not k:
                continue
            if any(is_equiv(k, x) for x in seen_keys):
                continue
            seen_keys.append(k)
            uniq.append(s)
        new_feat = '；'.join(uniq)
        if new_feat != old_feat:
            r['feature'] = new_feat
            filled_count += 1
            new_specs_total += len(appended)
            sample_log.append({
                'id': r['id'], 'name': r['name'],
                'old_feature': old_feat[:80],
                'new_feature': new_feat[:120],
                'appended': appended,
            })

    # 写回
    with open(MASTER, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f'已补全: {filled_count} 家 / 新增专科片段: {new_specs_total} 条')
    print(f'\n=== 详情（前 8 家）===')
    for s in sample_log[:8]:
        print(f"  [{s['id']:>4s}] {s['name'][:20]:20s}")
        print(f"    旧: {s['old_feature']}")
        print(f"    新: {s['new_feature']}")
        print(f"    追加: {'；'.join(s['appended'])}")
        print()

    # 生成报告
    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write(f"""# feature 字段反向补全报告（2026-09-06）

## 背景
主表 `feature` 字段是「擅长科室」分级的权威口径（L1 重点专科 / L2 优势科室 / L3 诊疗科室）。
68 家 `feature_level=1` 的医院中，部分综合医院的 `feature` 字段内容稀疏（如
北京医院只写"老年病科"，但实际国家临床重点专科有 9 个），原因是早期抓取时源数据
只写了科室名 1-2 个。

本次用上一轮联网补充的 `national_specialty` 字段（43 家医院、229 条国家级
临床重点专科记录，含专科名+批次+负责人）反向校验，自动把 `national` 中存在
但 `feature` 中缺失的专科追加到 `feature`，让两份数据口径自洽。

## 范围
- 仅处理 `feature_level='1'` AND `national_specialty_count > 0` 的医院：{len(target)} 家
- 备份：`data/processed/backup/master_institutions.before_feat_backfill.csv`
- 主表：`master_institutions.csv`（覆盖）

## 处理策略
1. 按 `；`/`,`/`，`/`/`；` 等分隔符拆 `feature` 和 `national_specialty`
2. 归一化：去括号、去尾部"中心/诊疗中心"、去空白
3. 求差集：`national_set - feature_set`，只追加长度 ≥2 的专科
4. 合并保留原顺序 + 按 national 顺序追加；最终按归一化名去重

## 结果
- 已补全医院: **{filled_count}** 家
- 新增专科片段: **{new_specs_total}** 条
""")

        f.write('\n## 详情\n\n')
        f.write('| id | 医院 | 旧 feature | 新 feature（新增部分） |\n')
        f.write('|---|---|---|---|\n')
        for s in sample_log:
            f.write(f"| {s['id']} | {s['name']} | {s['old_feature'][:40]} | +{'; '.join(s['appended'])} |\n")

    print(f'\n[report] {REPORT}')


if __name__ == '__main__':
    main()