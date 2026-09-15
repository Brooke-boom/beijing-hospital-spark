# -*- coding: utf-8 -*-
"""为 MySQL 业务库的服务层表建立查询索引。

背景
----
Spark ETL 以 mode="overwrite" 写 MySQL，该模式会 DROP + CREATE 目标表，
因此**每次重跑落库作业后索引都会丢失**，必须在本脚本中重建。

另一处坑：Spark JDBC 建表时字符串列被建为 TEXT 类型，
MySQL 不允许对 TEXT 列直接建索引（报错 1170：BLOB/TEXT column used
in key specification without a key length），必须使用**前缀索引**
指定 key length。UTF-8 下汉字占 3 字节，故前缀长度按 3 的倍数取：
  - district   「海淀区」「经济技术开发区」等，最长约 8 字 → 取 24
  - level_norm 「不适用医院分级」7 字 → 取 24
  - category   「社区卫生服务中心」8 字 → 取 24
  - name       机构名较长，仅用于前缀匹配（LIKE 'xxx%'）→ 取 60

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

# 表名 → [(索引名, [列名...]), ...]
TABLES = {
    # 检索主表（大屏筛选的核心）
    "ads_inst_search": [
        ("idx_inst_search_main", ["district", "level_norm", "category"]),
        ("idx_inst_level", ["level_norm"]),
        ("idx_inst_district", ["district"]),
        ("idx_inst_name", ["name"]),
        ("idx_inst_net", ["net_pediatric", "net_stroke", "net_neonatal", "net_maternal"]),
    ],
    # DWD 服务副本（机构详情、科室关系查询）
    "dwd_institution_clean": [
        ("idx_dwd_inst_id", ["id"]),
        ("idx_dwd_inst_district", ["district"]),
        ("idx_dwd_inst_level", ["level_norm"]),
        ("idx_dwd_inst_cat", ["category_norm"]),
        ("idx_dwd_inst_name", ["name"]),
        ("idx_dwd_inst_net", ["net_pediatric", "net_stroke", "net_neonatal", "net_maternal"]),
    ],
    "dwd_dept_relation_clean": [
        ("idx_dept_rel_hospital", ["hospital_id"]),
        ("idx_dept_rel_name", ["dept_name"]),
    ],
    "dwd_specialty_clean": [
        ("idx_spec_hospital", ["hospital_name"]),
    ],
    # DWS 服务副本（大屏图表）
    "dws_inst_by_district": [("idx_dws_district", ["district"])],
    "dws_inst_by_level": [("idx_dws_level", ["level_norm"])],
    "dws_inst_by_category": [("idx_dws_category", ["category_norm"])],
    "dws_dept_coverage": [("idx_dws_dept_name", ["dept_name"])],
    # ADS 分析结果
    "ads_district_overview": [("idx_ads_district", ["district"])],
    "ads_level_overview": [("idx_ads_level", ["level_norm"])],
    "ads_specialty_hospital": [
        ("idx_ads_spec_dept", ["dept_name"]),
        ("idx_ads_spec_district", ["district"]),
    ],
    "ads_network_summary": [("idx_ads_net_key", ["network_key"])],
    "ads_time_trend": [("idx_ads_time_dt", ["dt"])],
    "ads_time_feature": [("idx_ads_time_feature", ["feature"])],
    "ads_etl_snapshot": [("idx_ads_snap_date", ["batch_date"])],
}

# TEXT/BLOB 列必须指定前缀长度才能建索引；VARCHAR/INT 等则不能加
PREFIX_LEN = 24


def build_definition(col_name, col_type):
    """按列类型生成索引列定义：TEXT/BLOB 加前缀长度，其余原样。"""
    if "text" in col_type.lower() or "blob" in col_type.lower():
        return "%s(%d)" % (col_name, PREFIX_LEN)
    return col_name


def index_table(cur, table, specs):
    cur.execute("SHOW TABLES LIKE %s", (table,))
    if not cur.fetchone():
        print("  跳过 %s：表不存在" % table)
        return 0

    cur.execute("SHOW COLUMNS FROM %s" % table)
    col_types = {r[0]: r[1] for r in cur.fetchall()}
    cols = set(col_types)

    created = 0
    for name, fields in specs:
        missing = [f for f in fields if f not in cols]
        if missing:
            print("  跳过 %s.%s：缺少列 %s" % (table, name, missing))
            continue
        definition = ", ".join(build_definition(f, col_types[f]) for f in fields)
        try:
            cur.execute("CREATE INDEX %s ON %s (%s)" % (name, table, definition))
            created += 1
        except pymysql.err.OperationalError as e:
            if e.args[0] == 1061:  # Duplicate key name
                continue
            raise
    print("  %-26s 索引 %d 个" % (table, created))
    return created


def main():
    conn = pymysql.connect(**MYSQL)
    cur = conn.cursor()

    total = 0
    for table, specs in TABLES.items():
        total += index_table(cur, table, specs)
    conn.commit()

    print("\n=== ads_inst_search 当前索引 ===")
    cur.execute("SHOW INDEX FROM ads_inst_search")
    idx = {}
    for r in cur.fetchall():
        idx.setdefault(r[2], []).append(r[4])
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
    print("\n完成：共建索引 %d 个" % total)


if __name__ == "__main__":
    sys.exit(main())
