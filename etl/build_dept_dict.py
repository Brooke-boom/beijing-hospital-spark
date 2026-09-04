# -*- coding: utf-8 -*-
"""
科室字典生成脚本（医院-科室映射表）
====================================
输入：
  毕设/data/processed/master_institutions.csv     9,791 家机构主表
  毕设/data/processed/specialty_departments.csv   20 家三甲国家级重点专科
输出：
  毕设/data/processed/dept_dict.csv       标准科室字典（科室名 + 大类）
  毕设/data/processed/hospital_depts.csv  医院-科室映射表（含来源与重点专科标记）

科室来源优先级（source 字段）：
  specialty > key_depts > name > rule
  specialty  : 国家级重点专科名单（is_key_specialty=1）
  key_depts  : 主表登记的真实诊疗科目
  name       : 机构名称关键词推断（如"XX口腔诊所"→口腔科）
  rule       : 按 机构类型 × 等级 的规则推导（模拟数据，供筛选演示）
"""

import csv
import os
import re

BASE = os.path.expanduser("~/Desktop/毕设")
MASTER = os.path.join(BASE, "data/processed/master_institutions.csv")
SPECIALTY = os.path.join(BASE, "data/processed/specialty_departments.csv")
OUT_DICT = os.path.join(BASE, "data/processed/dept_dict.csv")
OUT_MAP = os.path.join(BASE, "data/processed/hospital_depts.csv")

# ---------------------------------------------------------------
# 1. 标准科室字典：科室名 -> 大类
# ---------------------------------------------------------------
DEPT_DICT = {
    # 内科类
    "心血管内科": "内科", "呼吸内科": "内科", "消化内科": "内科",
    "神经内科": "内科", "肾内科": "内科", "内分泌科": "内科",
    "血液内科": "内科", "老年病科": "内科", "普内科": "内科",
    "全科医疗科": "内科",
    # 外科类
    "普通外科": "外科", "骨科": "外科", "神经外科": "外科",
    "心胸外科": "外科", "泌尿外科": "外科", "肛肠外科": "外科",
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
}

# 原始科室名/病种名 -> 标准科室（关键词匹配，按顺序，先具体后泛化）
SYNONYMS = [
    # 中医特色病种（优先匹配，避免被内科规则吃掉）
    ("脾胃病", "消化内科"), ("肺病", "呼吸内科"), ("脑病", "神经内科"),
    ("神志", "精神心理科"), ("骨伤", "中医骨伤科"), ("正骨", "中医骨伤科"),
    ("针灸", "针灸推拿科"), ("推拿", "针灸推拿科"),
    ("心血管", "心血管内科"), ("肾病", "肾内科"), ("风湿", "普内科"),
    ("呼吸", "呼吸内科"), ("消化", "消化内科"), ("神经内科", "神经内科"),
    ("内分泌", "内分泌科"), ("血液", "血液内科"), ("老年", "老年病科"),
    ("心血管科", "心血管内科"),
    # 外科（先具体后泛化）
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
    # 感染/急救/康复/全科
    ("传染病", "感染科"), ("感染", "感染科"), ("肝病", "肝病科"),
    ("急诊", "急诊科"), ("重症", "重症医学科"), ("急救", "急诊科"),
    ("康复", "康复医学科"), ("全科", "全科医疗科"),
    # 中医泛化（放后面）
    ("中医内科", "中医内科"), ("中医", "中医内科"),
    # 内科泛化（最后）
    ("内科", "普内科"),
]

