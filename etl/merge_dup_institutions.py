#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主表「一名多机构 / 同机构多写法」的受控合并（2026-09-22）。

## 为什么需要这个环节

源数据（`市医保局-区属二三级定点医疗机构.csv`、`顺义区定点医疗机构名单.csv`、
`医疗保险定点医疗机构名单.csv` 等）采用**一行登记多块牌子**的写法，例如：

    北京市中关村医院（中国科学院中关村医院）、北京市海淀区老年康复医院

`clean_merge.py` 把整串照搬进 `name`。更关键的是它的去重键 `norm_name()`
只做「去空白 + 全角括号转半角 + 去『北京市』前缀」，因此**同一家机构的不同写法
会算出不同的 key**，`groupby("name_key")` 形同虚设：

    key A = 中关村医院(中国科学院中关村医院)                          → id 1503
    key B = 中关村医院(中国科学院中关村医院)、北京市海淀区老年康复医院   → id 1504
    key C = …、…、海淀区中关村社区卫生服务中心                        → id 3936

后果不只是「名字难看」：同一家机构占掉排序榜多个席位；`3936` 的类别还被
判成「社区卫生服务中心」却带「三级」等级；`330` 更是把**两家不同机构**
（丰台区心理卫生中心 / 丰台区精神卫生防治院）合成一条，两家同时消失。

## 设计取舍

**不改 `clean_merge.py` 的核心去重**——它上接入湖与 DWD/DWS，改动面太大。
改为在此处加一道**受控合并**：规则由判据自动生成、落盘成
`data/processed/dedup_rules.json`，人工可审、可改、可复现。

合并铁律（与 `apply_field_patch.py` 同源）：
  · **只填空，不覆盖** —— 保留行的已有值一律不动；
  · 名称一律取**保留行**的名字，合并行的名字只进备注；
  · `source_files` 取并集（来源溯源不能丢）；
  · **不重排 id** —— id 已被前端与其他表引用，删行后原 id 保持不动，
    新增行（拆分产生的）取 `max(id)+1` 递增。

## 两类例外

1. **院区·部门**（`（东院区）` `（西院区）` `（回龙观院区）` `（南区）` …）：
   属**不同执业地点**，本项目既有口径按独立记录保留 —— 本脚本**整条跳过**。
2. **主表里没有独立记录的主名**（如 `3937 北京市海淀区妇幼保健院`）：
   直接删会**丢机构**，因此改为**改名保留**，见 `RENAME_RULES`。

用法：
    python3 etl/merge_dup_institutions.py --gen      # 生成规则草案
    python3 etl/merge_dup_institutions.py --dry-run  # 按规则预演
    python3 etl/merge_dup_institutions.py --apply    # 落盘（先备份）
