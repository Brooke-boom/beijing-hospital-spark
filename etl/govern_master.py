# -*- coding: utf-8 -*-
"""
主表数据治理脚本（govern_master.py）
====================================
对 data/processed/master_institutions.csv 做一次性治理，产出 5 个新列并清理脏行：

1. 脏行清理：剔除 name 以「机构数:」开头的统计汇总行（非机构实体，如 id=291/631）
2. ownership / ownership_basis：公立/民营/未标注 三分类规则引擎
   - 口径：卫生统计惯例「公立 = 国有 + 集体全资」，其次看 profit 中的政府办/公立显式声明
   - 规则可解释：ownership_basis 记录命中的具体证据字段与取值
3. category_sub：类别细分口径统一（各区原始写法 → 统一子类枚举）
   - 诊所 → 普通/中医/口腔/医疗美容/中西医结合/其他诊所
   - 门诊部 → 综合/中医/口腔/医疗美容/眼科/普通专科/其他专科门诊部
   - 其他医疗机构 → 卫生所（室）/乡卫生院/医学检验实验室/医学研究（院）所/... 细分
   - 原始值为经济类型词或空 → 「未细分」
4. feature / feature_level：特色科室三级分级（权威优先）
   - L1 = 重点专科/重点科室：deep_out_W4 深度采集（官网核验）+ specialty_departments（国家/市级重点专科）
   - L2 = 登记诊疗科目/官方简介中的优势科室（master.key_depts）
   - L3 = 普通临床科室（hospital_depts 聚合）
   - 仅对 医院/中医医院/妇幼保健院/社区卫生服务中心/门诊部 生成；
     诊所/村卫生室/医务室/服务站等天然无「特色科室」概念，不生成
5. 治理报告：data/processed/govern_report.txt

运行：/Users/brooke/.workbuddy/binaries/python/envs/default/bin/python etl/govern_master.py
（普通 Python 亦可，无第三方依赖）
"""

import csv
import re
import shutil
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data" / "processed"
MASTER = DATA / "master_institutions.csv"
DEEP = DATA / "enrichment" / "net" / "waves" / "deep_out_W4.csv"
SPECIALTY = DATA / "specialty_departments.csv"
HOSPITAL_DEPTS = DATA / "hospital_depts.csv"
REPORT = DATA / "govern_report.txt"

# ---------- 配置：特色科室适用类别 ----------
FEATURE_ELIGIBLE = {"医院", "中医医院", "妇幼保健院", "社区卫生服务中心", "门诊部"}

# ---------- 配置：specialty_departments 名称别名（挂靠名 → master 注册名） ----------
SPECIALTY_ALIAS = {
    "卫生部北京医院": "北京医院",                # id=1152
    "首都医科大学附属宣武医院": "首都医科大学宣武医院",  # id=1592
    "首都医科大学附属地坛医院": "首都医科大学附属北京地坛医院",  # id=1473
}

# ---------- 配置：ownership 规则（有序，先命中先出） ----------
# (归属, 证据前缀, 匹配函数)
OWNERSHIP_RULES = [
    ("公立", "econ=国有全资",   lambda e, p: "国有全资" in e),
    ("公立", "econ=集体全资",   lambda e, p: "集体全资" in e),
    ("公立", "profit=政府办",   lambda e, p: "政府办" in p),
    ("公立", "profit=公立",     lambda e, p: p == "公立"),
    ("公立", "profit=政府非营利", lambda e, p: "政府非营利" in p),
    ("民营", "profit=民营",     lambda e, p: "民营" in p),
    ("民营", "econ=私有",       lambda e, p: "私有" in e),
    ("民营", "profit=营利性",   lambda e, p: "营利性" in p),
    ("民营", "econ=中外/港澳台合资合作", lambda e, p: ("中外" in e) or ("港、澳、台" in e)),
]

# ---------- 配置：category_sub 细分规则 ----------
def _strip_code(raw: str) -> str:
    """去掉原始类别前面的编码前缀：D211. / D212- / M300- / P939- 等"""
    return re.sub(r"^[A-Z]\d+[-．.]*\d*[-．.]?", "", raw).strip()

