#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出「就医决策」主线的离线数据包，供单文件形态（dashboard_offline.html）内联使用。

背景：单文件形态原本只含查阅能力（机构/筛选/统计快照），主线要连后端 /api/plan 才能跑，
分享出去（GitHub Pages）点「就医决策」只能 404。本脚本把主线跑起来所需的**最小数据集**
导出成紧凑 JSON，让前端用同一套打分公式本地复算候选排序。

导出内容
  1. ads_dept_strength（去掉医技类）—— 科室实力指数，16729 条左右
  2. dim_disease_dept               —— 口语 → 科室知识库，417 条
  3. app.py 里的排序常量            —— 用 AST 从源码提取，杜绝手工抄写漂移

体积控制
  - 科室名、大类名做字典索引化，避免每行重复存字符串
  - tier_label 不入库（前端由 tier 推导），输出仍是 8 列定长数组

用法：
    python etl/export_offline_plan_data.py            # 输出到 web/offline_plan_data.json
    python etl/export_offline_plan_data.py -o xx.json
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "etl"))

# 与 build_spa.sh / etl/*.py 保持一致的库连接口径
DB = dict(host="127.0.0.1", port=3307, user="root", password="hospital123",
          database="hospital", charset="utf8mb4")

# 需要从 web/app.py 提取的模块级常量（保证离线复算与后端同源）
CONSTS = [
    "LEVEL_SCORE", "BJ_DISTRICTS", "PLAN_PREFER", "PLAN_PREFER_LABEL",
    "PLAN_CROWD_BOOST", "PLAN_CROWD_FACTOR", "PLAN_NET_LABEL", "PLAN_NET_DEPT",
    "PLAN_DEPT_FAMILY", "DEPT_ALIAS", "CLARIFY_MAP",
]

# TIER_LABEL：五级证据分级（与 spark/jobs/dim_dept_strength.py 的 tier_label 同源）
# ⚠️ tier 的取值是 0-4，不是 1-5：0=已开设、1=登记、2=官网公示、3=市级、4=国家级。
# 这个偏移很容易写错（写错后所有机构都会被标成「已开设」），改动前先跑一次分布核对。
TIER_LABEL = {
    0: "已开设", 1: "登记重点专科", 2: "官网公示重点科室",
    3: "市级重点专科", 4: "国家临床重点专科",
}


def load_consts(app_path: str) -> dict:
    """用 AST 取 app.py 的模块级字面量常量，不在导入时执行 app.py（避免建库连接等副作用）。"""
    tree = ast.parse(open(app_path, encoding="utf-8").read())
    got = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id in CONSTS:
                try:
                    got[tgt.id] = ast.literal_eval(node.value)
                except ValueError:
                    print(f"  ! {tgt.id} 不是字面量，跳过", file=sys.stderr)
    missing = [c for c in CONSTS if c not in got]
    if missing:
        raise SystemExit("app.py 里缺少常量：" + ", ".join(missing))
    return got


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "web", "offline_plan_data.json"))
    args = ap.parse_args()

    import pymysql

    print("1/3 提取 app.py 常量（AST）")
    consts = load_consts(os.path.join(ROOT, "web", "app.py"))
    print("    " + "、".join(f"{k}({len(v)})" for k, v in consts.items() if hasattr(v, "__len__")))

    conn = pymysql.connect(**DB, cursorclass=pymysql.cursors.DictCursor)

    print("2/3 导出科室实力指数 ads_dept_strength")
    with conn.cursor() as cur:
        # 医技类（检验/影像/病理等）不是「看病要去哪一科」的答案，与 api_plan 的过滤口径一致
        cur.execute(
            "SELECT hospital_id, dept_name, dept_category, tier, strength, concentration, is_network "
            "FROM ads_dept_strength WHERE dept_category <> '医技'")
        rows = cur.fetchall()
    print(f"    {len(rows):,} 条")

    # 字典索引化：科室名 / 大类名各存一次
    dept_idx: dict[str, int] = {}
    cat_idx: dict[str, int] = {}
    strength = []
    for r in rows:
        d = r["dept_name"] or ""
        c = r["dept_category"] or ""
        dept_idx.setdefault(d, len(dept_idx))
        cat_idx.setdefault(c, len(cat_idx))
        strength.append([
            str(r["hospital_id"]).strip(),
            dept_idx[d],
            int(r["tier"] or 0),
            int(round(float(r["strength"] or 0))),          # 库里 strength 实测全为整数，取整无损
            round(float(r["concentration"] or 0), 3),       # 必须留 3 位：前端按 >=0.4 判「专科机构」，截断会误判
            1 if r["is_network"] else 0,
        ])

    print("3/3 导出疾病→科室知识库 dim_disease_dept")
    with conn.cursor() as cur:
        cur.execute("SELECT keyword, dept_name, weight, is_emergency FROM dim_disease_dept")
        kb_rows = cur.fetchall()
    print(f"    {len(kb_rows):,} 条")
    conn.close()

    kb = []
    for r in kb_rows:
        d = r["dept_name"] or ""
        if d not in dept_idx:          # 知识库科室必须能在实力表里查到，否则候选恒为空
            dept_idx[d] = len(dept_idx)
        kb.append([r["keyword"], dept_idx[d], round(float(r["weight"]), 2), int(r["is_emergency"])])

    payload = {
        "meta": {
            "source": "ads_dept_strength / dim_disease_dept / web/app.py",
            "dept_count": len(dept_idx),
            "strength_rows": len(strength),
            "kb_rows": len(kb),
            "note": "离线主线数据包：前端用同一套打分公式本地复算候选排序",
        },
        "depts": [None] * len(dept_idx),
        "cats": [None] * len(cat_idx),
        "tier_label": {str(k): v for k, v in TIER_LABEL.items()},
        "strength": strength,
        "kb": kb,
        "const": consts,
    }
    for name, i in dept_idx.items():
        payload["depts"][i] = name
    for name, i in cat_idx.items():
        payload["cats"][i] = name

    out = args.out
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(out)
    print(f"\n✅ 写出 {out}  ({size/1024/1024:.2f} MB)")
    print(f"   科室 {len(dept_idx)} · 实力行 {len(strength):,} · 知识库 {len(kb)}")

    # 自检：tier 是证据分级的核心，键位写错会让所有机构退化成「已开设」，这里直接打分布
    dist = {}
    for row in strength:
        dist[row[2]] = dist.get(row[2], 0) + 1
    print("   tier 分布：" + " · ".join(
        f"{TIER_LABEL.get(k, k)} {dist[k]:,}" for k in sorted(dist)))
    ss = [r[3] for r in strength]
    print(f"   实力分范围 {min(ss)}–{max(ss)}（满分 100）")
    conc = [r[4] for r in strength if r[4] >= 0.4]
    print(f"   集中度 ≥0.4（判为专科机构）：{len(conc):,} 行")


if __name__ == "__main__":
    main()
