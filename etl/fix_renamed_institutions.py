#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
机构更名同步（2026-09-10）

背景：
  以北京市医保 A 类定点医疗机构名单（2026-08-08，59 家）为权威基准做全量比对时，
  有 3 个关键词在系统 9,789 家机构中匹配不到：
      空军特色医学中心 / 通用航天医院 / 北大国际医院
  逐条核实后发现——这 3 家在本系统中**均已存在且等级正确（三级）**，
  并非数据缺失，而是**主表沿用旧名或简称**，导致与 A 类名单（用现名）关键词匹配失败。

  - 空军特色医学中心   = 原「空军总医院」（2018-11 更名），主表 id 1522 / 1481
  - 北京通用航天医院   = 原「中国航天科工集团七三一医院」（2026-02 挂牌更名），主表 id 1185 / 1186
  - 北大国际医院       = 「北京大学国际医院」简称，主表 id 1354（标准全称，无需改）

处理原则：
  采用「现用名（原旧名）」格式更新，新旧名称同时保留在 name 字段中，
  使前端关键词检索对新旧叫法均可命中；不新增记录，避免产生重复机构。

同步范围：master_institutions.csv → hospital_wide.csv → MySQL ads_inst_search
（snapshot_data.json 与离线大屏由 `bash web/build_spa.sh` 重新生成）
"""

import csv, os, sys, pymysql

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(BASE, "data/processed/master_institutions.csv")
WIDE = os.path.join(BASE, "data/processed/hospital_wide.csv")

# id -> (旧名, 新名)
RENAMES = {
    "1522": ("空军总医院",
             "空军特色医学中心（原空军总医院）"),
    "1481": ("中国人民解放军空军总医院",
             "中国人民解放军空军特色医学中心（原空军总医院）"),
    "1185": ("中国航天科工集团七三一医院",
             "北京通用航天医院（原中国航天科工集团七三一医院）"),
    "1186": ("中国航天科工集团七三一医院 北京航天医院",
             "北京通用航天医院（原北京航天医院）"),
    # 简称别名：A 类名单用词为「北大国际医院」，主表为全称，补常用简称以保证检索命中
    "1354": ("北京大学国际医院",
             "北京大学国际医院（北大国际医院）"),
}


def update_csv(path, key="id"):
    """就地更新 CSV 中指定 id 的 name 字段，返回实际改动行数。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = list(reader.fieldnames)
        rows = list(reader)
    changed = 0
    for r in rows:
        rid = str(r.get(key, "")).strip()
        if rid in RENAMES:
            old, new = RENAMES[rid]
            if r["name"] != old:
                print(f"    ! {path} id={rid} 名称与预期不符: 期望 {old!r}, 实际 {r['name']!r}（跳过）")
                continue
            r["name"] = new
            changed += 1
            print(f"    · {path} id={rid}: {old}  ->  {new}")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return changed


def update_mysql():
    c = pymysql.connect(host="127.0.0.1", port=3307, user="root",
                        password="hospital123", database="hospital",
                        charset="utf8mb4", connect_timeout=8)
    changed = 0
    try:
        with c.cursor() as cur:
            for rid, (old, new) in RENAMES.items():
                cur.execute(
                    "UPDATE ads_inst_search SET name=%s WHERE id=%s AND name=%s",
                    (new, rid, old))
                n = cur.rowcount
                if n:
                    changed += n
                    print(f"    · MySQL id={rid}: {old}  ->  {new}")
                else:
                    print(f"    ! MySQL id={rid} 未命中（当前 name 不是 {old!r}）")
        c.commit()
    finally:
        c.close()
    return changed


def main():
    print("=== 1/2 更新 CSV（主表 + wide 表）===")
    n1 = update_csv(MASTER)
    n2 = update_csv(WIDE)
    print(f"  主表改动 {n1} 行 / wide 表改动 {n2} 行（应各 4 行）")

    print("\n=== 2/2 更新 MySQL ads_inst_search ===")
    n3 = update_mysql()
    print(f"  MySQL 改动 {n3} 行（应 4 行）")

    ok = (n1 == n2 == n3 == len(RENAMES))
    print("\n" + ("✅ 三层同步一致" if ok else "⚠️ 各层改动行数不一致，请检查"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
