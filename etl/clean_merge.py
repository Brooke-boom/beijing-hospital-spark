# -*- coding: utf-8 -*-
"""
北京市医疗资源数据清洗整合脚本（毕设 ETL 第一环）
====================================================
输入：数据目录（默认 ~/Desktop/毕设/data，其次 ~/Downloads）下约 74 个异构表格文件
  - CSV（UTF-8 / GBK / GB18030 编码混杂）
  - 伪 CSV：实为 xlsx（PK 头）或老版 xls（OLE2 头）
  - 分号分隔的 CSV
  - 表头不在第一行（带大标题/落款行）
输出：
  - master_institutions.csv   全市医疗机构主表（去重合并后）
  - specialty_departments.csv 临床重点专科表（医院 -> 专科列表）
  - data_quality_report.md    数据质量报告
  默认写到数据目录的 processed/ 子目录；也可用参数指定。

用法：
  python clean_merge.py                    # 默认: 读 ~/Desktop/毕设/data, 写 毕设/data/processed
  python clean_merge.py <数据目录> [输出目录]
"""

import csv
import io
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict

import pandas as pd


def _default_src():
    p = os.path.expanduser("~/Desktop/毕设/data")
    return p if os.path.isdir(p) else os.path.expanduser("~/Downloads")


SRC_DIR = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get("HOSPITAL_DATA_DIR") or _default_src()
)
if len(sys.argv) > 2:
    OUT_DIR = sys.argv[2]
elif SRC_DIR == os.path.expanduser("~/Desktop/毕设/data"):
    OUT_DIR = os.path.join(SRC_DIR, "processed")   # 数据放毕设文件夹时，产物就地输出
else:
    OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT_DIR, exist_ok=True)

# ----------------------------------------------------------------------
# 1. 通用加载器：识别真实格式 + 编码 + 分隔符
# ----------------------------------------------------------------------

def load_any(path):
    """任意表格文件 -> (rows: list[list[str]])，识别 xlsx/xls 伪 CSV、多编码文本。"""
    with open(path, "rb") as f:
        head = f.read(8)
    if head[:2] == b"PK":                       # xlsx（含伪装成 .csv 的）
        return _load_xlsx(path)
    if head[:4] == b"\xd0\xcf\x11\xe0":         # 老版 xls（OLE2）
        return _load_xls(path)
    return _load_text(path)


def _load_xlsx(path):
    from openpyxl import load_workbook
    import shutil, tempfile
    # openpyxl 拒绝非 .xlsx 扩展名，伪装文件先复制成临时 .xlsx
    if not path.lower().endswith((".xlsx", ".xlsm", ".xltx", ".xltm")):
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        shutil.copy(path, tmp.name)
        path = tmp.name
    wb = load_workbook(path, read_only=True)
    ws = wb.active
    # 部分文件维度声明虚高（如 1048542x16331），需重置后按实际内容迭代
    if ws.max_row > 100000 or ws.max_column > 300:
        try:
            ws.reset_dimensions()
        except Exception:
            pass
    rows, empty_streak, MAX_EMPTY = [], 0, 50
    for r in ws.iter_rows(values_only=True):
        row = ["" if c is None else str(c).strip() for c in r[:40]]   # 只取前40列
        if any(row):
            rows.append(row)
            empty_streak = 0
        else:
            empty_streak += 1
            if empty_streak >= MAX_EMPTY:   # 连续50空行即认为数据结束
                break
    wb.close()
    return rows


def _load_xls(path):
    import xlrd
    sh = xlrd.open_workbook(path).sheet_by_index(0)
    rows = []
    for i in range(sh.nrows):
        row = []
        for j in range(sh.ncols):
            v = sh.cell_value(i, j)
            if isinstance(v, float) and v == int(v):
                v = str(int(v))                 # 59277120.0 -> 59277120
            row.append(str(v).strip())
        if any(row):
            rows.append(row)
    return rows


def _load_text(path):
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        raise ValueError("无法识别编码")
    sample = text[:2048]
    delim = max(",;\t", key=lambda d: sample.count(d))   # 自动选分隔符
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    return [[c.strip() for c in r] for r in rows]


# ----------------------------------------------------------------------
# 2. 表头行自动定位（跳过大标题 / 落款行）
# ----------------------------------------------------------------------

NAME_HINT = re.compile(r"名称")
HEADER_EXCLUDE = re.compile(r"乡镇|街道|区县|类别|大类|中类|小类|分类|等次|专科|项目|类型|管理|编码|时间|网址")

def find_header(rows):
    """在前 8 个非空行里选表头：得分 = 非空单元格数 + 命中'名称'列加分。"""
    best_i, best_score = 0, -1
    for i, row in enumerate(rows[:8]):
        nonempty = sum(1 for c in row if c)
        name_hit = any(NAME_HINT.search(c) and not HEADER_EXCLUDE.search(c) for c in row)
        score = nonempty + (10 if name_hit else 0)
        if score > best_score:
            best_i, best_score = i, score
    return best_i


