# -*- coding: utf-8 -*-
"""
北京市医院医疗资源整合与智能筛选可视化系统 —— Flask API
=========================================================
数据源：MySQL hospital 库 ADS 层（由 spark/etl_hospital.py 生成）
  - ads_inst_search        筛选排序主表（9,791 家机构）
  - ads_district_overview  区域概览
  - ads_level_overview     等级概览
  - ads_specialty_hospital 重点专科医院
  - dws_dept_coverage      科室覆盖度
  - dwd_dept_relation_clean 医院科室明细（详情页用）

运行：
  python web/app.py
  浏览器访问 http://127.0.0.1:5000
"""

import math
import os

import pymysql
from flask import Flask, g, jsonify, render_template, request, make_response

# ============== 配置 ==============
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 3307)),
    "user": os.environ.get("DB_USER", "app"),
    "password": os.environ.get("DB_PASS", "app123"),
    "database": "hospital",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

app = Flask(__name__)

# 默认坐标参考点：天安门（距离排序基准点）
DEFAULT_LNG, DEFAULT_LAT = 116.397428, 39.909230

# 等级 → 权重（加权评分用）
LEVEL_SCORE = {"三级": 3.0, "二级": 2.0, "一级": 1.0, "未定级": 0.5}


# ============== 数据库连接 ==============
def get_db():
    if "db" not in g:
        g.db = pymysql.connect(**DB_CONFIG)
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=None, one=False):
    with get_db().cursor() as cur:
        cur.execute(sql, args or ())
        rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


# ============== 页面 ==============
@app.route("/")
def index():
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ============== API：多维筛选与排序 ==============
@app.route("/api/institutions")
def api_institutions():
    """筛选主接口

    参数：
      q         机构名模糊搜索
      district  区名（如 海淀区）
      level     等级（三级/二级/一级/未定级）
      category  类型（医院/诊所/门诊部/...）
      dept      科室名（如 口腔科）
      lng/lat   参考点坐标（默认天安门），用于距离计算与排序
      sort      排序策略：distance | level | beds | depts | score（默认 score）
      page      页码（默认 1）
      page_size 每页条数（默认 20，最大 100）
    返回：{total, page, page_size, items[], meta{}}
    """
    args = request.args
    q = (args.get("q") or "").strip()
    district = (args.get("district") or "").strip()
    level = (args.get("level") or "").strip()
    category = (args.get("category") or "").strip()
    dept = (args.get("dept") or "").strip()
    sort = args.get("sort", "score")
    try:
        page = max(1, int(args.get("page", 1)))
        page_size = min(100, max(1, int(args.get("page_size", 20))))
    except ValueError:
        page, page_size = 1, 20
    try:
        lng = float(args.get("lng", DEFAULT_LNG))
        lat = float(args.get("lat", DEFAULT_LAT))
    except ValueError:
        lng, lat = DEFAULT_LNG, DEFAULT_LAT

    where, params = ["1=1"], []
    if q:
        where.append("name LIKE %s")
        params.append(f"%{q}%")
    if district:
        where.append("district = %s")
        params.append(district)
    if level:
        where.append("level_norm = %s")
        params.append(level)
    if category:
        where.append("category_norm = %s")
        params.append(category)
    if dept:
        where.append(
            "t.id IN (SELECT hospital_id FROM dwd_dept_relation_clean WHERE dept_name = %s)"
        )
        params.append(dept)
    where_sql = " AND ".join(where)

    # Haversine 距离（km）—— 有坐标的机构才算距离
    dist_expr = (
        "CASE WHEN lng IS NOT NULL AND lat IS NOT NULL THEN "
        "ROUND(6371 * 2 * ASIN(SQRT("
        " POWER(SIN(RADIANS(lat - %s) / 2), 2) +"
        " COS(RADIANS(%s)) * COS(RADIANS(lat)) *"
        " POWER(SIN(RADIANS(lng - %s) / 2), 2)"
        ")), 2) ELSE NULL END"
    )
    dist_params = [lat, lat, lng]

    # 排序策略
    # 加权评分 = 0.4*等级 + 0.3*距离归一 + 0.2*床位归一 + 0.1*科室归一
    score_expr = (
        "ROUND(0.4 * (CASE level_norm WHEN '三级' THEN 3 WHEN '二级' THEN 2"
        " WHEN '一级' THEN 1 ELSE 0.5 END) / 3"
        " + 0.3 * (1 - LEAST(IFNULL(distance_km, 60) / 60, 1))"
        " + 0.2 * LEAST(IFNULL(beds, 0) / 1500, 1)"
        " + 0.1 * LEAST(IFNULL(dept_count, 0) / 30, 1), 4)"
    )
    if sort == "distance":
        order_sql = "distance_km IS NULL, distance_km ASC"
    elif sort == "level":
        order_sql = (
            "CASE level_norm WHEN '三级' THEN 3 WHEN '二级' THEN 2"
            " WHEN '一级' THEN 1 ELSE 0 END DESC, distance_km ASC"
        )
    elif sort == "beds":
        order_sql = "CAST(beds AS UNSIGNED) DESC"
    elif sort == "depts":
        order_sql = "dept_count DESC"
    else:
        sort = "score"
        order_sql = "score DESC, distance_km ASC"

    base_select = (
        f"FROM ads_inst_search t"
        f" JOIN (SELECT id, {dist_expr} AS distance_km FROM ads_inst_search) d"
        f" ON t.id = d.id"
        f" WHERE {where_sql}"
    )

    total = query(f"SELECT COUNT(*) AS n {base_select}", dist_params + params, one=True)["n"]

    offset = (page - 1) * page_size
    items = query(
        "SELECT t.id, t.name, t.district, t.category_norm AS category, t.level_norm AS level,"
        " t.level_sub, t.addr, t.phone, t.beds, t.key_depts,"
        " t.lng, t.lat, t.coord_precision, t.dept_count, t.key_specialty_count,"
        " d.distance_km, " + score_expr + " AS score " + base_select +
        f" ORDER BY {order_sql} LIMIT %s OFFSET %s",
        dist_params + params + [page_size, offset],
    )
    return jsonify({
        "total": total,
        "page": page,
        "page_size": page_size,
        "sort": sort,
        "items": items,
    })


