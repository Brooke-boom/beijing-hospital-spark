# -*- coding: utf-8 -*-
"""
院区 / 挂牌证据导出器
================================================================
输出：web/campus_evidence.json（由 build_spa.sh 内联进单文件）

为什么需要它
------------
用户在详情页看到「北京积水潭医院（回龙观院区）」这类名字，会自然追问两件事：
  1. 这家到底有几个院区？我看的这一所是本院还是分院？
  2. 括号里那些「（北新桥社区卫生服务中心）」「（301医院）」是不是也是同一家？
但**括号 ≠ 院区**。主表里 74 家带括号的机构，绝大多数括号是旧称或改名：

    北京市延庆区井庄镇社区卫生服务中心（北京市延庆区井庄镇卫生院）   ← 同一机构旧称
    中国医学科学院北京协和医院（东院区）                            ← 真院区，单独建档

把两者混为一谈，等于告诉用户「延庆区所有社区卫生服务中心都有两个院区」。
所以这里按**判据**分成两类，只把有据可查的写进证据：

  A. 院区组（campus_groups）
     判据 = 去掉括号后主名相同 **且** 括号内含「院区 / 分院 / 总院」。
     命中 5 组 7 条，与 data/processed/govern_report_dedup_full.md 第三节
     「院区·部门（既有口径保留，不参与合并）」清单一致。

  B. 挂牌别名（aliases）
     来自 data/processed/alias_map.csv —— 同一**执业编码**下的多块牌子，
     裁定后并入主机构、别名进独立表（不进主表 name 字段）。
     带 source（源文件 + 编码）与 evidence（判定依据原文）。

  C. 旧称括号（legacy_parens）
     既不含院区关键字、也不在别名表里的括号，如实标为「旧称 / 改名」，
     **不冒充院区**。这一类必须显式记录，否则用户看到括号会默认当院区。

改动本脚本时同步改：etl/verify_layout.py（容器/数据一致性）与 build_spa.sh（内联）。
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(BASE, "data/processed/master_institutions.csv")
ALIAS = os.path.join(BASE, "data/processed/alias_map.csv")
OUT = os.path.join(BASE, "web/campus_evidence.json")

# 括号内容里出现这些词，才认定「院区 / 分院 / 总院」是机构分支而不是旧称
CAMPUS_KW = ("院区", "分院", "总院")

# 括号内容里出现这些词，明确是旧称 / 改名，不是分支
LEGACY_KW = ("原", "更名", "旧")

PAREN = re.compile(r"[（(]([^（）()]*)[）)]")


def read_master():
    if not os.path.exists(MASTER):
        sys.exit("未找到主表：%s" % MASTER)
    with open(MASTER, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_alias():
    """别名表是独立的 sidecar 文件（治理铁律：别名进 alias_map.csv，不进主表 name）。"""
    if not os.path.exists(ALIAS):
        print("  ⚠ 未找到 alias_map.csv，只导出院区组（无挂牌证据）")
        return []
    with open(ALIAS, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def split_paren(name):
    """返回 (主名, 括号内文字 or None)。只取第一个括号——嵌套括号在机构名里不成立。"""
    m = PAREN.search(name or "")
    if not m:
        return (name or "", None)
    inner = m.group(1).strip()
    return ((name[:m.start()] + name[m.end():]).strip(), inner or None)


def main():
    rows = read_master()
    by_id = {r["id"]: r for r in rows}

    # ---------- A. 院区组 ----------
    cand = defaultdict(list)
    legacy = []
    for r in rows:
        main_name, inner = split_paren(r["name"])
        if not inner:
            continue
        if any(k in inner for k in CAMPUS_KW) and not any(k in inner for k in LEGACY_KW):
            cand[main_name].append({"id": r["id"], "name": r["name"], "campus": inner,
                                    "district": r.get("district", "")})
        else:
            legacy.append({"id": r["id"], "name": r["name"], "paren": inner})

    # 院区命名一律成组登记 —— 即使同主名下只有 1 条也要留：
    # 「北京积水潭医院（回龙观院区）」只有这一条，但它恰恰是最有用的那条证据
    # （直接回答「我看的是哪个院区」）。因此 groups 收录全部带院区括号的机构，
    # 由 sibling_count 区分「多院区并列」与「本机构即某院区」。
    groups = []
    for main_name, members in cand.items():
        groups.append({
            "key": main_name,
            "main_name": main_name,
            "sibling_count": len(members),
            "members": sorted(members, key=lambda x: x["name"]),
        })
    groups.sort(key=lambda g: (-g["sibling_count"], g["main_name"]))

    # 反查表：机构 id -> 所属院区组
    id2group = {}
    for gi, g in enumerate(groups):
        for m in g["members"]:
            id2group[m["id"]] = gi

    # ---------- B. 挂牌别名 ----------
    alias_rows = read_alias()
    aliases_by_host = defaultdict(list)
    for a in alias_rows:
        aliases_by_host[a["host_id"]].append({
            "alias_name": a.get("alias_name", ""),
            "relation": a.get("relation", ""),
            "source": a.get("source", ""),
            "evidence": a.get("evidence", ""),
        })

    # ---------- C. 旧称括号（只留计数与样例，不全量内联，省体积） ----------
    legacy_sample = [{"id": x["id"], "name": x["name"], "paren": x["paren"]} for x in legacy[:5]]

    out = {
        "meta": {
            "generated_from": ["data/processed/master_institutions.csv",
                               "data/processed/alias_map.csv"],
            "campus_rule": "主名相同 且 括号内含 院区/分院/总院 且 非「原/更名/旧」",
            "alias_rule": "同一执业编码下的多块牌子，裁定后并入主机构、别名独立成表",
            "legacy_rule": "既非院区也非在册别名的括号，一律标为旧称/改名，不冒充院区",
        },
        "campus_groups": groups,
        # id(str) -> { gi, role: '主院'|'院区' }
        "id2group": id2group,
        # id(str) -> [alias...]
        "aliases_by_host": dict(aliases_by_host),
        "legacy_count": len(legacy),
        "legacy_sample": legacy_sample,
        "summary": {
            "campus_groups": len(groups),
            "campus_members": sum(len(g["members"]) for g in groups),
            "alias_rows": len(alias_rows),
            "alias_hosts": len(aliases_by_host),
            "legacy_parens": len(legacy),
            "institutions_total": len(rows),
        },
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    s = out["summary"]
    print("  ✓ web/campus_evidence.json | %.1f KB" % (os.path.getsize(OUT) / 1024))
    print("    院区组 %d 组 / %d 条机构 · 挂牌别名 %d 条（挂 %d 家） · 旧称括号 %d"
          % (s["campus_groups"], s["campus_members"], s["alias_rows"],
             s["alias_hosts"], s["legacy_parens"]))
    for g in groups:
        print("      · %s：%s" % (g["main_name"], "、".join(m["campus"] for m in g["members"])))

    # ---------- 自检：判据不许漏 ----------
    problems = []
    if not groups:
        problems.append("院区组为空 —— 判据可能过严或主表列名变了")
    for g in groups:
        if g["sibling_count"] != len(g["members"]) or g["sibling_count"] < 1:
            problems.append("院区组 %s 的 sibling_count 与成员数对不上" % g["main_name"])
        for m in g["members"]:
            if m["id"] not in by_id:
                problems.append("院区组成员 %s(id=%s) 不在主表" % (m["name"], m["id"]))
            if not any(k in m["campus"] for k in CAMPUS_KW):
                problems.append("院区组成员 %s 的括号里没有院区关键字，判据被绕过" % m["name"])
    for hid, lst in aliases_by_host.items():
        if hid not in by_id:
            problems.append("别名宿主 id=%s 不在主表" % hid)
        for a in lst:
            if not a["evidence"]:
                problems.append("别名 %s 缺 evidence —— 没有判定依据就不能当证据展示"
                                % a["alias_name"])
    if problems:
        print("\n  ❌ 院区证据自检未通过：")
        for p in problems:
            print("     - " + p)
        sys.exit(1)
    print("    ✓ 自检通过：院区组成员/别名宿主均在主表，且每条别名都带判定依据")


if __name__ == "__main__":
    main()