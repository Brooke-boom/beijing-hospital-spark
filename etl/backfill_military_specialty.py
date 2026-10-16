# -*- coding: utf-8 -*-
"""军队医院国家临床重点专科（军队建设项目）回填。

来源：data/processed/specialty_military.csv（2026-10-16 联网核实，一手来源以
mil.cn 官网/新华网/科学网为主，第三方交叉印证；不可核实的条目不收录，
详见 data/processed/govern_report_specialty_military.md）。

更新两张表（可重复执行，幂等）：
  dwd_specialty_clean : 每个别名一行（hospital_name, specialty_name 顿号拼接）
  ads_inst_search     : key_specialty_count / national_specialty_count / national_specialty

用法：
  python etl/backfill_military_specialty.py --dry-run   # 只打印，不写库
  python etl/backfill_military_specialty.py             # 备份后写库
"""
import csv
import json
import os
import sys
from datetime import datetime

import pymysql

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "data", "processed", "specialty_military.csv")
BACKUP_DIR = os.path.join(BASE, "data", "processed", "backup")

DB = dict(host="127.0.0.1", port=3307, user="root", password="hospital123",
          database="hospital", charset="utf8mb4")


def load_rows():
    with open(SRC, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        names = [n.strip() for n in r["match_names"].split("|") if n.strip()]
        specs = [s.strip() for s in r["specialties"].split("、") if s.strip()]
        assert len(specs) == int(r["specialty_count"]), \
            "计数不符: %s 声明 %s 实际 %d" % (r["canonical_name"], r["specialty_count"], len(specs))
        out.append({**r, "alias_list": names, "spec_list": specs})
    return out


def main():
    dry = "--dry-run" in sys.argv
    rows = load_rows()
    conn = pymysql.connect(**DB, cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as c:
        # 1) 备份受影响行
        all_names = [n for r in rows for n in r["alias_list"]]
        ph = ",".join(["%s"] * len(all_names))
        c.execute("SELECT name, key_specialty_count, national_specialty_count,"
                  " national_specialty FROM ads_inst_search WHERE name IN (%s)" % ph,
                  all_names)
        before = {r["name"]: r for r in c.fetchall()}
        missing = [n for n in all_names if n not in before]
        if missing:
            print("!! 库中未匹配到 %d 个名称：" % len(missing))
            for n in missing:
                print("   ", n)
        if not dry:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bpath = os.path.join(BACKUP_DIR, "specialty_military_backup_%s.json" % stamp)
            with open(bpath, "w", encoding="utf-8") as f:
                json.dump({"before": list(before.values()), "rows": rows}, f,
                          ensure_ascii=False, indent=1)
            print("✓ 备份 %d 行 → %s" % (len(before), os.path.relpath(bpath, BASE)))

        # 2) 逐行更新
        n_dwd, n_ads = 0, 0
        for r in rows:
            joined = "、".join(r["spec_list"])
            nat = ";".join(r["spec_list"])
            for name in r["alias_list"]:
                if name not in before:
                    continue
                print("  %-46s → %d 项 (%s)" % (name, len(r["spec_list"]), r["batch"]))
                if not dry:
                    c.execute(
                        "UPDATE ads_inst_search SET key_specialty_count=%s,"
                        " national_specialty_count=%s, national_specialty=%s WHERE name=%s",
                        (len(r["spec_list"]), len(r["spec_list"]), nat, name))
                    # dwd_specialty_clean 无主键：先删后插，保证幂等
                    c.execute("DELETE FROM dwd_specialty_clean WHERE hospital_name=%s", (name,))
                    c.execute(
                        "INSERT INTO dwd_specialty_clean (hospital_name, specialty_name)"
                        " VALUES (%s, %s)", (name, joined))
                    n_ads += 1
                n_dwd += 1
        if not dry:
            conn.commit()
            print("✓ 写入完成：ads %d 行、dwd %d 行" % (n_ads, n_dwd))
            # 3) 汇总校验
            c.execute("SELECT COUNT(*) n FROM ads_inst_search WHERE key_specialty_count>0")
            print("  ads 专科>0 医院数:", c.fetchone()["n"], "（回填前 72）")
            c.execute("SELECT COUNT(*) n FROM dwd_specialty_clean")
            print("  dwd_specialty_clean 行数:", c.fetchone()["n"], "（回填前 43）")
    conn.close()


if __name__ == "__main__":
    main()
