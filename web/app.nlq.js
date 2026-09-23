// ============================================================================
//  自然语言智能筛选 —— 单文件形态的离线引擎
// ----------------------------------------------------------------------------
//  为什么需要这个文件：
//    单文件形态（dashboard_offline.html）要能"打开即用、发链接即用"，不能依赖
//    服务器。所以把后端的自然语言解析 + 条件筛选 + 维度统计完整地在前端实现一份，
//    数据来自内嵌快照（9,684 家机构，字段与 MySQL ads_inst_search 同源）。
//
//  一致性纪律（改动前必读）：
//    本文件是 web/nlq.py 的等价 JavaScript 实现，逐条对应：
//      · 词表**不在这里写死**，全部来自 window.__NLQ_LEX__（由 etl/export_nlq_lexicon.py
//        从 web/nlq.py 自动导出）。改词表只改 nlq.py，然后重跑导出。
//      · 命中算法（长词优先 → 按长度与位置排序 → 贪心去重叠）与 Python 完全一致
//      · 停止词按长度降序逐条剥离（不是逐字剥离，否则"协和医院"的"和"会被吃掉）
//      · 等级下限先于精确等级识别；排序词先于关键词提取
//      · 医疗边界话术与后端同文
//    改完请跑：python3 etl/verify_offline_nlq.py   （两端解析逐字段比对）
//
//  纪律：本引擎**不产生任何机构名称或统计数字**——它们全部来自快照数据的真实筛选。
// ============================================================================
'use strict';

