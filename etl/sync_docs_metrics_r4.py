# -*- coding: utf-8 -*-
"""
文档数字同步 · 第四轮（办别构成 / 字段完整率 / 数据边界）
======================================================
前三轮（`sync_docs_metrics.py` / `_r2` / `_r3`）覆盖了总数、应参评、等级分布、
覆盖率与字段级完整率。剩下这一批**没被任何一轮覆盖**，于 2026-09-24 的收尾核查里
被扫出来：

  · 办别构成 trio「公立 3,085 / 民营 5,323 / 未标注 1,381」—— 全是**合并前**
    （9,789 家）的值，散落在 6 份文档里，其中 README 的一句话还是**当前态描述**；
  · 电话「823」、等次「255」、等级非空「942」—— 同样是合并前的值
    （现为 815 / 223 / 849）；
  · 数据边界两行「352 家民营医院等级缺失」「248 家村卫生室未标注办别」
    —— 现为 353 / 251。

这正是 r1 开头写的那句风险：**口径一变，同一组数字散落各处，漏一份就是
答辩时「论文说 X、系统说 Y」**。r4 把它们补齐。

与前三轮的区别（也是把「不许写死数字」这条教训落地）
----------------------------------------------------
`new` 一侧**不写死**：脚本每次运行都从 `data/processed/master_institutions.csv`
现算，再填进模版。所以下次数据再变，只要跑一遍 dry-run 就能看出文档是否落后。
只有 `old`（要替换掉的旧字面量）必须写死 —— 它天然是历史的。

**范围纪律**：只改「当前态陈述」。README 里带日期的 `[x] …（2026-09-21）`
条目描述的是**当时**的数据，属历史叙述，一律不动（脚本对它们零命中）。
`docs/数据联网核实报告.md` 同理，是时点报告，只在文末追加带日期的口径更新块。

用法
----
    python etl/sync_docs_metrics_r4.py            # 预演
    python etl/sync_docs_metrics_r4.py --apply    # 落盘
"""

import argparse
import io
import os
import sys
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

MASTER = "data/processed/master_institutions.csv"


