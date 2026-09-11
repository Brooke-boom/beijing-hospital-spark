# -*- coding: utf-8 -*-
"""
将疾病→科室知识库灌入 MySQL 维度表 dim_disease_dept
====================================================
这是「资源整合」的一环：把离线治理好的导诊词典沉淀到数仓，
web/app.py 的 /api/triage 直接 query 该表完成智能导诊。

运行（在 docker compose up 之后）：
    python etl/load_disease_dept.py
"""

import csv
import os
import sys

import pymysql

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSV_PATH = os.path.join(ROOT, "data", "processed", "disease_dept_map.csv")

DB = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 3307)),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASS", "hospital123"),
    "database": "hospital",
    "charset": "utf8mb4",
}


def main():
    if not os.path.exists(CSV_PATH):
        print("❌ 找不到", CSV_PATH, "请先运行 etl/build_disease_dept_map.py")
        sys.exit(1)

    conn = pymysql.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dim_disease_dept (
                    keyword      VARCHAR(64)  NOT NULL,
                    dept_name    VARCHAR(32)  NOT NULL,
                    dept_category VARCHAR(16)  DEFAULT '',
                    weight       FLOAT         DEFAULT 1.0,
                    is_emergency TINYINT      DEFAULT 0,
                    note         VARCHAR(128) DEFAULT '',
                    PRIMARY KEY (keyword, dept_name),
                    KEY idx_ddd_dept (dept_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("TRUNCATE TABLE dim_disease_dept")
            rows = []
            with open(CSV_PATH, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    rows.append((r["keyword"], r["dept_name"], r["dept_category"],
                                 float(r["weight"]), int(r["is_emergency"]), r["note"]))
            cur.executemany(
                "INSERT INTO dim_disease_dept "
                "(keyword, dept_name, dept_category, weight, is_emergency, note) "
                "VALUES (%s,%s,%s,%s,%s,%s)", rows)
            conn.commit()
            print(f"✅ dim_disease_dept 已写入 {len(rows)} 条（覆盖 {len(set(r[1] for r in rows))} 个科室）")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