var NLQ = (function () {
  var LEX = null;

  function init(lex) { LEX = lex; }

  // --------------------------------------------------------------------------
  //  小工具
  // --------------------------------------------------------------------------
  var FULL2HALF = /[\uFF01-\uFF5E]/g;
  function normalize(text) {
    // 全角转半角 + 去所有空白（空格会破坏"社区卫生服务中心"这类多字词匹配）
    var t = String(text == null ? '' : text).replace(FULL2HALF, function (c) {
      return String.fromCharCode(c.charCodeAt(0) - 0xFEE0);
    });
    return t.replace(/\s+/g, '');
  }

  function escapeRe(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  // 与 Python 的 _find_all 等价：长词优先 → 排序 → 贪心占位
  function findAll(text, table) {
    var words = Object.keys(table).sort(function (a, b) { return b.length - a.length; });
    var hits = [];
    words.forEach(function (w) {
      var start = text.indexOf(w);
      while (start >= 0) {
        hits.push({ word: w, start: start, len: w.length });
        start = text.indexOf(w, start + 1);
      }
    });
    hits.sort(function (a, b) { return (b.len - a.len) || (a.start - b.start); });
    var picked = [], occupied = Object.create(null);
    hits.forEach(function (h) {
      for (var i = h.start; i < h.start + h.len; i++) if (occupied[i]) return;
      picked.push(h);
      for (var j = h.start; j < h.start + h.len; j++) occupied[j] = 1;
    });
    picked.sort(function (a, b) { return a.start - b.start; });
    return picked;
  }

  function occupiedSet(spans) {
    var s = Object.create(null);
    spans.forEach(function (sp) { for (var i = sp[0]; i < sp[0] + sp[1]; i++) s[i] = 1; });
    return s;
  }

  function overlaps(occ, start, len) {
    for (var i = start; i < start + len; i++) if (occ[i]) return true;
    return false;
  }

  function mask(text, spans) {
    var chars = text.split('');
    spans.forEach(function (sp) {
      for (var i = sp[0]; i < sp[0] + sp[1] && i < chars.length; i++) chars[i] = '\u0000';
    });
    return chars.join('');
  }

  // --------------------------------------------------------------------------
  //  解析：自然语言 → 结构化筛选条件（对应 nlq.parse）
  // --------------------------------------------------------------------------
  function parse(text, deptNames) {
    var raw = String(text == null ? '' : text).trim();
    var t = normalize(raw);
    var out = {
      ok: true, intent: 'filter', query: raw,
      conditions: {}, districts: [], dimension: null, chart: null,
      applied: [], unmatched: [], engine: 'rule',
      message: '', scope_note: LEX.scope_note
    };
    if (!t) {
      out.ok = false; out.intent = 'unsupported';
      out.message = '请输入您想查找的机构条件。';
      return out;
    }

    var spans = [], cond = {};

    // ---------- 1. 行政区（多值） ----------
    var dTable = {};
    LEX.districts.forEach(function (d) { dTable[d] = d; });
    Object.keys(LEX.district_alias).forEach(function (k) { dTable[k] = LEX.district_alias[k]; });
    var dists = [], seenD = Object.create(null);
    findAll(t, dTable).forEach(function (h) {
      var name = dTable[h.word];
      if (!seenD[name]) { seenD[name] = 1; dists.push(name); }
      spans.push([h.start, h.len]);
    });
    if (dists.length) cond.district = dists;

    // ---------- 2. 等级（下限优先于精确等级） ----------
    var levelMin = null, minSpans = [];
    var mins = LEX.level_min_words.slice().sort(function (a, b) { return b[0].length - a[0].length; });
    for (var mi = 0; mi < mins.length; mi++) {
      var pos = t.indexOf(mins[mi][0]);
      if (pos >= 0) {
        levelMin = mins[mi][1];
        minSpans.push([pos, mins[mi][0].length]);
        spans = spans.concat(minSpans);
        break;
      }
    }
    var minOcc = occupiedSet(minSpans);
    var lTable = {};
    LEX.levels.forEach(function (d) { lTable[d] = d; });
    Object.keys(LEX.level_alias).forEach(function (k) { lTable[k] = LEX.level_alias[k]; });
    var levels = [], seenL = Object.create(null);
    findAll(t, lTable).forEach(function (h) {
      if (overlaps(minOcc, h.start, h.len)) return;
      var name = lTable[h.word];
      if (!seenL[name]) { seenL[name] = 1; levels.push(name); }
      spans.push([h.start, h.len]);
    });
    if (levels.length) cond.level = levels;
    if (levelMin !== null) cond.level_min = levelMin;

    // ---------- 3. 机构类型（长词优先，跳过已被占用的位置） ----------
    var occ1 = occupiedSet(spans);
    var cats = [], seenC = Object.create(null);
    findAll(t, LEX.category_alias).forEach(function (h) {
      if (overlaps(occ1, h.start, h.len)) return;
      var name = LEX.category_alias[h.word];
      if (!seenC[name]) { seenC[name] = 1; cats.push(name); }
      spans.push([h.start, h.len]);
    });
    if (cats.length) cond.category = cats;

    // ---------- 4. 所有制 ----------
    var owns = [], seenO = Object.create(null);
    findAll(t, LEX.ownership_alias).forEach(function (h) {
      var name = LEX.ownership_alias[h.word];
      if (!seenO[name]) { seenO[name] = 1; owns.push(name); }
      spans.push([h.start, h.len]);
    });
    if (owns.length) cond.ownership = owns;

    // ---------- 5. 数据来源（只认"来源类"的具体说法，避免与机构类型抢词） ----------
    var srcs = [];
    LEX.source_rules.forEach(function (rule) {
      var trig = rule.triggers.slice().sort(function (a, b) { return b.length - a.length; });
      for (var i = 0; i < trig.length; i++) {
        var p = t.indexOf(trig[i]);
        if (p < 0) continue;
        if (srcs.indexOf(rule.key) < 0) srcs.push(rule.key);
        spans.push([p, trig[i].length]);
        break;
      }
    });
    if (srcs.length) cond.source = srcs;

    // ---------- 6. 科室（基于真实科室表，不是疾病知识库） ----------
    if (deptNames && deptNames.length) {
      var dt = {};
      deptNames.forEach(function (d) { dt[d] = 1; });
      var dh = findAll(t, dt);
      if (dh.length) {
        cond.dept = dh[0].word;
        spans.push([dh[0].start, dh[0].len]);
      }
    }

    // ---------- 7. 结构性附加条件 ----------
    if (/有地址|有详细地址|地址信息|填了地址/.test(t)) {
      cond.has_addr = true;
      spans.push([t.indexOf('地址'), 2]);
    }
    if (/有坐标|有定位|能在地图|地图上/.test(t)) cond.has_coord = true;
    if (/多院区|多个来源|交叉验证|多源/.test(t)) cond.src_min = 2;

    // ---------- 7.5 排序偏好（必须先于关键词提取） ----------
    var occ2 = occupiedSet(spans);
    for (var si = 0; si < LEX.sort_words.length; si++) {
      var sw = LEX.sort_words[si][0], p2 = t.indexOf(sw);
      if (p2 >= 0 && !overlaps(occ2, p2, sw.length)) {
        cond._sort = LEX.sort_words[si][1];
        spans.push([p2, sw.length]);
        break;
      }
    }

    // ---------- 8. 剩余文本 → 机构名关键词 ----------
    var masked = mask(t, spans);
    masked = masked.replace(/\u0000([和与及或、])\u0000/g, '');
    var rest = masked.split('\u0000').join('');
    LEX.stop_phrases.forEach(function (ph) { rest = rest.split(ph).join(''); });
    // 排序说法是"意图"而不是"机构名"（「按距离从近到远」命中了"从近到远"，却剩下"按距离"）
    (LEX.sort_words || []).forEach(function (sw) { rest = rest.split(sw[0]).join(''); });
    // ① 城市作用域词：剥掉之后什么都不剩才是"整个北京市"这个范围；
    //    只要还剩东西（"北京协和"→"协和"）就原样保留，所以裸"北京"不在 stop_phrases 里。
    var cityScope = LEX.city_scope_words || ['北京市', '北京'];
    var probe = rest;
    cityScope.forEach(function (w) { probe = probe.split(w).join(''); });
    if (!probe) rest = '';
    // ② 纯程度残渣（"大医院"剩下一个"大"）：不是机构名关键词，也不算"没听懂"
    var degreeOnly = LEX.degree_only_chars || '大小好多少远近高低';
    if (rest && rest.length <= 2) {
      var allDegree = true;
      for (var di = 0; di < rest.length; di++) {
        if (degreeOnly.indexOf(rest.charAt(di)) < 0) { allDegree = false; break; }
      }
      if (allDegree) rest = '';
    }
    if (rest.length >= 2 && !/^[0-9]+$/.test(rest)) cond.kw = rest;
    else if (rest.length && !/^[0-9]+$/.test(rest)) out.unmatched.push(rest);

    // ---------- 8.5 数据年份（本数据集没有机构级年份字段，明确告知） ----------
    if (/(19|20)\d{2}\s*年?/.test(t)) {
      out.notice = '当前数据集的机构记录未保留「数据来源年份」字段，因此无法按年份筛选；'
        + '数据来源与批次时效可在「数据整合」与「数据质量」页查看。';
      if (cond.kw && /^(19|20)\d{2}年?$/.test(cond.kw)) delete cond.kw;
    }

    // ---------- 10. 意图判定 ----------
    var hasStructured = !!(dists.length || levels.length || levelMin !== null
      || owns.length || cond.dept);
    var medHits = LEX.medical_words.filter(function (w) { return t.indexOf(w) >= 0; });
    var narrative = LEX.narrative_crowd.some(function (w) { return t.indexOf(w) >= 0; })
      && LEX.narrative_course.some(function (w) { return t.indexOf(w) >= 0; });
    if ((medHits.length || narrative) && !hasStructured) {
      out.intent = 'unsupported';
      out.conditions = {}; out.districts = []; out.applied = [];
      out.medical_hits = (medHits.length ? medHits : ['就诊者叙述']).slice(0, 5);
      out.message = LEX.medical_refusal;
      return out;
    }

    var statsLike = LEX.stats_words.some(function (w) { return t.indexOf(w) >= 0; });
    if (statsLike) {
      var dim = null;
      for (var di = 0; di < LEX.dim_words.length; di++) {
        if (t.indexOf(LEX.dim_words[di][0]) >= 0) { dim = LEX.dim_words[di][1]; break; }
      }
      out.intent = 'stats';
      out.dimension = dim || 'district';
      out.chart = LEX.dim_chart[out.dimension] || 'bar';
    }

    out.conditions = cond;
    out.districts = dists;
    out.applied = describe(cond);
    out.unmatched = out.unmatched.slice(0, 6);
    if (!out.applied.length && out.intent === 'filter') {
      out.message = '暂未识别出明确的机构筛选条件。您可以描述行政区、机构类型、'
        + '医院等级、所有制或数据来源，例如「朝阳区三级公立医院」。';
    }
    return out;
  }

  // 与 nlq.describe 同序、同文
  function describe(cond) {
    var chips = [];
    function add(key, label, values, text) {
      chips.push({ key: key, label: label, values: values, text: text });
    }
    if (cond.district && cond.district.length) add('district', '行政区', cond.district, cond.district.join('、'));
    if (cond.level && cond.level.length) add('level', '医院等级', cond.level, cond.level.join('、'));
    if (cond.level_min != null) {
      var nm = { 3: '三级', 2: '二级', 1: '一级' }[cond.level_min] || '';
      add('level_min', '等级下限', [cond.level_min], nm + '及以上');
    }
    if (cond.category && cond.category.length) add('category', '机构类型', cond.category, cond.category.join('、'));
    if (cond.ownership && cond.ownership.length) add('ownership', '所有制', cond.ownership, cond.ownership.join('、'));
    if (cond.source && cond.source.length) {
      var labels = {};
      LEX.source_rules.forEach(function (r) { labels[r.key] = r.label; });
      add('source', '数据来源', cond.source,
        cond.source.map(function (k) { return labels[k] || k; }).join('、'));
    }
    if (cond.dept) add('dept', '科室', [cond.dept], cond.dept);
    if (cond.has_addr) add('has_addr', '数据完整度', [true], '含地址信息');
    if (cond.has_coord) add('has_coord', '数据完整度', [true], '含坐标');
    if (cond.src_min) add('src_min', '数据来源数', [cond.src_min], '至少 ' + cond.src_min + ' 个来源');
    if (cond.kw) add('kw', '机构名称关键词', [cond.kw], cond.kw);
    if (cond._sort) add('_sort', '排序方式', [cond._sort], LEX.sort_label[cond._sort] || cond._sort);
    return chips;
  }

  // --------------------------------------------------------------------------
  //  条件匹配度（与后端 MATCH_WEIGHTS 同源）
  // --------------------------------------------------------------------------
  function matchScore(inst, cond) {
    var W = LEX.match_weights, hit = 0, total = 0;
    ['district', 'level', 'category', 'ownership'].forEach(function (k) {
      if (!cond[k] || !cond[k].length) return;
      total += W[k];
      var field = { district: 'district', level: 'level', category: 'category',
        ownership: 'ownership' }[k];
      if (cond[k].indexOf(inst[field]) >= 0) hit += W[k];
    });
    if (cond.source && cond.source.length) {
      total += W.source;
      if (cond.source.some(function (key) {
        var rule = null;
        LEX.source_rules.forEach(function (r) { if (r.key === key) rule = r; });
        return rule ? new RegExp(rule.pattern).test(inst.source_files || '') : false;
      })) hit += W.source;
    }
    if (total <= 0) return 1;
    return Math.round((hit / total) * 10000) / 10000;
  }

  // --------------------------------------------------------------------------
  //  筛选（对应 nlq.build_where + run_filter）
  // --------------------------------------------------------------------------
  function matches(inst, cond) {
    if (cond.district && cond.district.length && cond.district.indexOf(inst.district) < 0) return false;
    if (cond.level && cond.level.length && cond.level.indexOf(inst.level) < 0) return false;
    if (cond.level_min != null) {
      var rk = LEX.level_rank[inst.level];
      if (rk == null || rk < cond.level_min) return false;
    }
    if (cond.category && cond.category.length && cond.category.indexOf(inst.category) < 0) return false;
    if (cond.ownership && cond.ownership.length && cond.ownership.indexOf(inst.ownership) < 0) return false;
    if (cond.source && cond.source.length) {
      var okSrc = cond.source.some(function (key) {
        var rule = null;
        LEX.source_rules.forEach(function (r) { if (r.key === key) rule = r; });
        return rule ? new RegExp(rule.pattern).test(inst.source_files || '') : false;
      });
      if (!okSrc) return false;
    }
    if (cond.dept) {
      // 与后端同语义。后端的 sql 是：
      //   t.id IN (SELECT hospital_id FROM dwd_dept_relation_clean WHERE dept_name = %s)
      // 即「该机构在科室隶属表里恰好有这条科室名」——精确相等，不做包含匹配
      // （否则"骨科"会把"中医骨伤科"也吞进来，数字就错了）。
      // inst.depts 正是这张表按机构聚合的结果（';' 分隔），由 build_spa.sh 带库导出。
      var ds = String(inst.depts || '');
      if (!ds || (';' + ds + ';').indexOf(';' + cond.dept + ';') < 0) return false;
    }
    if (cond.has_addr && !(inst.addr || '')) return false;
    if (cond.has_coord && !(inst.lng != null && inst.lat != null)) return false;
    if (cond.src_min && ((inst.src_count_int != null ? inst.src_count_int : inst.src_count) || 0) < cond.src_min) return false;
    if (cond.kw) {
      var kw = cond.kw;
      if ((inst.name || '').indexOf(kw) < 0 && (inst.addr || '').indexOf(kw) < 0) return false;
    }
    return true;
  }

  var ORDER = {
    score: null, distance: null, level: null, depts: null, name: null
  };

  // 距离基准：与后端 nlq.DEFAULT_BASE 完全同一口径 —— 不传基准点即按天安门，
  // 前端把这种情况的文案标成「距市中心」，避免出现一个说不清距离哪里的"距离"。
  var DEFAULT_BASE = { lng: 116.397428, lat: 39.90923 };

  function haversineKm(lng1, lat1, lng2, lat2) {
    var R = 6371, rad = Math.PI / 180;
    var dLat = (lat2 - lat1) * rad, dLng = (lng2 - lng1) * rad;
    var a = Math.pow(Math.sin(dLat / 2), 2) +
      Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.pow(Math.sin(dLng / 2), 2);
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  function sortItems(items, sort) {
    var s = ORDER[sort] != null ? sort : (ORDER.hasOwnProperty(sort) ? sort : 'score');
    if (s === 'distance') {
      items.sort(function (a, b) {
        if (a.distance_km == null && b.distance_km == null) return cmpName(a, b);
        if (a.distance_km == null) return 1;
        if (b.distance_km == null) return -1;
        return (a.distance_km - b.distance_km) || cmpName(a, b);
      });
    } else if (s === 'level') {
      items.sort(function (a, b) {
        return ((LEX.level_rank[b.level] || 0) - (LEX.level_rank[a.level] || 0)) || cmpName(a, b);
      });
    } else if (s === 'depts') {
      items.sort(function (a, b) {
        return ((b.dept_count || 0) - (a.dept_count || 0)) || cmpName(a, b);
      });
    } else if (s === 'name') {
      items.sort(cmpName);
    } else {
      items.sort(function (a, b) { return (b.score - a.score) || cmpName(a, b); });
    }
    return items;
  }
  // 名称比较用**码位序**（JS 的 < > 对 BMP 字符即码位序），与 Python 的字符串排序、
  // MySQL utf8mb4 的排序结果一致；不要用 localeCompare('zh')——那是拼音序，
  // 会让同一批数据在两端排出不同的顺序（双端一致性校验会立刻抓到）。
  function cmpName(a, b) {
    var x = String(a.name || ''), y = String(b.name || '');
    return x < y ? -1 : (x > y ? 1 : 0);
  }

  // 快照是否带科室隶属关系字段（旧版构建脚本产出的快照没有 depts）。
  // 只抽样看前若干家即可：depts 是 build_spa.sh 一次性给所有行写上的。
  function hasDeptField(institutions) {
    var n = Math.min(institutions.length, 200);
    for (var i = 0; i < n; i++) {
      if (institutions[i] && 'depts' in institutions[i]) return true;
    }
    return false;
  }

  function runFilter(institutions, cond, page, pageSize, baseIn) {
    page = page || 1; pageSize = pageSize || 20;
    if (cond.dept && !hasDeptField(institutions)) {
      // 快照版本过旧：宁可明说算不了，也不要给一个"看起来合理但其实是错的"数量。
      return { total: 0, page: 1, page_size: pageSize, sort: 'score',
        items: [], all: [], stats: overview([]), unsupported: 'dept',
        message: '当前内嵌快照未包含科室隶属关系（旧版构建脚本产出），无法按科室筛选。'
          + '请用 bash web/build_spa.sh 带库重建快照；或先改用行政区、机构类型、医院等级等条件。' };
    }
    // 距离必须**在排序之前**算好：此前 distance_km 恒为 null，于是"按距离排序"
    // 会静默退化成按名称排序——条件看着生效、其实没生效，正是最该避免的一类缺陷。
    var base = baseIn || DEFAULT_BASE;
    var out = [];
    for (var i = 0; i < institutions.length; i++) {
      var it = institutions[i];
      if (!matches(it, cond)) continue;
      // 与后端 haversine_sql 对齐：缺坐标给 null，有坐标则四舍五入到 2 位小数
      var dkm = (it.lng == null || it.lat == null) ? null
        : Math.round(haversineKm(base.lng, base.lat, +it.lng, +it.lat) * 100) / 100;
      out.push({
        id: it.id, name: it.name, district: it.district, category: it.category,
        category_sub: it.category_sub || '', level: it.level, ownership: it.ownership,
        addr: it.addr || '', phone: it.phone || '', lng: it.lng, lat: it.lat,
        coord_precision: it.coord_precision, dept_count: it.dept_count,
        // 科室数的口径字段必须一并带出：前端靠它判定「在线核实值可显数字 / 其余一律待补全」
        // （hospital_depts.csv 97% 的行是 rule/name 推导，只有 dept_count_src 非空才是核实值）。
        // 漏带会让所有机构都退化成「无核实值」，列表整列变成「科室资料待补全」而无法区分。
        dept_count_src: it.dept_count_src || '', rule_dept_count: it.rule_dept_count || 0,
        // 来源计数：带库构建的快照叫 src_count_int，手工回填的老快照叫 src_count，两者都认
        src_count_int: (it.src_count_int != null ? it.src_count_int
          : (it.src_count != null ? it.src_count : null)),
        source_files: it.source_files || '',
        key_depts: it.key_depts || '', depts: it.depts || '', distance_km: dkm,
        score: matchScore(it, cond)
      });
    }
    sortItems(out, cond._sort);
    out.forEach(function (o, idx) { o._rank = idx + 1; });
    var total = out.length;
    var start = (page - 1) * pageSize;
    return {
      total: total, page: page, page_size: pageSize, sort: cond._sort || 'score',
      items: out.slice(start, start + pageSize), all: out,
      stats: overview(out)
    };
  }

  function overview(items) {
    var s = { total: items.length, level3: 0, level2: 0, public_cnt: 0, private_cnt: 0, coord_ok: 0 };
    items.forEach(function (i) {
      if (i.level === '三级') s.level3++;
      if (i.level === '二级') s.level2++;
      if (i.ownership === '公立') s.public_cnt++;
      if (i.ownership === '民营') s.private_cnt++;
      if (i.lng != null && i.lat != null) s.coord_ok++;
    });
    return s;
  }

  // --------------------------------------------------------------------------
  //  维度统计（对应 nlq.run_stats + summarize_stats）
  // --------------------------------------------------------------------------
  function runStats(institutions, cond, dimension) {
    var pool = [];
    for (var i = 0; i < institutions.length; i++) {
      if (matches(institutions[i], cond)) pool.push(institutions[i]);
    }
    var rows = [];
    if (dimension === 'source') {
      LEX.source_rules.forEach(function (rule) {
        var re = new RegExp(rule.pattern);
        rows.push({ name: rule.label,
          cnt: pool.filter(function (x) { return re.test(x.source_files || ''); }).length });
      });
      rows.sort(function (a, b) { return (b.cnt - a.cnt) || cmpName(a, b); });
    } else {
      var field = { district: 'district', category: 'category', level: 'level',
        ownership: 'ownership' }[dimension];
      var agg = Object.create(null);
      pool.forEach(function (x) {
        var key = x[field] || '未标注';
        if (!agg[key]) agg[key] = { name: key, cnt: 0, level3: 0, public_cnt: 0 };
        agg[key].cnt++;
        if (x.level === '三级') agg[key].level3++;
        if (x.ownership === '公立') agg[key].public_cnt++;
      });
      rows = Object.keys(agg).map(function (k) { return agg[k]; });
      rows.sort(function (a, b) { return (b.cnt - a.cnt) || cmpName(a, b); });
    }
    return { dimension: dimension, label: LEX.dim_label[dimension],
      chart: LEX.dim_chart[dimension] || 'bar', rows: rows,
      summary: summarizeStats(cond, dimension, LEX.dim_label[dimension], rows) };
  }

  function summarizeStats(cond, dimension, label, rows) {
    var valid = rows.filter(function (r) { return r.cnt; });
    if (!valid.length) return '按当前条件没有查询到任何机构记录。';
    var total = valid.reduce(function (a, b) { return a + b.cnt; }, 0);
    var scope = valid.length > 1 ? '满足筛选条件的机构共 ' + total + ' 家，' : '';
    var top = valid[0];
    if (dimension === 'district') {
      var f3 = valid.slice(0, 3).map(function (r) { return r.name + ' ' + r.cnt + ' 家'; }).join('；');
      return '根据当前系统数据集，' + scope + '按行政区分布，机构数量最多的是 '
        + top.name + '（' + top.cnt + ' 家）。前三位：' + f3 + '。';
    }
    if (dimension === 'level') {
      var order = { '三级': 0, '二级': 1, '一级': 2, '未定级': 3 };
      valid.sort(function (a, b) {
        return (order[a.name] == null ? 9 : order[a.name]) - (order[b.name] == null ? 9 : order[b.name]);
      });
      return '根据当前系统数据集，按医院等级分布：'
        + valid.map(function (r) { return r.name + ' ' + r.cnt + ' 家'; }).join('；')
        + '。（' + label + '口径）';
    }
    if (dimension === 'ownership') {
      return '根据当前系统数据集，按所有制分布：'
        + valid.map(function (r) { return r.name + ' ' + r.cnt + ' 家'; }).join('；') + '。';
    }
    if (dimension === 'category') {
      return '根据当前系统数据集，按机构类型分布，数量最多的是 ' + top.name + '（'
        + top.cnt + ' 家）。前六位：'
        + valid.slice(0, 6).map(function (r) { return r.name + ' ' + r.cnt + ' 家'; }).join('；') + '。';
    }
    return '根据当前系统数据集，按' + label + '统计：'
      + valid.map(function (r) { return r.name + ' ' + r.cnt + ' 家'; }).join('；') + '。';
  }

  function summarizeFilter(cond, result) {
    if (!result.items.length) return '按当前条件没有查询到任何机构记录，可放宽条件后重试。';
    var chips = describe(cond);
    var text = chips.map(function (c) { return c.label + '=' + c.text; }).join('、') || '全部机构';
    return '按「' + text + '」在系统数据集中查询到 ' + result.total
      + ' 家机构，本页展示其中 ' + result.items.length + ' 家。列表中的每一项都可以点开查看详情数据来源。';
  }

  // --------------------------------------------------------------------------
  //  导出
  // --------------------------------------------------------------------------
  return {
    init: init,
    parse: parse,
    describe: describe,
    matches: matches,
    matchScore: matchScore,
    runFilter: runFilter,
    runStats: runStats,
    sortItems: sortItems,
    summarizeStats: summarizeStats,
    summarizeFilter: summarizeFilter,
    normalize: normalize,
    get lex() { return LEX; }
  };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = { NLQ: NLQ };
