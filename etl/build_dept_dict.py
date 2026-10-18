# -*- coding: utf-8 -*-
"""
科室字典生成脚本（医院-科室映射表）
====================================
输入：
  毕设/data/processed/master_institutions.csv     9,789 家机构主表
  毕设/data/processed/specialty_departments.csv   20 家三甲国家级重点专科
输出：
  毕设/data/processed/dept_dict.csv       标准科室字典（科室名 + 大类）
  毕设/data/processed/hospital_depts.csv  医院-科室映射表（含来源与重点专科标记）

科室来源优先级（source 字段）：
  specialty > online > key_depts > name > rule
  specialty  : 国家级重点专科名单（is_key_specialty=1）
  online     : 好大夫在线抓取的真实科室列表（haodf_depts.jsonl + haodf_match.csv，
               2026-09-22 新增；全表唯一「逐家核实过科室构成」的来源）
  key_depts  : 主表登记的真实诊疗科目
  name       : 机构名称关键词推断（如"XX口腔诊所"→口腔科）
  rule       : 仅限「类型职能规定」的科室（见 RULES 注释）。2026-10-18 起
               **不再按医院等级套通用清单** —— 那会给北大一院塞上官网没有的
               精神心理科；医院科室一律以 specialty/online/key_depts/name 为准。

⚠️ online 刻意排在 specialty **之后**：specialty 行带 is_key_specialty=1（国家级重点专科
   标记），若让 online 压过它就会把重点专科标记抹掉。但 online 必须压过 key_depts/name/rule
   —— 那三者要么只有一级科目、要么是推导值，都不如在线核实的完整科室列表。

院区行继承（2026-10-18）：院区与主院是同一家机构的执业延伸，科室设置一致，
   源数据却只登记主院。院区行从主院继承科室，source 沿用父行原始来源
   （不冒充逐家核实），raw_name 记「院区继承 · <主院名>」；只填空不覆盖。
"""

import csv
import json
import os
import re

BASE = os.path.expanduser("~/Desktop/毕设")
MASTER = os.path.join(BASE, "data/processed/master_institutions.csv")
SPECIALTY = os.path.join(BASE, "data/processed/specialty_departments.csv")
# 好大夫在线抓取产物（scrape_haodf_depts.py 抓、enrich_depts_haodf.py 匹配）
HAODF_JSONL = os.path.join(BASE, "data/processed/haodf_depts.jsonl")
HAODF_MATCH = os.path.join(BASE, "data/processed/haodf_match.csv")
OUT_DICT = os.path.join(BASE, "data/processed/dept_dict.csv")
OUT_MAP = os.path.join(BASE, "data/processed/hospital_depts.csv")

# ---------------------------------------------------------------
# 1. 标准科室字典：科室名 -> 大类
#    2026-10-18 口径扩容 32 → 44 类：联网核对协和 / 北大第一医院官网后，
#    补齐「口径内缺」的 12 类（风湿免疫全国第一的协和竟无处安放）：
#    临床 5 类 + 医技平台 7 类。医技平台此前被 SKIP_KW 整体丢弃。
# ---------------------------------------------------------------
DEPT_DICT = {
    # 内科类
    "心血管内科": "内科", "呼吸内科": "内科", "消化内科": "内科",
    "神经内科": "内科", "肾内科": "内科", "内分泌科": "内科",
    "血液内科": "内科", "老年病科": "内科", "普内科": "内科",
    "全科医疗科": "内科", "风湿免疫科": "内科",
    # 外科类
    "普通外科": "外科", "骨科": "外科", "神经外科": "外科",
    "心胸外科": "外科", "泌尿外科": "外科", "肛肠外科": "外科",
    "乳腺外科": "外科", "整形外科": "外科", "介入血管外科": "外科",
    "小儿外科": "外科",
    # 妇产儿科
    "妇产科": "妇产科儿科", "儿科": "妇产科儿科",
    # 肿瘤
    "肿瘤科": "肿瘤科",
    # 精神心理
    "精神心理科": "精神心理科",
    # 五官
    "眼科": "五官科", "耳鼻咽喉科": "五官科", "口腔科": "五官科",
    # 皮肤
    "皮肤科": "皮肤科",
    # 中医类（含中医特色病种归并）
    "中医内科": "中医科", "中医骨伤科": "中医科", "针灸推拿科": "中医科",
    # 感染肝病
    "感染科": "感染科", "肝病科": "感染科",
    # 急救重症
    "急诊科": "急诊重症", "重症医学科": "急诊重症",
    # 康复
    "康复医学科": "康复科",
    # 医技平台（2026-10-18 新增收录：只从 specialty/online/key_depts 等真实来源进入，
    # 规则不再给任何机构套配这些科室）
    "麻醉科": "医技平台", "医学影像科": "医技平台", "超声医学科": "医技平台",
    "核医学科": "医技平台", "医学检验科": "医技平台", "病理科": "医技平台",
    "临床营养科": "医技平台",
}