# ============== API：机构详情 ==============
@app.route("/api/institutions/<inst_id>")
def api_detail(inst_id):
    inst = query(
        "SELECT id, name, district, category, category_norm, level, level_sub, level_norm,"
        " grade_scope,"
        " addr, phone, postal, beds, key_depts,"
        " lng, lat, coord_formatted, coord_precision, coord_source,"
        " src_count_int, source_files, dept_count, key_specialty_count"
        " FROM ads_inst_search WHERE id = %s",
        [inst_id], one=True,
    )
    if not inst:
        return jsonify({"error": "not found"}), 404
    depts = query(
        "SELECT dept_name, is_key_specialty FROM dwd_dept_relation_clean"
        " WHERE hospital_id = %s ORDER BY is_key_specialty DESC, dept_name",
        [inst_id],
    )
    inst["departments"] = depts
    return jsonify(inst)


# ============== API：概览统计（大屏用） ==============
@app.route("/api/overview/districts")
def api_overview_districts():
    rows = query(
        "SELECT district, inst_count, level_3_count, level_2_count,"
        " coord_high_count, coord_rough_count, coord_missing_count"
        " FROM ads_district_overview ORDER BY inst_count DESC"
    )
    return jsonify(rows)


@app.route("/api/overview/levels")
def api_overview_levels():
    """等级分布概览。

    统计口径（数据治理要点）：全表 9791 家机构中仅约 1287 家属"参加医院等级评审"
    的医疗机构，其余 8500+ 家（诊所/村卫生室/门诊部/社区卫生服务站/医务室/急救/疾控
    /体检中心等）在制度上就没有一/二/三级等级，被归入 level_norm='不适用医院分级'。
    若把它们计入"未定级"，会形成 87% 的假性未定级，掩盖真实分布。
    因此默认 scope=graded（仅应参评机构）；scope=all 可看全量口径（含"不适用"桶）。
    """
    scope = (request.args.get("scope") or "graded").strip()
    where = "" if scope == "all" else " WHERE level_norm <> '不适用医院分级'"
    rows = query(
        "SELECT level_norm, inst_count, district_count, category_count"
        f" FROM ads_level_overview{where} ORDER BY inst_count DESC"
    )
    return jsonify(rows)


@app.route("/api/overview/depts")
def api_overview_depts():
    limit = min(50, max(1, int(request.args.get("limit", 20))))
    return jsonify(query(
        "SELECT dept_name, hospital_count, key_specialty_count"
        " FROM dws_dept_coverage ORDER BY hospital_count DESC LIMIT %s", [limit]
    ))


@app.route("/api/specialty")
def api_specialty():
    return jsonify(query(
        "SELECT hospital_id, name, district, level_norm AS level, dept_name"
        " FROM ads_specialty_hospital ORDER BY district, name"
    ))


@app.route("/api/specialty/groups")
def api_specialty_groups():
    """按重点专科（dept_name）分组聚合，附该专科下医院列表 + 数量"""
    rows = query(
        "SELECT dept_name, name AS hospital, district, level_norm AS level, hospital_id"
        " FROM ads_specialty_hospital ORDER BY dept_name, hospital"
    )
    groups = {}
    for r in rows:
        d = r["dept_name"]
        if d not in groups:
            groups[d] = {"dept_name": d, "hospital_count": 0, "hospitals": []}
        groups[d]["hospital_count"] += 1
        groups[d]["hospitals"].append({
            "id": r["hospital_id"], "name": r["hospital"],
            "district": r["district"], "level": r["level"],
        })
    out = sorted(groups.values(), key=lambda x: -x["hospital_count"])
    return jsonify(out)


# ============== API：筛选项可选值 ==============
@app.route("/api/meta/filters")
def api_filters():
    districts = query(
        "SELECT district, inst_count FROM ads_district_overview ORDER BY inst_count DESC"
    )
    # 等级筛选项：不暴露"不适用医院分级"（该口径机构请用类型维度筛选）
    levels = query(
        "SELECT level_norm AS level, inst_count FROM ads_level_overview"
        " WHERE level_norm <> '不适用医院分级' ORDER BY inst_count DESC"
    )
    categories = query(
        "SELECT category_norm AS category, inst_count FROM dws_inst_by_category"
        " ORDER BY inst_count DESC"
    )
    depts = query(
        "SELECT dept_name, hospital_count FROM dws_dept_coverage ORDER BY hospital_count DESC"
    )
    return jsonify({
        "districts": districts,
        "levels": levels,
        "categories": categories,
        "depts": depts,
    })


# ============== 健康检查 ==============
@app.route("/api/health")
def api_health():
    row = query("SELECT COUNT(*) AS n FROM ads_inst_search", one=True)
    return jsonify({"status": "ok", "institutions": row["n"]})


if __name__ == "__main__":
    # macOS 端口 5000 常被 AirPlay Receiver 占用，默认使用 5001
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False, threaded=True)
