# -*- coding: utf-8 -*-
"""
北京市医疗机构资源整合与多维筛选可视化系统 —— Flask API
=========================================================
数据源：MySQL hospital 库 ADS 服务层（由 spark/jobs/ 数仓作业产出，
        ODS/DWD/DWS 三层 Parquet 落在 HDFS /hospital）
  - ads_inst_search        筛选排序主表（9,678 家机构）
  - ads_district_overview  区域概览
  - ads_level_overview     等级概览
  - ads_specialty_hospital 重点专科医院
  - dws_dept_coverage      科室覆盖度
  - dwd_dept_relation_clean 医院科室明细（详情页用）

运行：
  python web/app.py
  浏览器访问 http://127.0.0.1:5000
"""

import datetime
import difflib
import hashlib
import json
import math
import os
import re
import uuid

import pymysql
from flask import Flask, g, jsonify, render_template, request, make_response, send_from_directory

# 自然语言筛选：解析 / 执行 / 统计 / 摘要（词表与前端离线引擎同源）
sys_path = os.path.dirname(os.path.abspath(__file__))
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)
import nlq  # noqa: E402

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
# 模板热重载：build_spa.sh 会重新生成 templates/index.html，若不开启自动重载，
# debug=False 下 Jinja 会把模板缓存在内存里，导致「产物已更新但页面还是旧的」这一经典误判。
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

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


# ============== Vue 单页应用（前后端分离形态）==============
# web/vue/dist 由 `bash web/vue/build.sh` 构建产出；Flask 只负责静态托管，
# 业务数据一律仍走 /api/* 从 MySQL 取——前后端通过 JSON 接口解耦，不共享模板。
# 与原有单文件大屏（/）并存：/ 是零依赖离线兜底，/spa/ 是 Vue 在线形态。
SPA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vue", "dist")


