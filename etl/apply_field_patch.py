#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字段补全回写主表（第二轮：把三路补丁合并进 master_institutions.csv）

三路来源（按可信度排序，同字段冲突时高者胜）：
  1. 源文件回收   data/processed/source_field_patch.csv
     —— 公卫数据源里本来就有、合并阶段被丢掉的列（电话/等级/等次/床位/交通/官网）
  2. 联网·好大夫  data/processed/haodf_contacts.jsonl（经 haodf_match.csv 映射到 inst_id）
     —— 北京 435 家医院详情页的电话与自述等级
  3. 联网·百科    data/processed/baike_field_patch.csv
     —— 既有百科词条 infobox 里的「医院等级」（此前只用了经营性质）

铁律（宁缺勿伪）
--------------
* **只填空，不覆盖**。已有值的字段一律跳过 —— 那是在线核实或官方名单结果，
  新来源没有资格推翻它们。
* 等级**冲突**的（主表三级 vs 来源二级）整条丢弃并记入报告，不自动改。
* 不写"未收录""无"之类的占位值 —— 空就是空，前端按"未收录"展示。
* 机构类型属于诊所 / 村卫生室 / 门诊部 / 社区卫生服务站 / 医务室 / 护理站的，
  按《机构基本标准》以诊疗科目执业、**不设医院等级建制**，任何来源的等级值都不采。

回写字段与溯源
--------------
  phone / traffic / website / beds  —— 逐值溯源在补丁 CSV 与报告里（不新增主表列，
                                        避免改动数仓与论文里已写定的表结构口径）
  level                              —— 同时写 level_src（既有列）
  level_sub                          —— 在线来源写 level_sub_online，文件来源写 level_src

产出
----
  data/processed/master_institutions.csv（原地更新，先备份）
  data/processed/govern_report_field_apply.md
  data/归档_旧版命名/processed_backup/master_institutions.csv.<时间戳>.bak

用法：
  python etl/apply_field_patch.py            # 演练，不落盘
  python etl/apply_field_patch.py --apply    # 真写