# 原始科室名/病种名 -> 标准科室（关键词匹配，按顺序，先具体后泛化）
SYNONYMS = [
    # 中医特色病种（优先匹配，避免被内科规则吃掉）
    ("脾胃病", "消化内科"), ("肺病", "呼吸内科"), ("脑病", "神经内科"),
    ("神志", "精神心理科"), ("骨伤", "中医骨伤科"), ("正骨", "中医骨伤科"),
    ("针灸", "针灸推拿科"), ("推拿", "针灸推拿科"),
    ("心血管", "心血管内科"), ("肾病", "肾内科"), ("风湿", "风湿免疫科"),
    ("呼吸", "呼吸内科"), ("消化", "消化内科"), ("神经内科", "神经内科"),
    ("内分泌", "内分泌科"), ("血液", "血液内科"), ("老年", "老年病科"),
    ("心血管科", "心血管内科"),
    # 外科（先具体后泛化；小儿外科/血管外科 必须排在更泛的关键词之前）
    ("小儿外科", "小儿外科"), ("儿外", "小儿外科"),
    ("血管外科", "介入血管外科"), ("介入", "介入血管外科"),
    ("乳腺", "乳腺外科"), ("整形外科", "整形外科"), ("整形", "整形外科"),
    ("骨", "骨科"), ("神经外科", "神经外科"), ("胸外", "心胸外科"),
    ("心外", "心胸外科"), ("泌尿", "泌尿外科"), ("肛肠", "肛肠外科"),
    ("普通外科", "普通外科"), ("普外", "普通外科"), ("外科", "普通外科"),
    # 妇儿
    ("妇产", "妇产科"), ("妇科", "妇产科"), ("产科", "妇产科"),
    ("儿科", "儿科"), ("儿童", "儿科"), ("小儿", "儿科"),
    # 专科
    ("肿瘤", "肿瘤科"), ("精神", "精神心理科"), ("心理", "精神心理科"),
    ("眼科", "眼科"), ("耳鼻喉", "耳鼻咽喉科"), ("耳鼻咽喉", "耳鼻咽喉科"),
    ("口腔", "口腔科"), ("牙", "口腔科"), ("皮肤", "皮肤科"),
    ("性病", "皮肤科"),
    # 医技平台（2026-10-18 起收录，不再一律丢弃）
    ("麻醉", "麻醉科"), ("影像", "医学影像科"), ("放射", "医学影像科"),
    ("超声", "超声医学科"), ("核医学", "核医学科"),
    ("检验", "医学检验科"), ("病理", "病理科"), ("营养", "临床营养科"),
    # 感染/急救/康复/全科
    ("传染病", "感染科"), ("感染", "感染科"), ("肝病", "肝病科"),
    ("急诊", "急诊科"), ("重症", "重症医学科"), ("急救", "急诊科"),
    ("康复", "康复医学科"), ("全科", "全科医疗科"),
    # 中医泛化（放后面）
    ("中医内科", "中医内科"), ("中医", "中医内科"),
    # 内科泛化（最后）
    ("内科", "普内科"),
]

# 非临床/技术科室关键词 -> 跳过（2026-10-18 收窄：检验/影像/病理/麻醉/营养
# 已进 DEPT_DICT 医技平台，不再丢；药剂/输血等仍无对应标准科室，继续跳过）
SKIP_KW = ("药剂", "预防保健", "临终关怀", "护理", "体检",
           "输血", "消毒", "制剂", "血液专业", "血清")