SUB_RULES = {
    "诊所": [
        ("口腔诊所", lambda t: "口腔" in t),
        ("医疗美容诊所", lambda t: ("医疗美容" in t) or ("医美" in t)),
        ("中西医结合诊所", lambda t: "中西医结合" in t),
        ("中医诊所", lambda t: "中医" in t),
        ("普通诊所", lambda t: "普通" in t),
        ("其他诊所", lambda t: t in ("其他诊所", "D229")),
    ],
    "门诊部": [
        ("口腔门诊部", lambda t: "口腔" in t),
        ("医疗美容门诊部", lambda t: "医疗美容" in t),
        ("眼科门诊部", lambda t: "眼科" in t),
        ("中医门诊部", lambda t: "中医" in t),
        ("综合门诊部", lambda t: "综合" in t),
        ("普通专科门诊部", lambda t: "普通专科" in t),
        ("其他专科门诊部", lambda t: "其他专科" in t),
    ],
    "其他医疗机构": [
        ("卫生所（室）", lambda t: "卫生所" in t or "卫生室" in t),
        ("乡卫生院", lambda t: "乡卫生院" in t),
        ("医学检验实验室", lambda t: ("检验" in t) or ("临床检验" in t)),
        ("医学研究（院）所", lambda t: ("研究院" in t) or ("研究所" in t)),
        ("中小学卫生保健所", lambda t: "保健所" in t),
        ("专科疾病防治所（站）", lambda t: "防治" in t),
        ("护理院", lambda t: "护理院" in t),
        ("医学教育培训机构", lambda t: ("培训" in t) or ("卫生学校" in t)),
        ("卫生防疫站", lambda t: "防疫站" in t),
        ("计划生育技术服务机构", lambda t: "计划生育" in t),
        ("卫生信息机构", lambda t: "统计信息" in t),
        ("医学学术团体", lambda t: ("医学会" in t) or ("科技交流" in t)),
        ("社区卫生服务管理中心", lambda t: "服务管理中心" in t),
        ("社区医疗机构", lambda t: "社区医疗机构" in t),
        ("预防保健中心", lambda t: "预防保健" in t),
    ],
}
# 经济类型词（出现在 category_raw 里说明该来源没有提供机构子类信息）
ECON_WORDS = ("国有", "私有", "有限责任", "内资", "联营", "股份", "国有全资", "其它", "其他", "独资", "法人")


