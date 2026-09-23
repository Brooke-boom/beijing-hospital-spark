#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""等级适用范围修复：清除非医院类机构被误盖的医院等级（2026-09-22）

问题（03 段「区域×等级机构数矩阵」暴露出来的）
==============================================
矩阵里大兴区「一级」= 369 家，成了全表最大的热格；而大兴区三级机构只有 11 家。
顺着查下去，全表 833 家「一级」里大兴区独占 369 家，且**全国所有「一级诊所」(175)
与「一级医务室」(87) 全部集中在大兴区** —— 真实分布不可能长这样。

根因有两层
----------
① 源文件名误解析（etl/clean_merge.py · std_level 的文件名兜底）
   - 《大兴区一级以下医院名单门诊部名单、诊所名单、医务室名单.csv》
     正则 (…|一级|二级|三级) 命中了「一级**以下**」里的"一级"，
     这份名单实际跨等级（一级＋未定级），旧写法让整份 318 行无条件盖上「一级」，
     其中 313 家是诊所 / 医务室 / 门诊部。
   - 《丰台区村一级卫生室.csv》—— 是"村级卫生室"，"一级"前一个字是"村"，
     16 家村卫生室因此变成「一级」。
② 缺少等级适用范围守卫
   三级/二级/一级是《医疗机构管理条例》下对**医院**的评审结论。诊所、村卫生室、
   门诊部、社区卫生服务站、医务室、护理站按各自《基本标准》以「诊疗科目」核准执业，
   本就没有等级建制；它们的 level 只可能来自脏单元格或 ① 的文件名兜底。

本脚本做什么
------------
按 etl/clean_merge.py 里的同一判据（level_not_applicable，与其 NOT_RATED_CATS 同源），
把已经产出在 data/processed/master_institutions.csv 上的这批脏值修掉：

  - level / level_sub  置空，并在 level_src 留下清除原因（可追溯，不静默改数）
  - grade_scope        置 'not_applicable'
      ⚠️ 这一列必须一并改：spark/jobs/layer_dwd.py:59 用
         `grade_scope == 'not_applicable' → level_norm = '不适用医院分级'`。
         只清 level 而不改 grade_scope，这 334 家仍会被标成「参评机构」，
         在 03 段矩阵里继续以"未定级"占位，等于没修。
         （build_grade_scope.py 的判定顺序是「level 非空 → applicable」优先，
          所以被误赋等级的机构反而被判成"参评"，这条短路正是这次要治的。）

为什么不在 clean_merge.py 全量重跑
----------------------------------
clean_merge 是全链路第一环，重跑会重建主表并**丢掉后续几十个治理脚本挂上的列**
（national_specialty / net_* / ownership_online / dept_count_online …），
那些脚本里有若干依赖联网（高德地理编码、百科、好大夫）。所以这里只对产物做外科式修复，
根因则同时修在 clean_merge.py（保证从零重建时不再产生）与 build_grade_scope.py
（保证 grade_scope 口径正确）。两条路用的是同一个判据函数，不会漂移。

产出
----
  data/processed/master_institutions.csv            原地修正（先备份）
  data/归档_旧版命名/processed_backup/master_institutions.<ts>.csv   备份
  data/processed/govern_report_level_scope.md       治理报告

