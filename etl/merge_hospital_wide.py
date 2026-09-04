# -*- coding: utf-8 -*-
"""
主表 + 地理编码缓存 合并为 hospital_wide.csv
==============================================
输入：
  - 毕设/data/processed/master_institutions.csv（9,791 家机构）
  - 毕设/data/processed/geocode_cache.csv（地理编码结果，按 id 增量）
  - 毕设/data/processed/hospital_depts.csv（科室映射）
  - 毕设/data/processed/dept_dict.csv（科室字典）
输出：
  - 毕设/data/processed/hospital_wide.csv（24+ 字段的统一宽表）
  - 毕设/data/processed/coordinate_quality_report.md（坐标精度报告）

字段说明：
  - 主表 17 字段 + 坐标 5 字段 + 科室统计 2 字段 = ~24 字段
  - coord_precision: door(门址) / poi(兴趣点) / rough(区县/乡镇等粗精度) / missing
  - 坐标粗精度的机构会在筛选时用粗精度警告标记
"""

import csv
import os
import sys
from collections import Counter, defaultdict

BASE = os.path.expanduser("~/Desktop/毕设")
MASTER = os.path.join(BASE, "data/processed/master_institutions.csv")
CACHE = os.path.join(BASE, "data/processed/geocode_cache.csv")
HOSPITAL_DEPTS = os.path.join(BASE, "data/processed/hospital_depts.csv")
DEPT_DICT = os.path.join(BASE, "data/processed/dept_dict.csv")
OUT_WIDE = os.path.join(BASE, "data/processed/hospital_wide.csv")
OUT_REPORT = os.path.join(BASE, "data/processed/coordinate_quality_report.md")

# 精度归一化：高德返回的 level → 我们的精度桶
PRECISION_MAP = {
    "门址": "door",
    "兴趣点": "poi",
    "门牌号": "door",
    "道路": "rough",
    "道路交叉点": "rough",
    "住宅区": "rough",
    "村庄": "rough",
    "乡镇": "rough",
    "区县": "rough",
    "区县中心": "rough",
    "公交地铁站点": "rough",
    "未知": "missing",
    "省": "rough",
    "": "missing",
}


def load_csv(path):
    if not os.path.exists(path):
        print("⚠️  文件不存在：%s" % path)
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    print("📂 加载数据...")
    masters = load_csv(MASTER)
    caches = load_csv(CACHE)
    hospital_depts = load_csv(HOSPITAL_DEPTS)
    dept_dict = {r["dept_name"]: r for r in load_csv(DEPT_DICT)}

    print("   主表：%d 家机构" % len(masters))
    print("   编码缓存：%d 条" % len(caches))
    print("   科室映射：%d 条" % len(hospital_depts))

    # 建索引
    cache_by_id = {r["id"]: r for r in caches}
    depts_by_hospital = defaultdict(list)
    key_specialty_by_hospital = defaultdict(list)
    for d in hospital_depts:
        depts_by_hospital[d["hospital_id"]].append(d["dept_name"])
        if d.get("is_key_specialty") == "1":
            key_specialty_by_hospital[d["hospital_id"]].append(d["dept_name"])

    # 精度统计
    precision_counter = Counter()
    missing_ids = []
    failed_ids = []

    # 写出宽表
    out_fields = [
        "id", "name", "district", "category", "level", "level_sub", "addr",
        "phone", "postal", "beds", "key_depts", "traffic", "website", "econ", "profit",
        "category_raw", "src_count", "source_files",
        # 坐标字段
        "lng", "lat", "coord_formatted", "coord_level_raw", "coord_precision", "coord_source",
        # 科室聚合
        "dept_count", "dept_list", "key_specialty_count", "key_specialty_list",
    ]

    rows = []
    for m in masters:
        cid = m["id"]
        cache = cache_by_id.get(cid, {})
        lng = (cache.get("lng") or "").strip()
        lat = (cache.get("lat") or "").strip()
        level_raw = (cache.get("level") or "").strip()
        precision = PRECISION_MAP.get(level_raw, "missing")
        if not lng or not lat:
            precision = "missing"
            missing_ids.append(cid)
        if cache.get("status") == "failed":
            failed_ids.append(cid)
        precision_counter[precision] += 1

        depts = depts_by_hospital.get(cid, [])
        key_specs = key_specialty_by_hospital.get(cid, [])

        row = dict(m)
        row["lng"] = lng
        row["lat"] = lat
        row["coord_formatted"] = (cache.get("formatted") or "").strip()
        row["coord_level_raw"] = level_raw
        row["coord_precision"] = precision
        row["coord_source"] = (cache.get("source") or "").strip()
        row["dept_count"] = len(depts)
        row["dept_list"] = "|".join(depts)
        row["key_specialty_count"] = len(key_specs)
        row["key_specialty_list"] = "|".join(key_specs)
        rows.append(row)

    # 写入
    with open(OUT_WIDE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        w.writerows(rows)

    print("✅ 写出：%s（%d 行 × %d 列）" % (OUT_WIDE, len(rows), len(out_fields)))

    # 报告
    total = len(rows)
    coord_ok = sum(1 for r in rows if r["coord_precision"] in ("door", "poi"))
    coord_rough = sum(1 for r in rows if r["coord_precision"] == "rough")
    coord_miss = sum(1 for r in rows if r["coord_precision"] == "missing")

    lines = []
    lines.append("# 坐标精度质量报告")
    lines.append("")
    lines.append("**生成时间**：自动生成  ")
    lines.append("**机构总数**：%d 家" % total)
    lines.append("")
    lines.append("## 坐标精度分布")
    lines.append("")
    lines.append("| 精度 | 数量 | 占比 |")
    lines.append("|---|---|---|")
    for label, key in [("门址(door)", "door"), ("兴趣点(poi)", "poi"),
                       ("粗精度(rough)", "rough"), ("缺失(missing)", "missing")]:
        n = precision_counter.get(key, 0)
        pct = 100.0 * n / total if total else 0
        lines.append("| %s | %d | %.1f%% |" % (label, n, pct))
    lines.append("")
    lines.append("## 关键指标")
    lines.append("")
    lines.append("- **可筛选(门址+兴趣点)**：%d 家（%.1f%%）—— 距离/排序可用" % (coord_ok, 100*coord_ok/total))
    lines.append("- **粗精度**：%d 家（%.1f%%）—— 仅能按区筛选，距离显示警告" % (coord_rough, 100*coord_rough/total))
    lines.append("- **缺失/失败**：%d 家（%.1f%%）—— 不出现在地图" % (coord_miss, 100*coord_miss/total))
    lines.append("")
    lines.append("## 缺失坐标的机构示例（前 20 条）")
    lines.append("")
    miss_rows = [r for r in rows if r["coord_precision"] == "missing"][:20]
    for r in miss_rows:
        lines.append("- %s | %s | %s" % (r["name"], r.get("district", "?"), r.get("addr", "?")))
    if len(miss_rows) < coord_miss:
        lines.append("- ...（其余 %d 条见 hospital_wide.csv）" % (coord_miss - len(miss_rows)))
    lines.append("")
    lines.append("## 字段说明")
    lines.append("")
    lines.append("- `coord_precision`：door / poi / rough / missing 四级")
    lines.append("- `coord_source`：API 调用时使用的地址（详细地址 / 区+机构名 / 兜底标记）")
    lines.append("- `dept_list` / `key_specialty_list`：用 `|` 分隔的多值字段")

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("✅ 报告：%s" % OUT_REPORT)


if __name__ == "__main__":
    main()