def read_csv(path: Path):
    for enc in ("utf-8-sig", "gb18030"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法读取 {path}")


def derive_ownership(econ: str, profit: str):
    e = (econ or "").strip()
    p = (profit or "").strip()
    for label, basis, fn in OWNERSHIP_RULES:
        try:
            if fn(e, p):
                return label, basis
        except Exception:
            continue
    return "未标注", ""


def derive_category_sub(category: str, category_raw: str) -> str:
    cat = (category or "").strip()
    raw = _strip_code((category_raw or "").strip())
    rules = SUB_RULES.get(cat)
    if not rules:
        return ""
    if not raw or any(w in raw for w in ECON_WORDS) or raw in ("对内", "对外专科"):
        return "未细分"
    for sub, fn in rules:
        if fn(raw):
            return sub
    return "未细分"


def split_ids(id_field: str):
    return [x.strip() for x in re.split(r"[;；,，]", str(id_field or "")) if x.strip()]


def split_depts(dept_field: str):
    return [x.strip() for x in re.split(r"[;；、,，]", str(dept_field or "")) if x.strip()]


def main():
    t0 = time.time()
    master = read_csv(MASTER)
    n_before = len(master)
    report = []
    log = report.append
    log("=" * 64)
    log("主表数据治理报告  govern_master.py")
    log("=" * 64)

    # ---------- 1. 脏行清理 ----------
    junk = [r for r in master if str(r.get("name", "")).startswith("机构数")]
    master = [r for r in master if not str(r.get("name", "")).startswith("机构数")]
    log(f"\n[1] 脏行清理：剔除 {len(junk)} 行统计汇总行（name 以「机构数:」开头）")
    for r in junk:
        log(f"    - id={r['id']} name={r['name']} district={r.get('district','')} source={str(r.get('source_files',''))[:40]}")

    # ---------- 2. ownership ----------
    own_counter = Counter()
    basis_counter = Counter()
    for r in master:
        label, basis = derive_ownership(r.get("econ", ""), r.get("profit", ""))
        r["ownership"] = label
        r["ownership_basis"] = basis
        own_counter[label] += 1
        if basis:
            basis_counter[basis] += 1
    log(f"\n[2] ownership 三分类分布（共 {len(master)} 行）：")
    for k, v in own_counter.most_common():
        log(f"    {k}: {v}  ({v/len(master)*100:.1f}%)")
    log("    规则命中明细：")
    for k, v in basis_counter.most_common():
        log(f"      {k}: {v}")

    # ---------- 3. category_sub ----------
    sub_counter = Counter()
    for r in master:
        sub = derive_category_sub(r.get("category", ""), r.get("category_raw", ""))
        r["category_sub"] = sub
        sub_counter[(r["category"], sub)] += 1
    log(f"\n[3] category_sub 细分分布（按 category 分组）：")
    cur = None
    for (cat, sub), v in sorted(sub_counter.items()):
        if cat != cur:
            log(f"  ◆ {cat}")
            cur = cat
        log(f"      {sub or '(空)'}: {v}")

    # ---------- 4. feature / feature_level ----------
    # 4.1 L1a: deep_out_W4（深度采集，官网核验的重点/优势科室）
    l1 = {}  # id -> OrderedDict(dept -> True)
    l1_basis = {}
    deep = read_csv(DEEP)
    deep_hit = 0
    for row in deep:
        for iid in split_ids(row.get("id", "")):
            depts = split_depts(row.get("key_depts", ""))
            if not depts:
                continue
            d = l1.setdefault(iid, OrderedDict())
            for dpt in depts:
                d[dpt] = True
            l1_basis.setdefault(iid, "深度采集(官网核验)")
            deep_hit += 1
    # 4.2 L1b: specialty_departments（国家/市级重点专科，按名称匹配 + 别名）
    spec = read_csv(SPECIALTY)
    name2id = {}
    for r in master:
        name2id.setdefault(r["name"], r["id"])
    spec_hit, spec_miss = 0, 0
    for row in spec:
        name = SPECIALTY_ALIAS.get(row["hospital"].strip(), row["hospital"].strip())
        iid = name2id.get(name)
        if not iid:
            spec_miss += 1
            log(f"    ⚠️ 专科表医院未匹配: {row['hospital']}")
            continue
        d = l1.setdefault(iid, OrderedDict())
        for dpt in split_depts(row.get("specialties", "")):
            d[dpt] = True
        l1_basis[iid] = "深度采集+重点专科"
        spec_hit += 1
    log(f"\n[4] feature 三级分级：")
    log(f"    L1 深度采集覆盖 id: {len(l1)}（deep 记录命中 {deep_hit}，专科表命中 {spec_hit}/{len(spec)}，未匹配 {spec_miss}）")

    # 4.3 L2: master.key_depts（登记诊疗科目/官方简介）
    l2_count = 0
    l3_count = 0
    # 4.4 L3: hospital_depts 聚合（普通临床科室）
    depts_by_hosp = {}
    for row in read_csv(HOSPITAL_DEPTS):
        iid = (row.get("hospital_id") or "").strip()
        dpt = (row.get("dept_name") or "").strip()
        if iid and dpt:
            depts_by_hosp.setdefault(iid, []).append(dpt)

    for r in master:
        cat = (r.get("category") or "").strip()
        iid = r["id"]
        r["feature"] = ""
        r["feature_level"] = ""
        if cat not in FEATURE_ELIGIBLE:
            continue
        if iid in l1:
            depts = list(l1[iid].keys())
            r["feature"] = ";".join(depts)
            r["feature_level"] = "1"
        elif str(r.get("key_depts", "") or "").strip():
            r["feature"] = ";".join(dict.fromkeys(split_depts(r["key_depts"])))
            r["feature_level"] = "2"
            l2_count += 1
        elif iid in depts_by_hosp:
            uniq = list(dict.fromkeys(depts_by_hosp[iid]))[:15]
            r["feature"] = ";".join(uniq)
            r["feature_level"] = "3"
            l3_count += 1

    lv_counter = Counter(r["feature_level"] or "(无)" for r in master)
    log(f"    L1(重点专科/重点科室): {lv_counter.get('1', 0)} 家")
    log(f"    L2(登记诊疗科目/优势科室): {l2_count} 家")
    log(f"    L3(普通临床科室 top15): {l3_count} 家")
    log(f"    不适用（诊所/村卫生室/医务室等）: {lv_counter.get('(无)', 0)} 家")

    # ---------- 5. 写回（先备份） ----------
    backup_dir = DATA / "backup"
    backup_dir.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M")
    backup = backup_dir / f"master_institutions.bak-{ts}.csv"
    shutil.copy2(MASTER, backup)
    log(f"\n[5] 备份 → {backup.name}")

    fieldnames = list(master[0].keys())
    with open(MASTER, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(master)
    log(f"    写回 {MASTER.name}: {n_before} → {len(master)} 行 × {len(fieldnames)} 列")
    log(f"    新增列: ownership, ownership_basis, category_sub, feature, feature_level")

    # ---------- 6. 校验 ----------
    check = read_csv(MASTER)
    assert len(check) == len(master), "行数不一致！"
    assert all("ownership" in r and "feature_level" in r for r in check[:50]), "新列缺失！"
    junk2 = [r for r in check if str(r.get("name", "")).startswith("机构数")]
    assert not junk2, "垃圾行仍存在！"
    log(f"\n[6] 校验通过 ✓  用时 {time.time()-t0:.1f}s")

    REPORT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print(f"\n✅ 治理完成，报告已写入 {REPORT}")


if __name__ == "__main__":
    sys.exit(main())