# 机构名称关键词 -> 标准科室（用于诊所/门诊部等无登记信息的机构）
NAME_KW = [
    ("口腔", ["口腔科"]), ("牙", ["口腔科"]),
    ("眼科", ["眼科"]), ("耳鼻喉", ["耳鼻咽喉科"]),
    ("皮肤病", ["皮肤科"]), ("皮肤", ["皮肤科"]),
    ("精神病", ["精神心理科"]), ("精神", ["精神心理科"]), ("心理", ["精神心理科"]),
    ("妇产", ["妇产科"]), ("妇科", ["妇产科"]), ("女子", ["妇产科"]),
    ("儿科", ["儿科"]), ("儿童", ["儿科"]),
    ("骨科", ["骨科"]), ("骨伤", ["中医骨伤科"]), ("正骨", ["中医骨伤科"]),
    ("肛肠", ["肛肠外科"]),
    ("肿瘤", ["肿瘤科"]),
    ("肝病", ["肝病科"]), ("传染", ["感染科"]),
    ("康复", ["康复医学科"]),
    ("中医", ["中医内科", "针灸推拿科"]), ("国医", ["中医内科"]),
    ("针灸", ["针灸推拿科"]),
    ("美容", []), ("整形", []),  # 医疗美容：不映射临床科室
]


def norm(s):
    """安全转字符串，NaN -> ''"""
    if s is None or (isinstance(s, float) and s != s):
        return ""
    return str(s).strip()


# 重点专科名单中的历史/全称医院名 -> master 主表标准名（修 join 丢失）
HOSP_ALIAS = {
    "卫生部北京医院": "北京医院",
    "首都医科大学附属宣武医院": "首都医科大学宣武医院",
    "首都医科大学附属地坛医院": "首都医科大学附属北京地坛医院",
}


def map_dept(raw):
    """原始科室名 -> 标准科室名；无法映射返回 None"""
    name = norm(raw).rstrip("*＊").strip()
    if not name:
        return None
    for kw in SKIP_KW:
        if kw in name:
            return None
    for kw, std in SYNONYMS:
        if kw in name:
            return std
    return None


def parse_key_depts(raw):
    """解析登记诊疗科目字符串，返回原始科室名列表
    格式1: '内科;呼吸内科专业 /外科;普通外科专业'（/ 分隔一级科目）
    格式2: '心血管科、急诊科、肿瘤科'（、 分隔）
    """
    s = norm(raw)
    if not s or s.lower() == "nan":
        return []
    parts = re.split(r"[/、，,]", s)
    out = []
    for p in parts:
        name = p.split(";")[0].split("；")[0].rstrip("*＊").strip()
        if name:
            out.append(name)
    return out


# ---------------------------------------------------------------
# 2. 规则表：**仅限类型职能规定**的科室
# ---------------------------------------------------------------
# 2026-10-18 起删除 三级/二级/一级 的「医院等级通用清单」——那是把模板套在医院
# 头上，实测给北大一院塞上了官网没有的精神心理科，属于过度推断（联网核对
# 协和 41 临床科室 / 北大第一医院 34 临床科室，模板都盖不住也盖不准）。
# 医院科室一律以 specialty > online > key_depts > name 四个来源为准。
# 保留的只是《基本标准》/机构职能**明文规定**的科室：
#   · 社区卫生服务中心：《城市社区卫生服务中心基本标准》要求设全科诊室、
#     中医诊室、康复治疗室 → 全科医疗科 / 中医内科 / 康复医学科
#   · 社区卫生服务站、村卫生室：基本医疗服务 → 全科医疗科
#   · 妇幼保健院：职能即妇女保健 + 儿童保健
#   · 急救机构：职能即院前急救
RULES = {
    "社区卫生服务中心": ["全科医疗科", "中医内科", "康复医学科"],
    "社区卫生服务站": ["全科医疗科"],
    "村卫生室": ["全科医疗科"],
    "妇幼保健院": ["妇产科", "儿科"],
    "急救机构": ["急诊科"],
    "体检机构": [],
    "公共卫生机构": [],
}