# 非临床/技术科室关键词 -> 跳过
SKIP_KW = ("检验", "影像", "病理", "药剂", "麻醉", "预防保健",
           "临终关怀", "护理", "体检", "输血", "营养", "消毒",
           "制剂", "血液专业", "血清")

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
# 2. 规则表：机构类型 × 等级 -> 标配科室
# ---------------------------------------------------------------
RULES = {
    "三级": ["心血管内科", "呼吸内科", "消化内科", "神经内科", "内分泌科",
             "普通外科", "骨科", "泌尿外科", "妇产科", "儿科",
             "眼科", "耳鼻咽喉科", "口腔科", "皮肤科",
             "急诊科", "肿瘤科", "精神心理科", "康复医学科", "中医内科"],
    "二级": ["普内科", "心血管内科", "呼吸内科", "消化内科",
             "普通外科", "骨科", "妇产科", "儿科",
             "眼科", "耳鼻咽喉科", "口腔科", "急诊科", "中医内科"],
    "一级": ["全科医疗科", "普内科", "普通外科", "妇产科", "儿科", "中医内科"],
    "社区卫生服务中心": ["全科医疗科", "普内科", "普通外科", "妇产科",
                        "儿科", "中医内科", "康复医学科"],
    "社区卫生服务站": ["全科医疗科"],
    "村卫生室": ["全科医疗科"],
    "医务室": ["全科医疗科"],
    "护理站": ["康复医学科"],
    "妇幼保健院": ["妇产科", "儿科"],
    "急救机构": ["急诊科"],
    "体检机构": [],
    "公共卫生机构": [],
    "其他医疗机构": ["全科医疗科"],
}


def rule_depts(cat, level, name):
    """按 类型/等级/名称 推导科室"""
    # 1) 机构名关键词优先（专科机构）
    for kw, depts in NAME_KW:
        if kw in name:
            return depts, "name"
    # 2) 类型专属规则
    if cat in RULES:
        return RULES[cat], "rule"
    # 3) 医院/中医医院/门诊部/诊所 兜底：按等级
    if level in ("三级", "二级", "一级"):
        return RULES[level], "rule"
    return ["普内科"], "rule"   # 门诊部/诊所等无等级的兜底


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
    mapping = {}   # (hid, dept) -> record
    stat = {"specialty": 0, "key_depts": 0, "name": 0, "rule": 0}
    for rec in insts:
        hid = rec["id"]
        hname = norm(rec["name"])
        cat = norm(rec.get("category"))
        level = norm(rec.get("level"))
        kds = parse_key_depts(rec.get("key_depts"))

        def add(dept, source, is_key=0, raw=""):
            if dept not in DEPT_DICT:
                return
            key = (hid, dept)
            # specialty > key_depts > name > rule
            rank = {"specialty": 0, "key_depts": 1, "name": 2, "rule": 3}
            if key not in mapping or rank[source] < rank[mapping[key]["source"]]:
                mapping[key] = {
                    "hospital_id": hid, "hospital_name": hname,
                    "dept_name": dept, "source": source,
                    "is_key_specialty": is_key, "raw_name": raw,
                }
                stat[source] += 1

        # 1) 国家级重点专科（最高优先，同科室标记 is_key=1）
        for sp in spec.get(hname, []):
            std = map_dept(sp)
            if std:
                add(std, "specialty", is_key=1, raw=sp)

        # 2) 登记诊疗科目
        for raw in kds:
            std = map_dept(raw)
            if std:
                add(std, "key_depts", raw=raw)

        # 3) 名称/规则推导（仅当无任何真实科室数据时）
        if not any(k[0] == hid for k in mapping) and hname not in spec:
            depts, source = rule_depts(cat, level, hname)
            for d in depts:
                add(d, source, raw="推导")

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

    # 统计
    from collections import Counter
    print("=== 科室字典 ===")
    print("标准科室数: %d" % len(DEPT_DICT))
    for cat in sorted(set(DEPT_DICT.values())):
        n = sum(1 for c in DEPT_DICT.values() if c == cat)
        print("  %-6s %d 个科室" % (cat, n))
    print("\n=== 医院-科室映射 ===")
    print("覆盖机构: %d / %d" % (len({r['hospital_id'] for r in rows}), len(insts)))
    print("映射总条数: %d" % len(rows))
    print("来源分布:", dict(stat))
    print("\n各科室机构数（Top 15）:")
    c = Counter(r["dept_name"] for r in rows)
    for dept, n in c.most_common(15):
        print("  %-8s %d 家" % (dept, n))
    print("\n输出:")
    print(" ", OUT_DICT)
    print(" ", OUT_MAP)


if __name__ == "__main__":
    main()
