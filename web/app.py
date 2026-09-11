# -*- coding: utf-8 -*-
"""
北京市医院医疗资源整合与多维筛选可视化系统 —— Flask API
=========================================================
数据源：MySQL hospital 库 ADS 层（由 spark/etl_hospital.py 生成）
  - ads_inst_search        筛选排序主表（9,789 家机构）
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
      net       协作网络（ped_core/ped_member/stroke/neonatal/maternal）
      lng/lat   参考点坐标（默认天安门），用于距离计算与排序
      sort      排序策略：distance | level | depts | score（默认 score）
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
        "SELECT t.id, t.name, t.district, t.category_norm AS category, t.level_norm AS level,"
        " t.level_sub, t.addr, t.phone, t.key_depts,"
        " t.category_sub, t.ownership, t.feature, t.feature_level,"
        " t.net_pediatric, t.net_stroke, t.net_neonatal, t.net_maternal,"
        " t.lng, t.lat, t.coord_precision, t.dept_count, t.key_specialty_count,"
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
        "SELECT id, name, district, category, category_norm, category_sub, level, level_sub, level_norm,"
        " grade_scope, ownership, ownership_basis, feature, feature_level,"
        " addr, phone, postal, key_depts,"
        " net_pediatric, net_stroke, net_neonatal, net_maternal,"
        " lng, lat, coord_formatted, coord_precision, coord_source,"
        " src_count_int, source_files, dept_count, key_specialty_count"
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

    统计口径（数据治理要点）：全表 9789 家机构中仅约 1287 家属"参加医院等级评审"
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


# ============== 大模型（Agnes AI）配置与调用 ==============
# 设计要点：前端 JS 规则引擎 + 本地疾病-科室知识库是**默认路径**，纯离线、零依赖、
# 可复现，答辩现场绝不受网络与额度影响；大模型只在「本地零命中」时兜底，
# 用于口语长尾句式与知识库未收录的病情描述。
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
# 交互式导诊必须用快模型，慢模型只适合离线批处理。可用 AI_MODEL 覆盖。
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
    # 故只做一次极短重试后快速失败并明确告知——不把用户挂在「导诊中…」干等。
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
AI_PARSE_PROMPT = (
    "你是北京市医疗机构检索系统的查询解析器，把用户口语转成 JSON 筛选条件。\n"
    "可选字段（用不到的省略）：district(行政区，须带\"区\"字，如朝阳区)、"
    "level(三级/二级/一级/未定级)、"
    "category(医院/诊所/门诊部/妇幼保健/体检中心/急救中心/其他机构)、"
    "dept(标准科室名，必须取自下列之一：" + "、".join(STD_DEPTS) + ")、"
    "sort(score/distance/level/depts/name)、kw(机构名关键词)。\n"
    "只输出 JSON 本体，不要解释、不要代码块。用户查询："
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


@app.route("/api/ai/warm")
def api_ai_warm():
    """预热大模型缓存：演示/答辩前跑一次，把常用问法固化到缓存，现场零等待。

    用法：/api/ai/warm?queries=手抖还瘦了很多|眼睛干涩发痒&kind=triage
    免费额度约 1 次/30 秒，故每次调用间自动 sleep，避免连续 429。
    返回每个问法的预热结果（ok / cached / rate_limited）。
    """
    raw = (request.args.get("queries") or "").strip()
    kind = (request.args.get("kind") or "triage").strip()
    if not raw:
        return jsonify({"ok": False, "reason": "empty"})
    if not (AI_LLM_ENABLED and AI_API_KEY):
        return jsonify({"ok": False, "reason": "llm_disabled"})
    queries = [x.strip() for x in raw.split("|") if x.strip()][:20]
    local_pairs = load_triage_map()
    out = []
    for i, q in enumerate(queries):
        ck = AI_MODEL + "|" + kind + "|" + q
        if ck in _LLM_CACHE or _ai_cache_get(ck) is not None:
            out.append({"q": q, "status": "cached"})
            continue
        # 本地知识库已能命中的问法不必消耗额度（现场本来就走的离线链路）
        if kind == "triage" and any(kw and kw in q for kw, _d, _w, _e in local_pairs):
            out.append({"q": q, "status": "skipped_local"})
            continue
        if i:                       # 免费额度约 1 次/30 秒，串行预热必须留足间隔
            time.sleep(30)
        try:
            if kind == "triage":
                wl = _dept_whitelist()
                picked, note = _llm_map_dept(q, wl)
                out.append({"q": q, "status": "ok", "depts": picked, "note": note})
            else:
                cond = _llm_json(AI_PARSE_PROMPT + q, "parse", q)
                out.append({"q": q, "status": "ok", "conditions": cond})
        except LLMRateLimited:
            out.append({"q": q, "status": "rate_limited"})
        except Exception as e:
            out.append({"q": q, "status": "error", "detail": str(e)[:120]})
    return jsonify({"ok": True, "kind": kind, "total": len(queries), "results": out})


# ============== 智能导诊（疾病/症状 → 科室 → 医院）==============
import csv as _csv


def load_triage_map():
    """从 dim_disease_dept 维度表加载导诊词典；表不存在时回退到本地 CSV。

    注意：每次请求实时读取，不使用模块级缓存——避免「改库后不重启就失效」的
    隐性 bug（演示/答辩时新增症状词后立即生效，无需重启服务）。
    """
    rows = []
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT keyword, dept_name, weight, is_emergency "
                "FROM dim_disease_dept")
            rows = [(r["keyword"], r["dept_name"], float(r["weight"]),
                     int(r["is_emergency"])) for r in cur.fetchall()]
    except Exception:
        rows = []
    if not rows:
        csv_path = os.path.join(os.path.dirname(__file__), "..",
                                "data", "processed", "disease_dept_map.csv")
        if os.path.exists(csv_path):
            with open(csv_path, encoding="utf-8") as f:
                for r in _csv.DictReader(f):
                    rows.append((r["keyword"], r["dept_name"],
                                 float(r["weight"]), int(r["is_emergency"])))
    return rows


def haversine(lng1, lat1, lng2, lat2):
    """两点间距离（km）"""
    rad = 3.141592653589793 / 180.0
    dlat = (lat2 - lat1) * rad
    dlng = (lng2 - lng1) * rad
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlng / 2) ** 2)
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


def _dept_whitelist():
    """取库里真实存在的标准科室名，作为大模型的候选约束。

    必须用真实取值而非写死清单：若模型返回库里没有的科室（如"神经外科"），
    join 结果会是 0 家，用户会误以为系统坏了。实测库中为 29 个科室。
    """
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT DISTINCT dept_name FROM dwd_dept_relation_clean")
        return sorted(r["dept_name"] for r in cur.fetchall() if r["dept_name"])


TRIAGE_LLM_RULES = (
    "你是北京市就医导诊助手。请把用户口语化的病情/症状，映射到【标准科室清单】中"
    "最相关的一个或多个科室。\n"
    "硬性要求：\n"
    "① 科室名只能从清单中原样选取，不得改写、不得自创、不得返回清单外名称；\n"
    "② 最多 3 个科室，按相关度从高到低排列；\n"
    "③ 属急危重症（胸痛、卒中、大出血、昏迷、呼吸困难、严重外伤、抽搐等）时，"
    "必须包含\"急诊科\"；\n"
    "④ 只输出 JSON 本体，格式 {\"depts\": [\"科室名\"], \"reason\": \"一句话依据\"}，"
    "不要解释、不要代码块；无法判断时 depts 返回空数组。\n"
    "【标准科室清单】"
)


def _llm_map_dept(q, whitelist, timeout=None):
    """大模型兜底：口语病情 → 标准科室。返回 (科室列表, 依据)。"""
    prompt = TRIAGE_LLM_RULES + "、".join(whitelist) + "\n用户描述："
    out = _llm_json(prompt + q, "triage", q, timeout=timeout)
    depts = out.get("depts") or []
    if isinstance(depts, str):
        depts = [depts]
    picked = [d for d in depts if isinstance(d, str) and d in whitelist]
    return picked, str(out.get("reason") or "")


@app.route("/api/triage")
def api_triage():
    """智能导诊：输入病情/疾病文本，推荐具备对应科室的医院。

    参数：q(必填), district(可选), level(可选: 一级/二级/三级),
          top_n(默认10), lng/lat(用户坐标，用于距离排序)
    """
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"ok": False, "reason": "empty"})
    district = (request.args.get("district") or "").strip()
    level = (request.args.get("level") or "").strip()
    try:
        top_n = max(1, min(50, int(request.args.get("top_n", 10))))
    except ValueError:
        top_n = 10
    try:
        ulng = float(request.args.get("lng", DEFAULT_LNG))
        ulat = float(request.args.get("lat", DEFAULT_LAT))
    except ValueError:
        ulng, ulat = DEFAULT_LNG, DEFAULT_LAT

    # 1) 文本 → 命中科室
    pairs = load_triage_map()
    matched = {}        # dept_name -> (weight, is_emergency)
    for kw, dept, w, emg in pairs:
        if kw and kw in q:
            old = matched.get(dept)
            if old is None or w > old[0]:
                matched[dept] = (w, emg)
    for kw, dept, w, emg in pairs:      # 直接输入科室名也能命中
        if dept in q and dept not in matched:
            matched[dept] = (w, emg)

    # 1.5) 本地知识库零命中 → 大模型兜底（用 AI_LLM_ENABLED=0 或 &llm=0 可强制关闭）
    engine, ai_note, llm_attempted = "local", "", False
    if (not matched) and request.args.get("llm", "auto") != "0" \
            and AI_LLM_ENABLED and AI_API_KEY:
        llm_attempted = True
        try:
            wl = _dept_whitelist()
            picked, ai_note = _llm_map_dept(q, wl)
            for d in picked:
                if d not in matched:
                    # 知识库未收录的口语病情，权重给 0.8（低于精确词条，高于模糊词条）
                    matched[d] = (0.8, d == "急诊科")
            if matched:
                engine = "llm"
        except LLMRateLimited:
            ai_note = "Agnes 免费额度限流，稍后重试即可（本地知识库不受影响）"
        except Exception as e:
            ai_note = "大模型兜底未生效：" + str(e)[:80]

    if not matched:
        return jsonify({
            "ok": False, "reason": "no_match",
            "llm_attempted": llm_attempted,
            "llm_note": ai_note,
            "hint": "本地知识库与大模型均未匹配到科室，请换个说法或补充更具体的症状",
            "examples": ["头痛", "骨折", "高血压", "咳嗽", "儿童发烧", "孕检", "牙痛"],
        })

    dept_list = list(matched.keys())
    placeholders = ",".join(["%s"] * len(dept_list))

    # 2) 科室 → 医院（join 联表），聚合该医院命中的科室
    sql = (
        "SELECT s.id, "
        "ANY_VALUE(s.name) AS name, ANY_VALUE(s.district) AS district, "
        "ANY_VALUE(s.level) AS level, ANY_VALUE(s.level_norm) AS level_norm, "
        "ANY_VALUE(s.addr) AS addr, ANY_VALUE(s.phone) AS phone, "
        "ANY_VALUE(s.lng) AS lng, ANY_VALUE(s.lat) AS lat, "
        "ANY_VALUE(s.key_specialty_count) AS key_specialty_count, "
        "GROUP_CONCAT(d.dept_name) AS matched_depts, "
        "MAX(d.is_key_specialty='1') AS has_key "
        "FROM ads_inst_search s "
        "JOIN dwd_dept_relation_clean d ON s.id = d.hospital_id "
        "WHERE d.dept_name IN (" + placeholders + ")"
    )
    args = list(dept_list)
    if district:
        sql += " AND s.district=%s"
        args.append(district)
    if level:
        sql += " AND s.level_norm=%s"
        args.append(level)
    sql += " GROUP BY s.id"

    db = get_db()
    results = []
    with db.cursor() as cur:
        cur.execute(sql, args)
        for r in cur.fetchall():
            try:
                dlng = float(r["lng"]) if r["lng"] is not None else None
                dlat = float(r["lat"]) if r["lat"] is not None else None
            except (TypeError, ValueError):
                dlng = dlat = None
            dist = haversine(ulng, ulat, dlng, dlat) if (dlng and dlat) else None
            md = set((r["matched_depts"] or "").split(","))
            hit = [d for d in dept_list if d in md]
            hit_w = sum(matched[d][0] for d in hit)
            total_w = sum(matched[d][0] for d in dept_list)
            frac = min(1.0, hit_w / total_w) if total_w else 0.0
            lvl = LEVEL_SCORE.get(r["level_norm"], 0.5)
            level_c = 0.5 * (lvl / 3.0)
            dist_c = 0.3 * (1.0 / (1.0 + (dist or 999) / 5.0)) if dist is not None else 0.0
            dept_c = 0.2 * frac
            score = level_c + dist_c + dept_c
            if r["has_key"] in (1, "1", True):
                score = min(1.0, score + 0.05)
            results.append({
                "id": r["id"], "name": r["name"], "district": r["district"],
                "level": r["level"], "addr": r["addr"], "phone": r["phone"],
                "distance_km": round(dist, 1) if dist is not None else None,
                "matched_depts": hit,
                "is_key_specialty": bool(r["has_key"] in (1, "1", True)),
                "score": round(score, 4),
                "score_break": {
                    "level": round(level_c, 3), "distance": round(dist_c, 3),
                    "dept": round(dept_c, 3),
                },
                "reason": _triage_reason(hit, r["level"], dist, r["has_key"]),
            })

    # 急诊优先：命中科室含急诊的排前
    results.sort(key=lambda x: (not any(matched[d][1] for d in x["matched_depts"]),
                                -x["score"]))
    results = results[:top_n]
    return jsonify({
        "ok": True,
        "query": q,
        "engine": engine,
        "model": AI_MODEL if engine == "llm" else None,
        "ai_note": ai_note,
        "matched_depts": [
            {"dept": d, "weight": matched[d][0], "emergency": bool(matched[d][1]),
             "source": engine}
            for d in dept_list
        ],
        "count": len(results),
        "hospitals": results,
    })


def _triage_reason(hit_depts, level, dist, has_key):
    parts = ["命中科室：" + "、".join(hit_depts)]
    if level:
        parts.append(level)
    if dist is not None:
        parts.append("距您约 %.1f km" % dist)
    if has_key in (1, "1", True):
        parts.append("含重点专科")
    return "；".join(parts)


if __name__ == "__main__":
    # macOS 端口 5000 常被 AirPlay Receiver 占用，默认使用 5001
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False, threaded=True)
