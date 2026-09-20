#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双端一致性闸门：自然语言筛选的「Python 实现」vs「浏览器 JS 实现」
================================================================================
为什么必须有这个脚本：
  单文件形态（dashboard_offline.html）为了"发个链接就能用"，把解析与筛选逻辑在
  前端又实现了一遍（web/app.nlq.js）。两份实现一旦分叉，用户会看到
  「同样一句话，联网查 57 家、离线查 100 家」——而且不报错、不白屏，
  只是结果悄悄不一样。这类问题靠肉眼是查不出来的。

比对内容：
  ① 解析层：nlq.parse()  vs  NLQ.parse()     —— 逐字段比对
            conditions / intent / dimension / applied 标签 / unmatched
  ② 筛选层：nlq 的条件语义 vs JS 的 matches() —— 比对总数、首位机构 id、统计概览
  ③ 统计层：维度分组结果与摘要文本

运行环境：
  - Python 侧只依赖 web/nlq.py（纯函数，不需要 MySQL）
  - JS 侧用 Node 跑 etl/offline_nlq_cli.js（读同一份 web/snapshot_data.json）
  因此本脚本在**没有数据库、没有浏览器**的环境下也能跑，适合放进 CI/收尾清单。

用法：
  python3 etl/verify_offline_nlq.py
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))

import nlq  # noqa: E402

NODE = "/Users/brooke/.workbuddy/binaries/node/versions/22.22.2-2/bin/node"
if not Path(NODE).exists():
    NODE = "node"

# ---- 用例：覆盖用户手册里给出的全部示例 + 边界 + 拒答场景 ----------------
QUERIES = [
    "朝阳区三级医院",
    "海淀区公立医院",
    "北京有哪些三级医院？",
    "帮我找朝阳区综合医院",
    "查询各区医疗机构数量",
    "找有详细地址的医疗机构",
    "比较朝阳区和海淀区的三级医院数量",
    "筛选二级及以上医院",
    "查询公立和民营医疗机构分布",
    "帮我筛选朝阳区三级公立医院",
    "找北京市社区卫生服务中心",
    "查找密云区医院",
    "北京市哪个区医疗机构最多？",
    "北京各区三级医院数量是多少？",
    "查询数据来源为医保定点的机构",
    "给我离我最近的三级医院",
    "2024年朝阳区三级医院",
    "协和医院",
    "2026年朝阳区三级公立综合医院",
    "75岁女性 腰椎滑脱走路困难",
    "孩子发烧去哪家医院好",
    "心慌胸闷睡不着",
]

# ---- 筛选用例：直接给结构化条件（条件筛选 Tab 的路径） ----------------
FILTER_CASES = [
    {"name": "朝阳区+三级+公立", "conditions": {"district": ["朝阳区"], "level": ["三级"],
                                                "ownership": ["公立"]}},
    {"name": "海淀区+二级及以上", "conditions": {"district": ["海淀区"], "level_min": 2}},
    {"name": "全部医院", "conditions": {"category": ["医院"]}},
    {"name": "西城区含地址", "conditions": {"district": ["西城区"], "has_addr": True}},
    {"name": "密云区全部", "conditions": {"district": ["密云区"]}},
    {"name": "东城区+诊所", "conditions": {"district": ["东城区"], "category": ["诊所"]}},
    {"name": "多来源机构", "conditions": {"src_min": 2}},
    {"name": "医保定点+三级", "conditions": {"source": ["insurance"], "level": ["三级"]}},
    {"name": "名称关键词", "conditions": {"kw": "协和"}},
    {"name": "无匹配条件", "conditions": {"district": ["朝阳区"], "category": ["村卫生室"],
                                          "level": ["三级"]}},
]