# ---------------------------------------------------------------------------
# 一、从主表现算（唯一真源，不写死）
# ---------------------------------------------------------------------------
def metrics():
    import csv
    with io.open(MASTER, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    hdr, body = rows[0], [dict(zip(rows[0], r)) for r in rows[1:]]
    n = len(body)
    ow = Counter(r["ownership"] for r in body)
    appl = [r for r in body if r["grade_scope"] == "applicable"]
    lv_ok = [r for r in appl if r["level"] not in ("", "未定级")]
    hosp_lv_missing = [r for r in body
                       if "医院" in r["name"] and r["level"] in ("", "未定级")]
    m = {
        "n": n,
        "pub": ow["公立"], "priv": ow["民营"], "unknown": ow["未标注"],
        "unknown_pct": ow["未标注"] * 100.0 / n,
        "phone": sum(1 for r in body if r["phone"]),
        "levelsub": sum(1 for r in body if r["level_sub"]),
        "applic": len(appl),
        "level_ok": len(lv_ok),
        "level_pct": len(lv_ok) * 100.0 / len(appl),
        "hosp_lv_missing": len(hosp_lv_missing),
        "hosp_lv_missing_priv": sum(1 for r in hosp_lv_missing
                                    if r["ownership"] == "民营"),
        "village_unknown": sum(1 for r in body
                               if r["ownership"] == "未标注"
                               and r["category"] == "村卫生室"),
    }
    return m


# ---------------------------------------------------------------------------
# 二、替换表：(文件, 旧字面量, 新字面量, 期望出现次数)
# ---------------------------------------------------------------------------
def build_pairs(m):
    fmt = lambda k: format(m[k], ",")
    return [
        # ============ docs/项目说明书.md ============
        ("docs/项目说明书.md",
         "办别未标注率从 15.5% 降至 14.1%",
         "办别未标注 %s 家（%.1f%%）" % (fmt("unknown"), m["unknown_pct"]), 1),
        ("docs/项目说明书.md",
         "电话 570 → **823**（8.4%）",
         "电话 570 → **%s**（8.4%%）" % fmt("phone"), 1),
        ("docs/项目说明书.md",
         "等次 175 → **255**",
         "等次 175 → **%s**" % fmt("levelsub"), 1),
        ("docs/项目说明书.md",
         "非空由 922 增至 942",
         "非空由 922 增至 %s" % fmt("level_ok"), 1),
        ("docs/项目说明书.md",
         "| 352 家民营医院等级缺失 |",
         "| %s 家名称含「医院」的机构等级缺失 |" % fmt("hosp_lv_missing"), 1),
        ("docs/项目说明书.md",
         "| 248 家村卫生室未标注办别 |",
         "| %s 家村卫生室未标注办别 |" % fmt("village_unknown"), 1),
        ("docs/项目说明书.md",
         "| 公立 **3,085** / 民营 **5,323** / 未标注 **1,381**（未标注从 1,514 降至 1,381） |",
         "| 公立 **%s** / 民营 **%s** / 未标注 **%s**（未标注从 1,514 降至 %s） |"
         % (fmt("pub"), fmt("priv"), fmt("unknown"), fmt("unknown")), 1),
        ("docs/项目说明书.md",
         "| 1,381 家办别未标注 |",
         "| %s 家办别未标注 |" % fmt("unknown"), 1),

        # ============ README.md（当前态描述那一句）============
        ("README.md",
         "办别分布（3,085 / 5,323 / 1,381）",
         "办别分布（%s / %s / %s）"
         % (fmt("pub"), fmt("priv"), fmt("unknown")), 1),

        # README 2026-09-22 那条修复记录：**混了历史值与现值**。
        # 该轮的产出是 823 / 942 / 255，但其中「等级 922 → 849」被 r1 按当前值改过，
        # 于是同一句里 823（该轮）与 849（合并后）并存 —— 读者会算出「补全反而变少」。
        # 修法：把该轮结果还原成该轮的值，再补一句「合并治理后现值」，两个口径都在。
        ("README.md",
         "**结果**：电话 570 → **823（8.4%）**、等级 922 → **849**（应参评 874 家，"
         "适用口径补全率 **97.1%**）、等次 175 → **255**；",
         "**结果**：电话 570 → **823（8.4%%）**、等级 922 → **942**、等次 175 → **255**；"
         "三者经 2026-09-22 同名合并治理（机构数 9,789 → 9,678）后现为 电话 **%s（8.4%%）**、"
         "等级 **%s**（应参评 %d 家，适用口径补全率 **%.1f%%**）、等次 **%s**；"
         % (fmt("phone"), fmt("level_ok"), m["applic"], m["level_pct"], fmt("levelsub")), 1),

        # ============ docs/功能点-代码对应表.md ============
        ("docs/功能点-代码对应表.md",
         "**公立 3,085 / 民营 5,323 / 未标注 1,381**",
         "**公立 %s / 民营 %s / 未标注 %s**"
         % (fmt("pub"), fmt("priv"), fmt("unknown")), 1),
        ("docs/功能点-代码对应表.md",
         "电话 **570 → 823（8.4%）**、等级 **922 → 942**（适用口径 **97.1%**）、等次 **175 → 255**",
         "电话 **570 → %s（8.4%%）**、等级 **922 → %s**（适用口径 **%.1f%%**）、等次 **175 → %s**"
         % (fmt("phone"), fmt("level_ok"), m["level_pct"], fmt("levelsub")), 1),
        ("docs/功能点-代码对应表.md",
         "如 352 家民营医院等级缺失 = 真实边界",
         "如 %s 家名称含「医院」的机构等级缺失 = 真实边界"
         % fmt("hosp_lv_missing"), 1),
        ("docs/功能点-代码对应表.md",
         "如民营 352 家百科确无等级字段",
         "如民营 %s 家百科确无等级字段" % fmt("hosp_lv_missing_priv"), 1),

        # ============ docs/毕业答辩问题库.md ============
        ("docs/毕业答辩问题库.md",
         "结果：公立 **3,085** / 民营 **5,323** / 未标注 **1,381**。",
         "结果：公立 **%s** / 民营 **%s** / 未标注 **%s**（%.1f%%）。"
         % (fmt("pub"), fmt("priv"), fmt("unknown"), m["unknown_pct"]), 1),

        # ============ docs/答辩与简历讲解手册.md ============
        ("docs/答辩与简历讲解手册.md",
         "公立 3,085 / 民营 5,323 / 未标注 1,381，口径=",
         "公立 %s / 民营 %s / 未标注 %s，口径="
         % (fmt("pub"), fmt("priv"), fmt("unknown")), 1),

        # ============ docs/项目文件说明与系统演示指南.md ============
        ("docs/项目文件说明与系统演示指南.md",
         "→ 公立 3,085 / 民营 5,323 / 未标注 1,381",
         "→ 公立 %s / 民营 %s / 未标注 %s"
         % (fmt("pub"), fmt("priv"), fmt("unknown")), 1),
    ]


# ---------------------------------------------------------------------------
# 三、残差扫描：这些旧值出现在「当前态陈述」里就是漏网
# ---------------------------------------------------------------------------
RESIDUAL = ["3,085", "5,323", "1,381", "**823**", "175 → **255**",
            "922 → 942", "352 家", "248 家"]
# 时点/历史叙述：只报告、不判定为漏网。判据是「描述的是当时，不是现在」。
HISTORICAL_FILES = (
    "docs/开发日志.md",            # append-only 的带日期日志
    "docs/数据联网核实报告.md",      # 时点报告：正文冻结，口径更新只追加到文末日期块
)
HISTORICAL_HINTS = (
    "3 个数据点齐全",      # 项目说明书 9.4 ⑤「本轮修前实测」的探针回放
    "三者经 2026-09-22 同名合并治理",   # README 那条「该轮值 + 合并后现值」的并存写法
    "（2026-09-21）", "（2026-09-20）", "（2026-09-22）",
)


def residual_scan():
    import glob
    files = ["README.md"] + sorted(glob.glob("docs/*.md"))
    hits = []
    for f in files:
        for i, line in enumerate(io.open(f, encoding="utf-8").read().split("\n"), 1):
            for k in RESIDUAL:
                if k in line:
                    hist = (f in HISTORICAL_FILES
                            or any(h in line for h in HISTORICAL_HINTS))
                    hits.append((f, i, k, hist, line.strip()[:110]))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    m = metrics()
    print("=== 主表现算口径 ===")
    print("  机构 %s 家 | 办别 公 %s / 民 %s / 未标注 %s（%.1f%%）"
          % (format(m["n"], ","), format(m["pub"], ","), format(m["priv"], ","),
             format(m["unknown"], ","), m["unknown_pct"]))
    print("  应参评 %d | 等级非空 %d（%.1f%%）| 电话 %s | 等次 %s"
          % (m["applic"], m["level_ok"], m["level_pct"],
             format(m["phone"], ","), format(m["levelsub"], ",")))
    print()

    pairs = build_pairs(m)
    plan, fail, done = [], [], 0
    cache = {}
    for f, old, new, cnt in pairs:
        if f not in cache:
            cache[f] = io.open(f, encoding="utf-8").read()
        got = cache[f].count(old)
        if got != cnt:
            # 幂等：新值已在文中（说明这一条之前同步过）→ 视为已完成，不算失败。
            # 前三轮脚本缺这一步，重复跑会「匹配失败」退出，容易被误读成故障。
            if old != new and cache[f].count(new) >= cnt:
                done += 1
                continue
            fail.append((f, old, cnt, got))
            continue
        if old == new:
            continue
        plan.append((f, old, new, cnt))
    if done:
        print("· %d 处已是新值，跳过（幂等）\n" % done)

    if fail:
        print("✗ 字面量匹配失败（不做模糊替换，直接退出）：")
        for f, old, cnt, got in fail:
            print("  %s\n    期望 %d 次，实际 %d 次\n    片段：%s" % (f, cnt, got, old[:90]))
        return 2

    print("=== 命中 %d 处替换 ===\n" % len(plan))
    for f, old, new, cnt in plan:
        print("  [%s] ×%d" % (f, cnt))
        print("    - %s" % old[:110])
        print("    + %s\n" % new[:110])

    if args.apply:
        for f in {p[0] for p in plan}:
            cache[f] = io.open(f, encoding="utf-8").read()
            for ff, old, new, cnt in plan:
                if ff == f:
                    cache[f] = cache[f].replace(old, new)
            io.open(f, "w", encoding="utf-8").write(cache[f])
            print("[落盘] %s" % f)
    else:
        print("（预演模式，未写入。加 --apply 落盘）")

    print("\n=== 残差复查（旧值是否还出现在活文档里）===")
    hits = residual_scan()
    if not hits:
        print("  ✓ 零残留")
    else:
        live = [h for h in hits if not h[3]]
        hist = [h for h in hits if h[3]]
        for f, i, k, _, line in live:
            print("  ⚠️ %-40s:%-5d [%s] 请人工判断" % (f, i, k))
            print("      %s" % line)
        if hist:
            print("  · 以下 %d 处是时点/历史叙述（描述的是当时的数据），按规则保留："
                  % len(hist))
            for f, i, k, _, line in hist[:6]:
                print("      %-38s:%-5d [%s]" % (f, i, k))
            if len(hist) > 6:
                print("      …（其余 %d 处同类）" % (len(hist) - 6))
        if not live:
            print("  ✓ 当前态陈述已零残留")
    return 0


if __name__ == "__main__":
    sys.exit(main())
