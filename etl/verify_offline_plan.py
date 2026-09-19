#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线主线引擎 vs 后端 /api/plan 的双端一致性验证。

单文件形态的「就医决策」是前端本地复算的（web/app.plan.js），必须与 Flask 的
api_plan() 给出同样的判科、同样的候选顺序、同样的匹配度。任何一处漂移都会让
「在线看到的」和「分享出去看到的」不是同一个系统，这个脚本就是那道闸门。

做法：
  1. 用 Flask 测试客户端直接调 /api/plan（走真实 MySQL、真实 SQL）
  2. 用 node 跑 web/app.plan.js（走内嵌数据包，纯本地）
  3. 逐用例比对判科结果、候选 id 顺序、match_score、距离、推荐依据

用法：
    python etl/verify_offline_plan.py
    python etl/verify_offline_plan.py -v      # 打印每个用例的 Top3
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = "/Users/brooke/.workbuddy/binaries/python/envs/default/bin/python"
NODE = "/Users/brooke/.workbuddy/binaries/node/versions/22.22.2-2/bin/node"

# 覆盖七大类需求与主要分支：专科旗舰用例、区域限定、人群加权、科室族展开、语音口语词
CASES = [
    {"q": "孩子反复发烧咳嗽三天了"},
    {"q": "心慌胸闷"},
    {"q": "骨折"},
    {"q": "眼睛看不清"},
    {"q": "孕检"},
    {"q": "老人最近总心慌胸闷"},
    {"q": "朝阳区 牙痛"},
    {"q": "高血压"},
    {"q": "听不见"},
    {"q": "腰酸"},
    {"q": "徐汇区 头疼"},                       # 区名纠错：徐汇区不存在，应纠正为相近区
    {"q": "心慌", "prefer": "distance", "lng": 116.397428, "lat": 39.90923, "base_name": "天安门"},
    {"q": "心慌", "prefer": "level", "lng": 116.397428, "lat": 39.90923, "base_name": "天安门"},
    {"q": "心慌", "prefer": "balanced", "lng": 116.397428, "lat": 39.90923, "base_name": "天安门"},
    {"q": "孩子发烧", "lng": 116.34, "lat": 39.95, "base_name": "海淀区中心"},
    {"q": "骨折", "public_only": True, "level": "三级"},
    {"q": "", "dept": "眼科"},
]


def load_flask_app():
    """加载 web/app.py 为独立模块（避免 `import app` 与其他同名模块撞车）。"""
    spec = importlib.util.spec_from_file_location("hospital_app", os.path.join(ROOT, "web", "app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app


def norm(x):
    """把浮点收敛到 1e-6，避免双精度最后一位的噪音把比对染红。

    同时把 None 与空串视为同一个「没有值」：后端 JSON 给 null，而快照在打包时
    统一把 NULL 写成了空串用于前端拼接字符串。两者在前端渲染上完全等价
    （都落到「—」），不属于真实差异。
    """
    if x is None:
        return ''
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items()}
    if isinstance(x, list):
        return [norm(v) for v in x]
    return x


def diff_case(idx, case, be, fe, verbose):
    """比对单个用例，返回问题列表。"""
    problems = []
    tag = f"#{idx} {case.get('q') or case.get('dept')!r}"

    if be.get("ok") != fe.get("ok"):
        problems.append(f"{tag} ok 不一致：后端={be.get('ok')} 离线={fe.get('ok')}")
        return problems
    if not be.get("ok"):
        if be.get("reason") != fe.get("reason"):
            problems.append(f"{tag} reason 不一致：{be.get('reason')} vs {fe.get('reason')}")
        return problems

    # ---- 判科 ----
    b_depts = [(d["name"], norm(d["weight"]), d["matched_by"]) for d in be["triage"]["target_depts"]]
    f_depts = [(d["name"], norm(d["weight"]), d["matched_by"]) for d in fe["triage"]["target_depts"]]
    if sorted(b_depts) != sorted(f_depts):
        problems.append(f"{tag} 判科不一致：\n    后端={b_depts}\n    离线={f_depts}")
    if be["triage"]["emergency"] != fe["triage"]["emergency"]:
        problems.append(f"{tag} 急诊标记不一致")

    # ---- 候选顺序与分数 ----
    b_c, f_c = be["candidates"], fe["candidates"]
    if len(b_c) != len(f_c):
        problems.append(f"{tag} 候选数不一致：后端={len(b_c)} 离线={len(f_c)}")
    for i, (b, f) in enumerate(zip(b_c, f_c)):
        if b["id"] != f["id"]:
            problems.append(f"{tag} 第 {i+1} 位候选不一致：后端={b['name']}({b['id']}) vs 离线={f['name']}({f['id']})")
            break
        if abs(norm(b["match_score"]) - norm(f["match_score"])) > 1e-6:
            problems.append(f"{tag} 第 {i+1} 位 match_score 不一致：{b['match_score']} vs {f['match_score']}")
        for key in ("strength", "distance_km", "tier", "dept_name", "concentration",
                    "addr", "phone", "level_norm", "ownership", "district", "dept_count"):
            if norm(b.get(key)) != norm(f.get(key)):
                problems.append(f"{tag} 第 {i+1} 位 {key} 不一致：{b.get(key)} vs {f.get(key)}")
        if b["reasons"] != f["reasons"]:
            problems.append(f"{tag} 第 {i+1} 位推荐依据不一致：\n    后端={b['reasons']}\n    离线={f['reasons']}")

    # ---- 总量 ----
    if be["stats"]["candidate_total"] != fe["stats"]["candidate_total"]:
        problems.append(f"{tag} 候选池总数不一致：后端={be['stats']['candidate_total']} 离线={fe['stats']['candidate_total']}")

    if verbose and not problems:
        top = "｜".join(f"{c['name']} {c['match_score']}" for c in f_c[:3])
        print(f"  ✓ {tag} 判科={[d[0] for d in f_depts]} Top3={top}")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    print("1/3 启动 Flask 测试客户端（走后端真实 SQL）")
    flask_app = load_flask_app()
    client = flask_app.test_client()

    print("2/3 跑离线引擎（node web/app.plan.js）")
    proc = subprocess.run(
        [NODE, os.path.join(ROOT, "etl", "offline_plan_cli.js")],
        input=json.dumps({"cases": CASES}, ensure_ascii=False),
        capture_output=True, text=True, cwd=ROOT,
    )
    if proc.returncode != 0:
        print(proc.stderr[-3000:], file=sys.stderr)
        raise SystemExit("离线引擎执行失败")
    fe_all = json.loads(proc.stdout)["results"]

    print(f"3/3 逐用例比对（共 {len(CASES)} 个）\n")
    problems = []
    for i, case in enumerate(CASES, 1):
        resp = client.post("/api/plan", json=case)
        be = resp.get_json()
        problems += diff_case(i, case, be, fe_all[i - 1], args.verbose)

    print()
    if problems:
        for p in problems:
            print("❌ " + p)
        print(f"\n共 {len(problems)} 处不一致")
        raise SystemExit(1)
    print(f"✅ 双端完全一致：{len(CASES)} 个用例的判科、候选顺序、匹配度、推荐依据逐字对齐")


if __name__ == "__main__":
    main()
