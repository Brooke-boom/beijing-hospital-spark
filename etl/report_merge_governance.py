#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成**完整版**主表同名合并治理报告（`data/processed/govern_report_dedup_full.md`）。

## 为什么需要这个脚本

`etl/merge_dup_institutions.py --apply` 每次运行都会重写
`data/processed/govern_report_dedup.md` —— 于是**第二次运行时，
第一轮的 105 条合并明细被覆盖掉了**，报告只剩「净减 6 条」。

那份报告本该是「还有没有类似情况」的唯一凭据，被覆盖等于审计链断了。
本脚本改为**从 `data/processed/dedup_rules.json`（完整计划，不随运行覆盖）
＋ 补前备份与现表求差集（权威校验）**重建一份覆盖全过程的报告。

用法：
    python3 etl/report_merge_governance.py
"""
import csv
import io
import json
import os
import sys
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

RULES = 'data/processed/dedup_rules.json'
CUR = 'data/processed/master_institutions.csv'
OUT = 'data/processed/govern_report_dedup_full.md'
# 补前基线：这份是 9,789 版（治理前）
BEFORE_CANDIDATES = [
    'data/归档_旧版命名/processed_backup/master_institutions.20260922_175721.csv',
    'data/归档_旧版命名/processed_backup/master_institutions.20260922_175859.csv',
    'data/归档_旧版命名/processed_backup/master_institutions_20260922_165158.csv',
]


def load(path):
    with io.open(path, encoding='utf-8-sig') as f:
        return {r['id']: r for r in csv.DictReader(f)}


def pick_before():
    for p in BEFORE_CANDIDATES:
        if os.path.exists(p) and len(load(p)) > 9000:
            return p
    return None


def main():
    if not os.path.exists(RULES):
        print('✗ 缺少 %s（先跑 etl/merge_dup_institutions.py --gen）' % RULES)
        return 1
    plan = json.load(io.open(RULES, encoding='utf-8'))
    cur = load(CUR)
    before_path = pick_before()
    before = load(before_path) if before_path else {}

    removed = sorted((i for i in before if i not in cur), key=int)
    added = sorted((i for i in cur if i not in before), key=int)
    n_before, n_after = len(before) or plan['total_before'], len(cur)

    L = []
    A = L.append
    A('# 主表同名合并治理报告（完整版）')
    A('')
    A('> 由 `etl/report_merge_governance.py` 从 `dedup_rules.json` + 补前备份与现表差集重建。')
    A('> **完整覆盖 9,%s → 9,%s 的全过程**，不受"每次运行覆盖上一次报告"影响。'
      % (str(n_before)[1:], str(n_after)[1:]))
    A('')
    A('## 一、口径与摘要')
    A('')
    A('**口径：合并挂牌名、保留院区。**')
    A('')
    A('| 项目 | 值 |')
    A('|---|---:|')
    A('| 治理前 | %s |' % f'{n_before:,}')
    A('| 治理后 | %s |' % f'{n_after:,}')
    A('| 净减 | **%d** |' % (n_before - n_after))
    A('| 合并删除 | %d |' % len(removed))
    A('| 拆分新增 | %d |' % len(added))
    A('| 自动合并组 | %d |' % len(plan['rules']))
    A('| 院区保留组 | %d |' % len(plan['skips']))
    A('')
    A('净减 = 合并删除 − 拆分新增：**%d − %d = %d** ✓' % (len(removed), len(added), len(removed) - len(added)))
    A('')
    A('### 根因')
    A('')
    A('不是数据缺失，是**源文件「一行登记多块牌子」+ 主表去重键失效**：')
    A('')
    A('- 源文件（医保定点名单等）把一家机构挂的多块牌子全写在一行；')
    A('- `etl/clean_merge.py` 的 `norm_name()` 只做「去空白 + 全角括号转半角 + 去『北京市』前缀」，')
    A('  同一机构的不同写法算出**不同的 key**，`groupby("name_key")` 形同虚设。')
    A('')

    # ---- 二、全部合并组 ----
    A('## 二、全部自动合并组（%d 组）' % len(plan['rules']))
    A('')
    A('判据：`core_of()` 剥括注 → 取首个并列段 → 去「北京市」→ 归一化后相同，')
    A('且不属于院区/部门形态。')
    A('')
    A('| # | 保留 id | 保留名 | 并入 | 被并入的记录 |')
    A('|---:|---|---|---:|---|')
    for i, g in enumerate(plan['rules'], 1):
        merges = g.get('merge') or []
        names = '<br>'.join('%s · %s' % (m.get('id'), m.get('name', '')) for m in merges)
        A('| %d | %s | %s | %d | %s |'
          % (i, g.get('keep_id'), g.get('keep_name'), len(merges), names))
    A('')

    # ---- 三、院区保留 ----
    A('## 三、院区·部门（既有口径保留，不参与合并）')
    A('')
    A('这些是**同一法人的不同执业地点或内设部门**，合并会丢信息。')
    A('')
    for s in plan['skips']:
        kept = '；'.join('%s %s' % (k.get('id'), k.get('name')) for k in s.get('kept', []))
        A('- **%s** —— %s｜%s' % (s.get('core'), s.get('reason'), kept))
    A('')
    A('> ⚠️ 形态上容易误判的是「××镇社区卫生服务中心」这类**规范括注**')
    A('> （如 `北京四季青医院（北京市海淀区四季青镇社区卫生服务中心）`）——')
    A('> 它长得像别名，其实是院区/分支机构，按院区保留。')
    A('')

    # ---- 四、改名保留 ----
    A('## 四、改名保留（主表无独立记录，合并即永久丢失 → 改为保留并纠正类别）')
    A('')
    A('`RENAME_RULES` 的元组是 `(保留名称, 类别纠正值, 说明)`；类别纠正值为 `—` 表示无需纠正。')
    A('')
    A('| 源 id | 保留名称 | 类别纠正 | 说明 |')
    A('|---|---|---|---|')
    for rid, v in (plan.get('rename') or {}).items():
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            nm = v[0] or '—'
            cat = v[1] or '—（不改）'
            why = v[2] if len(v) > 2 else ''
            A('| %s | %s | %s | %s |' % (rid, nm, cat, why))
        else:
            A('| %s | %s | — | — |' % (rid, v))
    A('')
    for nm, spec in (plan.get('merge_rename') or {}).items():
        if isinstance(spec, dict):
            A('- 合并+正名：`%s` ← id %s（%s）'
              % (nm, ' / '.join(spec.get('ids', [])), spec.get('reason', '')))
        else:
            A('- 合并+正名：`%s` → %s' % (nm, spec))
    A('')

    # ---- 五、拆分 ----
    A('## 五、拆分（一行实为两家独立机构）')
    A('')
    for rid, v in (plan.get('split') or {}).items():
        A('- `%s` → %s' % (rid, json.dumps(v, ensure_ascii=False)))
    A('')

    # ---- 六、逐条清单 ----
    A('## 六、被合并删除的记录（逐条，共 %d 条）' % len(removed))
    A('')
    A('> 这是「还有没有类似情况」的直接答案。按区统计：')
    A('')
    for d, c in Counter(before[i].get('district') or '(空)' for i in removed).most_common():
        A('- %s：%d 条' % (d, c))
    A('')
    A('| id | 机构名 | 区 |')
    A('|---|---|---|')
    for i in removed:
        A('| %s | %s | %s |' % (i, before[i].get('name', ''), before[i].get('district', '')))
    A('')
    if added:
        A('## 七、拆分新增的记录')
        A('')
        A('| id | 机构名 | 区 |')
        A('|---|---|---|')
        for i in added:
            A('| %s | %s | %s |' % (i, cur[i].get('name', ''), cur[i].get('district', '')))
        A('')

    A('## 八、待补录机构（留档，不臆造）')
    A('')
    A('这些名字与主记录**不是同一家**（不同法人或不同执业地点），本轮未单独建条 ——')
    A('凭名字臆造地址电话违反「宁缺勿伪」。留档待联网核实后补录。')
    A('')
    A('| 机构名 | 来源 id | 区 | 说明 |')
    A('|---|---|---|---|')
    A('| 北京市海淀区老年康复医院 | 1504 / 3936 | 海淀区 | 中关村医院行把它带进了名字；本身是区属独立机构 |')
    A('| 北京市东城区交道口社区卫生服务中心 | 3703 | 东城区 | 第六医院举办；主表无独立记录 |')
    A('| 北京市东城区北新桥社区卫生服务中心 | 3703 | 东城区 | 第六医院举办；主表无独立记录 |')
    A('| 北京市东城区景山社区卫生服务中心 | 3704 / 3705 | 东城区 | 隆福医院举办；主表无独立记录 |')
    A('| 北京市海淀区四季青镇社区卫生服务中心 | 3935 | 海淀区 | 四季青医院举办；主表无独立记录 |')
    A('| 北京市怀柔区汤河口镇社区卫生服务中心 | 3832 | 怀柔区 | 怀柔二院举办；主表无独立记录 |')
    A('| 北京市顺义区后沙峪镇社区卫生服务中心 | 3981 | 顺义区 | 空港医院举办；主表无独立记录 |')
    A('| 北京市顺义区牛栏山社区卫生服务中心 | 3983 | 顺义区 | 顺义三院举办；主表无独立记录 |')
    A('| 北京市平谷区牙病防治所 | 1657 | 平谷区 | 与平谷妇幼保健院合署 |')
    A('')
    A('## 九、复现方式')
    A('')
    A('```bash')
    A('python3 etl/audit_name_multibrand.py            # 只读审计：怪名 + core 冲突分组')
    A('python3 etl/merge_dup_institutions.py --dry-run # 预演')
    A('python3 etl/merge_dup_institutions.py --apply   # 落盘（幂等，自动重跑 grade_scope）')
    A('python3 etl/report_merge_governance.py          # 重建本报告')
    A('```')
    A('')
    A('接入：`scripts/run_pipeline.sh` 第 0.5 步，**必须在 `upload_to_hdfs` 之前**。')
    A('')

    io.open(OUT, 'w', encoding='utf-8').write('\n'.join(L))
    print('✓ %s' % OUT)
    print('  治理前 %s → 治理后 %s（净减 %d = 删 %d − 增 %d）'
          % (f'{n_before:,}', f'{n_after:,}', n_before - n_after, len(removed), len(added)))
    print('  自动合并组 %d / 院区保留 %d / 改名 %d / 拆分 %d'
          % (len(plan['rules']), len(plan['skips']), len(plan.get('rename') or {}), len(plan.get('split') or {})))
    return 0


if __name__ == '__main__':
    sys.exit(main())