"""
import collections
import csv
import json
import os
import re
import shutil
import sys
from datetime import datetime

BASE = os.path.expanduser('~/Desktop/毕设')
PROC = os.path.join(BASE, 'data', 'processed')
MASTER = os.path.join(PROC, 'master_institutions.csv')
BAKDIR = os.path.join(BASE, 'data', '归档_旧版命名', 'processed_backup')
REPORT = os.path.join(PROC, 'govern_report_field_apply.md')

PATCHES = [
    (os.path.join(PROC, 'source_field_patch.csv'), 90, '源文件回收'),
    (os.path.join(PROC, 'baike_field_patch.csv'), 70, '联网·百科'),
]

NOT_RATED = {'诊所', '村卫生室', '门诊部', '社区卫生服务站', '医务室', '护理站'}
TARGET_FIELDS = ['phone', 'level', 'level_sub', 'traffic', 'key_depts', 'beds', 'website']


def load_master():
    with open(MASTER, newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        return list(r), list(r.fieldnames)


def main():
    apply = '--apply' in sys.argv
    rows, cols = load_master()
    by_id = {r['id']: r for r in rows}

    cand = []          # (inst_id, field, value, source, weight, how)
    for path, w, tag in PATCHES:
        if not os.path.exists(path):
            continue
        for r in csv.DictReader(open(path, encoding='utf-8-sig')):
            cand.append((r['inst_id'], r['field'], r['value'], '%s:%s' % (tag, r['src_file']), w, r['match']))

    # 好大夫：经 haodf_match.csv 映射（与科室补全用同一套匹配结论，不重新匹配一遍）
    hm = os.path.join(PROC, 'haodf_match.csv')
    if os.path.exists(hm) and os.path.exists(os.path.join(PROC, 'haodf_contacts.jsonl')):
        id_of = {}
        for r in csv.DictReader(open(hm, encoding='utf-8-sig')):
            id_of[str(r['hid'])] = r['inst_id']
        for line in open(os.path.join(PROC, 'haodf_contacts.jsonl'), encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            iid = id_of.get(str(o.get('hid')))
            if not iid:
                continue
            for fld in ('phone', 'level', 'traffic', 'addr'):
                v = (o.get(fld) or '').strip()
                if not v:
                    continue
                if fld == 'addr':
                    continue                    # 地址已有 89.5% 覆盖，且主表地址经过标准化，不回写
                cand.append((iid, fld, v, '联网·好大夫在线', 80, 'haodf'))
            if o.get('level') and o.get('level_sub'):
                cand.append((iid, 'level_sub', o['level_sub'], '联网·好大夫在线', 80, 'haodf'))

    # 只填空 + 冲突检测
    filled = collections.Counter()
    skipped_has = collections.Counter()
    conflicts = []
    not_rated_blocked = []
    applied = []           # (inst_id, field, old, new, source)

    # 同一 (id, field) 取权重最高；权重同取更长值（信息更多）
    best = {}
    for iid, fld, val, src, w, how in cand:
        if fld not in TARGET_FIELDS:
            continue
        k = (iid, fld)
        cur = best.get(k)
        if cur is None or (w, len(val)) > (cur[4], len(val)):
            best[k] = (iid, fld, val, src, w, how)

    for (iid, fld), (_, _, val, src, w, how) in sorted(best.items()):
        r = by_id.get(iid)
        if r is None:
            continue
        if fld in ('level', 'level_sub') and (r.get('category') or '') in NOT_RATED:
            not_rated_blocked.append((r['name'], r.get('category'), fld, val, src))
            continue
        old = (r.get(fld) or '').strip()
        if old:
            if fld == 'level' and old != val:
                conflicts.append((r['name'], old, val, src))
            skipped_has[fld] += 1
            continue
        # level 的填法：同时写 level_src；等次依来源写不同列
        if fld == 'level':
            r['level'] = val
            r['level_src'] = '补全:%s' % src
        elif fld == 'level_sub':
            r['level_sub'] = val
            if '联网' in src:
                r['level_sub_online'] = val
            else:
                r['level_src'] = '补全:%s' % src
        else:
            r[fld] = val
        filled[fld] += 1
        applied.append((r['name'], fld, old, val, src))

    # ---------------- 报告 ----------------
    before = {}
    for f in TARGET_FIELDS:
        before[f] = None
    # before 需要"补前"的家数：已填的都算新增，故 before = 当前非空 - 本次新增
    now = {f: sum(1 for r in rows if (r.get(f) or '').strip()) for f in TARGET_FIELDS}

    L = ['# 字段补全回写报告', '',
         '生成时间：%s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
         '模式：%s' % ('**已写回主表**' if apply else '演练（未落盘）'), '',
         '## 一、本次补了多少（只填空，不覆盖）', '',
         '| 字段 | 补前非空 | 本次新增 | 补后非空 | 主表 %d 家中的占比 |' % len(rows),
         '|---|---:|---:|---:|---:|']
    for f in TARGET_FIELDS:
        n_old = now[f] - filled[f]
        n_new = now[f]
        L.append('| %s | %d | **+%d** | %d | %.1f%% |'
                 % (f, n_old, filled[f], n_new, n_new / len(rows) * 100))
    L += ['', '## 二、因为主表已有值而跳过（不覆盖）', '',
          '| 字段 | 跳过条数 |', '|---|---:|']
    for f in TARGET_FIELDS:
        L.append('| %s | %d |' % (f, skipped_has[f]))
    L += ['', '## 三、等级冲突：不自动改，留待人工确认', '',
          '| 机构 | 主表现值 | 来源值 | 来源 |', '|---|---|---|---|']
    for nm, a, b, s in conflicts[:120]:
        L.append('| %s | %s | %s | %s |' % (nm, a, b, s))
    if not conflicts:
        L.append('| —— | | | |')
    L += ['', '共 %d 条。处理原则：主表值来自卫健委 / 医保局名单，来源值多为百科或平台自述，' % len(conflicts),
          '不构成推翻依据，因此只记录不修改。', '',
          '## 四、被"等级适用范围"守卫拦下的（六类基层机构不设医院等级建制）', '',
          '共 %d 条。示例：' % len(not_rated_blocked)]
    for nm, cat, fld, val, src in not_rated_blocked[:20]:
        L.append('- %s（%s）%s=%s ← %s' % (nm, cat, fld, val, src))
    L += ['', '## 五、明细（前 200 条）', '',
          '| 机构 | 字段 | 原值 | 新值 | 来源 |', '|---|---|---|---|---|']
    for nm, fld, old, val, src in applied[:200]:
        L.append('| %s | %s | %s | %s | %s |' % (nm, fld, old or '（空）', val, src))
    L += ['', '## 六、口径', '',
          '- **只填空**：主表已有值一律跳过。已有值来自卫健委 / 医保局名单或此前的在线核实，',
          '  新来源没有资格覆盖它们。',
          '- **不写占位值**：不填"未收录 / 无 / —"，空就是空，前端按「未收录」展示。',
          '- **等级适用范围守卫**：诊所 / 村卫生室 / 门诊部 / 社区卫生服务站 / 医务室 / 护理站',
          '  六类按《医疗机构基本标准》以诊疗科目核准执业，不设医院等级建制，任何来源的等级都不采。',
          '- 逐值溯源在 `source_field_patch.csv` / `baike_field_patch.csv` / `haodf_contacts.jsonl`',
          '  三份文件里（含匹配方式 exact/core/alias/contain/suffix，可逐条复核）。']

    open(REPORT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')

    print('候选补丁 %d 条 → 去重后 %d 条' % (len(cand), len(best)))
    for f in TARGET_FIELDS:
        print('  %-10s 新增 %4d  跳过(已有值) %4d  → 补后 %d' % (f, filled[f], skipped_has[f], now[f]))
    print('  等级冲突 %d 条（不覆盖）| 等级适用范围拦截 %d 条' % (len(conflicts), len(not_rated_blocked)))
    print('✓ %s' % REPORT)

    if not apply:
        print('\n（演练模式，未写盘。加 --apply 真正写回）')
        return 0

    os.makedirs(BAKDIR, exist_ok=True)
    bak = os.path.join(BAKDIR, 'master_institutions.csv.%s.bak'
                       % datetime.now().strftime('%Y%m%d_%H%M%S'))
    shutil.copy2(MASTER, bak)
    with open(MASTER, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print('  ✓ 备份 → %s' % bak)
    print('  ✓ 已写回 %s' % MASTER)
    return 0


if __name__ == '__main__':
    sys.exit(main())