def rule_depts(cat, level, name):
    """按 类型/名称 推导科室；无依据时返回空（宁缺勿编）"""
    # 1) 机构名关键词优先（专科机构）
    for kw, depts in NAME_KW:
        if kw in name:
            return depts, "name"
    # 2) 类型职能规定
    if cat in RULES:
        return RULES[cat], "rule"
    # 3) 医院等无职能清单的机构：不再按等级套模板，也不给无等级的
    #    门诊部/诊所硬塞「普内科」——没有依据就不生成
    return [], "rule"


def load_online_depts():
    """读好大夫在线抓取结果 → {inst_id: [原始科室名, ...]}

    依赖 haodf_match.csv（etl/enrich_depts_haodf.py 产出）：那张表已经把
    「好大夫医院」与「主表机构」做过严格匹配，这里直接用 inst_id 取值，
    绝不在本脚本里再做一次名称匹配 —— 名称匹配最容易出错的环节只保留一处。
    """
    if not (os.path.exists(HAODF_JSONL) and os.path.exists(HAODF_MATCH)):
        return {}
    depts = {}
    for line in open(HAODF_JSONL, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        names = [d.get("name") for d in (o.get("depts") or []) if d.get("name")]
        if names:
            depts[str(o.get("hid"))] = names
    out = {}
    with open(HAODF_MATCH, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            ds = depts.get(str(row.get("hid")))
            if ds:
                out[row["inst_id"]] = ds
    return out


def main():
    # 读取主表
    with open(MASTER, newline="", encoding="utf-8-sig") as f:
        insts = list(csv.DictReader(f))
    # 读取重点专科表
    spec = {}
    if os.path.exists(SPECIALTY):
        with open(SPECIALTY, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                h = norm(row.get("hospital"))
                h = HOSP_ALIAS.get(h, h)   # 历史全称 -> 主表标准名
                s = norm(row.get("specialties"))
                if h and s:
                    spec[h] = [x.strip() for x in re.split(r"[、，,]", s) if x.strip()]

    # 医院-科室映射
    online = load_online_depts()
    print("  好大夫在线科室明细：%d 家机构可用" % len(online))
    mapping = {}   # (hid, dept) -> record
    rank = {"specialty": 0, "online": 1, "key_depts": 2, "name": 3, "rule": 4}

    def add(dept, source, hid, hname, is_key=0, raw=""):
        if dept not in DEPT_DICT:
            return
        key = (hid, dept)
        # specialty > online > key_depts > name > rule
        if key not in mapping or rank[source] < rank[mapping[key]["source"]]:
            mapping[key] = {
                "hospital_id": hid, "hospital_name": hname,
                "dept_name": dept, "source": source,
                "is_key_specialty": is_key, "raw_name": raw,
            }

    for rec in insts:
        hid = rec["id"]
        hname = norm(rec["name"])
        cat = norm(rec.get("category"))
        level = norm(rec.get("level"))
        kds = parse_key_depts(rec.get("key_depts"))

        # 1) 国家级重点专科（最高优先，同科室标记 is_key=1）
        for sp in spec.get(hname, []):
            std = map_dept(sp)
            if std:
                add(std, "specialty", hid, hname, is_key=1, raw=sp)

        # 2) 好大夫在线核实的科室列表（完整科室构成，压过下面三项推导/单级科目）
        for raw in online.get(hid, []):
            std = map_dept(raw)
            if std:
                add(std, "online", hid, hname, raw=raw)

        # 3) 登记诊疗科目
        for raw in kds:
            std = map_dept(raw)
            if std:
                add(std, "key_depts", hid, hname, raw=raw)

        # 4) 名称/类型职能推导（仅当无任何真实科室数据时）
        if not any(k[0] == hid for k in mapping) and hname not in spec:
            depts, source = rule_depts(cat, level, hname)
            for d in depts:
                add(d, source, hid, hname, raw="推导")

    # ---------------------------------------------------------------
    # 5) 院区行继承主院科室（2026-10-18）
    #    院区与主院是同一家机构的执业延伸，科室设置一致；源数据只登记主院，
    #    院区行此前只靠名称推导剩 0~2 个科室。父机构判定：
    #      a. web/campus_evidence.json 的 campus_groups（括号院区，有证据留档）；
    #      b. 兜底：名称去掉「XX院区」后缀后恰好命中一行
    #         （北京中医药大学东直门医院通州院区 / 北京儿童医院顺义院区（市属）——
    #          这两行的院区不在括号里，campus_evidence 规则接不住）。
    #    source 沿用父行原始来源，不冒充逐家核实；只填空不覆盖（rank 保证）。
    # ---------------------------------------------------------------
    name2id = {}
    for rec in insts:
        nm = norm(rec["name"])
        if nm and nm not in name2id:
            name2id[nm] = rec["id"]
    parent_of = {}
    CAMPUS_EV = os.path.join(BASE, "web/campus_evidence.json")
    if os.path.exists(CAMPUS_EV):
        with open(CAMPUS_EV, encoding="utf-8") as f:
            ev = json.load(f)
        for g in ev.get("campus_groups", []):
            pid = name2id.get(norm(g.get("main_name")))
            if not pid:
                continue
            for m in g.get("members", []):
                if str(m.get("id")) != str(pid):
                    parent_of[str(m["id"])] = str(pid)
    # 「XX院区」只取结尾的院区段（{1,8} 且排除「院」字，避免把「医院」当院区名；
    # 贪婪匹配会把整串都吃掉 → 前缀为空）。北医大东直门→通州院区、儿童医院→顺义院区。
    re_paren = re.compile(r"[（(][^（）()]*[)）]")
    re_campus = re.compile(r"[^院（）()]{1,8}院区$")
    for rec in insts:
        nid, nm = rec["id"], norm(rec["name"])
        if nid in parent_of or "院区" not in nm:
            continue
        cand = re_paren.sub("", nm).strip()
        m2 = re_campus.search(cand)
        if not m2:
            continue
        cand = cand[:m2.start()].strip("（）() ")
        pid = name2id.get(cand)
        if pid and pid != nid:
            parent_of[nid] = pid

    n_inherit = 0
    for cid, pid in sorted(parent_of.items(), key=lambda kv: int(kv[0])):
        prows = [r for r in mapping.values() if r["hospital_id"] == pid]
        if not prows:
            continue
        cname = norm(next(r["name"] for r in insts if r["id"] == cid))
        pname = prows[0]["hospital_name"]
        exist = {k for k in mapping if k[0] == cid}
        for pr in prows:
            add(pr["dept_name"], pr["source"], cid, cname,
                is_key=int(pr["is_key_specialty"] or 0),
                raw="院区继承 · " + pname)
        n_inherit += sum(1 for k in mapping if k[0] == cid and k not in exist)
    print("  院区行继承：%d 家院区，从主院带入 %d 条科室记录" % (len(parent_of), n_inherit))

    # 输出科室字典
    with open(OUT_DICT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["dept_name", "dept_category", "is_clinical"])
        for name, cat in DEPT_DICT.items():
            w.writerow([name, cat, 1])
    # 输出映射表
    rows = sorted(mapping.values(), key=lambda r: (int(r["hospital_id"]), r["dept_name"]))
    with open(OUT_MAP, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["hospital_id", "hospital_name", "dept_name", "source",
                    "is_key_specialty", "raw_name"])
        for r in rows:
            w.writerow([r["hospital_id"], r["hospital_name"], r["dept_name"],
                        r["source"], r["is_key_specialty"], r["raw_name"]])

    # 统计（来源分布按**最终保留**的行算，而不是累计添加次数 ——
    # 优先级替换会让旧 source 多计一次）
    from collections import Counter
    print("=== 科室字典 ===")
    print("标准科室数: %d" % len(DEPT_DICT))
    for cat in sorted(set(DEPT_DICT.values())):
        n = sum(1 for c in DEPT_DICT.values() if c == cat)
        print("  %-6s %d 个科室" % (cat, n))
    print("\n=== 医院-科室映射 ===")
    print("覆盖机构: %d / %d" % (len({r['hospital_id'] for r in rows}), len(insts)))
    print("映射总条数: %d" % len(rows))
    print("来源分布(最终保留):", dict(Counter(r["source"] for r in rows)))
    print("\n各科室机构数（Top 15）:")
    c = Counter(r["dept_name"] for r in rows)
    for dept, n in c.most_common(15):
        print("  %-8s %d 家" % (dept, n))
    print("\n输出:")
    print(" ", OUT_DICT)
    print(" ", OUT_MAP)


if __name__ == "__main__":
    main()
