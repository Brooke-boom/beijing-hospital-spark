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
            （含科室隶属、按距离排序：距离必须在排序前算好，否则"按距离排序"
              会静默退化成按名称排序）
  ③ 统计层：维度分组结果与摘要文本
  ④ 真库核对（可选）：条件总数与 MySQL 直接比对 —— 用后端同一个 nlq.build_where
            生成 SQL，因此核对的是"页面上的数字"与"库里的数字"是否一致。
            本机没起 MySQL 时自动跳过（其余三节照跑）。

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
    "海淀区骨科",
    "海淀区有哪些骨科医院",
    "找朝阳区的口腔科",
    "全市的儿科在哪几家",
    "75岁女性 腰椎滑脱走路困难",
    "孩子发烧去哪家医院好",
    "心慌胸闷睡不着",
    # ---- 口语化输入（本轮新增）----
    # 这些句子里的"想找/靠谱/那边/附近/什么好点"是**意图**而不是机构名。
    # 不收口的话会被当成机构名关键词（"想找靠谱大"），机构表里没有任何名字含它 →
    # 结果恒为 0，而且两端一致地错，只有真人点一下才看得出来。
    "想找个靠谱的大医院",
    "想找个好点的大医院",
    "海淀那边有哪些大医院",
    "帮我找找海淀区的大医院",
    "附近有什么好点的医院",
    "海淀区有没有能看心脏的医院",
    "朝阳区大医院",
    "找个三甲",
    "我想找协和",
    # ---- 机构名前缀（本轮新增）----
    # 裸"北京"曾是停用词，被全局 replace 掉会把真实机构名打成残渣
    # （"北京大学第一医院" → kw="大学第一"）。现在只有整句剥完什么都不剩时才算"范围词"。
    "北京大学第一医院",
    "北京协和医院",
    "北京儿童医院",
    "北京市三级医院",
    "北京协和医院有多少家",
]

# ---- 筛选用例：直接给结构化条件（条件筛选 Tab 的路径） ----------------
# ⚠️ 科室条件（dept）在离线形态是**能真的筛**的：快照里带了 depts（科室隶属名录，
#    由 build_spa.sh 从 dwd_dept_relation_clean 导出），匹配语义与后端 SQL 一致。
# ---- 语义断言用例（①.5 节）--------------------------------------------------
# ① 节只保证"两端算得一样"，**两端一起错它查不出来**。这一节直接断言解析结果的
# 语义对不对，专门盯住"口语残渣被当成机构名关键词"这一类静默错误。
# 格式：(问句, 期望**一定出现**的 applied 标签, 期望**一定不出现**的 applied 标签)
SEMANTIC_CASES = [
    # 口语填充词不该进机构名关键词
    ("想找个靠谱的大医院",   ["机构类型=医院"],              ["机构名称关键词"]),
    ("想找个好点的大医院",   ["机构类型=医院"],              ["机构名称关键词"]),
    ("海淀那边有哪些大医院", ["行政区=海淀区", "机构类型=医院"], ["机构名称关键词"]),
    ("帮我找找海淀区的大医院", ["行政区=海淀区", "机构类型=医院"], ["机构名称关键词"]),
    ("附近有什么好点的医院", ["机构类型=医院"],              ["机构名称关键词"]),
    ("朝阳区大医院",         ["行政区=朝阳区", "机构类型=医院"], ["机构名称关键词"]),
    ("北京市三级医院",       ["医院等级=三级", "机构类型=医院"], ["机构名称关键词"]),
    # 顺带确认"程度字"没把机构类型一起吃掉
    ("海淀区有没有能看心脏的医院", ["行政区=海淀区", "机构类型=医院"], []),
    # 机构名前缀必须保住（裸"北京"过去被当停用词全局剥掉）
    ("我想找协和",     ["机构名称关键词=协和"],     []),
    ("北京协和医院",   ["机构名称关键词=北京协和"], []),
    ("北京大学第一医院", ["机构名称关键词=北京大学第一"], []),
    ("北京儿童医院",   ["机构名称关键词=北京儿童"], []),
]
"""这几条的观测点是"机构名称关键词必须**完整含'北京'**"。若哪天裸"北京"又被当成
停用词全局剥掉，kw 会退化成"协和/儿童/大学第一"，这里立刻变红。
（机构类型"医院"仍会被正常识别，所以不把它列进"必无"。）"""


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
    # ---- 科室维度（本轮新增：此前离线形态遇到科室条件直接拒答 0 家）----
    {"name": "海淀区+骨科", "conditions": {"district": ["海淀区"], "dept": "骨科"}},
    {"name": "全市骨科", "conditions": {"dept": "骨科"}},
    {"name": "全市口腔科", "conditions": {"dept": "口腔科"}},
    {"name": "海淀区+骨科+三级", "conditions": {"district": ["海淀区"], "dept": "骨科",
                                                "level": ["三级"]}},
    {"name": "骨科+民营", "conditions": {"dept": "骨科", "ownership": ["民营"]}},
    # ---- 距离排序：距离必须在排序前算好（否则会静默退化成按名称排序）----
    {"name": "全市医院按距离排序", "conditions": {"category": ["医院"], "_sort": "distance"}},
    {"name": "骨科按距离排序", "conditions": {"dept": "骨科", "_sort": "distance"}},
    # ---- 科室 + 距离 + 多条件叠加 ----
    {"name": "海淀区骨科按距离排序",
     "conditions": {"district": ["海淀区"], "dept": "骨科", "_sort": "distance"}},
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
        # 与后端 build_where 同语义：该机构在科室隶属表里**恰好有**这条科室名。
        # 快照把这张表按机构聚合成 ';' 分隔的 depts 字段（build_spa.sh 导出）。
        # 必须精确相等 —— 用包含匹配会让"骨科"把"中医骨伤科"也一起吞进来。
        ds = str(inst.get("depts") or "")
        if not ds or (";" + cond["dept"] + ";") not in (";" + ds + ";"):
            return False
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