# =============================================================================
#  Python 侧参考实现（与 web/app.nlq.js 的 matches / overview 语义一致）
# =============================================================================
def py_matches(inst, cond):
    if cond.get("district") and inst.get("district") not in cond["district"]:
        return False
    if cond.get("level") and inst.get("level") not in cond["level"]:
        return False
    if cond.get("level_min") is not None:
        rank = nlq.LEVEL_RANK.get(inst.get("level"))
        if rank is None or rank < cond["level_min"]:
            return False
    if cond.get("category") and inst.get("category") not in cond["category"]:
        return False
    if cond.get("ownership") and inst.get("ownership") not in cond["ownership"]:
        return False
    import re as _re
    if cond.get("source"):
        patterns = {r["key"]: r["pattern"] for r in nlq.SOURCE_RULES}
        sf = inst.get("source_files") or ""
        if not any(_re.search(patterns[k], sf) for k in cond["source"] if k in patterns):
            return False
    if cond.get("dept"):
        return False                       # 离线形态不支持科室筛选（与 JS 一致）
    if cond.get("has_addr") and not (inst.get("addr") or ""):
        return False
    if cond.get("has_coord") and not (inst.get("lng") is not None and inst.get("lat") is not None):
        return False
    if cond.get("src_min"):
        # 与 app.nlq.js 的 matches() 严格同源：优先取 src_count_int（数仓产物字段），
        # 回退到历史的 src_count（早期由 etl/export_inst_source.py 回填）。
        # 只读其中一个字段会让"多来源机构"这类用例在两端得到不同结果——
        # 之前就是因为参考实现还停在旧字段名，才把 3137 家算成了 0 家。
        n = inst.get("src_count_int")
        if n is None:
            n = inst.get("src_count")
        if (n or 0) < cond["src_min"]:
            return False
    if cond.get("kw"):
        kw = cond["kw"]
        if kw not in (inst.get("name") or "") and kw not in (inst.get("addr") or ""):
            return False
    return True


def py_overview(items):
    s = {"total": len(items), "level3": 0, "level2": 0, "public_cnt": 0,
         "private_cnt": 0, "coord_ok": 0}
    for i in items:
        if i["level"] == "三级":
            s["level3"] += 1
        if i["level"] == "二级":
            s["level2"] += 1
        if i["ownership"] == "公立":
            s["public_cnt"] += 1
        if i["ownership"] == "民营":
            s["private_cnt"] += 1
        if i.get("lng") is not None and i.get("lat") is not None:
            s["coord_ok"] += 1
    return s


def py_sort(items, sort):
    """与 JS sortItems 同序（score 用 matchScore，兜底比名称）。"""
    key_name = lambda x: x["name"] or ""          # noqa: E731
    if sort == "distance":
        items.sort(key=lambda x: (x["distance_km"] is None,
                                  x["distance_km"] if x["distance_km"] is not None else 0,
                                  key_name(x)))
    elif sort == "level":
        items.sort(key=lambda x: (-(nlq.LEVEL_RANK.get(x["level"]) or 0), key_name(x)))
    elif sort == "depts":
        items.sort(key=lambda x: (-(x["dept_count"] or 0), key_name(x)))
    elif sort == "name":
        items.sort(key=key_name)
    else:
        items.sort(key=lambda x: (-x["score"], key_name(x)))
    return items


def py_score(inst, cond):
    hit, total = 0.0, 0.0
    for k in ("district", "level", "category", "ownership"):
        if not cond.get(k):
            continue
        total += nlq.MATCH_WEIGHTS[k]
        if inst.get(k) in cond[k]:
            hit += nlq.MATCH_WEIGHTS[k]
    if cond.get("source"):
        import re as _re
        total += nlq.MATCH_WEIGHTS["source"]
        pats = {r["key"]: r["pattern"] for r in nlq.SOURCE_RULES}
        sf = inst.get("source_files") or ""
        if any(_re.search(pats[k], sf) for k in cond["source"] if k in pats):
            hit += nlq.MATCH_WEIGHTS["source"]
    if total <= 0:
        return 1.0
    return round(hit / total, 4)


def py_filter(insts, cond, page=1, page_size=20):
    out = []
    for it in insts:
        if not py_matches(it, cond):
            continue
        out.append({
            "id": str(it["id"]), "name": it["name"], "district": it["district"],
            "category": it["category"], "level": it["level"], "ownership": it["ownership"],
            "addr": it.get("addr") or "", "lng": it.get("lng"), "lat": it.get("lat"),
            "dept_count": it.get("dept_count"),
            "distance_km": None, "score": py_score(it, cond),
        })
    sort = cond.get("_sort") or "score"
    py_sort(out, sort)
    total = len(out)
    start = (page - 1) * page_size
    return {"total": total, "items": out[start:start + page_size], "sort": sort,
            "stats": py_overview(out)}


def py_stats(insts, cond, dimension):
    pool = [i for i in insts if py_matches(i, cond)]
    import re as _re
    if dimension == "source":
        rows = []
        for rule in nlq.SOURCE_RULES:
            rex = _re.compile(rule["pattern"])
            rows.append({"name": rule["label"],
                         "cnt": sum(1 for x in pool if rex.search(x.get("source_files") or ""))})
        rows.sort(key=lambda r: (-r["cnt"], r["name"]))
    else:
        field = {"district": "district", "category": "category",
                 "level": "level", "ownership": "ownership"}[dimension]
        agg = {}
        for x in pool:
            k = x.get(field) or "未标注"
            agg.setdefault(k, {"name": k, "cnt": 0})
            agg[k]["cnt"] += 1
        rows = sorted(agg.values(), key=lambda r: (-r["cnt"], r["name"]))
    return {"rows": rows, "label": nlq.DIM_LABEL[dimension],
            "summary": nlq.summarize_stats(cond, {"rows": rows, "label": nlq.DIM_LABEL[dimension],
                                                  "dimension": dimension})}


