#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计主表「一名多机构」问题（只读，不改数据）。

背景（2026-09-22）：
  用户在列表页发现两条机构名异常：
    北京市中关村医院（中国科学院中关村医院）、北京市海淀区老年康复医院
    北京大学第三医院、北京大学第三临床医学院
  回溯发现根因在 `clean_merge.py` 的去重键 `norm_name()`：
  它只做「去空白 + 括号转半角 + 去『北京市』前缀」，因此**同一家机构的
  不同写法会算出不同的 key**，绕过去重双双入库。

本脚本做三件事：
  ① 找出「名字里含并列分隔符」的记录（界面显示为怪名）—— 无争议缺陷；
  ② 找出「同一机构多写法」的重复组（core 相同）—— 涉及口径决策；
  ③ 把重复组分成三类：院区/部门型（既有口径保留）、多块牌子型（真冗余）、混合型。

用法：python3 etl/audit_name_multibrand.py [--json out.json]
"""
import argparse
import collections
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "data", "processed", "master_institutions.csv")

PAREN = re.compile(r"[（(][^（()）]*[）)]")
# 并列分隔符：顿号 / 分号 / 逗号 / 斜杠 / 任意空白 / 全角空格
SPLIT = re.compile(r"[、；;，,／/]+|\s+|\u3000")
# 界面显示的并列分隔符（句内空白也算）
OUT_SEP = re.compile(r"[、；;，,／/]|\s|\u3000")

# 判定「院区 / 部门」型：这些写法属于同一法人的不同执业地点或内设部门，
# 本项目既有口径是**按独立记录保留**（东院区/西院区/回龙观院区…共 8 条），
# 按「合并挂牌名、保留院区」口径保留为独立记录（2026-09-22 同名合并治理后
# 主表 9,678 家，其中院区/部门 10 条）。
CAMPUS_RE = re.compile(r"院区|东院|西院|南院|北院|分院|院区|体检部|门诊部|社区[^（）]*$")

# 字段丰富度参考列
RICH_COLS = ("addr", "phone", "level", "level_sub", "beds", "traffic",
             "website", "key_depts", "ownership", "dept_count_online")


def core(name):
    """同一机构的各种写法应收敛到同一个 core：剥括注 → 取第一个并列段 → 去『北京市』。"""
    n = PAREN.sub("", name)
    n = SPLIT.split(n)[0].strip()
    if n.startswith("北京市") and len(n) > 6:
        n = n[3:]
    return n


def filled(r):
    return sum(1 for c in RICH_COLS if (r.get(c) or "").strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    with open(MASTER, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # ---------- ① 怪名（括号外仍有并列分隔符，或括号内含顿号） ----------
    def strip_paren(n):
        prev = None
        while prev != n:
            prev = n
            n = PAREN.sub("", n)
        return n

    weird = []
    for r in rows:
        nm = r["name"]
        why = []
        if OUT_SEP.search(strip_paren(nm).strip()):
            why.append("括号外并列分隔符")
        if any("、" in m.group(0) for m in PAREN.finditer(nm)):
            why.append("括号内顿号")
        if why:
            weird.append((r, why))

    # ---------- ② 重复组（core 相同） ----------
    g = collections.defaultdict(list)
    for r in rows:
        g[core(r["name"])].append(r)
    multi = {k: v for k, v in g.items() if len(v) > 1}

    groups = {"campus": [], "multibrand": [], "mixed": []}
    for k, v in multi.items():
        v = sorted(v, key=lambda r: (-filled(r), r["id"]))
        names = [r["name"] for r in v]
        n_campus = sum(1 for n in names if CAMPUS_RE.search(n))
        n_bare = sum(1 for n in names if "(" not in n and "（" not in n)
        if n_campus >= len(names) - 1 and n_bare <= 1:
            groups["campus"].append((k, v))
        elif n_campus == 0:
            groups["multibrand"].append((k, v))
        else:
            groups["mixed"].append((k, v))

    # ---------- ③ 输出 ----------
    print(f"主表记录数：{len(rows)}")
    print(f"\n① 名字含并列分隔符（界面显示为怪名）：{len(weird)} 条")
    for r, why in sorted(weird, key=lambda x: int(x[0]["id"])):
        nf = filled(r)
        print(f"  {r['id']:>6} f={nf:>2} | {r['name']}")
        print(f"          {'/'.join(why)} | cat={r['category']} lv={r['level']} "
              f"dist={r['district']} | {r['source_files']}")

    print(f"\n② 同一机构多写法（core 冲突）：{len(multi)} 组 / "
          f"{sum(len(v) for v in multi.values())} 条")

    label = {"campus": "A 院区·部门型（既有口径保留）",
             "multibrand": "B 多块牌子型（真冗余）",
             "mixed": "C 混合型（需人工判）"}
    for key in ("campus", "multibrand", "mixed"):
        gs = sorted(groups[key], key=lambda x: -len(x[1]))
        print(f"\n  {label[key]}：{len(gs)} 组 / {sum(len(v) for v in gs)} 条")
        for k, v in gs:
            print(f"    [{k}]")
            for i, r in enumerate(v):
                mark = "★" if i == 0 else " "
                print(f"      {mark} {r['id']:>6} f={filled(r):>2} | {r['name']}")

    n_campus = sum(len(v) - 1 for _, v in groups["campus"])
    n_mb = sum(len(v) - 1 for _, v in groups["multibrand"] + groups["mixed"])
    print(f"\n>>> 若 A 保留、B+C 合并：可减 {n_mb} 条 → {len(rows) - n_mb} 家")
    print(f">>> 若全合并（含院区）：可减 {n_mb + n_campus} 条 → {len(rows) - n_mb - n_campus} 家")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({
                "total": len(rows),
                "weird": [{"id": r["id"], "name": r["name"], "why": why,
                           "filled": filled(r), "category": r["category"],
                           "level": r["level"], "district": r["district"]}
                          for r, why in weird],
                "groups": {k: [{"core": c, "members": [
                    {"id": r["id"], "name": r["name"], "filled": filled(r)}
                    for r in v]} for c, v in gs]
                    for k, gs in groups.items()},
            }, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 已写出：{args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