@app.route("/spa/")
@app.route("/spa/<path:sub>")
def spa(sub=""):
    """托管 Vue 构建产物。hash 路由模式，任意深链都回退到 index.html。"""
    if not os.path.isdir(SPA_DIR):
        return ("Vue 前端尚未构建：请先执行  bash web/vue/build.sh", 503)
    target = sub if sub and os.path.isfile(os.path.join(SPA_DIR, sub)) else "index.html"
    resp = make_response(send_from_directory(SPA_DIR, target))
    if target.endswith(".html"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
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
      net       协作网络（ped_core/ped_member/stroke/neonatal/maternal）
      lng/lat   参考点坐标（默认天安门），用于距离计算与排序
      sort      排序策略：score（条件匹配度加权）| distance（近→远）| level（等级优先）
                          | depts（科室收录量多→少）| name（机构名称，默认 score）
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
    net = (args.get("net") or "").strip()
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
    if net:
        _net_map = {"ped_core": ("net_pediatric", "核心"), "ped_member": ("net_pediatric", "成员"),
                    "stroke": ("net_stroke", "1"), "neonatal": ("net_neonatal", "市级"),
                    "maternal": ("net_maternal", "市级")}
        if net in _net_map:
            _c, _v = _net_map[net]
            where.append(f"{_c} = %s")
            params.append(_v)
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
    # 加权评分 = 0.5*等级 + 0.3*距离归一 + 0.2*科室归一（床位数据覆盖率仅1.5%且真实性存疑，已移除并权重重配）
    score_expr = (
        "ROUND(0.5 * (CASE level_norm WHEN '三级' THEN 3 WHEN '二级' THEN 2"
        " WHEN '一级' THEN 1 ELSE 0.5 END) / 3"
        " + 0.3 * (1 - LEAST(IFNULL(distance_km, 60) / 60, 1))"
        " + 0.2 * LEAST(IFNULL(dept_count, 0) / 30, 1), 4)"
    )
    if sort == "distance":
        order_sql = "distance_km IS NULL, distance_km ASC"
    elif sort == "level":
        order_sql = (
            "CASE level_norm WHEN '三级' THEN 3 WHEN '二级' THEN 2"
            " WHEN '一级' THEN 1 ELSE 0 END DESC, distance_km ASC"
        )
    elif sort == "depts":
        order_sql = "dept_count DESC"
    elif sort == "name":
        # 机构名称（MySQL utf8mb4_0900_ai_ci 排序规则下对中文按 Unicode 码位排序，
        # 与单文件大屏的本地 localeCompare 结果可能存在细微差异，但同一批数据下稳定可复现）
        order_sql = "name ASC"
    else:
        sort = "score"
        order_sql = "score DESC, distance_km ASC"

    base_select = (
        f"FROM ads_inst_search t"
        f" JOIN (SELECT id, {dist_expr} AS distance_km FROM ads_inst_search) d"
        f" ON t.id = d.id"
        f" LEFT JOIN (SELECT hospital_id, COUNT(*) AS rule_dept_count FROM dwd_dept_relation_clean"
        f" WHERE source = 'rule' GROUP BY hospital_id) rc ON rc.hospital_id = t.id"
        f" WHERE {where_sql}"
    )

    total = query(f"SELECT COUNT(*) AS n {base_select}", dist_params + params, one=True)["n"]

    offset = (page - 1) * page_size
    items = query(
        "SELECT t.id, t.name, t.district, t.category_norm AS category, t.category AS category_fine,"
        " t.level_norm AS level,"
        " t.level_sub, t.addr, t.phone, t.key_depts,"
        " t.category_sub, t.ownership, t.feature, t.feature_level,"
        " t.net_pediatric, t.net_stroke, t.net_neonatal, t.net_maternal,"
        " t.lng, t.lat, t.coord_precision, t.dept_count, t.dept_count_src, t.key_specialty_count,"
        " d.distance_km, COALESCE(rc.rule_dept_count, 0) AS rule_dept_count, " + score_expr + " AS score " + base_select +
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
        "SELECT id, name, district, category, category AS category_fine, category_norm, category_sub,"
        " level, level_sub, level_norm,"
        " grade_scope, ownership, ownership_basis, feature, feature_level,"
        " addr, phone, postal, key_depts,"
        " net_pediatric, net_stroke, net_neonatal, net_maternal,"
        " lng, lat, coord_formatted, coord_precision, coord_source,"
        " src_count_int, source_files, dept_count, dept_count_src, key_specialty_count"
        " FROM ads_inst_search WHERE id = %s",
        [inst_id], one=True,
    )
    if not inst:
        return jsonify({"error": "not found"}), 404
    depts = query(
        "SELECT dept_name, is_key_specialty, source FROM dwd_dept_relation_clean"
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

    统计口径（数据治理要点）：全表 9678 家机构中仅约 874 家属"参加医院等级评审"
    的医疗机构，其余 8800+ 家（诊所/村卫生室/门诊部/社区卫生服务站/医务室/急救/疾控
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


# ============== 大模型（Agnes AI）配置与调用 ==============
# 设计要点：web/nlq.py 的规则引擎（词表 + 正则）是**默认路径**，纯离线、零依赖、
# 可复现，答辩现场绝不受网络与额度影响；大模型只在「规则零命中」时兜底，
# 且提示词中写死"只输出筛选条件，不输出机构名与数字"，从设计上堵死幻觉。
# 开启方式（三级优先，后者兜底）：
#   1) export AI_API_KEY=sk-xxx            # 环境变量
#   2) data/.ai_key.txt                    # 密钥文件（已被 .gitignore 排除，绝不入库）
#   3) AI_LLM_ENABLED=0 可强制关闭（离线答辩时用）
# 可选覆盖：AI_API_BASE / AI_MODEL / AI_TIMEOUT
import json as _json
import time
import urllib.error
import urllib.request


def _read_secret(rel_path):
    """从项目根目录读取密钥文件（用于本地开发；文件已 gitignore，不会入库）。"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", rel_path)
    try:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read().strip()
    except OSError:
        return ""
    return ""


AI_API_BASE = (os.environ.get("AI_API_BASE")
               or "https://apihub.agnes-ai.com/v1").rstrip("/")
AI_API_KEY = os.environ.get("AI_API_KEY") or _read_secret("data/.ai_key.txt")
# 实测选型：agnes-2.0-flash 平均约 4s；agnes-2.5-flash 平均约 18s（最长 32s），
# 交互式解析必须用快模型，慢模型只适合离线批处理。可用 AI_MODEL 覆盖。
AI_MODEL = os.environ.get("AI_MODEL") or "agnes-2.0-flash"
# 开关：显式设置 AI_LLM_ENABLED 时以其为准；未设置则「有密钥即自动启用」
_ENV_FLAG = os.environ.get("AI_LLM_ENABLED", "").strip()
AI_LLM_ENABLED = (_ENV_FLAG == "1") if _ENV_FLAG != "" else bool(AI_API_KEY)
AI_TIMEOUT = float(os.environ.get("AI_TIMEOUT", "10"))
# 实测 2.0-flash 正常约 4 秒，10 秒已留 2.5 倍余量；
# 设太大（如 20 秒）会让「模型不可用」时用户干等太久。

class LLMRateLimited(Exception):
    """免费额度限流（HTTP 429）：既非网络故障也非配置错误，需向用户明确区分。"""


# 双层缓存（进程内内存 + MySQL 持久化）：
# Agnes 免费额度实测约 1 次/30~40 秒，靠重试硬扛会让界面长时间空转；
# 因此把「问题 → 科室」结果落库，重复提问零额度、零等待，且答辩前可预热。
_LLM_CACHE = {}
_LLM_CACHE_MAX = 200
_AI_CACHE_DDL = (
    "CREATE TABLE IF NOT EXISTS dim_ai_cache ("
    " cache_key VARCHAR(255) NOT NULL PRIMARY KEY,"
    " kind VARCHAR(24) NOT NULL,"
    " model VARCHAR(64) DEFAULT NULL,"
    " payload MEDIUMTEXT NOT NULL,"
    " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    " ON UPDATE CURRENT_TIMESTAMP) DEFAULT CHARSET=utf8mb4"
)


def _ai_cache_get(key):
    """读持久化缓存；表不存在或数据库异常时静默返回 None（缓存不是主链路）。"""
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT payload FROM dim_ai_cache WHERE cache_key=%s", (key,))
            row = cur.fetchone()
        return _json.loads(row["payload"]) if row else None
    except Exception:
        return None


def _ai_cache_put(key, kind, payload):
    """写持久化缓存；失败不影响本次返回结果。"""
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute(_AI_CACHE_DDL)
            cur.execute(
                "INSERT INTO dim_ai_cache (cache_key, kind, model, payload) "
                "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE "
                "payload=VALUES(payload), model=VALUES(model)",
                (key, kind, AI_MODEL, _json.dumps(payload, ensure_ascii=False)))
        db.commit()
    except Exception:
        pass


def _llm_chat(messages, timeout=None, temperature=0):
    """调用 OpenAI 兼容的 /chat/completions，返回助手正文。

    Agnes 是推理模型，思维链在 reasoning_content、正文在 content，取后者。
    免费额度实测约 1 次/30~40 秒：命中 429 时短暂退避重试，仍失败则抛
    LLMRateLimited，由调用方给出明确提示（而不是含糊的"服务异常"）。
    """
    payload = _json.dumps({
        "model": AI_MODEL, "messages": messages, "temperature": temperature,
    }, ensure_ascii=False).encode("utf-8")
    # 免费额度窗口实测约 30~40 秒，短退避重试等不到窗口恢复，
    # 故只做一次极短重试后快速失败并明确告知——不把用户挂在「解析中…」干等。
    # 真正的解法是预热缓存（/api/ai/warm，见 etl/warm_ai_cache.py）。
    backoff = [2.0]
    for attempt in range(len(backoff) + 1):
        req = urllib.request.Request(
            AI_API_BASE + "/chat/completions", data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + AI_API_KEY})
        try:
            with urllib.request.urlopen(req, timeout=timeout or AI_TIMEOUT) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            return (data["choices"][0]["message"].get("content") or "").strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if attempt < len(backoff):
                    time.sleep(backoff[attempt])
                    continue
                raise LLMRateLimited("Agnes 免费额度限流（429）")
            if e.code in (500, 502, 503, 504) and attempt < len(backoff):
                time.sleep(backoff[attempt])
                continue
            raise


def _llm_json(prompt, kind, q, timeout=None):
    """要求模型只输出 JSON，按「内存 → MySQL → 接口」三级读取并回写缓存。

    容忍模型用代码块围栏包裹 JSON，或前后带解释性客套话。
    """
    ck = AI_MODEL + "|" + kind + "|" + q
    if ck in _LLM_CACHE:
        return _LLM_CACHE[ck]
    cached = _ai_cache_get(ck)
    if cached is not None:
        _LLM_CACHE[ck] = cached
        return cached
    txt = _llm_chat([{"role": "user", "content": prompt}], timeout=timeout)
    a, b = txt.find("{"), txt.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("模型未返回 JSON：" + txt[:80])
    out = _json.loads(txt[a:b + 1])
    if len(_LLM_CACHE) >= _LLM_CACHE_MAX:
        _LLM_CACHE.clear()
    _LLM_CACHE[ck] = out
    _ai_cache_put(ck, kind, out)
    return out

STD_DEPTS = ("心血管内科 呼吸内科 消化内科 神经内科 肾内科 内分泌科 血液内科 老年病科 普内科 "
             "全科医疗科 普通外科 骨科 神经外科 心胸外科 泌尿外科 肛肠外科 妇产科 儿科 肿瘤科 "
             "精神心理科 眼科 耳鼻咽喉科 口腔科 皮肤科 中医内科 中医骨伤科 针灸推拿科 感染科 "
             "肝病科 急诊科 重症医学科 康复医学科").split()
# 大模型兜底解析提示词。
# 它与 web/nlq.py 的规则解析器**共用同一套条件 schema**——这样"规则命中"和"模型兜底"
# 两条路径产出的条件长得一样，前端只有一套渲染逻辑，用户也看不出差别。
# 强调"不许生成机构名/数字"，是为了在任何路径下都堵死幻觉。
AI_PARSE_PROMPT = (
    "你是「北京市医疗机构检索系统」的自然语言查询解析器。"
    "任务：把用户的中文查询转成 JSON 格式的结构化筛选条件。\n"
    "可选字段（没有提到的就省略，不要猜）：\n"
    "  district       行政区数组，取值必须来自：" + "、".join(nlq.DISTRICTS) + "\n"
    "  level          医院等级数组，取值来自：三级/二级/一级/未定级\n"
    "  level_min      等级下限（整数 1/2/3），仅当用户说「二级以上」这类表达时给出\n"
    "  category       机构类型数组，取值来自：" + "、".join(nlq.CATEGORIES) + "\n"
    "  ownership      所有制数组，取值来自：公立/民营/未标注\n"
    "  source         数据来源数组，取值来自：" + "、".join(r["key"] for r in nlq.SOURCE_RULES) + "\n"
    "  dept           科室名，必须取自：" + "、".join(STD_DEPTS) + "\n"
    "  kw             机构名称关键词\n"
    "  sort           排序，取值 score/distance/level/depts/name\n"
    "铁律：只输出筛选条件，绝不输出任何机构名称、医院名、数量或统计数字——"
    "那些必须由数据库查询得到。若用户描述的是病症、用药、治疗或诊断诉求，"
    "输出 {\"unsupported\": true} 即可，不要试图判断病情。\n"
    "只输出 JSON 本体，不要解释、不要代码块。用户查询："
)
# 结果摘要提示词：模型只负责"把 SQL 查出来的事实讲成人话"，
# 数字与机构名一律照抄事实，杜绝编造（答辩会问"AI 会不会瞎编"）。
SUMMARY_PROMPT = (
    "你是北京市医疗机构数据平台的查询结果说明助手。请依据给定的结构化事实，"
    "用 2~3 句中文说明这次查询。硬性要求：\n"
    "① 只能使用事实中出现的信息；机构名称、数量、比例必须与事实完全一致，"
    "不得新增、不得四舍五入改数、不得编造排名或结论；\n"
    "② 这是**数据查询说明**，不是医疗建议：不要给出就诊推荐、诊断、用药或治疗意见；\n"
    "③ 语言客观平实，不夸大、不营销，不使用 Markdown 与列表；\n"
    "④ 若事实里指明了筛选条件，第一句要先复述条件。\n"
    "只输出说明正文。事实(JSON)："
)


@app.route("/api/ai/health")
def api_ai_health():
    """大模型探活：前端据此决定是否开启兜底（离线单文件永不调用）。

    默认不发起真实推理（避免拖慢首屏）；加 ?probe=1 才做一次真实连通性测试。
    """
    enabled = bool(AI_LLM_ENABLED and AI_API_KEY)
    out = {
        "ok": True,
        "llm_enabled": enabled,
        "model": AI_MODEL if enabled else None,
        "base": AI_API_BASE if enabled else None,
    }
    if request.args.get("probe") == "1" and enabled:
        try:
            _llm_chat([{"role": "user", "content": "回复 ok"}], timeout=AI_TIMEOUT)
            out["probe"] = "ok"
        except Exception as e:
            out["probe"] = "fail"
            out["detail"] = str(e)[:120]
    return jsonify(out)


@app.route("/api/ai/parse")
def api_ai_parse():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"ok": False, "reason": "empty"})
    if not (AI_LLM_ENABLED and AI_API_KEY):
        return jsonify({
            "ok": False, "reason": "llm_disabled",
            "hint": "大模型兜底未启用。前端规则引擎可独立完成解析（离线可用）；"
                    "如需启用请在 data/.ai_key.txt 放置密钥或设置 AI_API_KEY。",
        })
    try:
        cond = _llm_json(AI_PARSE_PROMPT + q, "parse", q)
        return jsonify({"ok": True, "engine": "llm", "model": AI_MODEL,
                        "conditions": cond})
    except LLMRateLimited:
        return jsonify({"ok": False, "reason": "llm_rate_limited",
                        "hint": "Agnes 免费额度限流（约 1 次/30 秒），稍后重试即可；"
                                "前端规则引擎不受影响，仍可离线解析。"})
    except Exception as e:  # 兜底绝不影响主流程
        return jsonify({"ok": False, "reason": "llm_error", "detail": str(e)[:200]})


# 注：SUMMARY_PROMPT 已上移到 AI_PARSE_PROMPT 旁边统一定义，
# 避免两处提示词漂移（旧版这里还留着一份"面向普通患者的总结"，已删除）。


@app.route("/api/ai/summary")
def api_ai_summary():
    """生成式总结：把结构化筛选结果写成一段自然语言。

    三级降级：LLM 润色 → 命中缓存 → 调用方回传的本地模板（local）。
    离线单文件永不调用本接口，本地模板保证无网络也一定有总结可看。
    """
    facts = (request.args.get("facts") or "").strip()[:4000]
    local = (request.args.get("local") or "").strip()[:1200]
    if not facts:
        return jsonify({"ok": False, "reason": "empty", "summary": local})
    if not (AI_LLM_ENABLED and AI_API_KEY):
        return jsonify({"ok": True, "engine": "local", "summary": local})
    ck = AI_MODEL + "|summary|" + hashlib.sha1(facts.encode("utf-8")).hexdigest()[:24]
    if ck in _LLM_CACHE:
        return jsonify({"ok": True, "engine": "llm", "model": AI_MODEL,
                        "summary": _LLM_CACHE[ck], "cached": True})
    cached = _ai_cache_get(ck)
    if cached is not None:
        _LLM_CACHE[ck] = cached
        return jsonify({"ok": True, "engine": "llm", "model": AI_MODEL,
                        "summary": cached, "cached": True})
    try:
        txt = (_llm_chat([{"role": "user", "content": SUMMARY_PROMPT + facts}],
                         temperature=0.3) or "").strip()
        if not txt:
            raise ValueError("模型返回空")
        if len(_LLM_CACHE) >= _LLM_CACHE_MAX:
            _LLM_CACHE.clear()
        _LLM_CACHE[ck] = txt
        _ai_cache_put(ck, "summary", txt)
        return jsonify({"ok": True, "engine": "llm", "model": AI_MODEL, "summary": txt})
    except LLMRateLimited:
        return jsonify({"ok": True, "engine": "local", "summary": local,
                        "note": "Agnes 免费额度限流（约 1 次/30 秒），已用本地模板生成"})
    except Exception as e:  # 兜底绝不影响主流程
        return jsonify({"ok": True, "engine": "local", "summary": local,
                        "note": "大模型不可用，已用本地模板生成：" + str(e)[:80]})


@app.route("/api/ai/warm")
def api_ai_warm():
    """预热大模型解析缓存：演示/答辩前跑一次，把常用问法固化到缓存，现场零等待。

    用法：/api/ai/warm?queries=朝阳区三级公立医院|海淀区二级以上医院
    免费额度约 1 次/30 秒，故每次调用间自动 sleep，避免连续 429。
    返回每个问法的预热结果（ok / cached / skipped_local / rate_limited）。

    注意：规则解析器（web/nlq.py）能直接命中的问法**不消耗额度**——
    现场本来就优先走规则链路，大模型只是长尾兜底。
    """
    raw = (request.args.get("queries") or "").strip()
    if not raw:
        return jsonify({"ok": False, "reason": "empty"})
    if not (AI_LLM_ENABLED and AI_API_KEY):
        return jsonify({"ok": False, "reason": "llm_disabled"})
    queries = [x.strip() for x in raw.split("|") if x.strip()][:20]
    out = []
    for i, q in enumerate(queries):
        ck = AI_MODEL + "|parse|" + q
        if ck in _LLM_CACHE or _ai_cache_get(ck) is not None:
            out.append({"q": q, "status": "cached"})
            continue
        rule = nlq.parse(q)
        if rule["intent"] != "unsupported" and rule["applied"]:
            out.append({"q": q, "status": "skipped_local",
                        "conditions": rule["conditions"]})
            continue
        if i:                       # 免费额度约 1 次/30 秒，串行预热必须留足间隔
            time.sleep(30)
        try:
            cond = _llm_json(AI_PARSE_PROMPT + q, "parse", q)
            out.append({"q": q, "status": "ok", "conditions": cond})
        except LLMRateLimited:
            out.append({"q": q, "status": "rate_limited"})
        except Exception as e:
            out.append({"q": q, "status": "error", "detail": str(e)[:120]})
    return jsonify({"ok": True, "total": len(queries), "results": out})


def haversine(lng1, lat1, lng2, lat2):
    """两点间距离（km）"""
    rad = 3.141592653589793 / 180.0
    dlat = (lat2 - lat1) * rad
    dlng = (lng2 - lng1) * rad
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlng / 2) ** 2)
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))

# ==============================================================================
# 增强模块：机构详情（联系方式/位置/重点专科）+ 对比 + 行为埋点 + 运营后台
# ==============================================================================
# 设计原则（与自然语言筛选一致）：
#   1) 一切"真实可得"的信息优先用真实数据：重点专科、联系方式、地址、坐标、距离；
#   2) 需要外部数据的（周边地铁站/停车场）走高德开放平台实时查询，结果落库缓存；
#   3) 拿不到真实数据的（实时排队人数）**明确标注"演示模拟"**，绝不伪装成真实数据；
#   4) 不外呼大模型编造医生姓名/职称——医学事实性错误在答辩现场是致命伤。

import hashlib
import urllib.parse

# 高德开放平台（Key 存 data/.amap_key.txt，已 gitignore）
AMAP_KEY = os.environ.get("AMAP_KEY") or _read_secret("data/.amap_key.txt")

# 北京市预约挂号统一平台（北京 114）：官方入口。京医通已于 2022 年停用，
# 现行为 114 统一平台 + 各医院自有渠道，故统一指向 114。
GUAHao_114 = "https://www.114yygh.com/"
POI_CACHE_DDL = (
    "CREATE TABLE IF NOT EXISTS dim_poi_cache ("
    " cache_key VARCHAR(191) NOT NULL PRIMARY KEY,"
    " kind VARCHAR(16) NOT NULL,"
    " payload MEDIUMTEXT NOT NULL,"
    " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    " ON UPDATE CURRENT_TIMESTAMP) DEFAULT CHARSET=utf8mb4"
)


def _poi_cache_get(key):
    try:
        with get_db().cursor() as cur:
            cur.execute("SELECT payload FROM dim_poi_cache WHERE cache_key=%s", (key,))
            row = cur.fetchone()
        return _json.loads(row["payload"]) if row else None
    except Exception:
        return None


def _poi_cache_put(key, kind, payload):
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute(POI_CACHE_DDL)
            cur.execute(
                "INSERT INTO dim_poi_cache (cache_key, kind, payload) VALUES (%s,%s,%s)"
                " ON DUPLICATE KEY UPDATE payload=VALUES(payload)",
                (key, kind, _json.dumps(payload, ensure_ascii=False)))
        db.commit()
    except Exception:
        pass


def _amap_around(lng, lat, keywords, radius=2000, limit=5):
    """高德「周边搜索」。失败（无 Key / 超额 / 断网）一律返回 None，由调用方降级。"""
    if not AMAP_KEY:
        return None
    qs = urllib.parse.urlencode({
        "key": AMAP_KEY, "location": f"{lng:.6f},{lat:.6f}",
        "keywords": keywords, "radius": radius, "offset": limit,
        "page": 1, "sortrule": "distance", "output": "json",
    })
    try:
        req = urllib.request.Request(
            "https://restapi.amap.com/v3/place/around?" + qs,
            headers={"User-Agent": "hospital-dashboard/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if str(data.get("status")) != "1":
        return None
    out = []
    for p in (data.get("pois") or [])[:limit]:
        dm = p.get("distance")
        try:
            dm = int(float(dm))
        except (TypeError, ValueError):
            dm = None
        addr = p.get("address")
        if isinstance(addr, list):
            addr = ""
        out.append({
            "name": p.get("name") or "",
            "distance_m": dm,
            "walk_min": max(1, int(round(dm / 75.0))) if dm else None,  # 75 m/min 步行
            "type": (p.get("type") or "").split(";")[-1],
            "address": addr or "",
            "tel": (p.get("tel") if isinstance(p.get("tel"), str) else "") or "",
            "lng": _safe_float((p.get("location") or ",").split(",")[0]),
            "lat": _safe_float((p.get("location") or ",").split(",")[-1]),
        })
    return out


def _safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _around_cached(lng, lat, kind, keywords, radius=2000, limit=5):
    """周边配套查询（缓存键按 ~100m 网格取整，避免同一医院反复消耗高德额度）。"""
    if lng is None or lat is None:
        return None
    key = f"poi|{round(float(lng),3)}|{round(float(lat),3)}|{kind}|{radius}|{limit}"
    hit = _poi_cache_get(key)
    if hit is not None:
        return hit
    res = _amap_around(lng, lat, keywords, radius, limit)
    if res is not None:
        _poi_cache_put(key, kind, res)
    return res


def _amap_geocode(address):
    """高德「地理编码」：任意地址文本 → 坐标（距离基准自定义起点用）。

    失败（无 Key / 超额 / 断网 / 未命中）一律返回 None，由调用方降级为
    前端本地匹配（区中心 / 机构名 / 地址关键词）。
    """
    if not AMAP_KEY:
        return None
    qs = urllib.parse.urlencode({
        "key": AMAP_KEY, "address": address, "city": "北京",
        "citylimit": "true", "output": "json",
    })
    try:
        req = urllib.request.Request(
            "https://restapi.amap.com/v3/geocode/geo?" + qs,
            headers={"User-Agent": "hospital-dashboard/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if str(data.get("status")) != "1":
        return None
    gs = data.get("geocodes") or []
    if not gs:
        return None
    g = gs[0]
    loc = (g.get("location") or "").split(",")
    if len(loc) != 2:
        return None
    try:
        lng, lat = float(loc[0]), float(loc[1])
    except ValueError:
        return None
    return {
        "lng": lng, "lat": lat,
        "formatted": g.get("formatted_address") or address,
        "district": g.get("district") or "",
        "level": g.get("level") or "",
    }


@app.route("/api/geocode")
def api_geocode():
    """地址文本 → 坐标。成功结果写 dim_poi_cache（kind=geocode），失败不缓存可重试。"""
    address = (request.args.get("address") or "").strip()
    if not address:
        return jsonify({"error": "address required"}), 400
    address = address[:60]
    key = "geocode|" + address
    hit = _poi_cache_get(key)
    if hit is not None:
        return jsonify(hit)
    out = _amap_geocode(address)
    if out is None:
        return jsonify({"error": "geocode failed"}), 502
    _poi_cache_put(key, "geocode", out)
    return jsonify(out)


def _consult_links(r):
    """机构公开联系入口：官方平台外链 / 电话 / 官网 / 导航。

    这里只做**公开信息的跳转**，不抓取也不展示号源与排班；
    不伪造深度链接（114 平台为 JS 单页应用，不存在可构造的按医院直达 URL，硬拼会得到死链）。
    """
    lng, lat = _safe_float(r.get("lng")), _safe_float(r.get("lat"))
    nav = ""
    if lng is not None and lat is not None:
        nav = ("https://uri.amap.com/marker?position=%.6f,%.6f&name=%s&src=hospital-dashboard"
               "&coordinate=gaode&callnative=1" % (lng, lat, urllib.parse.quote(r.get("name") or "医院")))
    phone = (r.get("phone") or "").strip()
    return {
        "guahao_114": GUAHao_114,
        "hospital_phone": phone,
        "hospital_tel_link": ("tel:" + phone) if phone else "",
        "website": (r.get("website") or "").strip(),
        "amap_nav": nav,
        "hospital_name": r.get("name") or "",
    }


def _specialty_detail(r):
    """特色科室 / 重点专科：来自真实数据的权威分级。

    国家级重点专科 > 北京市级重点专科 > 擅长科室（feature）。全部有据可查。
    """
    nat = [x.strip() for x in (r.get("national_specialty") or "").split(";") if x.strip()]
    mun = [x.strip() for x in (r.get("municipal_specialty") or "").split(";") if x.strip()]
    feat = [x.strip() for x in (r.get("feature") or "").split(";") if x.strip()]
    return {"national": nat, "municipal": mun, "feature": feat,
            "national_count": r.get("national_specialty_count") or 0,
            "municipal_count": r.get("municipal_specialty_count") or 0,
            "key_count": r.get("key_specialty_count") or 0}


# -------- 详情 --------
@app.route("/api/inst/<inst_id>/detail")
def api_inst_detail(inst_id):
    """医院详情：联系方式 + 就诊入口 + 特色科室 + 周边配套 + 实时状态（模拟）。"""
    r = query(
        "SELECT id, name, district, category_norm, category_sub, level_norm, level_sub,"
        " grade_scope, ownership, ownership_basis, feature, feature_level,"
        " addr, phone, postal, key_depts,"
        " national_specialty, national_specialty_count,"
        " municipal_specialty, municipal_specialty_count, key_specialty_count, dept_count,"
        " net_pediatric, net_stroke, net_neonatal, net_maternal,"
        " lng, lat, coord_precision"
        " FROM ads_inst_search WHERE id = %s", [inst_id], one=True)
    if not r:
        return jsonify({"ok": False, "reason": "not_found"}), 404

    lng, lat = _safe_float(r.get("lng")), _safe_float(r.get("lat"))
    around, around_ok = {"metro": None, "parking": None, "bus": None}, False
    if lng is not None and lat is not None:
        metro = _around_cached(lng, lat, "metro", "地铁站", 3000, 3)
        parking = _around_cached(lng, lat, "parking", "停车场", 1500, 3)
        bus = _around_cached(lng, lat, "bus", "公交站", 800, 3)
        around = {"metro": metro, "parking": parking, "bus": bus}
        around_ok = any(v for v in (metro, parking, bus))

    return jsonify({
        "ok": True,
        "base": {
            "id": r["id"], "name": r["name"], "district": r["district"],
            "level": r["level_norm"], "level_sub": r["level_sub"],
            "category": r["category_norm"],
            "category_fine": r.get("category") or r["category_norm"],
            "category_sub": r.get("category_sub") or "",
            "ownership": r.get("ownership") or "", "ownership_basis": r.get("ownership_basis") or "",
            "grade_scope": r.get("grade_scope") or "",
            "dept_count": r.get("dept_count") or 0,
            "dept_count_src": r.get("dept_count_src") or "",
            "key_specialty_count": r.get("key_specialty_count") or 0,
        },
        "contact": {
            "addr": (r.get("addr") or "").strip(),
            "phone": (r.get("phone") or "").strip(),
            "postal": (r.get("postal") or "").strip(),
            "website": (r.get("website") or "").strip(),
            "traffic": (r.get("traffic") or "").strip(),
            "lng": lng, "lat": lat, "coord_precision": r.get("coord_precision") or "",
        },
        "links": _consult_links(r),
        "specialty": _specialty_detail(r),
        "networks": _net_list(r),
        "around": around,
        "around_online": around_ok,
        "around_enabled": bool(AMAP_KEY),
        "depts": query(
            "SELECT dept_name, is_key_specialty, source FROM dwd_dept_relation_clean"
            " WHERE hospital_id = %s ORDER BY is_key_specialty DESC, dept_name LIMIT 60",
            [inst_id]),
    })


def _net_list(r):
    n = []
    if r.get("net_pediatric") == "核心":
        n.append("儿科医联体·核心医院")
    elif r.get("net_pediatric") == "成员":
        n.append("儿科医联体·成员机构")
    if r.get("net_stroke") == "1":
        n.append("卒中中心")
    if r.get("net_neonatal") == "市级":
        n.append("危重新生儿救治中心（市级）")
    if r.get("net_maternal") == "市级":
        n.append("危重孕产妇救治中心（市级）")
    return n


# -------- 对比 --------
COMPARE_FIELDS = [
    ("name", "机构名称"), ("level", "医院等级"), ("category", "机构类型"),
    ("ownership", "办别性质"), ("district", "所属区域"),
    ("key_specialty_count", "重点专科数"), ("national_specialty_count", "国家级重点专科"),
    ("municipal_specialty_count", "市级重点专科"), ("dept_count", "科室数量（含推导）"),
    ("networks_text", "协作网络"), ("national_specialty", "国家级专科清单"),
    ("municipal_specialty", "市级专科清单"), ("feature", "擅长科室"),
    ("addr", "地址"), ("phone", "联系电话"), ("distance_text", "距离基准点"),
    ("coord_precision", "坐标精度"),
]


@app.route("/api/inst/compare")
def api_inst_compare():
    """多机构横向对比（2~4 家）。

    距离统一以「天安门」为基准，保证横向可比（不同机构用不同基准点没有意义）。
    """
    ids = [x.strip() for x in (request.args.get("ids") or "").split(",") if x.strip()][:4]
    if len(ids) < 2:
        return jsonify({"ok": False, "reason": "need_2_to_4_ids"})
    ph = ",".join(["%s"] * len(ids))
    rows = query(
        "SELECT id, name, district, category_norm, level_norm, ownership, ownership_basis,"
        " addr, phone, feature, national_specialty, national_specialty_count,"
        " municipal_specialty, municipal_specialty_count, key_specialty_count, dept_count,"
        " net_pediatric, net_stroke, net_neonatal, net_maternal, lng, lat, coord_precision"
        f" FROM ads_inst_search WHERE id IN ({ph})", ids)
    order = {i: n for n, i in enumerate(ids)}
    rows.sort(key=lambda r: order.get(str(r["id"]), 99))
    for r in rows:
        lng, lat = _safe_float(r.get("lng")), _safe_float(r.get("lat"))
        r["distance_km"] = (round(haversine(DEFAULT_LNG, DEFAULT_LAT, lng, lat), 1)
                            if (lng is not None and lat is not None) else None)
        r["distance_text"] = (f"{r['distance_km']} km（距天安门）"
                              if r["distance_km"] is not None else "—")
        r["level"] = r.pop("level_norm")
        r["category"] = r.pop("category_norm")
        r["networks_text"] = "、".join(_net_list(r)) or "未纳入"
        for k in ("feature", "national_specialty", "municipal_specialty", "addr", "phone"):
            r[k] = (r.get(k) or "").strip()
    return jsonify({"ok": True, "fields": COMPARE_FIELDS, "items": rows})


# -------- 行为埋点 --------
EVENT_DDL = (
    "CREATE TABLE IF NOT EXISTS fact_user_event ("
    " id BIGINT AUTO_INCREMENT PRIMARY KEY,"
    " ev VARCHAR(24) NOT NULL,"
    " k1 VARCHAR(191) DEFAULT NULL,"
    " k2 VARCHAR(191) DEFAULT NULL,"
    " num INT DEFAULT NULL,"
    " sid VARCHAR(40) DEFAULT NULL,"
    " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    " INDEX idx_ev (ev), INDEX idx_created (created_at)"
    ") DEFAULT CHARSET=utf8mb4"
)


@app.route("/api/track", methods=["GET", "POST"])
def api_track():
    """行为埋点。用于「运营后台」的真实使用统计。

    刻意保持极简（单条 INSERT，失败静默）：埋点绝不能影响主流程。
    """
    a = request.values
    ev = (a.get("ev") or "").strip()[:24]
    if not ev:
        return jsonify({"ok": False})
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute(EVENT_DDL)
            cur.execute(
                "INSERT INTO fact_user_event (ev, k1, k2, num, sid) VALUES (%s,%s,%s,%s,%s)",
                (ev, (a.get("k1") or "")[:191] or None, (a.get("k2") or "")[:191] or None,
                 a.get("num", type=int), (a.get("sid") or "")[:40] or None))
        db.commit()
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/api/admin/stats")
def api_admin_stats():
    """运营后台：① 真实行为统计（埋点累积） ② 资源热度（源自 9,678 家真实数据）。

    冷启动时行为统计为空，前端会明确提示「尚无行为数据」——不编造演示数据。
    """
    def top(ev, limit=10, days=30):
        return query(
            "SELECT k1 AS label, COUNT(*) AS n FROM fact_user_event"
            f" WHERE ev=%s AND k1 IS NOT NULL AND k1<>''"
            f" AND created_at > DATE_SUB(NOW(), INTERVAL {days} DAY)"
            " GROUP BY k1 ORDER BY n DESC LIMIT %s", (ev, limit))

    behaviors = {
        "days": 30,
        "totals": query(
            "SELECT ev, COUNT(*) AS n FROM fact_user_event"
            " WHERE created_at > DATE_SUB(NOW(), INTERVAL 30 DAY) GROUP BY ev ORDER BY n DESC"),
        "total_events": (query("SELECT COUNT(*) AS n FROM fact_user_event", one=True) or {}).get("n", 0),
        "top_keywords": top("search", 10),
        "top_districts": top("filter_district", 10),
        "top_detail": top("detail", 8),
        "top_nlq": top("nlq", 8),
        "daily": query(
            "SELECT DATE(created_at) AS d, COUNT(*) AS n FROM fact_user_event"
            " WHERE created_at > DATE_SUB(NOW(), INTERVAL 14 DAY)"
            " GROUP BY DATE(created_at) ORDER BY d"),
    }
    # 资源热度：完全由真实数据计算，冷启动即有内容
    resources = {
        "district_density": query(
            "SELECT district, inst_count, level_3_count, coord_high_count"
            " FROM ads_district_overview ORDER BY inst_count DESC LIMIT 16"),
        "level_mix": query(
            "SELECT level_norm AS level, inst_count FROM ads_level_overview"
            " WHERE level_norm <> '不适用医院分级' ORDER BY inst_count DESC"),
        "specialty_top": query(
            "SELECT dept_name, hospital_count, key_specialty_count FROM dws_dept_coverage"
            " ORDER BY hospital_count DESC LIMIT 12"),
        "category_mix": query(
            "SELECT category_norm AS category, inst_count FROM dws_inst_by_category"
            " ORDER BY inst_count DESC LIMIT 10"),
        "network_cover": {
            "ped_core": (query("SELECT COUNT(*) AS n FROM ads_inst_search WHERE net_pediatric='核心'", one=True) or {}).get("n", 0),
            "ped_member": (query("SELECT COUNT(*) AS n FROM ads_inst_search WHERE net_pediatric='成员'", one=True) or {}).get("n", 0),
            "stroke": (query("SELECT COUNT(*) AS n FROM ads_inst_search WHERE net_stroke='1'", one=True) or {}).get("n", 0),
            "neonatal": (query("SELECT COUNT(*) AS n FROM ads_inst_search WHERE net_neonatal='市级'", one=True) or {}).get("n", 0),
            "maternal": (query("SELECT COUNT(*) AS n FROM ads_inst_search WHERE net_maternal='市级'", one=True) or {}).get("n", 0),
        },
        "ownership": query(
            "SELECT ownership, COUNT(*) AS n FROM ads_inst_search GROUP BY ownership ORDER BY n DESC"),
    }
    return jsonify({"ok": True, "behaviors": behaviors, "resources": resources})


# -------- AI 就医提示（可选增强，绝不编造事实） --------
# 定位纪律（答辩口径）：本系统是"机构资源数据平台"，不是就医助手。
# 因此这里生成的是**机构数据画像解读**，不是就医建议——不判科、不推荐、不引导挂号。
AI_ADVICE_RULES = (
    "你是「北京市医疗机构数据智能分析与筛选平台」的数据解读助手。"
    "请基于用户给出的【该机构的真实数据】，写一段 80~120 字的**机构数据画像解读**。\n"
    "硬性要求：\n"
    "① 只能引用给定的真实信息（等级、区域、类型、所有制、重点专科名称、协作网络），"
    "不得添加任何未给出的信息；\n"
    "② 严禁编造医生姓名、职称、出诊时间、号源数量、价格、治愈率或任何具体数字；\n"
    "③ 严禁使用「全国第一」「最好的医院」等无法核实的绝对化表述；\n"
    "④ 严禁给出就诊建议、科室推荐、疾病相关判断或挂号引导——本系统只做机构资源数据查询；\n"
    "⑤ 语气客观，结尾用一句话说明这些字段来自哪些公开数据源；\n"
    "⑥ 只输出这段文字，不要标题、不要 Markdown、不要 JSON。\n"
    "【该机构的真实数据】\n"
)


@app.route("/api/ai/advice")
def api_ai_advice():
    inst_id = (request.args.get("id") or "").strip()
    if not inst_id:
        return jsonify({"ok": False, "reason": "empty"})
    r = query(
        "SELECT name, district, level_norm, category_norm, ownership, feature,"
        " national_specialty, municipal_specialty, key_specialty_count, dept_count,"
        " net_pediatric, net_stroke, net_neonatal, net_maternal"
        " FROM ads_inst_search WHERE id=%s", [inst_id], one=True)
    if not r:
        return jsonify({"ok": False, "reason": "not_found"}), 404
    if not (AI_LLM_ENABLED and AI_API_KEY):
        return jsonify({"ok": False, "reason": "llm_disabled",
                        "hint": "大模型未启用（离线版不支持该增强）"})
    facts = (
        f"名称：{r['name']}\n区域：{r['district']}\n等级：{r['level_norm']}\n"
        f"类型：{r['category_norm']}\n办别：{r.get('ownership') or '未标注'}\n"
        f"国家级重点专科：{r.get('national_specialty') or '无'}\n"
        f"北京市级重点专科：{r.get('municipal_specialty') or '无'}\n"
        f"擅长科室：{(r.get('feature') or '无')}\n"
        f"重点专科总数：{r.get('key_specialty_count') or 0}\n"
        f"协作网络：{'、'.join(_net_list(r)) or '未纳入'}"
    )
    try:
        txt = _llm_chat([{"role": "user", "content": AI_ADVICE_RULES + facts}],
                        timeout=AI_TIMEOUT)
        return jsonify({"ok": True, "engine": "llm", "model": AI_MODEL,
                        "advice": txt.strip(),
                        "constraint": "仅基于数据库真实字段生成机构数据画像，禁止编造医生、数字与就诊建议"})
    except LLMRateLimited:
        return jsonify({"ok": False, "reason": "llm_rate_limited",
                        "hint": "Agnes 免费额度限流（约 1 次/30 秒），稍后重试"})
    except Exception as e:
        return jsonify({"ok": False, "reason": "llm_error", "detail": str(e)[:160]})


# -------- 数据来源 / 更新日志（关于页） --------
@app.route("/api/about")
def api_about():
    """关于页数据：数据来源、清洗流程、更新时间、规模指标。全部取自真实表。"""
    def one(sql):
        return (query(sql, one=True) or {})
    return jsonify({
        "ok": True,
        "counts": {
            "institutions": one("SELECT COUNT(*) AS n FROM ads_inst_search")["n"],
            "dwd_institutions": one("SELECT COUNT(*) AS n FROM dwd_institution_clean")["n"],
            "dept_relations": one("SELECT COUNT(*) AS n FROM dwd_dept_relation_clean")["n"],
            "specialty_rows": one("SELECT COUNT(*) AS n FROM dwd_specialty_clean")["n"],
            "tables": one(
                "SELECT COUNT(*) AS n FROM information_schema.tables"
                " WHERE table_schema='hospital'")["n"],
            "with_coord": one(
                "SELECT COUNT(*) AS n FROM ads_inst_search WHERE lng IS NOT NULL")["n"],
        },
        "warehouse": query(
            "SELECT table_schema AS db, table_name AS name, table_rows AS rows_,"
            " table_comment AS comment FROM information_schema.tables"
            " WHERE table_schema='hospital' ORDER BY table_name"),
        "pipeline": [
            {"step": 1, "name": "数据采集", "tool": "公开渠道 / 26 类来源",
             "desc": "整合北京市卫健委公开数据、医疗机构名录、重点专科公示名单、协作网络名单等多源文件（去重后 70 个源文件）。"},
            {"step": 2, "name": "数据治理", "tool": "etl/govern_master.py",
             "desc": "机构去重合并、办别归属判定（国有+集体全资→公立）、机构类型细分、机构更名纠偏。"},
            {"step": 3, "name": "资源整合", "tool": "etl/integrate_networks.py",
             "desc": "接入儿科医联体、卒中中心、危重新生儿/孕产妇救治中心等协作网络名单，形成网络维度。"},
            {"step": 4, "name": "数据入湖", "tool": "HDFS 3.3.6 · etl/upload_to_hdfs.py",
             "desc": "治理后 CSV 与用户行为日志统一上传至 HDFS /hospital/ods/raw，作为后续分析数据的唯一来源。"},
            {"step": 5, "name": "数仓分层与维度分析", "tool": "Spark 3.5.3 · spark/jobs/",
             "desc": "ODS 原始层 → DWD 明细清洗层 → DWS 五维汇总层（空间/类型等级/科室/协作网络/时间）→ ADS 服务层；ODS/DWD/DWS 以 Parquet 存于 HDFS，仅 ADS 服务层结果落 MySQL。"},
            {"step": 6, "name": "地理编码与距离", "tool": "高德地理编码 / Haversine",
             "desc": "补全机构经纬度（覆盖率 99.98%），用于距离计算、排序与地图散点。"},
            {"step": 7, "name": "索引优化", "tool": "etl/create_indexes.py",
             "desc": "为筛选主表建立复合前缀索引，实测典型多维筛选扫描行数由 9,777 降至 33。"},
            {"step": 8, "name": "服务与可视化", "tool": "Flask + ECharts",
             "desc": "Flask 提供自然语言筛选/条件筛选/维度统计/详情/概览/对比等接口，ECharts 渲染地图与多维分析图表，并可导出零依赖离线单文件。"},
        ],
        "sources": [
            {"name": "北京市卫生健康委员会", "url": "https://wjw.beijing.gov.cn/",
             "desc": "医疗机构名录、重点专科公示、协作网络名单"},
            {"name": "北京市政务数据资源网", "url": "https://data.beijing.gov.cn/",
             "desc": "医疗机构基础信息开放数据"},
            {"name": "高德开放平台", "url": "https://lbs.amap.com/",
             "desc": "地理编码与周边配套（地铁站/停车场）POI 查询"},
        ],
        "updated_at": "2026-09-20",
        "update_log": [
            {"date": "2026-09-08", "desc": "快照数据更新（9,789 家机构）；修正机构更名与别名映射"},
            {"date": "2026-09-11", "desc": "新增智能导诊、多维分析、详情抽屉、机构对比、运营后台模块（导诊模块已于 2026-09-20 下线）"},
            {"date": "2026-09-17", "desc": "多维分析数据联网完善：办别与等级在线核实（公立 3,085 / 民营 5,323 / 未标注 1,381）；352 家等级缺失经核实确为数据边界"},
            {"date": "2026-09-18", "desc": "信息架构重构为七视图；新增 Vue 3 + Flask 前后端分离形态（/spa/），与零依赖离线单文件并存"},
            {"date": "2026-09-20", "desc": "「就医决策 / 智能导诊」下线，重构为「自然语言智能筛选」：新增 web/nlq.py（条件解析 + 真实数据查询 + 维度统计）与 /api/nlq/* 、/api/statistics/* 接口；AI 定位收敛为机构数据筛选助手"},
        ],
    })


# ==============================================================================
#  API：自然语言智能筛选（项目主线）
# ==============================================================================
# 设计要点（答辩必答）：
#   ① 规则优先：web/nlq.py 用词表 + 正则把中文转成结构化条件，完全离线、可复现。
#   ② 大模型只兜底：规则零命中时才问 Agnes，且提示词里写死"只输出条件，
#      不许输出机构名与数字"，从设计上堵死幻觉。
#   ③ 真实数据：条件最终编译成**参数化 SQL** 打到 MySQL 的 ads_inst_search，
#      所有机构名称与统计数字都来自查询结果，AI 不产生任何数字。
#   ④ 用户可改：解析出的条件在前端是可增删的卡片，用户确认后才真正查询。


def _dept_dict():
    """取库里真实存在的科室名，用于识别"骨科相关机构"这类查询（真实科室表，非疾病库）。"""
    try:
        rows = query("SELECT DISTINCT dept_name FROM dwd_dept_relation_clean"
                     " WHERE dept_name IS NOT NULL AND dept_name <> ''")
        return sorted(r["dept_name"] for r in rows)
    except Exception:
        return []


def _merge_llm_conditions(rule_cond, llm_cond):
    """把模型给出的条件并入规则结果：规则已识别的字段优先（规则是确定性的）。"""
    merged = dict(rule_cond or {})
    for key in ("district", "level", "category", "ownership", "source", "dept",
                "level_min", "kw", "_sort"):
        if merged.get(key):
            continue
        val = (llm_cond or {}).get(key) or (llm_cond or {}).get(key.lstrip("_"))
        if not val:
            continue
        if isinstance(val, list):
            val = [str(v).strip() for v in val if str(v).strip()]
            if not val:
                continue
        merged[key] = val
    return merged


def _try_llm_parse(text, rule_result):
    """规则零命中时的长尾兜底。任何异常都吞掉——兜底绝不能拖垮主流程。"""
    if not (AI_LLM_ENABLED and AI_API_KEY):
        return None, "llm_disabled"
    if rule_result.get("applied"):
        return None, "rule_hit"
    try:
        cond = _llm_json(AI_PARSE_PROMPT + text, "parse", text)
    except LLMRateLimited:
        return None, "llm_rate_limited"
    except Exception as e:
        return None, "llm_error:" + str(e)[:60]
    if cond.get("unsupported"):
        return None, "llm_unsupported"
    return cond, "ok"


@app.route("/api/nlq/parse", methods=["GET", "POST"])
def api_nlq_parse():
    """自然语言 → 结构化筛选条件（只做理解，不查数据）。

    入参：?q=... （GET）或 {"q": "..."}（POST JSON）
    返回：{ok, intent, conditions, applied[], unmatched[], engine, message, notice}
    """
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        text = (body.get("q") or "").strip()
    else:
        text = (request.args.get("q") or "").strip()
    if not text:
        return jsonify({"ok": False, "reason": "empty",
                        "message": "请输入您想查找的机构条件。"})
    res = nlq.parse(text, dept_names=_dept_dict())
    if res["intent"] != "unsupported":
        llm_cond, why = _try_llm_parse(text, res)
        if llm_cond:
            res["conditions"] = _merge_llm_conditions(res["conditions"], llm_cond)
            res["applied"] = nlq.describe(res["conditions"])
            res["engine"] = "llm"
        else:
            res["llm"] = why
    return jsonify(res)


def _nlq_base(body):
    """距离基准点：(lng, lat) 或 None（None = 按天安门计算，前端标注为"距市中心"）。

    口径与 /api/institutions 完全一致——同一个基准点、同一套 Haversine 公式，
    这样"自然语言筛选出的距离"和"机构查询里的距离"不会对不上。
    """
    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    lng = num(body.get("lng", request.args.get("lng")))
    lat = num(body.get("lat", request.args.get("lat")))
    if lng is None or lat is None:
        return None
    return (lng, lat)


def _nlq_execute(parsed, text="", base=None):
    """条件 → 真实数据（筛选清单 或 维度统计）。parsed 是 nlq.parse 的产物。"""
    if parsed.get("intent") == "unsupported":
        return {"ok": False, "intent": "unsupported", "message": parsed.get("message"),
                "conditions": {}, "applied": [],
                "data_source": _data_source_note()}
    cond = dict(parsed.get("conditions") or {})
    cn = dict(parsed.get("conditions") or {})
    try:
        if parsed.get("intent") == "stats":
            stats = nlq.run_stats(query, cond, parsed.get("dimension") or "district")
            return {"ok": True, "intent": "stats", "conditions": cond,
                    "applied": parsed.get("applied") or nlq.describe(cond),
                    "dimension": stats["dimension"], "dimension_label": stats["label"],
                    "chart": stats["chart"], "rows": stats["rows"],
                    "summary": nlq.summarize_stats(cond, stats),
                    "total": sum(r["cnt"] for r in stats["rows"]),
                    "data_source": _data_source_note()}
        page = max(1, int(cn.pop("_page", 1) or 1))
        size = min(100, max(1, int(cn.pop("_page_size", 20) or 20)))
        data = nlq.run_filter(query, cn, page=page, page_size=size, base=base)
        return {"ok": True, "intent": "filter", "conditions": cn,
                "applied": parsed.get("applied") or nlq.describe(cn),
                "total": data["total"], "page": data["page"], "page_size": data["page_size"],
                "sort": data["sort"], "base": data.get("base"), "items": data["items"],
                "summary": nlq.summarize_filter(cn, data),
                "stats": _result_overview(cn),
                "data_source": _data_source_note()}
    except Exception as e:
        return {"ok": False, "intent": "error",
                "message": "查询失败：" + str(e)[:160],
                "conditions": cond, "applied": parsed.get("applied") or [],
                "data_source": _data_source_note()}


def _result_overview(cond):
    """筛选结果的小统计（总数 / 三级 / 二级 / 公立 / 民营 / 含坐标）。"""
    try:
        where, params = nlq.build_where(cond)
        row = query(
            "SELECT COUNT(*) AS total,"
            " SUM(CASE WHEN level_norm='三级' THEN 1 ELSE 0 END) AS level3,"
            " SUM(CASE WHEN level_norm='二级' THEN 1 ELSE 0 END) AS level2,"
            " SUM(CASE WHEN ownership='公立' THEN 1 ELSE 0 END) AS public_cnt,"
            " SUM(CASE WHEN ownership='民营' THEN 1 ELSE 0 END) AS private_cnt,"
            " SUM(CASE WHEN lng IS NOT NULL AND lat IS NOT NULL THEN 1 ELSE 0 END) AS coord_ok"
            " FROM ads_inst_search t WHERE " + where, params, one=True)
        return {k: int(v or 0) for k, v in (row or {}).items()}
    except Exception:
        return {}


def _data_source_note():
    """对外展示的数据来源说明——保证用户随时能看到「这些数字是哪来的」。"""
    batch = ""
    total = 0
    files = 0
    try:
        row = query("SELECT CAST(MAX(batch_date) AS CHAR) AS d FROM ads_etl_snapshot", one=True)
        batch = (row or {}).get("d") or ""
        total = query("SELECT COUNT(*) AS n FROM ads_inst_search", one=True)["n"]
        files = query("SELECT COUNT(*) AS n FROM (SELECT source_files FROM ads_inst_search"
                      " WHERE source_files <> '' GROUP BY source_files) x", one=True)["n"]
    except Exception:
        pass
    return {
        "database": "MySQL hospital 库 · ads_inst_search（由 Spark 数仓 ADS 层写入）",
        "institutions": total,
        "batch_date": batch,
        "source_files": files,
        "detail": ("原始数据来自北京市卫健委、市 / 区医保局、各区卫健委公开数据及社区"
                   "卫生服务机构名录等多源材料，经 HDFS 入湖 → Spark 清洗整合 → "
                   "ADS 层落库 MySQL。"),
        "note": nlq.AI_SCOPE_NOTE,
    }


@app.route("/api/nlq/query", methods=["GET", "POST"])
def api_nlq_query():
    """自然语言 → 解析 → 真实数据查询（项目主线接口，一站到底）。

    POST {"q": "帮我找朝阳区三级公立医院"}
    POST {"conditions": {...}}          # 条件筛选 Tab：结构化条件直接查询
    可选 {"lng": 116.40, "lat": 39.91}  # 距离基准点；缺省按天安门计算（标注为"距市中心"）
    返回：筛选结果（含统计概览）或维度统计（含图表数据），以及模板生成的中文说明。
    """
    body = (request.get_json(silent=True) or {}) if request.method == "POST" else {}
    text = (body.get("q") or request.args.get("q") or "").strip()
    conditions = body.get("conditions") if isinstance(body.get("conditions"), dict) else None
    if not text and not conditions:
        return jsonify({"ok": False, "reason": "empty",
                        "message": "请先描述您想查找的机构条件。"})
    if conditions is not None:
        parsed = {"ok": True, "intent": "stats" if conditions.get("dimension") else "filter",
                  "conditions": conditions, "districts": conditions.get("district") or [],
                  "applied": nlq.describe(conditions), "unmatched": [], "message": ""}
        if parsed["intent"] == "stats":
            parsed["dimension"] = conditions["dimension"]
    else:
        parsed = nlq.parse(text, dept_names=_dept_dict())
    res = _nlq_execute(parsed, text, base=_nlq_base(body))
    if text:
        res["parsed"] = {"intent": parsed.get("intent"),
                         "dimension": parsed.get("dimension"),
                         "engine": parsed.get("engine", "rule"),
                         "unmatched": parsed.get("unmatched") or [],
                         "notice": parsed.get("notice"),
                         "districts": parsed.get("districts") or []}
    return jsonify(res)


@app.route("/api/nlq/ask")
def api_nlq_ask():
    """为本次查询结果生成一段中文说明（可选增强）。

    GET /api/nlq/ask?facts=...&local=...
    三级降级：Agnes 润色 → 命中缓存 → 调用方回传的本地模板。
    本地模板由 nlq.summarize_* 在服务端生成，因此**断网也一定有说明可看**。
    """
    facts = (request.args.get("facts") or "").strip()[:4000]
    local = (request.args.get("local") or "").strip()[:1200]
    if not facts:
        return jsonify({"ok": False, "reason": "empty", "summary": local})
    if not (AI_LLM_ENABLED and AI_API_KEY):
        return jsonify({"ok": True, "engine": "local", "summary": local})
    ck = AI_MODEL + "|nqsummary|" + hashlib.sha1(facts.encode("utf-8")).hexdigest()[:24]
    if ck in _LLM_CACHE:
        return jsonify({"ok": True, "engine": "llm", "model": AI_MODEL,
                        "summary": _LLM_CACHE[ck], "cached": True})
    cached = _ai_cache_get(ck)
    if cached is not None:
        _LLM_CACHE[ck] = cached
        return jsonify({"ok": True, "engine": "llm", "model": AI_MODEL,
                        "summary": cached, "cached": True})
    try:
        txt = (_llm_chat([{"role": "user", "content": SUMMARY_PROMPT + facts}],
                         temperature=0.2) or "").strip()
        if not txt:
            raise ValueError("模型返回空")
        _LLM_CACHE[ck] = txt
        _ai_cache_put(ck, "nqsummary", txt)
        return jsonify({"ok": True, "engine": "llm", "model": AI_MODEL, "summary": txt})
    except LLMRateLimited:
        return jsonify({"ok": True, "engine": "local", "summary": local,
                        "note": "Agnes 免费额度限流（约 1 次/30 秒），已用本地模板生成"})
    except Exception as e:
        return jsonify({"ok": True, "engine": "local", "summary": local,
                        "note": "大模型不可用，已用本地模板生成：" + str(e)[:80]})


@app.route("/api/statistics/<dim>")
def api_statistics(dim):
    """按维度取真实统计结果（ECharts 直接消费）。

    dim ∈ overview | district | category | level | ownership | source | quality
    可选筛选：district / level / category / ownership / source（逗号分隔多值）
    """
    if dim == "overview":
        row = query(
            "SELECT COUNT(*) AS total,"
            " COUNT(DISTINCT district) AS districts,"
            " COUNT(DISTINCT category_norm) AS categories,"
            " SUM(CASE WHEN category_norm='医院' THEN 1 ELSE 0 END) AS hospital,"
            " SUM(CASE WHEN level_norm='三级' THEN 1 ELSE 0 END) AS level3,"
            " SUM(CASE WHEN level_norm='二级' THEN 1 ELSE 0 END) AS level2,"
            " SUM(CASE WHEN level_norm='一级' THEN 1 ELSE 0 END) AS level1,"
            " SUM(CASE WHEN ownership='公立' THEN 1 ELSE 0 END) AS public_cnt,"
            " SUM(CASE WHEN ownership='民营' THEN 1 ELSE 0 END) AS private_cnt,"
            " SUM(CASE WHEN lng IS NOT NULL AND lat IS NOT NULL THEN 1 ELSE 0 END) AS coord_ok,"
            " SUM(CASE WHEN addr IS NOT NULL AND addr<>'' THEN 1 ELSE 0 END) AS addr_ok,"
            " SUM(CASE WHEN source_files<>'' THEN 1 ELSE 0 END) AS source_ok,"
            " SUM(CASE WHEN src_count_int>=2 THEN 1 ELSE 0 END) AS multi_source"
            " FROM ads_inst_search t", one=True)
        return jsonify({"ok": True, "dimension": "overview",
                        "stats": {k: int(v or 0) for k, v in (row or {}).items()},
                        "data_source": _data_source_note()})
    if dim == "quality":
        total = query("SELECT COUNT(*) AS n FROM ads_inst_search", one=True)["n"]
        fields = [
            ("district", "行政区", "district IS NOT NULL AND district<>''"),
            ("addr", "地址", "addr IS NOT NULL AND addr<>''"),
            ("phone", "联系电话", "phone IS NOT NULL AND phone<>''"),
            ("lng", "坐标", "lng IS NOT NULL AND lat IS NOT NULL"),
            ("level", "医院等级", "level_norm <> '不适用医院分级'"),
            ("category", "机构类型", "category_norm IS NOT NULL AND category_norm<>''"),
            ("ownership", "所有制", "ownership IS NOT NULL AND ownership<>''"),
            ("source", "数据来源", "source_files IS NOT NULL AND source_files<>''"),
        ]
        rows = []
        for key, label, expr in fields:
            n = query("SELECT COUNT(*) AS n FROM ads_inst_search WHERE " + expr, one=True)["n"]
            rows.append({"field": key, "label": label, "nonnull": n,
                         "pct": round(n * 100.0 / total, 1) if total else 0})
        return jsonify({"ok": True, "dimension": "quality", "total": total,
                        "fields": rows, "data_source": _data_source_note()})
    if dim not in ("district", "category", "level", "ownership", "source"):
        return jsonify({"ok": False, "reason": "unknown_dimension",
                        "hint": "可用维度：overview / district / category / level /"
                                " ownership / source / quality"}), 400
    cond = {}
    for key in ("district", "level", "category", "ownership", "source"):
        raw = (request.args.get(key) or "").strip()
        if raw:
            cond[key] = [x.strip() for x in raw.split(",") if x.strip()]
    if "level_min" in request.args:
        try:
            cond["level_min"] = int(request.args.get("level_min"))
        except ValueError:
            pass
    try:
        stats = nlq.run_stats(query, cond, dim)
    except Exception as e:
        return jsonify({"ok": False, "message": "统计失败：" + str(e)[:160]}), 500
    stats["ok"] = True
    stats["summary"] = nlq.summarize_stats(cond, stats)
    stats["data_source"] = _data_source_note()
    return jsonify(stats)


@app.route("/api/nlq/lexicon")
def api_nlq_lexicon():
    """词表导出：前端（尤其离线单文件形态）据此与后端保持同源，避免手抄漂移。"""
    return jsonify(nlq.export_lexicon())



if __name__ == "__main__":
    # macOS 端口 5000 常被 AirPlay Receiver 占用，默认使用 5001
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False, threaded=True)