用法: python3 etl/fix_level_not_applicable.py [--dry-run]
"""
import csv
import datetime
import importlib.util
import os
import re
import shutil
import sys
from collections import Counter

BASE = os.path.expanduser("~/Desktop/毕设")
DATA = os.path.join(BASE, "data", "processed")
MASTER = os.path.join(DATA, "master_institutions.csv")
BAKDIR = os.path.join(BASE, "data", "归档_旧版命名", "processed_backup")
REPORT = os.path.join(DATA, "govern_report_level_scope.md")

# 复用 clean_merge.py 的判据，避免同一规则在两处各写一遍（会漂移）
_spec = importlib.util.spec_from_file_location(
    "clean_merge_rule", os.path.join(BASE, "etl", "clean_merge.py"))
_rule = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rule)
level_not_applicable = _rule.level_not_applicable
NOT_RATED_CATS = _rule.NOT_RATED_CATS

# ---------- 规则②：范围式文件名的残留等级 ----------
# 《大兴区一级以下医院名单门诊部名单、诊所名单、医务室名单》这类文件名写的是
# **范围**（"一级以下" = 一级 ＋ 未定级），不是单一级别枚举，任何行都不该从它取等级。
# 判据：某行的 level 若**只能**来自范围式文件名（source_files 里含等级词的文件
# 全是范围式），则该等级无依据。
# 实测恰为 5 家（其他医疗机构 4 + 精神疾病农疗康复中心 1），
# 另外 313 家同类已被规则①（六类无等级建制）先行清掉 —— 两条规则不重叠、无假阳性。
LEVEL_IN_FNAME = re.compile(r"(三级甲等|三级乙等|二级甲等|二级乙等|一级|二级|三级)")
RANGE_FNAME = re.compile(r"(一级|二级|三级)以[下上]")


def level_from_range_filename(srcs):
    """该机构的等级是否只可能来自"…以下/以上…"这类范围式文件名。"""
    named = [f.strip() for f in str(srcs or "").split("|")
             if f.strip() and LEVEL_IN_FNAME.search(f)]
    return bool(named) and all(RANGE_FNAME.search(f) for f in named)


def main():
    dry = "--dry-run" in sys.argv
    rows = list(csv.DictReader(open(MASTER, encoding="utf-8-sig")))
    fields = list(rows[0].keys())
    for c in ("level_src", "grade_scope"):
        if c not in fields:                     # 缺列则补，避免 KeyError
            fields.append(c)
            for r in rows:
                r.setdefault(c, "")
    print(f"[读入] {MASTER}：{len(rows)} 家机构")

    hit_lv, hit_scope, hit_rng = [], [], []
    for r in rows:
        cat = r.get("category") or ""
        # ① 被盖上的医院等级（非参评类别）
        if level_not_applicable(cat, r.get("level")):
            hit_lv.append(r)
            r["_orig_level"] = r.get("level")      # 仅供报告留痕，不写回 CSV
            r["level"] = ""
            r["level_sub"] = ""
            r["level_src"] = "cleared:not_rated_category"
        # ② 等级只可能来自范围式文件名
        elif r.get("level") and level_from_range_filename(r.get("source_files")):
            hit_rng.append(r)
            r["_orig_level"] = r.get("level")
            r["level"] = ""
            r["level_sub"] = ""
            r["level_src"] = "cleared:range_list_filename"
        # ③ 非参评类别却被判成参评（含 level='未定级' 这一类，一并归位）
        if cat in NOT_RATED_CATS and (r.get("grade_scope") or "") != "not_applicable":
            hit_scope.append(r)
            r["grade_scope"] = "not_applicable"

    hit_all = hit_lv + hit_rng
    print(f"[命中] 规则①非参评类别 {len(hit_lv)} 家；规则②范围式文件名 {len(hit_rng)} 家；"
          f"grade_scope → not_applicable {len(hit_scope)} 家")
    print("       清除等级的区分布:", Counter(r.get("district") for r in hit_all).most_common())
    print("       清除的等级取值:", Counter(r.get("_orig_level") for r in hit_all).most_common())
    if hit_rng:
        print("       规则②明细（等级只来自「…以下」名单）:")
        for r in hit_rng:
            print("         -", r.get("name"), "|", r.get("category"), "|", r.get("district"))

    if dry:
        print("[dry-run] 未写盘")
        return

    os.makedirs(BAKDIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = os.path.join(BAKDIR, f"master_institutions.{ts}.csv")
    shutil.copy2(MASTER, bak)
    print(f"[备份] {bak}")

    with open(MASTER, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"[写回] {MASTER}")

    _write_report(rows, hit_lv, hit_rng, hit_scope, bak, ts)


def _write_report(rows, hit_lv, hit_rng, hit_scope, bak, ts):
    """留下可追溯的治理记录：改了什么、依据是什么、改完的分布长什么样。"""
    A = []
    A.append("# 等级适用范围治理报告（2026-09-22）\n")
    A.append("## 结论\n")
    A.append(f"- 规则① 非参评类别被盖等级：**{len(hit_lv)}** 家")
    A.append(f"- 规则② 等级只来自「…以下」范围式文件名：**{len(hit_rng)}** 家")
    A.append(f"- 连同把 grade_scope 归位为 not_applicable 的：**{len(hit_scope)}** 家")
    A.append(f"- 备份：`{os.path.relpath(bak, BASE)}`（{ts}）\n")
    A.append("## 依据\n")
    A.append("三级/二级/一级是《医疗机构管理条例》下对**医院**的评审结论。")
    A.append("诊所、村卫生室、门诊部、社区卫生服务站、医务室、护理站六类，")
    A.append("按各自《基本标准》以「诊疗科目」核准执业，不设等级建制，")
    A.append("其 level 只可能来自脏单元格或源文件名误解析。\n")
    A.append("判据函数 `level_not_applicable()` 定义在 `etl/clean_merge.py`，")
    A.append("与前端 `web/vue/src/deptLabel.js` 的 `NO_DEPT_CAT`、")
    A.append("`etl/build_grade_scope.py` 的 `NON_GRADED_CAT` 同源。\n")
    A.append("## 触发明细\n")
    A.append("### 规则① 非参评类别被盖上医院等级（共 %d 家，列前 40）\n" % len(hit_lv))
    A.append("| 区 | 机构名 | 类别 | 被清除的等级 |")
    A.append("|---|---|---|---|")
    for r in sorted(hit_lv, key=lambda x: (x.get("district") or "", x.get("name") or ""))[:40]:
        A.append("| %s | %s | %s | %s |" % (
            r.get("district") or "（未知）", r.get("name") or "",
            r.get("category") or "", r.get("_orig_level") or ""))
    if len(hit_lv) > 40:
        A.append(f"| … | 其余 {len(hit_lv) - 40} 家同类 | | |")
    if hit_rng:
        A.append("\n### 规则② 等级只来自「…以下/以上」范围式文件名（共 %d 家，全列）\n"
                 % len(hit_rng))
        A.append("| 区 | 机构名 | 类别 | 被清除的等级 | 来源文件 |")
        A.append("|---|---|---|---|---|")
        for r in hit_rng:
            A.append("| %s | %s | %s | %s | %s |" % (
                r.get("district") or "（未知）", r.get("name") or "", r.get("category") or "",
                r.get("_orig_level") or "", r.get("source_files") or ""))
    A.append("\n## 修正后的等级分布\n")
    A.append("| 等级 | 数量 |")
    A.append("|---|---:|")
    cnt = Counter((r.get("level") or "（空/不适用）") for r in rows)
    for k, v in cnt.most_common():
        A.append(f"| {k} | {v} |")
    A.append("\n## 修正后各区「一级」机构数（对照 03 段矩阵）\n")
    A.append("| 区 | 一级 | 二级 | 三级 |")
    A.append("|---|---:|---:|---:|")
    by = {}
    for r in rows:
        d = r.get("district") or "（未知）"
        by.setdefault(d, Counter())[r.get("level") or ""] += 1
    for d, c in sorted(by.items(), key=lambda kv: -kv[1]["三级"]):
        A.append(f"| {d} | {c['一级']} | {c['二级']} | {c['三级']} |")
    open(REPORT, "w", encoding="utf-8").write("\n".join(A) + "\n")
    print(f"[报告] {REPORT}")


if __name__ == "__main__":
    main()
