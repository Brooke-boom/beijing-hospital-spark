# -*- coding: utf-8 -*-
"""为 ads_inst_search 建立查询索引。

背景
----
Spark ETL（spark/etl_hospital.py）以 mode="overwrite" 写 MySQL，
该模式会 DROP + CREATE 目标表，因此**每次重跑 ETL 后索引都会丢失**，
必须在本脚本中重建。

另一处坑：Spark JDBC 建表时字符串列被建为 TEXT 类型，
MySQL 不允许对 TEXT 列直接建索引（报错 1170：BLOB/TEXT column used
in key specification without a key length），必须使用**前缀索引**
指定 key length。UTF-8 下汉字占 3 字节，故前缀长度按 3 的倍数取：
  - district  「海淀区」「经济技术开发区」等，最长约 8 字 → 取 24
  - level_norm「不适用医院分级」7 字 → 取 24
  - category  「社区卫生服务中心」8 字 → 取 24
  - name      机构名较长，仅用于前缀匹配（LIKE 'xxx%'）→ 取 60

用法
----
    python etl/create_indexes.py
"""

import sys

import pymysql

MYSQL = dict(
    host="127.0.0.1",
    port=3307,
    user="root",
    password="hospital123",
    database="hospital",
    charset="utf8mb4",
)

# (索引名, "列定义") —— 列定义含前缀长度
INDEXES = [
    ("idx_inst_search_main", "district(24), level_norm(24), category(24)"),
    ("idx_inst_level", "level_norm(24)"),
    ("idx_inst_district", "district(24)"),
    ("idx_inst_name", "name(60)"),
    # net_* 由 ALTER TABLE 显式建为 VARCHAR，非 TEXT，无需前缀长度
    ("idx_inst_net", "net_pediatric, net_stroke, net_neonatal, net_maternal"),
]


def main():
    conn = pymysql.connect(**MYSQL)
    cur = conn.cursor()

    cur.execute("SHOW COLUMNS FROM ads_inst_search")
    cols = {r[0] for r in cur.fetchall()}

    created = skipped = 0
    for name, definition in INDEXES:
        # 校验列存在（去掉前缀长度后比对）
        fields = [f.split("(")[0].strip() for f in definition.split(",")]
        missing = [f for f in fields if f not in cols]
        if missing:
            print("  跳过 %s：缺少列 %s" % (name, missing))
            skipped += 1
            continue
        try:
            cur.execute("CREATE INDEX %s ON ads_inst_search (%s)" % (name, definition))
            print("  已创建 %s (%s)" % (name, definition))
            created += 1
        except pymysql.err.OperationalError as e:
            if e.args[0] == 1061:  # Duplicate key name
                print("  已存在，跳过 %s" % name)
            else:
                raise
    conn.commit()

    print("\n=== 当前索引 ===")
    cur.execute("SHOW INDEX FROM ads_inst_search")
    idx = {}
    for r in cur.fetchall():
        idx.setdefault(r[2], []).append(r[4])
    if not idx:
        print("  (无)")
    for k, v in idx.items():
        print("  %s: %s" % (k, v))

    # 验证：区域 + 等级 + 类型 组合筛选是否走索引
    print("\n=== EXPLAIN 验证 ===")
    cur.execute(
        "EXPLAIN SELECT id, name FROM ads_inst_search "
        "WHERE district='海淀区' AND level_norm='三级' AND category='医院' LIMIT 20"
    )
    row = cur.fetchone()
    print("  type=%s  key=%s  rows=%s" % (row[3], row[6], row[9]))

    conn.close()
    print("\n完成：新建 %d 个，跳过 %d 个" % (created, skipped))


if __name__ == "__main__":
    sys.exit(main())