# ----------------------------------------------------------------------
# 3. 列名映射（正则优先级匹配 -> 统一字段）
# ----------------------------------------------------------------------

COL_MAP = {   # 统一字段: [候选列名正则，按优先级排序]
    "name":     [r"定点医疗机构名称", r"医疗机构全称", r"医疗机构名称", r"机构名称",
                 r"单位名称", r"医院名称", r"急救站点名称", r"名称"],
    "addr":     [r"地址"],
    "phone":    [r"电话", r"联系方式"],
    "level":    [r"医院等级", r"机构等级", r"机构级别", r"分类级别", r"级别"],
    "level_sub":[r"等次", r"等级等"],
    "district": [r"所属辖区", r"所属区", r"区县名称", r"区属名称", r"区名称", r"区县"],
    "dist_code":[r"行政区划代码"],
    "category": [r"卫生机构类别", r"机构类别", r"小类", r"医院类型", r"类别", r"类型"],
    "econ":     [r"经济类型名称", r"经济类型", r"所有制"],
    "profit":   [r"机构分类管理", r"机构管理名称", r"营利性质", r"经营性质", r"公立/民营"],
    "postal":   [r"邮政编码", r"邮编"],
    "beds":     [r"床位"],
    "key_depts":[r"重点科室", r"诊疗科目"],
    "traffic":  [r"交通"],
    "website":  [r"挂号网址", r"医院网址", r"网址"],
    "specialty":[r"专科名称"],      # 临床重点专科名单专用
}
COMPILED = {k: [re.compile(p) for p in v] for k, v in COL_MAP.items()}


def map_columns(header):
    """返回 {统一字段: 列下标}。name 列必须存在，否则返回 None（该文件按非机构明细处理）。"""
    colmap = {}
    for field, pats in COMPILED.items():
        for pat in pats:
            for idx, col in enumerate(header):
                col_clean = re.sub(r"\s+", "", col)
                if idx in colmap.values():
                    continue
                if pat.search(col_clean):
                    colmap[field] = idx
                    break
            if field in colmap:
                break
    # name 列必须真正是"机构名"（排除 街道/区县/类别等同名干扰列）
    if "name" in colmap:
        raw_col = re.sub(r"\s+", "", header[colmap["name"]])
        if HEADER_EXCLUDE.search(raw_col):
            colmap.pop("name")
    return colmap if "name" in colmap else None


# ----------------------------------------------------------------------
# 4. 字段标准化
# ----------------------------------------------------------------------

DISTRICTS = ["东城区", "西城区", "朝阳区", "海淀区", "丰台区", "石景山区", "门头沟区",
             "房山区", "通州区", "顺义区", "大兴区", "昌平区", "平谷区", "怀柔区",
             "密云区", "延庆区"]
ADDR_DIST_RE = re.compile(r"北京市?(?:" + "|".join(DISTRICTS) + r")")

def norm_name(s):
    """机构名标准化（去空白、全角括号转半角、去'北京市'前缀）—— 用作去重键。"""
    s = re.sub(r"\s+", "", str(s))
    s = s.replace("（", "(").replace("）", ")").rstrip("；;。，,")
    if s.startswith("北京市") and len(s) > 6:
        s = s[3:]
    return s

def std_level(raw, fname):
    s = re.sub(r"\s+", "", str(raw))
    if s in ("", "nan", "None", "未评", "未评级", "未定级", "无", "—", "-", "/"):
        s = ""
    base = sub = ""
    if "三" in s:
        base = "三级"
    elif "二" in s:
        base = "二级"
    elif "一" in s:
        base = "一级"
    if "甲" in s:
        sub = "甲等"
    elif "乙" in s:
        sub = "乙等"
    elif "合格" in s:
        sub = "合格"
    if not base and fname:                     # 文件名兜底：如"通州区一级医院名单"
        m = re.search(r"(三级甲等|三级乙等|二级甲等|二级乙等|一级|二级|三级)", fname)
        if m:
            t = m.group(1)
            base = t[:2]
            sub = t[2:] if len(t) > 2 else ""
    if not base:
        return ("未定级", sub) if sub else ("", "")
    return base, sub

def std_district(rec_addr, dist_val, code_val, fname):
    for v in (dist_val,):
        v = re.sub(r"^北京", "", str(v).strip())   # 清洗"北京昌平区"等脏值
        for d in DISTRICTS:
            if d in v:
                return d
    if code_val:
        m = re.search(r"\d+-?(.+)", str(code_val))
        if m and m.group(1) in DISTRICTS:
            return m.group(1)
    m = ADDR_DIST_RE.search(str(rec_addr or ""))
    if m:
        return re.sub(r"^北京市?", "", m.group(0))
    if fname:
        for d in DISTRICTS:
            if d in fname:
                return d
    return ""