def py_haversine(lng1, lat1, lng2, lat2):
    """与 nlq.haversine_sql（SQL 里的 6371 * 2 * ASIN(SQRT(...))）同一公式。"""
    import math
    r = 6371.0
    dlng = math.radians(lng2 - lng1)
    dlat = math.radians(lat2 - lat1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def py_distance_km(inst, base):
    """与 SQL 的 CASE ... ROUND(...,2) ELSE NULL 对齐：缺坐标给 None。"""
    if inst.get("lng") is None or inst.get("lat") is None:
        return None
    return round(py_haversine(base[0], base[1], inst["lng"], inst["lat"]), 2)


def py_filter(insts, cond, page=1, page_size=20, base=None):
    base = base or nlq.DEFAULT_BASE
    out = []
    for it in insts:
        if not py_matches(it, cond):
            continue
        out.append({
            "id": str(it["id"]), "name": it["name"], "district": it["district"],
            "category": it["category"], "level": it["level"], "ownership": it["ownership"],
            "addr": it.get("addr") or "", "lng": it.get("lng"), "lat": it.get("lat"),
            "dept_count": it.get("dept_count"),
            "distance_km": py_distance_km(it, base), "score": py_score(it, cond),
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

    # 科室词表用**快照里的那一份**（meta.depts，来自 dws_dept_coverage），
    # 因为浏览器侧的 deptNames() 读的就是它。后端 /api/nlq/query 走 app.py 的
    # _dept_dict()，查的也是同一张表 —— 两边同源，所以这个断言同时锁住了两侧。
    dept_names = [d["dept_name"] for d in (snap.get("meta") or {}).get("depts") or []]
    print("科室词表：%d 个（快照 meta.depts）" % len(dept_names))
    assert dept_names, "快照 meta.depts 为空：离线解析认不出科室词，科室筛选会静默失效"
    has_depts_field = any("depts" in i for i in insts[:200])
    print("快照是否带科室隶属字段 depts：%s" % ("是" if has_depts_field else "否 ✗"))

    def base_of(case):
        b = case.get("base")
        return (b["lng"], b["lat"]) if b else None

    payload = [dict(c, page_size=20, with_stats=c.get("with_stats", False))
               for c in FILTER_CASES]
    req = {"queries": QUERIES, "dept_names": dept_names, "cases": payload}
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

    check("快照带科室隶属字段 depts", has_depts_field,
          "缺字段 → 离线按科室筛会直接提示「无法按科室筛选」，请带库重跑 web/build_spa.sh")

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

    print("\n=== ①.5 语义断言：口语化输入不得产出机构名残渣 ===")
    for q, must, forbid in SEMANTIC_CASES:
        p = nlq.parse(q, dept_names=dept_names)
        got = ["%s=%s" % (c["label"], c["text"]) for c in p["applied"]]
        labels = [c["label"] for c in p["applied"]]
        for want in must:
            check("必有[%s]∋%s" % (q, want), want in got, "实际=%s" % got)
        for bad in forbid:
            check("必无[%s]∌%s" % (q, bad), bad not in labels, "实际=%s" % got)
    print("  语义层：%d 条问句检查完成" % len(SEMANTIC_CASES))

    print("\n=== ② 筛选层一致性（%d 个条件组合）===" % len(FILTER_CASES))
    for c, j in zip(FILTER_CASES, js_cases):
        cond = dict(c["conditions"])
        p = py_filter(insts, cond, base=base_of(c))
        check("total[%s]" % c["name"], p["total"] == j["total"],
              "py=%d js=%d" % (p["total"], j["total"]))
        pf = p["items"][0]["id"] if p["items"] else None
        check("first[%s]" % c["name"], pf == j["first_id"],
              "py=%s(%s) js=%s(%s)" % (pf, p["items"][0]["name"] if p["items"] else "-",
                                       j["first_id"], j["first_name"]))
        check("stats[%s]" % c["name"], p["stats"] == j["stats"],
              "py=%s js=%s" % (p["stats"], j["stats"]))
        check("unsupported[%s]" % c["name"], not j.get("unsupported"),
              "js 报 unsupported=%s —— 离线形态本应能算这个条件" % j.get("unsupported"))
        # 距离：三处实现（SQL / Python 参考 / JS 引擎）都取 6371 球面距离，
        # 但浮点四舍五入在 .5 边界上可能差 1 分位，故用容差判定而不是逐位相等。
        pd = p["items"][0]["distance_km"] if p["items"] else None
        jd = j.get("first_dist")
        if pd is None or jd is None:
            check("first_dist[%s]" % c["name"], (pd is None) == (jd is None),
                  "py=%s js=%s" % (pd, jd))
        else:
            check("first_dist[%s]" % c["name"], abs(pd - jd) <= 0.011,
                  "py=%s js=%s" % (pd, jd))

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

    # ---------------------------------------------------------------------
    #  ④ 与真库核对（可选）：页面上那个数字，和库里的数字是同一个吗？
    #     用后端同一个 nlq.build_where() 生成 SQL，所以这里核对的是
    #     「离线引擎算出来的总数」vs「后端接口查出来的总数」。
    # ---------------------------------------------------------------------
    print("\n=== ④ 真库核对（离线结果 vs MySQL）===")
    try:
        import os
        import pymysql
        conn = pymysql.connect(
            host=os.environ.get("DB_HOST", "127.0.0.1"),
            port=int(os.environ.get("DB_PORT", 3307)),
            user=os.environ.get("DB_USER", "app"),
            password=os.environ.get("DB_PASS", "app123"),
            database="hospital", charset="utf8mb4")
    except Exception as e:  # noqa: BLE001
        print("  · 跳过：MySQL 不可达（%s）" % str(e)[:80])
        print("    这不算失败：①②③ 三节不需要数据库即可完成。")
    else:
        def db_count(cond):
            where, params = nlq.build_where(cond)
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM ads_inst_search t WHERE " + where, params)
                return cur.fetchone()[0]

        for c in FILTER_CASES:
            cond = dict(c["conditions"])
            cond.pop("_sort", None)
            try:
                n_db = db_count(cond)
            except Exception as e:  # noqa: BLE001
                check("db[%s]" % c["name"], False, "SQL 失败：%s" % str(e)[:120])
                continue
            n_local = py_filter(insts, cond, base=base_of(c))["total"]
            check("db_total[%s]" % c["name"], n_db == n_local,
                  "库=%d 离线=%d" % (n_db, n_local))
        # 决定性的一例：这次用户报的"海淀区骨科匹配不到"
        n_db = db_count({"district": ["海淀区"], "dept": "骨科"})
        n_local = py_filter(insts, {"district": ["海淀区"], "dept": "骨科"})["total"]
        check("db_total[海淀区骨科]", n_db == n_local == 40,
              "库=%d 离线=%d（预期 40）" % (n_db, n_local))
        print("  真库核对：海淀区+骨科 = %d 家（库里查同一条件也是 %d 家）" % (n_local, n_db))
        # 口语化问句：解析出来的条件拿去查库，必须是**非空**的。
        # 这正是用户会踩的坑——句子读得懂，结果 0 条，且不报任何错。
        for q in ("想找个靠谱的大医院", "海淀那边有哪些大医院", "附近有什么好点的医院",
                  "北京市三级医院", "北京协和医院"):
            cond = dict(nlq.parse(q, dept_names=dept_names)["conditions"])
            cond.pop("_sort", None)
            try:
                n_q = db_count(cond)
            except Exception as e:  # noqa: BLE001
                check("db_nonempty[%s]" % q, False, "SQL 失败：%s" % str(e)[:120])
                continue
            check("db_nonempty[%s]" % q, n_q > 0,
                  "解析为 %s → 库里 0 条，说明条件被误收紧了" % json.dumps(cond, ensure_ascii=False))
            print("  · %-12s → %s → 库里 %d 家" % (
                q, json.dumps(cond, ensure_ascii=False), n_q))
        conn.close()

    print("\n" + "=" * 68)
    if fail:
        print("❌ 双端一致性校验未通过：通过 %d / 失败 %d" % (ok, fail))
        return 1
    print("✅ 双端一致性校验通过：%d 项断言全部一致" % ok)
    return 0


if __name__ == "__main__":
    sys.exit(main())