"""
import argparse
import collections
import csv
import json
import os
import re
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "data", "processed", "master_institutions.csv")
RULES = os.path.join(ROOT, "data", "processed", "dedup_rules.json")
BACKUP_DIR = os.path.join(ROOT, "data", "归档_旧版命名", "processed_backup")
REPORT = os.path.join(ROOT, "data", "processed", "govern_report_dedup.md")

PAREN = re.compile(r"[（(][^（()）]*[）)]")
SPLIT = re.compile(r"[、；;，,／/]+|\s+|\u3000")

# 院区 / 内设部门：不同执业地点，既有口径保留，不参与合并
CAMPUS_RE = re.compile(r"院区|东院|西院|南院|北院|东区|西区|南区|北区|分院|总院|分部")

# 标量字段：保留行为空时才用合并行的值填
FILL_COLS = [
    "district", "addr", "phone", "postal", "beds", "traffic", "website",
    "econ", "profit", "ownership", "ownership_basis", "category_sub",
    "feature", "feature_level", "level", "level_sub",
    "net_pediatric", "net_stroke", "net_neonatal", "net_maternal",
    "dept_count_online", "dept_count_src", "ownership_online", "ownership_src",
    "level_online", "level_sub_online", "level_src", "baike_src", "specialty_src",
]
# 顿号分隔的列表字段：取并集
UNION_COLS = ["key_depts", "baike_key_depts", "national_specialty", "municipal_specialty"]
# 计数列：并集后重算
COUNT_COLS = ["national_specialty_count", "municipal_specialty_count"]

EMPTY = ("", "nan", "None", "未收录", "无")


# ---------------------------------------------------------------------------
# 规则生成
# ---------------------------------------------------------------------------
def strip_paren(name):
    prev = None
    while prev != name:
        prev = name
        name = PAREN.sub("", name)
    return name


def core_of(name):
    """同一机构的各种写法应收敛到同一个 core：剥括注 → 取第一个并列段 → 去『北京市』。"""
    n = SPLIT.split(strip_paren(name))[0].strip()
    if n.startswith("北京市") and len(n) > 6:
        n = n[3:]
    return n


def richness(r):
    return sum(1 for c in FILL_COLS if (r.get(c) or "").strip() not in EMPTY)


# ---------------------------------------------------------------------------
# 人工核定规则（自动判据覆盖不到的）
# ---------------------------------------------------------------------------
# ① 改名保留：主表里没有这家机构的独立记录，直接删会丢机构。
#    new_category 用于修正被拼接名带错的类别。
RENAME_RULES = {
    "3937": ("北京市海淀区妇幼保健院", "妇幼保健院",
             "原名把下属的计划生育服务中心与海淀社区卫生服务中心塞进了括号"),
    "1639": ("北京市顺义区顺安医院", None,
             "原名并入了顺义区精神卫生防治所（该所已归 id 1637）"),
    "1659": ("北京市延庆区牙病防治所", "其他医疗机构",
             "原名并入了延庆区妇幼保健院（该院已有独立记录 id 1658）"),
    "201": ("北京中医药大学东直门医院通州院区", None,
            "源文件《市医保局-区属二三级定点医疗机构.csv》第 10 行该院区属名称=通州区、"
            "等级三级，与东城区本部（id 7）**不是同一记录**，直接按名合并会丢掉通州院区"),
}
# ② 同机构两种写法都非法，合并为一条并正名
MERGE_RENAME = {
    "北京市红十字会急诊抢救中心": {
        "ids": ["1442", "1708"],
        "reason": "两条都是拼接形态，同属红十字急诊抢救中心",
    },
}
# ③ 真·两家不同机构合成一条：必须拆开，否则两家同时从系统消失
SPLIT_RULES = {
    "330": {
        "into": ["北京市丰台区心理卫生中心", "北京市丰台区精神卫生防治院"],
        "category": "其他医疗机构",
        "district": "丰台区",
        "reason": "两家不同机构，主表均无独立记录",
    },
}
# ③b 手工核定的合并：**「括号后直接接下一个机构名」**这种粘连形态。
#     它既没有顿号也没有空格，所以 `core_of()` 切不开（剥离括注后整串成了
#     一个词），自动判据天然抓不到。这 6 条是全表精确扫描后逐条核对的产物：
#     判据 = 剥掉括注后名字里**嵌了另一个主表机构名**，且剩余部分不含
#     「门诊部/服务站/分院/村卫生室」等下属单位词（含下属词的属正常命名，不动）。
#     扫描共命中 72 条，其中 66 条是误报（如「中国中医科学院针灸医院」嵌
#     「中国中医科学院」），真正粘连的只有下面 6 条。
MANUAL_MERGE = {
    "79":   ("76",   "北京市怀柔区中医医院 = 北京中医医院怀柔医院，源文件里两名直接相连"),
    "1312": ("1313", "北京怀柔医院 = 首都医科大学附属北京朝阳医院怀柔医院"),
    "1363": ("1362", "北京市昌平区南口医院 = 北京市昌平区南口中西医结合医院"),
    "1661": ("1662", "北京市怀柔区妇幼保健院 = 首都医科大学附属北京妇产医院怀柔妇幼保健院"),
    "3704": ("1166", "北京市隆福医院（北京中西医结合老年医院）+ 它办的景山社区卫生服务中心"),
    "53":   ("54",   "中国中医科学院广安门医院南区，与 id 54 是同一院区的两种写法"),
}
# ④ 有专属规则的 id 不参与自动合并，避免两套规则打架
EXCLUDE_FROM_MERGE = (set(RENAME_RULES) | set(SPLIT_RULES) | set(MANUAL_MERGE)
                      | {i for s in MERGE_RENAME.values() for i in s["ids"]})

# ⑤ 被折叠进来、**当时判不准**是否是独立机构的名字。
#
#    ⚠️ 这份清单的**性质已在第二轮变更**：2026-09-24 逐文件回查 + 联网核实后确认，
#    下面 9 个全部不是被误删的独立机构，而是宿主机构执业许可证上的**另一块牌子**
#    （同一个医疗机构编码 / 医保定点编码）。因此不新增行，改由
#    `etl/patch_alias_names.py` 把牌子名**写回宿主行的 `name`**（机构总数仍 9,678）。
#    逐条依据见 `data/processed/govern_report_alias.md`。
#
#    本清单保留为**第一轮的历史留档**，不再是待办事项；脚本自身不读它来改数。
PENDING_INSTITUTIONS = [
    ("北京市海淀区老年康复医院", "1504 / 3936", "海淀区",
     "中关村医院行把它带进了名字；本身是区属独立机构"),
    ("北京市东城区交道口社区卫生服务中心", "3703", "东城区",
     "第六医院举办；主表无独立记录"),
    ("北京市东城区北新桥社区卫生服务中心", "3703", "东城区",
     "第六医院举办；主表无独立记录"),
    ("北京市东城区景山社区卫生服务中心", "3704 / 3705", "东城区",
     "隆福医院举办；主表无独立记录"),
    ("北京市海淀区四季青镇社区卫生服务中心", "3935", "海淀区",
     "四季青医院举办；主表无独立记录"),
    ("北京市怀柔区汤河口镇社区卫生服务中心", "3832", "怀柔区",
     "怀柔二院举办；主表无独立记录"),
    ("北京市顺义区后沙峪镇社区卫生服务中心", "3981", "顺义区",
     "空港医院举办；主表无独立记录"),
    ("北京市顺义区牛栏山社区卫生服务中心", "3983", "顺义区",
     "顺义三院举办；主表无独立记录，其 4 个下属服务站（5149-5152）仍在表内，父子关系待补"),
    ("北京市平谷区牙病防治所", "1657", "平谷区",
     "与平谷妇幼保健院合署；怀柔区同类机构有独立记录（id 1307）"),
]


def name_rank(r):
    """keep 选取键（越小越优先）。

    ⚠️ 不能用「字段最多」直接当选主记录的依据 —— 实测会让 `北京四季青医院`
    输给 `北京四季青医院（…四季青镇社区卫生服务中心）`，因为后者多带了括注字段。
    名字的「干净程度」必须先于字段多寡：
      1. 带「北京市」前缀（正式名）优先
      2. 无任何括注 > 只有挂牌括注 > 括号外有并列分隔符（即挂别人的牌子）
      3. 剥掉括注后名字更长（更完整）优先
      4. 字段更全优先
      5. id 更小（更早登记）优先
    """
    n = r["name"]
    bare = strip_paren(n).strip()
    has_paren = bool(PAREN.search(n))
    has_sep = bool(SPLIT.search(bare))
    tier = 2 if has_sep else (1 if has_paren else 0)
    return (0 if n.startswith("北京市") else 1, tier, -len(bare),
            -richness(r), int(r["id"]))


def strip_affix(name):
    """剥掉末尾的**挂牌**括注，只留主名。

    `北京市中关村医院（中国科学院中关村医院）` → `北京市中关村医院`
    但 `首都医科大学附属北京同仁医院（东院区）` **不动**（院区是不同执业地点，
    由 CAMPUS_RE 拦下）。括号里是专科说明的（如「（精神病、老年病专科）」）
    同样剥掉 —— 那本来就不该进机构名。
    """
    out = name
    while True:
        m = re.search(r"[（(]([^（()）]*)[）)]\s*$", out)
        if not m:
            break
        if CAMPUS_RE.search(m.group(1)):
            break
        out = out[:m.start()].strip()
    return out or name


def gen_rules(rows):
    """按 core 分组，组内选出「保留行」，其余挂牌行列为待合并。"""
    g = collections.defaultdict(list)
    for r in rows:
        if r["id"] in EXCLUDE_FROM_MERGE:
            continue
        g[core_of(r["name"])].append(r)

    rules, skips = [], []
    for core, members in sorted(g.items()):
        if len(members) < 2:
            continue
        keep = min(members, key=name_rank)
        # 整组都是院区/部门 → 既有口径保留，整组跳过
        if CAMPUS_RE.search(keep["name"]) and all(
                CAMPUS_RE.search(m["name"]) for m in members):
            skips.append({"core": core, "reason": "整组均为院区·部门",
                          "kept": [{"id": r["id"], "name": r["name"]} for r in members]})
            continue

        merge_items, keep_aside = [], []
        for r in members:
            if r["id"] == keep["id"]:
                continue
            if CAMPUS_RE.search(r["name"]):
                keep_aside.append({"id": r["id"], "name": r["name"]})
            else:
                merge_items.append({
                    "id": r["id"], "name": r["name"],
                    "category": r["category"], "level": r["level"],
                    "filled": richness(r),
                })
        if merge_items:
            rules.append({
                "core": core,
                "keep_id": keep["id"], "keep_name": keep["name"],
                "keep_filled": richness(keep),
                "merge": merge_items,
                "aside": keep_aside,
            })
        if keep_aside:
            skips.append({"core": core, "reason": "院区·部门，既有口径保留",
                          "kept": keep_aside})
    return rules, skips


def apply_merge(keep, drop):
    """把 drop 行的信息并入 keep，返回 (补齐的字段, 冲突明细)。

    「只填空」意味着 keep 已有值时 drop 的值被丢弃 —— 丢的是**同一机构的另一个
    来源值**（例如两个名单登记的床位数不同）。按项目铁律不自动改，但**必须留档**，
    否则事后无法回答「合并有没有丢信息」。
    """
    touched, conflicts = [], []
    for c in FILL_COLS:
        if c not in keep:
            continue
        kv = (keep.get(c) or "").strip()
        dv = (drop.get(c) or "").strip()
        if kv in EMPTY and dv not in EMPTY:
            keep[c] = drop[c]
            touched.append(c)
        elif kv not in EMPTY and dv not in EMPTY and kv != dv:
            conflicts.append((c, kv, dv))
    for c in UNION_COLS:
        if c not in keep:
            continue
        a = [x for x in (keep.get(c) or "").split("、") if x.strip() and x.strip() not in EMPTY]
        b = [x for x in (drop.get(c) or "").split("、") if x.strip() and x.strip() not in EMPTY]
        u = sorted(set(a) | set(b))
        if u:
            keep[c] = "、".join(u)
            if len(u) > len(a):
                touched.append(c)
    for c in COUNT_COLS:
        if c not in keep:
            continue
        src = "national_specialty" if c.startswith("national") else "municipal_specialty"
        vals = [x for x in (keep.get(src) or "").split("、")
                if x.strip() and x.strip() not in EMPTY]
        if vals:
            keep[c] = str(len(vals))
    # 来源文件并集
    files = set()
    for r in (keep, drop):
        for f in (r.get("source_files") or "").split("|"):
            if f.strip():
                files.add(f.strip())
    keep["source_files"] = "|".join(sorted(files))
    keep["src_count"] = str(len(files))
    return touched, conflicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", action="store_true", help="重新生成规则草案")
    ap.add_argument("--dry-run", action="store_true", help="按现有规则预演")
    ap.add_argument("--apply", action="store_true", help="落盘（先备份）")
    args = ap.parse_args()

    with open(MASTER, encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        cols = list(rd.fieldnames)
        rows = list(rd)
    by_id = {r["id"]: r for r in rows}

    if args.gen or not os.path.exists(RULES):
        rules, skips = gen_rules(rows)
        payload = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_before": len(rows),
            "rules": rules, "skips": skips,
            "rename": RENAME_RULES, "merge_rename": MERGE_RENAME,
            "split": SPLIT_RULES,
        }
        with open(RULES, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[规则] 自动判据生成 {len(rules)} 组待合并 / {len(skips)} 条院区保留")
        print(f"       已写出 {os.path.relpath(RULES, ROOT)}")
        if args.gen and not (args.apply or args.dry_run):
            return 0
    else:
        with open(RULES, encoding="utf-8") as f:
            payload = json.load(f)
        print(f"[规则] 读入 {os.path.relpath(RULES, ROOT)}"
              f"（生成于 {payload.get('generated_at')}）")

    # ---------------- 预演 ----------------
    log = []
    drop_ids = set()
    touched_stat = collections.Counter()
    conflict_stat = collections.Counter()
    conflict_log = []

    for rule in payload["rules"]:
        keep = by_id.get(rule["keep_id"])
        if keep is None:
            continue
        for item in rule["merge"]:
            drop = by_id.get(item["id"])
            if drop is None:
                continue
            t, cf = apply_merge(keep, drop)
            drop_ids.add(drop["id"])
            for k in t:
                touched_stat[k] += 1
            for c, kv, dv in cf:
                conflict_stat[c] += 1
                conflict_log.append(
                    f"  {c}: {drop['id']}→{keep['id']} | {keep['name'][:28]} "
                    f"| 保留「{kv[:40]}」 丢弃「{dv[:40]}」")
            log.append(f"  合并 {drop['id']} → {keep['id']}  |  {drop['name'][:44]}"
                       f"  →  {keep['name'][:34]}  补: {','.join(t) or '无新字段'}")
        # 正名：合并后把保留行的「挂牌括注」剥掉（院区括注不动）
        before = keep["name"]
        after = strip_affix(before)
        if after != before:
            keep["name"] = after
            touched_stat["name"] += 1
            log.append(f"  正名 {keep['id']}: 「{before}」 → 「{after}」")

    # 改名保留（主表无独立记录，不能删）
    for i, (new_name, new_cat, why) in payload["rename"].items():
        r = by_id.get(i)
        if r is None:
            continue
        changed = False
        if r["name"] != new_name:
            log.append(f"  改名 {i}: 「{r['name'][:44]}」 → 「{new_name}」  ({why})")
            r["name"] = new_name
            changed = True
        if new_cat and r["category"] != new_cat:
            r["category"] = new_cat
            changed = True
        if changed:
            touched_stat["name"] += 1

    # 同机构两写法都非法 → 合并正名
    for new_name, spec in payload["merge_rename"].items():
        ids = [i for i in spec["ids"] if i in by_id]
        if len(ids) < 2:
            continue
        target = max((by_id[i] for i in ids), key=lambda r: (richness(r), -int(r["id"])))
        for i in ids:
            if i == target["id"]:
                continue
            _t, cf = apply_merge(target, by_id[i])
            for c, kv, dv in cf:
                conflict_stat[c] += 1
                conflict_log.append(
                    f"  {c}: {i}→{target['id']} | {target['name'][:28]} "
                    f"| 保留「{kv[:40]}」 丢弃「{dv[:40]}」")
            drop_ids.add(i)
            log.append(f"  合并 {i} → {target['id']}  |  同机构两写法 → 「{new_name}」")
        target["name"] = new_name if target["name"] != new_name else target["name"]

    # 粘连形态（括号后直接接下一机构名，无分隔符）→ 手工核定的合并
    for drop_id, (keep_id, why) in MANUAL_MERGE.items():
        keep, drop = by_id.get(keep_id), by_id.get(drop_id)
        if keep is None or drop is None:
            continue
        t, cf = apply_merge(keep, drop)
        for c, kv, dv in cf:
            conflict_stat[c] += 1
            conflict_log.append(
                f"  {c}: {drop_id}→{keep_id} | {keep['name'][:28]} "
                f"| 保留「{kv[:40]}」 丢弃「{dv[:40]}」")
        for k in t:
            touched_stat[k] += 1
        drop_ids.add(drop_id)
        log.append(f"  合并 {drop_id} → {keep_id}  |  粘连形态  |  {drop['name'][:48]}"
                   f"  →  {keep['name'][:30]}  补: {','.join(t) or '无新字段'}  ({why})")

    # 真·两家被合成一条 → 拆分（幂等：目标名已在表内则跳过）
    next_id = max(int(r["id"]) for r in rows) + 1
    existed_names = {r["name"] for r in rows}
    split_new = []
    for i, spec in payload["split"].items():
        r = by_id.get(i)
        if r is None:
            continue
        if r["name"] != spec["into"][0]:
            log.append(f"  拆分 {i}: 主名 → 「{spec['into'][0]}」  ({spec['reason']})")
            r["name"] = spec["into"][0]
            touched_stat["name"] += 1
        r["category"] = spec.get("category", r["category"])
        for extra in spec["into"][1:]:
            if extra in existed_names:
                continue
            nr = dict(r)
            nr["id"] = str(next_id)
            nr["name"] = extra
            nr["source_files"] = r["source_files"]
            split_new.append(nr)
            existed_names.add(extra)
            log.append(f"  拆分 {i} → 新增 {next_id}: 「{extra}」  ({spec['reason']})")
            next_id += 1

    kept = [r for r in rows if r["id"] not in drop_ids] + split_new

    # 重名自检：合并/正名都不该制造出两条同名机构
    dup_names = {n: c for n, c in collections.Counter(
        r["name"] for r in kept).items() if c > 1}
    if dup_names:
        print("\n✗ 合并后出现重名，请检查规则：")
        for n, c in sorted(dup_names.items(), key=lambda x: -x[1]):
            ids = [r["id"] for r in kept if r["name"] == n]
            print(f"   {c} 条 | {n} | ids={ids}")
        if args.apply:
            print("已中止，未写入。")
            return 1

    print(f"\n=== 待改动 ===")
    print(f"  合并删除 {len(drop_ids)} 条 · 拆分新增 {len(split_new)} 条")
    print(f"  机构数 {len(rows)} → {len(kept)}  （净 {len(kept) - len(rows):+d}）")
    print(f"  字段补齐统计：{dict(touched_stat)}")
    print(f"  字段冲突统计（保留行已有值，丢弃行值不覆盖）：{dict(conflict_stat)}")
    print(f"\n=== 明细（{len(log)} 条）===")
    for line in log:
        print(line)
    if conflict_log:
        print(f"\n=== 冲突留档（{len(conflict_log)} 处）===")
        for line in conflict_log:
            print(line)

    if not args.apply:
        print("\n[预演完成] 未写入。加 --apply 落盘。")
        return 0

    # ---------------- 落盘 ----------------
    # 幂等保护：主表已合并过时，规则里的 drop id 都不存在了 → 零改动，
    # 此时既不备份也不写盘，避免在流水线里每次跑批都堆一堆无用的 .bak。
    if not drop_ids and not split_new and not touched_stat["name"]:
        print("\n[无改动] 主表已是合并后状态，跳过写入。")
        return 0

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = os.path.join(BACKUP_DIR, f"master_institutions.csv.{stamp}.bak")
    shutil.copy2(MASTER, bak)
    with open(MASTER, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in kept:
            w.writerow({c: r.get(c, "") for c in cols})
    print(f"\n[落盘] 备份 → {os.path.relpath(bak, ROOT)}")
    print(f"[落盘] 主表 {len(rows)} → {len(kept)} 条")

    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("# 主表同名合并治理报告（2026-09-22）\n\n")
        f.write(f"口径：**合并挂牌名、保留院区**。\n\n")
        f.write(f"- 合并前：{len(rows)} 条\n- 合并后：{len(kept)} 条"
                f"（净 {len(kept) - len(rows):+d}）\n")
        f.write(f"- 合并删除：{len(drop_ids)} 条\n- 拆分新增：{len(split_new)} 条\n")
        f.write(f"- 院区/部门按既有口径保留：{sum(len(s['kept']) for s in payload['skips'])} 条\n\n")
        f.write("## 明细\n\n```\n" + "\n".join(log) + "\n```\n")
        f.write(f"\n## 字段冲突留档（{len(conflict_log)} 处）\n\n")
        f.write("下列字段在保留行已有值，被合并行的值**不覆盖、只留档**。\n")
        f.write("冲突几乎都来自「同一机构在两个名单里登记值不同」，属正常现象；\n")
        f.write("留档是为了事后能回答「合并有没有丢信息」。\n\n")
        f.write(f"按字段汇总：{dict(conflict_stat)}\n\n```\n")
        f.write("\n".join(conflict_log) + "\n```\n")
        f.write("\n## 曾判不准的挂牌名（第一轮留档，已于 2026-09-24 裁定）\n\n")
        f.write("第一轮把这 9 个名字**整块丢掉**了 —— 既没单独立条，也没写回宿主名。\n")
        f.write("第二轮逐文件回查确认：它们都是宿主机构执业许可证上的另一块牌子\n")
        f.write("（同一个医疗机构编码 / 医保定点编码），**不是被误删的独立机构**。\n")
        f.write("故不新增行，机构总数仍为 9,678；映射落盘为\n")
        f.write("`data/processed/alias_map.csv`，逐条依据见 "
                "`data/processed/govern_report_alias.md`。\n\n")
        f.write("> 名字不进 `name` —— 与 `strip_affix()`「保留行只留主名」的既定口径保持一致。\n\n")
        f.write("| 挂牌名 | 第一轮记录来源 id | 区 | 第一轮的判断（已被第二轮取代） |\n|---|---|---|---|\n")
        for nm, src, dist, why in PENDING_INSTITUTIONS:
            f.write(f"| {nm} | {src} | {dist} | {why} |\n")
        f.write("\n> 上表「第一轮的判断」当时认为它们可能是独立机构；第二轮据执业编码证据推翻。\n")
        f.write("\n## 院区·部门（既有口径保留，本轮不动）\n\n")
        for s in payload["skips"]:
            for k in s["kept"]:
                f.write(f"- {k['id']} {k['name']}\n")
    print(f"[落盘] 报告 → {os.path.relpath(REPORT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