# =============================================================================
#  跑 Node 侧
# =============================================================================
def node_run(payload):
    proc = subprocess.run(
        [NODE, str(ROOT / "etl" / "offline_nlq_cli.js")],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(ROOT))
    if proc.returncode != 0:
        raise RuntimeError("Node 执行失败：" + proc.stderr.decode("utf-8")[:400])
    return json.loads(proc.stdout.decode("utf-8"))


def main():
    snap = json.loads((ROOT / "web" / "snapshot_data.json").read_text(encoding="utf-8"))
    insts = snap["institutions"]
    print("快照机构数：%d" % len(insts))

    dept_names = ["骨科", "口腔科", "心血管内科", "儿科"]
    req = {"queries": QUERIES, "dept_names": dept_names,
           "cases": [dict(c, page_size=20, with_stats=c.get("with_stats", False))
                     for c in FILTER_CASES]}
    js = node_run(req)
    assert js.get("ok"), js
    js_queries = js["results"][:len(QUERIES)]
    js_cases = js["results"][len(QUERIES):]

    ok = fail = 0

    def check(label, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("  ✗ %s %s" % (label, detail))

    print("\n=== ① 解析层一致性（%d 条问句）===" % len(QUERIES))
    for q, j in zip(QUERIES, js_queries):
        p = nlq.parse(q, dept_names=dept_names)
        check("intent[%s]" % q, p["intent"] == j["intent"],
              "py=%s js=%s" % (p["intent"], j["intent"]))
        check("dimension[%s]" % q, (p["dimension"] or None) == j["dimension"],
              "py=%s js=%s" % (p["dimension"], j["dimension"]))
        check("conditions[%s]" % q, p["conditions"] == j["conditions"],
              "\n      py=%s\n      js=%s" % (json.dumps(p["conditions"], ensure_ascii=False),
                                             json.dumps(j["conditions"], ensure_ascii=False)))
        pa = [c["label"] + "=" + c["text"] for c in p["applied"]]
        check("applied[%s]" % q, pa == j["applied"],
              "\n      py=%s\n      js=%s" % (pa, j["applied"]))
        check("unmatched[%s]" % q, p["unmatched"] == j["unmatched"],
              "py=%s js=%s" % (p["unmatched"], j["unmatched"]))
    print("  解析层：%d 条全部比对完成" % len(QUERIES))

    print("\n=== ② 筛选层一致性（%d 个条件组合）===" % len(FILTER_CASES))
    for c, j in zip(FILTER_CASES, js_cases):
        cond = dict(c["conditions"])
        p = py_filter(insts, cond)
        check("total[%s]" % c["name"], p["total"] == j["total"],
              "py=%d js=%d" % (p["total"], j["total"]))
        pf = p["items"][0]["id"] if p["items"] else None
        check("first[%s]" % c["name"], pf == j["first_id"],
              "py=%s(%s) js=%s(%s)" % (pf, p["items"][0]["name"] if p["items"] else "-",
                                       j["first_id"], j["first_name"]))
        check("stats[%s]" % c["name"], p["stats"] == j["stats"],
              "py=%s js=%s" % (p["stats"], j["stats"]))

    print("\n=== ③ 统计层一致性 ===")
    for dim in ("district", "category", "level", "ownership", "source"):
        cond = {}
        p = py_stats(insts, cond, dim)
        jsr = node_run({"cases": [{"name": dim, "conditions": cond, "with_stats": True,
                                   "dimension": dim}]})["results"][0]
        check("stats_rows[%s]" % dim,
              [[x["name"], x["cnt"]] for x in p["rows"]] == jsr["stats_rows"],
              "py=%s js=%s" % ([[x["name"], x["cnt"]] for x in p["rows"]][:3],
                               jsr["stats_rows"][:3]))
        check("stats_summary[%s]" % dim, p["summary"] == jsr["stats_summary"],
              "\n      py=%s\n      js=%s" % (p["summary"], jsr["stats_summary"]))

    print("\n" + "=" * 68)
    if fail:
        print("❌ 双端一致性校验未通过：通过 %d / 失败 %d" % (ok, fail))
        return 1
    print("✅ 双端一致性校验通过：%d 项断言全部一致" % ok)
    return 0


if __name__ == "__main__":
    sys.exit(main())
