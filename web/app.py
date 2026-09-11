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
    # 多轮对话：extra 为前几轮已确认的补充信息（如"伴发热""3天""老年人"），
    # 只参与科室匹配，不改变对外回显的 query（保持对话可追溯）。
    extra = (request.args.get("extra") or "").strip()
    match_text = q + (" " + extra if extra else "")
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
        if kw and kw in match_text:
            old = matched.get(dept)
            if old is None or w > old[0]:
                matched[dept] = (w, emg)
    for kw, dept, w, emg in pairs:      # 直接输入科室名也能命中
        if dept in match_text and dept not in matched:
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
            key_bonus = 0.05 if r["has_key"] in (1, "1", True) else 0.0
            score = min(1.0, score + key_bonus)
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
                # 推荐理由可视化：把加权评分的每一项摊开给用户看（可解释，非黑箱）
                "reason_detail": [
                    {"label": "医院等级", "value": r["level_norm"] or "未知",
                     "weight": 0.5, "score": round(level_c, 3),
                     "desc": "等级越高得分越高（三级=满分）"},
                    {"label": "距离", "weight": 0.3, "score": round(dist_c, 3),
                     "value": ("%.1f km" % dist) if dist is not None else "无坐标",
                     "desc": "基于 Haversine 球面距离，越近得分越高"},
                    {"label": "科室匹配", "weight": 0.2, "score": round(dept_c, 3),
                     "value": "、".join(hit) or "—",
                     "desc": "命中科室权重之和 / 全部候选科室权重之和"},
                ] + ([{"label": "重点专科加成", "weight": 0.05, "score": key_bonus,
                       "value": "含重点专科", "desc": "该院该科室为权威认定重点专科"}] if key_bonus else []),
                "reason": _triage_reason(hit, r["level"], dist, r["has_key"]),
            })

    # 急诊优先：命中科室含急诊的排前
    results.sort(key=lambda x: (not any(matched[d][1] for d in x["matched_depts"]),
                                -x["score"]))
    results = results[:top_n]
    return jsonify({
        "ok": True,
        "query": q,
        "extra": extra,
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


# ==============================================================================
# 增强模块：医院详情（联系方式/挂号入口/周边配套/实时状态）+ 对比 + 行为埋点 + 运营后台
# ==============================================================================
# 设计原则（与智能导诊一致）：
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


def _mock_status(inst_id, level):
    """就诊实时状态（**演示模拟数据**，非真实候诊信息）。

    以机构 id 做确定性散列，保证同一医院每次显示一致（不像随机数那样跳变，
    答辩演示时可复现）；三级医院整体偏繁忙，符合常识直觉。
    """
    h = int(hashlib.md5(str(inst_id).encode("utf-8")).hexdigest(), 16)
    labels = ["空闲", "较少", "中等", "较多", "繁忙"]
    bias = {"三级": 2, "二级": 1, "一级": 0}.get(level, -1)
    idx = min(4, max(0, (h % 5) + bias - 1))
    wait = [5, 12, 20, 35, 55][idx]
    slots = ["上午号源充足", "上午偏紧、下午充足", "当日号源偏紧", "当日号源紧张", "当日号源已满"]
    return {
        "simulated": True,
        "level": labels[idx],
        "level_index": idx,
        "queue_label": labels[idx],
        "wait_min": wait,
        "slots": slots[idx],
        "note": "演示模拟数据 · 非医院实时候诊信息",
    }


def _consult_links(r):
    """就诊入口链接：114 统一平台 / 电话 / 官网 / 导航。

    只给真实可用的入口，不伪造深度链接（114 平台为 JS 单页应用，
    不存在可构造的按医院直达 URL，硬拼会得到死链）。
    """
    lng, lat = _safe_float(r.get("lng")), _safe_float(r.get("lat"))
    nav = ""
    if lng is not None and lat is not None:
        nav = ("https://uri.amap.com/marker?position=%.6f,%.6f&name=%s&src=hospital-dashboard"
               "&coordinate=gaode&callnative=1" % (lng, lat, urllib.parse.quote(r.get("name") or "医院")))
    phone = (r.get("phone") or "").strip()
    return {
        "guahao_114": GUAHao_114,
        "guahao_114_tel": "010-114",
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
            "category_sub": r.get("category_sub") or "",
            "ownership": r.get("ownership") or "", "ownership_basis": r.get("ownership_basis") or "",
            "grade_scope": r.get("grade_scope") or "",
            "dept_count": r.get("dept_count") or 0,
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
        "status": _mock_status(r["id"], r["level_norm"]),
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
    ("municipal_specialty_count", "市级重点专科"), ("dept_count", "科室数量"),
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
    """运营后台：① 真实行为统计（埋点累积） ② 资源热度（源自 9,789 家真实数据）。

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
        "top_triage": top("triage", 10),
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
AI_ADVICE_RULES = (
    "你是北京市就医助手。请基于用户给出的【该机构的真实数据】，写一段 80~120 字的就医提示。\n"
    "硬性要求：\n"
    "① 只能引用给定的真实信息（等级、区域、重点专科名称、协作网络、类型），"
    "不得添加任何未给出的信息；\n"
    "② 严禁编造医生姓名、职称、出诊时间、号源数量、价格、治愈率或任何具体数字；\n"
    "③ 严禁使用「全国第一」「最好的医院」等无法核实的绝对化表述；\n"
    "④ 语气客观，最后用一句提示用户「具体号源与出诊信息请以 114 平台及医院官方公布为准」；\n"
    "⑤ 只输出这段文字，不要标题、不要 Markdown、不要 JSON。\n"
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
                        "advice": txt.strip(), "constraint": "仅基于真实字段生成，禁止编造医生与数字"})
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
            "triage_dict": one("SELECT COUNT(*) AS n FROM dim_disease_dept")["n"],
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
            {"step": 4, "name": "数仓分层 ETL", "tool": "Spark 3.5.3 · spark/etl_hospital.py",
             "desc": "ODS 原始层 → DWD 明细清洗层 → DWS 汇总层 → ADS 应用层，共四层建模，Spark SQL 完成清洗、关联、聚合。"},
            {"step": 5, "name": "地理编码与距离", "tool": "高德地理编码 / Haversine",
             "desc": "补全机构经纬度（覆盖率 99.98%），用于距离计算、排序与地图散点。"},
            {"step": 6, "name": "索引优化", "tool": "etl/create_indexes.py",
             "desc": "为筛选主表建立复合前缀索引，实测典型多维筛选扫描行数由 9,777 降至 33。"},
            {"step": 7, "name": "服务与可视化", "tool": "Flask + ECharts",
             "desc": "Flask 提供筛选/排序/详情/导诊接口，ECharts 渲染地图与多维分析图表，并可导出零依赖离线单文件。"},
        ],
        "sources": [
            {"name": "北京市卫生健康委员会", "url": "https://wjw.beijing.gov.cn/",
             "desc": "医疗机构名录、重点专科公示、协作网络名单"},
            {"name": "北京市预约挂号统一平台（114）", "url": GUAHao_114,
             "desc": "预约挂号官方入口（仅做链接跳转，不抓取号源数据）"},
            {"name": "北京市政务数据资源网", "url": "https://data.beijing.gov.cn/",
             "desc": "医疗机构基础信息开放数据"},
            {"name": "高德开放平台", "url": "https://lbs.amap.com/",
             "desc": "地理编码与周边配套（地铁站/停车场）POI 查询"},
        ],
        "updated_at": "2026-09-08",
        "update_log": [
            {"date": "2026-09-08", "desc": "快照数据更新（9,789 家机构）；修正机构更名与别名映射"},
            {"date": "2026-09-11", "desc": "新增智能导诊、多维分析、详情抽屉、机构对比、运营后台模块"},
        ],
    })


if __name__ == "__main__":
    # macOS 端口 5000 常被 AirPlay Receiver 占用，默认使用 5001
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False, threaded=True)