CAT_RULES = [  # (类别, 关键词)——按顺序命中即归类
    ("急救机构",       ["急救"]),
    ("社区卫生服务站", ["社区卫生服务站"]),
    ("社区卫生服务中心", ["社区卫生服务中心"]),
    ("村卫生室",       ["村卫生室", "村卫生所"]),
    ("医务室",         ["医务室"]),
    ("体检机构",       ["体检"]),
    ("护理站",         ["护理站"]),
    ("妇幼保健院",     ["妇幼保健院", "妇幼保健所"]),
    ("公共卫生机构",   ["疾病预防控制", "卫生监督", "血站", "健康教育", "急救中心"]),
    ("门诊部",         ["门诊部"]),
    ("诊所",           ["诊所"]),
]
def std_category(name, cat_raw):
    text = str(name) + " " + str(cat_raw or "")
    for cat, kws in CAT_RULES:
        if any(k in text for k in kws):
            return cat
    if "医院" in text:
        return "中医医院" if "中医" in text else "医院"
    if "研究所" in text or "检验" in text or "实验室" in text:
        return "其他医疗机构"
    return "其他医疗机构"


# ----------------------------------------------------------------------
# 5. 主流程
# ----------------------------------------------------------------------

def main():
    files = sorted(f for f in os.listdir(SRC_DIR)
                   if f.lower().endswith((".csv", ".xlsx", ".xls")) and not f.startswith("."))
    stats = {"per_file": [], "excluded": [], "level_raw": Counter(), "errors": []}
    records = []          # 统一记录
    specialty = defaultdict(set)   # 机构 -> 重点专科集合

    for fname in files:
        path = os.path.join(SRC_DIR, fname)
        try:
            rows = load_any(path)
            if not rows:
                stats["excluded"].append((fname, "空文件"))
                continue
            hi = find_header(rows)
            header = [re.sub(r"\s+", "", c) for c in rows[hi]]
            colmap = map_columns(header)
            if colmap is None:
                stats["excluded"].append((fname, "无机构名称列（统计表/非机构明细）"))
                continue
            if "specialty" in colmap:          # 临床重点专科名单 -> 单独成表
                for r in rows[hi + 1:]:
                    if len(r) <= max(colmap.values()):
                        continue
                    nm, sp = r[colmap["name"]], r[colmap["specialty"]]
                    if nm and sp:
                        specialty[norm_name(nm)].add(sp)
                stats["per_file"].append((fname, len(rows) - hi - 1, "专科表"))
                continue

            n = 0
            for r in rows[hi + 1:]:
                if len(r) <= colmap["name"]:
                    continue
                def g(field):
                    i = colmap.get(field)
                    if i is None or i >= len(r):
                        return ""
                    v = str(r[i]).strip()
                    return "" if v in ("nan", "None") else v
                name = g("name")
                if not name or len(name) < 4 or name in header:
                    continue
                if re.search(r"^(总计|合计|单位|人次)", name):
                    continue
                addr = g("addr")
                level_raw = g("level")
                level, sub = std_level(level_raw, fname)
                stats["level_raw"][level_raw] += 1
                records.append({
                    "name": name,
                    "name_key": norm_name(name),
                    "district": std_district(addr, g("district"), g("dist_code"), fname),
                    "addr": addr,
                    "phone": g("phone"),
                    "level": level,
                    "level_sub": sub,
                    "category_raw": g("category"),
                    "econ": g("econ"),
                    "profit": g("profit"),
                    "postal": g("postal"),
                    "beds": g("beds"),
                    "key_depts": g("key_depts"),
                    "traffic": g("traffic"),
                    "website": g("website"),
                    "_src": fname,
                })
                n += 1
            stats["per_file"].append((fname, n, "机构明细"))
        except Exception as e:
            stats["errors"].append((fname, f"{type(e).__name__}: {e}"))

    df = pd.DataFrame(records)

    # ---- 去重合并：同名机构按信息丰富度排序，逐字段取第一个非空值 ----
    RICH = ["addr", "phone", "level", "district", "category_raw", "profit",
            "econ", "postal", "beds", "key_depts", "traffic", "website", "level_sub"]
    df["_rich"] = df[RICH].notna().sum(axis=1) + (df[RICH] != "").sum(axis=1)
    df = df.sort_values("_rich", ascending=False)
    merged = df.groupby("name_key", sort=False).agg(
        {**{c: "first" for c in ["name", "district", "addr", "phone", "level", "level_sub",
                                  "category_raw", "econ", "profit", "postal", "beds",
                                  "key_depts", "traffic", "website"]},
           "_src": lambda s: "|".join(sorted(set(s)))}
    ).reset_index()
    merged["src_count"] = merged["_src"].str.split("|").str.len()
    merged["category"] = merged.apply(
        lambda r: std_category(r["name"], r["category_raw"]), axis=1)

    # ---- 专科表挂接：能对上主表的机构，把专科并入 key_depts ----
    spec_df = pd.DataFrame([{"name_key": k, "specialties": "、".join(sorted(v))}
                            for k, v in specialty.items()])
    merged = merged.merge(spec_df, on="name_key", how="left")
    merged["key_depts"] = merged.apply(
        lambda r: "、".join(x for x in [
            str(r["key_depts"]).strip("、 ") if pd.notna(r["key_depts"]) else "",
            str(r["specialties"]).strip("、 ") if pd.notna(r.get("specialties")) else "",
        ] if x and x != "nan"),
        axis=1)
    merged = merged.drop(columns=["specialties"])

    # ---- 输出主表 ----
    out_cols = ["name", "district", "category", "level", "level_sub", "addr", "phone",
                "postal", "beds", "key_depts", "traffic", "website", "econ", "profit",
                "category_raw", "src_count", "_src"]
    master = merged[out_cols].rename(columns={"_src": "source_files"}).sort_values(
        ["category", "district", "name"]).reset_index(drop=True)
    master.insert(0, "id", range(1, len(master) + 1))
    master.to_csv(os.path.join(OUT_DIR, "master_institutions.csv"),
                  index=False, encoding="utf-8-sig")

    # ---- 专科表 ----
    spec_out = pd.DataFrame([{"hospital": k, "specialties": "、".join(sorted(v))}
                             for k, v in specialty.items()])
    spec_out.to_csv(os.path.join(OUT_DIR, "specialty_departments.csv"),
                    index=False, encoding="utf-8-sig")

    # ---- 质量报告 ----
    write_report(master, df, stats, len(specialty))
    print(f"[完成] 原始明细 {len(df)} 条 -> 去重合并后主表 {len(master)} 家机构；"
          f"重点专科覆盖 {len(specialty)} 家")
    print(f"输出目录: {OUT_DIR}")


