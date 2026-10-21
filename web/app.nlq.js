// ============================================================================
//  自然语言智能筛选 —— 单文件形态的离线引擎
// ----------------------------------------------------------------------------
//  为什么需要这个文件：
//    单文件形态（dashboard_offline.html）要能"打开即用、发链接即用"，不能依赖
//    服务器。所以把后端的自然语言解析 + 条件筛选 + 维度统计完整地在前端实现一份，
//    数据来自内嵌快照（9,678 家机构，字段与 MySQL ads_inst_search 同源）。
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
    var gradeHits = t.match(/[一二三](?:级)?[甲乙丙](?:等)?/g) || [];
    if (gradeHits.length) {
      var gradeRe = /[一二三](?:级)?[甲乙丙](?:等)?/g, gm;
      while ((gm = gradeRe.exec(t)) !== null) spans.push([gm.index, gm[0].length]);
      cond.grades = Array.from(new Set(gradeHits.map(function (g) {
        var chars = g.match(/[一二三甲乙丙]/g); return chars[0] + '级' + chars[1] + '等';
      })));
      var bare = t.replace(/[一二三](?:级)?[甲乙丙](?:等)?/g, '');
      levels = levels.filter(function (lv) { return bare.indexOf(lv) >= 0; });
    }
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
    // ---------- 6.2 检查/项目说法 → 标准科室（"想拍核磁"→ 医学影像科） ----------
    // 与 nlq.py 6.2 同源：标准科室名没命中时才扫描检查词表（LEX.dept_exam_alias）。
    // 只做名词映射，不推断"哪家机构能做这个检查"——由 dept 条件去真实科室表里查。
    var examWord = '';
    if (!cond.dept && LEX.dept_exam_alias) {
      var eh = findAll(t, LEX.dept_exam_alias);
      if (eh.length) {
        examWord = eh[0].word;
        cond.dept = LEX.dept_exam_alias[examWord];
        spans.push([eh[0].start, eh[0].len]);
      }
    }

    // ---------- 6.5 科室证据与距离半径（与后端 nlq.py 6.5 同源） ----------
    // 「（仅有/只有/有）来源记录」→ 只认 specialty/online/key_depts 三类真实来源；
    // 整段掩蔽，防止"记录"漏进机构名关键词。
    var evM = t.match(/(?:仅|只)?有?来源记录/);
    if (evM) {
      cond.dept_evidence = 'recorded';
      spans.push([evM.index, evM[0].length]);
    }
    // 「N 公里/千米/km 内」→ 直线半径（仅高精度坐标）；「N 米内」换算成 km。
    var radM = t.match(/(\d+(?:\.\d+)?)\s*(?:公里|千米|km)(?:以内|内|范围内|范围)?/i);
    if (radM) {
      cond.radius = Number(radM[1]);
      spans.push([radM.index, radM[0].length]);
    } else {
      var metM = t.match(/(\d+(?:\.\d+)?)\s*米/);
      if (metM) {
        cond.radius = Math.round(Number(metM[1]) / 10) / 100;
        spans.push([metM.index, metM[0].length]);
      }
    }
    if (cond.radius != null) {
      // 基准点词是"从哪算"的参照物，不是机构名（与 nlq.py 6.5 同源）
      ['天安门', '市中心'].forEach(function (bp) {
        var p3 = t.indexOf(bp);
        if (p3 >= 0 && !overlaps(occupiedSet(spans), p3, bp.length)) spans.push([p3, bp.length]);
      });
    }

    // ---------- 6.7 就近参照：「在 X 附近 / 周边 / 周围」（与 nlq.py 6.7 同源） ----------
    // 参照词既不是行政区也不是机构名关键词——留在第 8 步会把
    // "北京航空航天大学想拍核磁"整串吞进 kw → 0 命中。执行时由 runFilter/runStats
    // 从数据集内取名称/地址含 X 的机构坐标当距离基准，按距离就近排序。
    var nearSpecial = false;
    var nearM = t.match(/(?:[在离从])?([0-9A-Za-z\u4e00-\u9fa5]{2,15}?)(?:附近|周边|周围)/);
    if (nearM) {
      var nx = nearM[1];
      var xs = t.indexOf(nx, nearM.index);
      var occN = occupiedSet(spans);
      // 已识别片段占用的前导字符逐字退掉（「海淀区附近」→ 只留行政区条件，不做就近）
      while (nx && occN[xs]) { nx = nx.slice(1); xs++; }
      if (nx.length >= 2 && (LEX.city_scope_words || ['北京市', '北京']).indexOf(nx) < 0) {
        spans.push([nearM.index, nearM[0].length]);
        if (nx === '天安门' || nx === '市中心') nearSpecial = true;
        else cond.near_kw = nx;
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
    // 排序说法是"意图"而不是"机构名"（「按距离从近到远」命中了"从近到远"，却剩下"按距离"）。
    // ⚠ 必须**先于** stop_phrases：停用词里有「按」，先把「按距离」切成「距离」后排序词
    // 就再也删不掉 → 两个示例查询曾经 kw="距离"、命中 0 条（与 nlq.py 同源同坑）。
    (LEX.sort_words || []).forEach(function (sw) { rest = rest.split(sw[0]).join(''); });
    LEX.stop_phrases.forEach(function (ph) { rest = rest.split(ph).join(''); });
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
    // ④ 排序意图残渣（兜底，与 nlq.py 同源）：整句只剩"距离 / 远近"这类词时，
    //    它是排序意图而不是机构名；机构名里不存在这些词，删除不误伤真实关键词。
    if (rest && /^(距离|远近|近远|由近|从近|升序|降序|排序方式)$/.test(rest)) rest = '';
    // ③ 症状词剥离（与 nlq.py SYMPTOM_WORDS 同源）：「海淀区 头疼发烧」若不剥，
    //    "头疼发烧"会整段变成机构名关键词 → 查询恒为 0。剥掉后有效条件照常生效。
    var strippedSyms = [];
    (LEX.symptom_words || []).slice().sort(function (a, b) { return b.length - a.length; })
      .forEach(function (w) {
        if (rest.indexOf(w) >= 0) { strippedSyms.push(w); rest = rest.split(w).join(''); }
      });
    if (rest.length >= 2 && !/^[0-9]+$/.test(rest)) cond.kw = rest;
    else if (rest.length && !/^[0-9]+$/.test(rest)) out.unmatched.push(rest);

    // ---------- 8.5 数据年份（本数据集没有机构级年份字段，明确告知） ----------
    if (/(19|20)\d{2}\s*年?/.test(t)) {
      var prevNote = out.notice || '';
      out.notice = (prevNote ? prevNote + '\n' : '')
        + '当前数据集的机构记录未保留「数据来源年份」字段，因此无法按年份筛选；'
        + '数据来源与批次时效可在「数据整合」与「数据质量」页查看。';
      if (cond.kw && /^(19|20)\d{2}年?$/.test(cond.kw)) delete cond.kw;
    }

    // ---------- 10. 意图判定 ----------
    var hasStructured = !!(dists.length || levels.length || levelMin !== null
      || owns.length || cond.dept || cond.grades || cond.radius != null
      || cond.dept_evidence);
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

    // ---------- 10.5 症状词剥离说明（放在拒答判定之后：纯症状输入走拒答，不重复提示） ----------
    if (strippedSyms.length) {
      var prevSym = out.notice || '';
      out.notice = (prevSym ? prevSym + '\n' : '')
        + (LEX.symptom_notice || '「%s」是症状描述，已忽略这部分内容。')
          .replace('%s', strippedSyms.join('、'));
    }

    // ---------- 10.6 检查词映射说明（与 nlq.py 10.6 同源） ----------
    if (examWord) {
      var prevEx = out.notice || '';
      out.notice = (prevEx ? prevEx + '\n' : '')
        + (LEX.exam_notice || '「%s」是检查/项目说法，已按映射改用科室「%s」查询。')
          .replace('%s', examWord).replace('%s', cond.dept);
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

    // ---------- 10.9 就近参照的默认排序（与 nlq.py 10.9 同源） ----------
    // 「X 附近」没显式说排序方式时默认按距离；显式给了排序词就尊重用户选择。
    if ((cond.near_kw || nearSpecial) && !cond._sort) cond._sort = 'distance';

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
    if (cond.grades && cond.grades.length) add('grades', '等级与等次', cond.grades, cond.grades.join('、') + '（等次缺失不计入）');
    if (cond.dept_evidence === 'recorded') add('dept_evidence', '科室证据', ['recorded'], '仅有来源记录（排除名称及规则推断）');
    if (cond.radius != null) add('radius', '直线距离', [cond.radius], Number(cond.radius).toFixed(1) + ' km 内（仅高精度坐标）');
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
    // key 用 "_near" 前缀：explain() 跳过所有 "_" 开头的 chip —— 就近参照是
    // 排序意图不是筛选条件，给它算"命中贡献"会得出「去掉无影响」的假解释。
    if (cond.near_kw) add('_near', '就近参照', [cond.near_kw],
      cond.near_kw + ' 附近（参照点取数据集内真实坐标，按距离就近排序）');
    if (cond._sort) add('_sort', '排序方式', [cond._sort], LEX.sort_label[cond._sort] || cond._sort);
    return chips;
  }

  // --------------------------------------------------------------------------
  //  命中解释 / 无结果放宽建议
  // --------------------------------------------------------------------------
  //  要回答两个用户真的会问的问题：
  //    「为什么只剩 30 家？」      → 每条条件在别的条件之上又筛掉了多少
  //    「一条都没有，怎么改？」    → 哪个条件一去掉就立刻有结果
  //
  //  做法：对每个条件各算两次 —— ①只用这一条 ②用「除这一条以外的全部条件」。
  //  两者都走同一个 matches()，因此解释口径与结果口径**不可能**漂移；
  //  这是刻意的：另写一套过滤逻辑再指望两边对上，正是这类功能最常见的 bug 来源。
  //
  //  ⚠️ 边际贡献 = keep_n - total，**不是** alone_n - keep_n。
  //     alone_n（只用该条）可能远大于也可能远小于 keep_n，两者相减会得到负数，
  //     界面上就会出现「收紧 -261 家」这种自相矛盾的话。
  //     keep_n - total 才是「在其它条件都满足的前提下，这条又筛掉多少」，
  //     由集合包含关系保证恒 ≥ 0。
  // 复杂度：O(机构数 × 条件数)，全量 9,678 家 × 最多 10 条条件 ≈ 20 万次匹配，
  //  实测 < 60 ms，只在出结果时算一次，不需要缓存。
  function explain(institutions, cond, baseIn, total) {
    // "_" 开头的 chip（_sort 排序 / _near 就近参照）是意图不是筛选条件，
    // 参与命中解释会得出「去掉它毫无影响」的假解释（与 nlq.py explain 同源）。
    var chips = describe(cond).filter(function (c) {
      return String(c.key || '').charAt(0) !== '_';
    });
    if (!chips.length) return { items: [], suggestion: null, total: total };

    var items = chips.map(function (c) {
      var alone = 0;
      for (var i = 0; i < institutions.length; i++) {
        if (matches(institutions[i], onlyKey(cond, c.key), baseIn)) alone++;
      }
      return { key: c.key, label: c.label, text: c.text,
               alone_n: alone, keep_n: null, drop_n: null };
    });

    // keep_n：逐条剔除重算 —— 在「其余全部条件」下，放开这一条会多出多少家
    items.forEach(function (it) {
      var kept = 0;
      var c2 = withoutKey(cond, it.key);
      for (var j = 0; j < institutions.length; j++) {
        if (matches(institutions[j], c2, baseIn)) kept++;
      }
      it.keep_n = kept;
      it.drop_n = kept - total;          // 边际贡献，恒 ≥ 0
    });

    // 建议放宽哪一个：**边际贡献最小**的那条 —— 它对结果影响最小，去掉最不心疼。
    // ⚠️ 只在「去掉后确实还有结果」的候选里挑。原实现先按边际贡献排序再判断
    //    keep_n > 0，一旦排在最前的那条去掉后仍是 0 家（比如「医院类型」被
    //    「民营 + 某区」完全排除），就整条不给建议 —— 而旁边明明有一条
    //    去掉就能出 15 家的条件。这是把「候选集」和「排序」搞反了。
    var usable = items.filter(function (it) { return it.keep_n > 0; });
    var ranked = usable.slice().sort(function (a, b) {
      return (a.drop_n - b.drop_n) || (a.alone_n - b.alone_n);
    });
    var best = ranked[0] || null;

    return {
      items: items,
      // usable 为空 = 去掉任意单条条件都还是 0 家。此时给不出有意义的动作，
      // 由界面回落到泛化提示，而不是硬推一条注定无结果的建议。
      suggestion: best,
      total: total,
    };
  }

  // 只保留 cond 里的一个条件键（其余置空）→ 用来算 alone_n
  function onlyKey(cond, key) {
    var c = copyCond(cond);
    FILTER_KEYS.forEach(function (k) { if (k !== key) c[k] = emptyLike(cond[k]); });
    return c;
  }
  // 剔掉 cond 里的一个条件键（其余保留）→ 用来算 keep_n
  function withoutKey(cond, key) {
    var c = copyCond(cond);
    if (FILTER_KEYS.indexOf(key) >= 0) c[key] = emptyLike(cond[key]);
    return c;
  }
  // 浅拷贝即可：cond 的值全是数组/字符串/数字/布尔，改副本不影响原对象。
  // （注意别复用 normalize —— 那个是给用户输入文本做全半角与去空白的，
  //   拿它处理条件对象会把数组变成字符串。）
  function copyCond(cond) {
    var c = {};
    Object.keys(cond).forEach(function (k) { c[k] = cond[k]; });
    return c;
  }
  // ⚠️ 这个清单必须与 matches() 里实际读的字段一一对应，且与 describe() 的 chip key 对齐。
  //    少登记一个 → explain 算不出那条条件的贡献（UI 上那行会静默消失）；
  //    多登记一个 → matches 根本不读它，alone/keep 恒等于总数，给出「去掉它毫无影响」的假解释。
  var FILTER_KEYS = ['district', 'level', 'grades', 'level_min', 'radius', 'category',
    'ownership', 'source', 'dept', 'dept_evidence', 'src_min', 'has_addr', 'has_coord', 'kw'];
  function emptyLike(v) {
    if (Array.isArray(v)) return [];
    if (typeof v === 'boolean') return false;
    return null;
  }

  // --------------------------------------------------------------------------
  //  条件匹配度（与后端 MATCH_WEIGHTS 同源）
  // --------------------------------------------------------------------------
  function matchScore(inst, cond) {
    return 1;
  }

  // --------------------------------------------------------------------------
  //  筛选（对应 nlq.build_where + run_filter）
  // --------------------------------------------------------------------------
  function matches(inst, cond, baseIn) {
    if (cond.district && cond.district.length && cond.district.indexOf(inst.district) < 0) return false;
    if ((cond.level && cond.level.length) || (cond.grades && cond.grades.length)) {
      var bareMatch = cond.level && cond.level.indexOf(inst.level) >= 0;
      var gradeMatch = (cond.grades || []).some(function (g) {
        return inst.level === g.slice(0, 2) && (inst.level_sub === g.slice(2) || inst.level_sub === g.charAt(2));
      });
      if (!bareMatch && !gradeMatch) return false;
    }
    if (cond.radius != null) {
      var radius = Number(cond.radius), b = baseIn || DEFAULT_BASE;
      if (!Number.isFinite(radius) || radius <= 0 || radius > 200) throw new Error('距离半径应大于 0 且不超过 200 km');
      if (inst.coord_precision !== 'high' || inst.lng == null || inst.lat == null) return false;
      if (Math.round(haversineKm(b.lng, b.lat, +inst.lng, +inst.lat) * 100) / 100 > radius) return false;
    }
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
      var ds = String((cond.dept_evidence === 'recorded' ? inst.recorded_depts : inst.depts) || '');
      if (!ds || (';' + ds + ';').indexOf(';' + cond.dept + ';') < 0) return false;
    }
    if (!cond.dept && cond.dept_evidence === 'recorded') {
      // 与后端同语义：未指定科室时，证据条件同样生效——至少一条来源证据映射，
      // 否则单独勾选「仅有来源记录」会不过滤任何机构。
      if (!String(inst.recorded_depts || '')) return false;
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

  // --------------------------------------------------------------------------
  //  就近参照点（"在 X 附近"）—— 与 nlq.py pick_near_row / resolve_near_base 同序
  //  排序键：高精度坐标优先 → 名称命中优先于地址命中 → 来源数多优先 → 快照序（id 升序）。
  //  没有高精度时退用低精度并在 note 注明；连带坐标的都没有 → 绝不伪造基准点，
  //  参照词退回机构名关键词检索（kw 为空才并入）。
  // --------------------------------------------------------------------------
  function pickNearRow(institutions, nk) {
    var best = null, bestKey = null;
    for (var i = 0; i < institutions.length; i++) {
      var it = institutions[i];
      if (it.lng == null || it.lat == null) continue;
      var inName = (it.name || '').indexOf(nk) >= 0;
      if (!inName && (it.addr || '').indexOf(nk) < 0) continue;
      var key = [
        it.coord_precision === 'high' ? 1 : 0,
        inName ? 1 : 0,
        (it.src_count_int != null ? it.src_count_int : (it.src_count || 0)),
      ];
      var better = false;
      if (!bestKey) better = true;
      else for (var k = 0; k < 3; k++) {
        if (key[k] !== bestKey[k]) { better = key[k] > bestKey[k]; break; }
      }
      if (better) {
        best = { lng: +it.lng, lat: +it.lat, name: it.name, precision: it.coord_precision };
        bestKey = key;
      }
    }
    return best;
  }
  function resolveNearBase(institutions, cond) {
    var nk = cond.near_kw;
    if (!nk) return null;
    var hit = pickNearRow(institutions, nk);
    if (hit) {
      var rough = hit.precision !== 'high';
      return { base: hit,
        note: '就近参照「' + nk + '」：基准点取数据集内 ' + hit.name + ' 的登记坐标'
          + (rough ? '（街道级精度，距离仅供参考）' : '') };
    }
    cond.near_kw = null;
    if (!cond.kw) {
      cond.kw = nk;
      return { note: '数据集内没有名称或地址含「' + nk + '」且带坐标的机构，已改按机构名称/地址关键词检索' };
    }
    return { note: '数据集内没有名称或地址含「' + nk + '」且带坐标的机构，已忽略就近参照' };
  }

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
      // score 的并列裁决（与 nlq.py ORDER_BY['score'] 同源）：
      // 等级（高→低，未定级垫底）→ 科室收录量（多→少）→ 名称码位序。
      // 只按名称排会让"世界…门诊部"排在中国中医科学院望京医院前面，反直觉。
      items.sort(function (a, b) {
        return (b.score - a.score)
          || ((LEX.level_rank[b.level] || 0) - (LEX.level_rank[a.level] || 0))
          || ((b.dept_count || 0) - (a.dept_count || 0))
          || cmpName(a, b);
      });
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
    if (cond.radius != null && (!Number.isFinite(Number(cond.radius)) || Number(cond.radius) <= 0 || Number(cond.radius) > 200)) throw new Error('距离半径应大于 0 且不超过 200 km');
    if (cond.dept_evidence === 'recorded' && institutions.some(function (r) { return !Object.prototype.hasOwnProperty.call(r, 'recorded_depts'); })) {
      return { total: 0, page: 1, page_size: pageSize, sort: 'score', items: [], all: [], stats: overview([]), unsupported: 'dept',
        message: '此快照未收录科室来源证据，无法执行仅有来源记录的筛选。请带数据库重建快照，或取消该证据条件。' };
    }
    if (cond.dept && !hasDeptField(institutions)) {
      // 快照版本过旧：宁可明说算不了，也不要给一个"看起来合理但其实是错的"数量。
      return { total: 0, page: 1, page_size: pageSize, sort: 'score',
        items: [], all: [], stats: overview([]), unsupported: 'dept',
        message: '当前内嵌快照未包含科室隶属关系（旧版构建脚本产出），无法按科室筛选。'
          + '请用 bash web/build_spa.sh 带库重建快照；或先改用行政区、机构类型、医院等级等条件。' };
    }
    // 距离必须**在排序之前**算好：此前 distance_km 恒为 null，于是"按距离排序"
    // 会静默退化成按名称排序——条件看着生效、其实没生效，正是最该避免的一类缺陷。
    // 就近参照（near_kw）优先于页面传入的基准点：它是用户显式给定的参照物。
    var nearNote = null;
    if (cond.near_kw) {
      var nr = resolveNearBase(institutions, cond);
      if (nr) { nearNote = nr.note; if (nr.base) baseIn = { lng: nr.base.lng, lat: nr.base.lat }; }
    }
    var base = baseIn || DEFAULT_BASE;
    var out = [];
    for (var i = 0; i < institutions.length; i++) {
      var it = institutions[i];
      if (!matches(it, cond, baseIn)) continue;
      // 与后端 haversine_sql 对齐：缺坐标给 null，有坐标则四舍五入到 2 位小数
      var dkm = (it.lng == null || it.lat == null) ? null
        : Math.round(haversineKm(base.lng, base.lat, +it.lng, +it.lat) * 100) / 100;
      out.push({
        id: it.id, name: it.name, district: it.district, category: it.category,
        category_sub: it.category_sub || '', level: it.level, level_sub: it.level_sub || '', ownership: it.ownership,
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
      stats: overview(out),
      near_note: nearNote,
      // 命中解释随结果一起返回。只在第 1 页算：翻页时条件没变，重算一遍纯属浪费。
      explain: page === 1 ? explain(institutions, cond, baseIn, total) : null,
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
  function runStats(institutions, cond, dimension, baseIn) {
    if (cond.dept_evidence === 'recorded' && institutions.some(function (r) { return !Object.prototype.hasOwnProperty.call(r, 'recorded_depts'); })) {
      throw new Error('此快照未收录科室来源证据，请带数据库重建快照后再统计。');
    }
    // 就近参照解析失败会退回 kw（改写 cond），必须发生在筛选之前——
    // 否则统计条件与展示的条件卡片对不上（与 nlq.run_stats 同源）。
    var nearNote = null;
    if (cond.near_kw) {
      var nr0 = resolveNearBase(institutions, cond);
      if (nr0) nearNote = nr0.note;
    }
    var pool = [];
    for (var i = 0; i < institutions.length; i++) {
      if (matches(institutions[i], cond, baseIn)) pool.push(institutions[i]);
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
      near_note: nearNote,
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
    resolveNearBase: resolveNearBase,
    matchScore: matchScore,
    runFilter: runFilter,
    explain: explain,
    runStats: runStats,
    sortItems: sortItems,
    summarizeStats: summarizeStats,
    summarizeFilter: summarizeFilter,
    normalize: normalize,
    get lex() { return LEX; }
  };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = { NLQ: NLQ };