def write_report(master, raw_df, stats, n_spec):
    lines = []
    A = lines.append
    A("# 北京市医疗资源数据清洗整合 · 质量报告\n")
    A(f"- 源文件数: {len(stats['per_file']) + len(stats['excluded']) + len(stats['errors'])}"
      f"（机构明细 {len(stats['per_file'])}，统计表/排除 {len(stats['excluded'])}，读取失败 {len(stats['errors'])}）")
    A(f"- 原始机构记录: {len(raw_df)} 条")
    A(f"- 去重合并后主表: {len(master)} 家机构")
    A(f"- 临床重点专科覆盖: {n_spec} 家\n")

    A("## 按机构类别分布\n")
    A("| 类别 | 数量 | 占比 |")
    A("|---|---:|---:|")
    for k, v in master["category"].value_counts().items():
        A(f"| {k} | {v} | {v/len(master)*100:.1f}% |")

    A("\n## 按行政区分布\n")
    A("| 区 | 数量 |")
    A("|---|---:|")
    for k, v in master["district"].value_counts().items():
        A(f"| {k or '（未知）'} | {v} |")

    A("\n## 按等级分布\n")
    A("| 等级 | 数量 |")
    A("|---|---:|")
    for k, v in master["level"].replace("", "（未定级/缺失）").value_counts().items():
        A(f"| {k} | {v} |")

    A("\n## 关键字段完整度\n")
    A("| 字段 | 非空 | 完整率 |")
    A("|---|---:|---:|")
    for c in ["addr", "phone", "level", "district", "profit", "beds", "key_depts", "traffic"]:
        nn = master[c].astype(str).replace("", pd.NA).notna().sum()
        A(f"| {c} | {nn} | {nn/len(master)*100:.1f}% |")

    dup = raw_df["name_key"].value_counts()
    multi = dup[dup > 1]
    A(f"\n## 去重情况\n")
    A(f"- 涉及多来源重复的机构名: {len(multi)} 个（最多被 {dup.max()} 个来源重复收录）")
    A(f"- 多来源交叉验证（src_count>=3）的机构: {(master['src_count']>=3).sum()} 家")

    A("\n## 未纳入主表的文件（统计汇总类）\n")
    for f, why in stats["excluded"]:
        A(f"- {f}：{why}")
    if stats["errors"]:
        A("\n## 读取失败\n")
        for f, e in stats["errors"]:
            A(f"- {f}：{e}")

    A("\n## 原始'等级'字段取值（供扩展映射字典）\n")
    A("```")
    for v, c in stats["level_raw"].most_common(30):
        A(f"{v or '(空)'}: {c}")
    A("```")

    with open(os.path.join(OUT_DIR, "data_quality_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
