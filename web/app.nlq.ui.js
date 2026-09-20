// ============================================================================
//  智能筛选页（自然语言 + 条件双通道）—— 单文件形态的界面层
// ----------------------------------------------------------------------------
//  定位：
//    本页做的是「把中文说法翻译成结构化筛选条件，再去查真实机构数据」。
//    它**不是**问诊页、诊断页、也不是推荐页——系统里没有患者数据，
//    也不做医学知识问答（见 nlq.py 的 MEDICAL_REFUSAL 边界与拒答话术）。
//
//  两条通道，同一套执行链：
//    · 自然语言通道：一句话 → NLQ 解析 → 条件卡片 → 数据库查询
//    · 条件筛选通道：下拉框组合 → 条件卡片 → 数据库查询
//
//  三处硬约束（改动前必读）：
//    ① **不产生数字**：KPI、列表、图表里的每个数字都来自这一次真实查询的返回；
//       前端不写死任何统计值，也不让模型参与出数。
//    ② **不产生机构名**：机构列表只由查询结果渲染，模型只输出筛选条件。
//    ③ **双端同源**：联网走 /api/nlq/*，离线走 window.NLQ（由 nlq.py 同源导出词表）。
//
//  与 app.js 的关系：
//    本文件是 app.js 的"附属页面"，复用它的 $.esc / svgIcon / openDrawer /
//    togglePick / levelBadge / curBase / switchView 等公共设施，不重复实现。
// ============================================================================
'use strict';

var NLQ_UI = (function () {
  var PAGE = 1, PAGE_SIZE = 20;
  var CUR = null;            // 最近一次查询结果（结构对齐 /api/nlq/query 的返回）
  var COND = {};             // 当前生效的结构化条件
  var ALL = [];              // 全量命中（离线形态本地持有；联网形态只持有当前页）
  var TOTAL = 0;
  var SORT = 'score';
  var BUSY = false, INITED = false, ENTERED = false;
  var CH = null, STAT_CHART = null;                      // 结果地图 / 统计图
  var ROW_EL = {}, SCATTER = {}, HOVER = null;           // 列表 ↔ 地图 悬停互指
  var SRC_CACHE = null;                                  // 离线形态的数据来源说明缓存

  var EXAMPLES = [
    '朝阳区和海淀区的三级医院',
    '全市的公立三级医院，按距离排序',
    '二级以上的中医院',
    '来自医保定点名单的社区卫生服务中心',
    '昌平区的民营医院，名称里带“妇儿”',
    '按行政区统计朝阳区的机构数量',
  ];

  // --------------------------------------------------------------------------
  //  小工具
  // --------------------------------------------------------------------------
  function el(id) { return document.getElementById(id); }
  function setText(id, v) { var e = el(id); if (e) e.textContent = v; }
  function backend() { return !!(window.ENV && ENV.api); }
  function hasLex() { return !!(window.NLQ && NLQ.lex); }

  function jsonPost(url, body) {
    return fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    }).then(function (r) { return r.json().catch(function () { return null; }); });
  }

  function setBusy(on) {
    BUSY = !!on;
    var b = el('nlq_run');
    if (b) { b.disabled = !!on; }
    var w = el('nlq_wait');
    if (w) w.style.display = on ? '' : 'none';
  }

  // --------------------------------------------------------------------------
  //  离线形态的数据来源说明（口径与后端 _data_source_note 对齐）
  // --------------------------------------------------------------------------
  function offlineSourceNote() {
    if (SRC_CACHE) return SRC_CACHE;
    var insts = (DATA && DATA.institutions) || [];
    var seen = Object.create(null), n = 0;
    for (var i = 0; i < insts.length; i++) {
      var s = insts[i].source_files || '';
      if (s && !seen[s]) { seen[s] = 1; n++; }
    }
    SRC_CACHE = {
      database: '离线数据快照（由 Spark 数仓 ADS 层导出，字段与 MySQL ads_inst_search 同源）',
      institutions: (DATA && DATA.total) || insts.length,
      batch_date: (DATA && DATA.snapshot_time) || '',
      source_files: n,
      detail: '原始数据来自北京市卫健委、市 / 区医保局、各区卫健委公开数据及社区卫生服务机构名录等多源材料，'
        + '经 HDFS 入湖 → Spark 清洗整合 → ADS 层产出机构宽表。',
      note: (window.NLQ && NLQ.lex && NLQ.lex.scope_note) || '',
    };
    return SRC_CACHE;
  }

  // --------------------------------------------------------------------------
  //  执行：两条通道共用的唯一入口
  //    req = {q: '...'}  或  {conditions: {...}}
  // --------------------------------------------------------------------------
  // 查询策略：**本地内嵌快照优先，后端只做兜底**。
  //   ① 单文件形态的目标是"打开链接就能用"（GitHub Pages / file:// 都算），
  //      内嵌快照由同一套 ETL 从同一个库导出、字段与 MySQL 同源，
  //      因此本地复算与后端结果一致 —— etl/verify_offline_nlq.py 逐字段盯着这件事。
  //   ② 本地优先还保住两件事：地图与结果概览按**全量**结果算（后端分页只回当前页，
  //      用它画地图会只亮一页的点），以及断网时行为完全不变。
  //   ③ 只有本地明确"算不了"（unsupported，例如快照版本过旧没有科室隶属关系）
  //      且后端可达时，才回退 /api/nlq/query。医疗边界拒答不走回退——
  //      本地规则已给出结论，再往返一次没有意义。
  function execute(req, opts) {
    if (BUSY) return;
    setBusy(true);
    var local = null, localErr = null;
    try { local = localExecute(req); } catch (e) { localErr = e; }
    var canLocal = local && local.ok !== false && !local.unsupported;
    var p;
    if (canLocal) {
      p = Promise.resolve(local);
    } else if (backend() && local && local.unsupported) {
      p = jsonPost('/api/nlq/query', req);
    } else {
      p = localErr ? Promise.reject(localErr) : Promise.resolve(local);
    }
    p.then(function (res) {
      setBusy(false);
      if (!res) { toast(svgIcon('warn') + ' 查询失败，请稍后重试'); return; }
      if (res.ok === false) {
        COND = {};
        renderReply(res, null);
        renderResult(null);
        return;
      }
      COND = res.conditions || {};
      CUR = res;
      PAGE = 1;
      SORT = res.sort || (COND && COND._sort) || 'score';
      if (res.intent === 'stats') {
        ALL = null; TOTAL = 0;          // 清掉上一次筛选的本地全量，避免地图残留旧点位
        renderReply(res, null);
        renderStats(res);
        renderResultForStats(res);
        return;
      }
      // 筛选：联网形态后端已分页（只回当前页），离线形态本地持有全量
      if (res.all) { ALL = res.all; TOTAL = res.total; }
      else { ALL = null; TOTAL = res.total; }
      renderReply(res, null);
      renderStats(null);
      renderResult(res);
      if (opts && opts.scroll !== false) scrollTo(el('nlq_reply'));
    }).catch(function (e) {
      setBusy(false);
      console.error('[NLQ_UI.execute]', e);
      toast(svgIcon('err') + ' 查询出错：' + esc(e && e.message ? e.message : e));
    });
  }

  // 离线形态：本地解析 + 本地复算（与后端 nlq.py 逐字段同源）
  function localExecute(req) {
    if (!window.NLQ || !DATA) return { ok: false, message: '离线解析引擎尚未就绪' };
    var parsed, cond;
    if (req.q) {
      parsed = NLQ.parse(req.q, deptNames());
      if (parsed.intent === 'unsupported') {
        return { ok: false, intent: 'unsupported', message: parsed.message,
                 conditions: {}, applied: [], unmatched: parsed.unmatched || [],
                 data_source: offlineSourceNote() };
      }
      cond = parsed.conditions || {};
    } else {
      cond = req.conditions || {};
      parsed = { ok: true, intent: cond.dimension ? 'stats' : 'filter',
                 conditions: cond, applied: NLQ.describe(cond), unmatched: [], message: '' };
      if (cond.dimension) parsed.dimension = cond.dimension;
    }
    if (parsed.intent === 'stats') {
      var st = NLQ.runStats(DATA.institutions, cond, parsed.dimension || 'district');
      var tot = st.rows.reduce(function (a, b) { return a + (b.cnt || 0); }, 0);
      return { ok: true, intent: 'stats', conditions: cond, applied: parsed.applied || NLQ.describe(cond),
               dimension: st.dimension, dimension_label: st.label, chart: st.chart, rows: st.rows,
               summary: st.summary, total: tot, data_source: offlineSourceNote() };
    }
    // 距离基准点：用户设过就用它；没设过 curBase() 会回退天安门，文案显示"距市中心"，
    // 与后端 nlq.DEFAULT_BASE 同一口径。距离必须在筛选内算好，否则"按距离排序"无效。
    var base = (typeof curBase === 'function') ? curBase() : null;
    var r = NLQ.runFilter(DATA.institutions, cond, 1, 1e9, base);
    return { ok: true, intent: 'filter', conditions: cond,
             applied: parsed.applied || NLQ.describe(cond),
             total: r.total, page: 1, page_size: PAGE_SIZE, sort: r.sort,
             items: r.items, all: r.all, stats: r.stats, unsupported: r.unsupported,
             message: r.message || '', summary: NLQ.summarizeFilter(cond, r),
             data_source: offlineSourceNote() };
  }

  // 科室词表（离线形态带不上全量科室明细，给空数组即可，行为与后端一致）
  function deptNames() {
    var meta = (DATA && DATA.meta) || {};
    var ds = meta.depts || [];
    return ds.map(function (d) { return d.dept_name || d; }).filter(Boolean);
  }

  // --------------------------------------------------------------------------
  //  解析结果区：条件卡片 + 说明 + 未识别片段
  // --------------------------------------------------------------------------
  function renderReply(res, extra) {
    var box = el('nlq_chips'), msg = el('nlq_msg'), mis = el('nlq_unmatched'), note = el('nlq_notice');
    var applied = (res && res.applied) || [];

    // —— 主提示语 ——
    if (msg) {
      if (res && res.ok === false) {
        // 医疗边界拒答 / 无有效条件
        msg.className = 'nlqmsg nlqrefuse';
        msg.innerHTML = '<div class="rf-t">' + svgIcon('warn') + ' 无法按此输入筛选</div>' +
          '<div class="rf-b">' + esc(res.message || '').replace(/\\n/g, '<br>') + '</div>';
      } else if (applied.length) {
        msg.className = 'nlqmsg';
        msg.innerHTML = '<span class="okdot"></span>已从您的描述中解析出 <b>' + applied.length +
          '</b> 个筛选条件，均为机构属性条件（不含任何诊疗判断）。';
      } else {
        msg.className = 'nlqmsg muted';
        msg.textContent = '还没有筛选条件：在输入框里描述行政区、机构类型、医院等级、所有制或数据来源，'
          + '也可以切到「条件筛选」标签直接选。';
      }
    }

    // —— 条件卡片（可逐项删除）——
    if (box) {
      box.innerHTML = applied.map(function (c) {
        return '<button type="button" class="nlqchip" data-ck="' + esc(c.key) + '"' +
          ' title="点击移除该条件">' +
          '<em>' + esc(c.label) + '</em><b>' + esc(c.text) + '</b><i>×</i></button>';
      }).join('');
      Array.prototype.forEach.call(box.querySelectorAll('[data-ck]'), function (b) {
        b.addEventListener('click', function () { dropCondition(b.getAttribute('data-ck')); });
      });
    }

    // —— 未识别的片段：如实告知，不猜 ——
    var un = (res && res.unmatched) || [];
    if (mis) {
      mis.style.display = un.length ? '' : 'none';
      mis.innerHTML = un.length
        ? '以下内容未被识别为筛选条件，已忽略：' +
          un.map(function (u) { return '<code>' + esc(u) + '</code>'; }).join(' ')
        : '';
    }

    // —— 数据年份之类的边界说明 ——
    if (note) {
      var n = (res && res.notice) || ((res && res.data_source && res.data_source.note) || '');
      note.style.display = n ? '' : 'none';
      note.textContent = n || '';
    }

    // —— 查询说明（本地模板先生成，联网时再交给 Agnes 润色）——
    var sum = el('nlq_summary');
    if (sum) {
      if (res && res.summary) {
        sum.style.display = '';
        sum.innerHTML = '<span class="ai-badge">' + svgIcon('spark') + '结果说明</span>' +
          '<span class="ai-txt">' + esc(res.summary) + '</span>';
        enhanceSummary(res, sum);
      } else {
        sum.style.display = 'none';
      }
    }
  }

  // --------------------------------------------------------------------------
  //  结果说明：Agnes 润色（三级降级 —— Agnes → 本地模板，失败一律保留本地模板）
  //  · 大模型只负责"把已经查到的事实讲成人话"：数字与机构名照抄事实，不得新增；
  //    且明确禁止输出就诊建议 / 科室推荐（提示词见 web/app.py 的 SUMMARY_PROMPT）。
  //  · 只有后端可达时才发请求；离线形态（Pages / file://）完全不发网络请求。
  //  · 事实里不含任何机构名（避免模型把名字编造或错配），只给统计口径。
  // --------------------------------------------------------------------------
  var SUM_CACHE = {};   // facts 签名 → 已润色文本 / 引擎，避免同一查询反复消耗额度
  var SUM_SEQ = 0;      // 只允许最后一次请求回写，防止慢响应覆盖新结果

  function summaryFacts(res) {
    var s = res.stats || {}, cond = res.conditions || {};
    var applied = (res.applied || []).map(function (c) { return c.label + '=' + c.text; }).join('、');
    var sortKey = res.sort || cond._sort || 'score';
    var f = {
      '场景': res.intent === 'stats' ? '维度统计查询' : '机构筛选查询',
      '筛选条件': applied || '（无条件，全市全量）',
      '命中机构数': res.total,
      '三级医院': s.level3, '二级医院': s.level2,
      '公立机构': s.public_cnt, '民营机构': s.private_cnt,
      '含坐标机构': s.coord_ok,
      '排序方式': (typeof SORT_LABEL !== 'undefined' && SORT_LABEL[sortKey]) || sortKey,
      '数据来源': (res.data_source && res.data_source.database) || '',
      '快照批次': (res.data_source && res.data_source.batch_date) || '',
    };
    if (res.intent === 'stats') {
      f['分组明细（前8组）'] = (res.rows || []).slice(0, 8)
        .map(function (r) { return r.name + ' ' + r.cnt + ' 家'; });
      delete f['命中机构数'];
    }
    return f;
  }

  function enhanceSummary(res, host) {
    if (!backend() || !res || !res.summary) return;
    var txt = host.querySelector('.ai-txt');
    if (!txt) return;
    var facts = summaryFacts(res);
    var key = JSON.stringify(facts);
    if (SUM_CACHE[key] != null) {
      txt.textContent = SUM_CACHE[key];
      setEngineBadge(host, SUM_CACHE[key + '|engine']);
      return;
    }
    var seq = ++SUM_SEQ;
    fetch('/api/nlq/ask?facts=' + encodeURIComponent(key) +
          '&local=' + encodeURIComponent(res.summary))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.summary || seq !== SUM_SEQ) return;   // 丢弃过期响应
        SUM_CACHE[key] = j.summary;
        SUM_CACHE[key + '|engine'] = j.engine || 'local';
        txt.textContent = j.summary;
        setEngineBadge(host, SUM_CACHE[key + '|engine']);
        if (typeof track === 'function') track('nlq_summary', 'nlq', j.engine || 'local', 1);
      })
      .catch(function () { /* 失败即静默保留本地模板，不打扰用户 */ });
  }

  function setEngineBadge(host, engine) {
    var b = host.querySelector('.ai-badge');
    if (!b) return;
    var llm = engine === 'llm';
    b.innerHTML = svgIcon('spark') + (llm ? '结果说明 · Agnes 润色' : '结果说明 · 本地模板');
    b.title = llm
      ? '由 Agnes 大模型在给定事实范围内润色：数字与机构名照抄查询结果，不新增、不推断'
      : '本地模板生成（未启用大模型或大模型不可用，此说明离线同样可用）';
  }

  // 删除单个条件 → 用剩余条件重新查询
  function dropCondition(key) {
    if (!COND) return;
    if (key === 'district') delete COND.district;
    else if (key === 'level') delete COND.level;
    else if (key === 'level_min') delete COND.level_min;
    else if (key === 'category') delete COND.category;
    else if (key === 'ownership') delete COND.ownership;
    else if (key === 'source') delete COND.source;
    else if (key === 'dept') delete COND.dept;
    else if (key === 'kw') delete COND.kw;
    else if (key === 'src_min') delete COND.src_min;
    else if (key === 'has_addr') delete COND.has_addr;
    else if (key === 'has_coord') delete COND.has_coord;
    else if (key === '_sort') delete COND._sort;
    else delete COND[key];
    syncCondControls();
    if (!Object.keys(COND).length) {
      COND = {}; CUR = null;
      renderReply({ ok: false, message: '条件已全部移除，请重新描述或在上方选择条件。' }, null);
      renderResult(null); renderStats(null);
      return;
    }
    execute({ conditions: shrink(COND) }, { scroll: false });
  }

  // 只把后端认识的键送过去（前端内部键以 _ 开头的一并保留，用于排序）
  function shrink(cond) {
    var out = {};
    Object.keys(cond).forEach(function (k) { if (k !== 'dimension') out[k] = cond[k]; });
    return out;
  }

  // --------------------------------------------------------------------------
  //  维度统计的"结果区"：统计查询不产出机构清单，所以 KPI 换成统计口径，
  //  列表区改成一句说明——避免出现"图表有数据、旁边却写等待筛选"的割裂感。
  // --------------------------------------------------------------------------
  function renderResultForStats(res) {
    var kbox = el('nlq_kpis'), list = el('nlq_list'), cnt = el('nlq_count');
    var rows = (res.rows || []).filter(function (r) { return r.cnt; });
    var dim = res.dimension_label || '维度';
    var total = res.total || rows.reduce(function (a, b) { return a + (b.cnt || 0); }, 0);
    var top = rows[0] || null, last = rows.length ? rows[rows.length - 1] : null;

    if (kbox) {
      kbox.className = 'nlqkpis k4';
      var cards = [
        ['统计机构总数', total, '满足本次条件的机构条数合计', 'hero'],
        ['覆盖' + dim + '数', rows.length, '有命中记录的分组数量', 'k2'],
        ['数量最多的一组', top ? top.cnt : null,
          top ? (esc(top.name) + ' · 占比 ' + (total ? (top.cnt / total * 100).toFixed(1) : '0') + '%') : '无数据', 'k3'],
        ['数量最少的一组', last ? last.cnt : null,
          last ? (esc(last.name) + ' · 占比 ' + (total ? (last.cnt / total * 100).toFixed(1) : '0') + '%') : '无数据', 'k4'],
      ];
      kbox.innerHTML = cards.map(function (c) {
        var v = (c[1] == null) ? '—' : Number(c[1]).toLocaleString();
        return '<div class="card ' + c[3] + '"><div class="l">' + c[0] + '</div>' +
          '<div class="v">' + v + '</div><div class="s">' + c[2] + '</div></div>';
      }).join('');
    }
    if (cnt) cnt.textContent = '统计查询';
    setText('nlq_pg', '— / —');
    var pv = el('nlq_prev'), nx = el('nlq_next');
    if (pv) pv.disabled = true;
    if (nx) nx.disabled = true;
    setText('nlq_sortnote', '这是一次维度统计查询：结果以图表呈现，不产出机构清单。' +
      '若要逐家查看机构，请改用筛选类说法（例如「海淀区的三级医院」）。');
    if (list) {
      list.innerHTML = '<div class="empty">' +
        '<div class="et">统计结果在上方图表中</div>' +
        '<div class="es">本条输入识别为「统计」意图，系统按 ' + esc(dim) +
        ' 分组汇总，而不是返回机构列表。<br>换成筛选类说法即可看到机构清单。</div></div>';
      ROW_EL = {}; SCATTER = {};
    }
    renderSource(el('nlq_source'), res.data_source);
    drawMap({ items: [] });
  }

  // --------------------------------------------------------------------------
  //  结果：概览 KPI + 列表 + 地图 + 数据来源
  // --------------------------------------------------------------------------
  function renderResult(res) {
    var kbox = el('nlq_kpis'), list = el('nlq_list'), cnt = el('nlq_count');
    var src = el('nlq_source');

    if (!res) {
      if (kbox) { kbox.className = 'nlqkpis'; kbox.innerHTML = ''; }
      if (list) list.innerHTML = '<div class="empty"><div class="et">等待筛选</div>' +
        '<div class="es">输入一句话或选择条件后，这里会显示匹配到的机构。</div></div>';
      if (cnt) cnt.textContent = '— 家';
      setText('nlq_pg', '— / —');
      var pv = el('nlq_prev'), nx = el('nlq_next');
      if (pv) pv.disabled = true;
      if (nx) nx.disabled = true;
      renderSource(src, (CUR && CUR.data_source) || null);
      drawMap(null);
      return;
    }

    var s = res.stats || {};
    if (kbox) {
      kbox.className = 'nlqkpis';       // 统计查询会把栅格改成 4 列，这里还原
      var cards = [
        ['命中机构', res.total, '本次条件的真实查询结果', 'hero'],
        ['三级医院', s.level3, '三级（含三甲 / 三乙口径）', 'k2'],
        ['二级医院', s.level2, '二级（含二甲 / 二乙口径）', 'k3'],
        ['公立机构', s.public_cnt, '所有制判定为公立', 'k4'],
        ['民营机构', s.private_cnt, '所有制判定为民营', 'k5'],
        ['含坐标', s.coord_ok, '可用于地理分布与距离计算', 'k6'],
      ];
      kbox.innerHTML = cards.map(function (c) {
        var v = (c[1] == null) ? '—' : Number(c[1]).toLocaleString();
        return '<div class="card ' + c[3] + '"><div class="l">' + c[0] + '</div>' +
          '<div class="v">' + v + '</div><div class="s">' + c[2] + '</div></div>';
      }).join('');
    }

    if (res.unsupported === 'dept') {
      if (list) list.innerHTML = '<div class="empty"><div class="et">离线形态不支持按科室筛选</div>' +
        '<div class="es">' + esc(res.message || '') + '</div></div>';
      if (cnt) cnt.textContent = '0 家';
      renderSource(src, res.data_source);
      drawMap([]);
      return;
    }

    renderListPage();
    renderSource(src, res.data_source);
    drawMap(res);
  }

  // 列表分页（联网形态按页取后端数据；离线形态从 ALL 本地切页）
  function renderListPage() {
    var list = el('nlq_list'), cnt = el('nlq_count');
    var items, total = TOTAL;

    if (ALL) {
      total = ALL.length;
      items = ALL.slice((PAGE - 1) * PAGE_SIZE, PAGE * PAGE_SIZE);
    } else {
      items = (CUR && CUR.items) || [];
      total = (CUR && CUR.total) || 0;
    }
    TOTAL = total;

    var totalPg = Math.max(1, Math.ceil(total / PAGE_SIZE));
    if (PAGE > totalPg) PAGE = totalPg;
    setText('nlq_pg', PAGE + ' / ' + totalPg);
    var pv = el('nlq_prev'), nx = el('nlq_next');
    if (pv) pv.disabled = PAGE <= 1;
    if (nx) nx.disabled = PAGE >= totalPg;
    if (cnt) cnt.textContent = total.toLocaleString() + ' 家';
    setText('nlq_sortnote', '按 ' + ((SORT_LABEL && SORT_LABEL[SORT]) || SORT) +
      ' 排序 · 点击行查看详情 · 勾选左侧加入对比（最多 ' + PICK_MAX + ' 家）');

    if (!list) return;
    if (!items.length) {
      list.innerHTML = '<div class="empty"><div class="et">没有符合条件的机构</div>' +
        '<div class="es">条件组合偏窄，试着去掉 1–2 个条件，或换一种说法。</div></div>';
      ROW_EL = {}; SCATTER = {};
      return;
    }
    list.innerHTML = items.map(rowHtml).join('');
    ROW_EL = {}; HOVER = null;
    Array.prototype.forEach.call(list.querySelectorAll('.row'), function (rowEl) {
      var rid = String(rowEl.getAttribute('data-id'));
      ROW_EL[rid] = rowEl;
      rowEl.addEventListener('click', function (ev) {
        if (ev.target.closest('[data-pick]') || ev.target.closest('[data-fav]')) return;
        openDrawer(rid);
      });
      rowEl.addEventListener('mouseenter', function () { hoverRow(rid, true); });
      rowEl.addEventListener('mouseleave', function () { hoverRow(rid, false); });
    });
    Array.prototype.forEach.call(list.querySelectorAll('[data-pick]'), function (b) {
      b.addEventListener('click', function (ev) { ev.stopPropagation(); togglePick(b.getAttribute('data-pick')); });
    });
    Array.prototype.forEach.call(list.querySelectorAll('[data-fav]'), function (b) {
      b.addEventListener('click', function (ev) { ev.stopPropagation(); toggleFav(b.getAttribute('data-fav')); });
    });
  }

  function distOf(r) {
    if (r.distance_km != null) return r.distance_km;
    if (r.lng == null || r.lat == null) return null;
    var b = curBase();
    if (b.lng == null || b.lat == null) return null;
    var d = haversine(b.lng, b.lat, r.lng, r.lat);
    return (d == null || isNaN(d)) ? null : d;
  }

  function rowHtml(r) {
    var on = PICKED.has(String(r.id));
    var d = distOf(r);
    var dist = (d == null) ? '—' : (Math.round(d * 10) / 10).toFixed(1) + ' km';
    var distLabel = '距' + ((BASE_NOW && curBase().name) ? curBase().name : '市中心');
    var ksc = r.key_specialty_count || 0;
    var scoreTxt = (r.score == null) ? '' :
      '<div class="score" title="条件匹配度：命中条件权重之和 ÷ 本次条件权重之和">' +
      Number(r.score).toFixed(3) + '</div>';
    return '<div class="row' + (on ? ' sel' : '') + '" data-id="' + esc(r.id) + '">' +
      '<div class="pick" data-pick="' + esc(r.id) + '" title="加入对比（最多 ' + PICK_MAX + ' 家）">' + svgIcon('ok') + '</div>' +
      '<div class="body">' +
        '<div class="name">' + esc(r.name) + '</div>' +
        '<div class="meta">' + levelBadge(r.level) + catBadge(r.category) + ownBadge(r.ownership) +
          '<span>' + esc(r.district || '未标注') + '</span><span style="color:' + FAINT + '">·</span>' +
          '<span>' + (r.dept_count || 0) + ' 个科室</span>' +
          (r.src_count_int ? '<span style="color:' + FAINT + '">·</span><span>' + r.src_count_int + ' 个来源</span>' : '') +
        '</div>' +
        featLine(r) + netLine(r) +
      '</div>' +
      '<div class="side">' +
        '<div class="dist">' + dist + '<div style="color:' + DIM + ';font-size:10px;font-weight:400">' + esc(distLabel) + '</div></div>' +
        scoreTxt +
        '<div class="ksc ' + (ksc > 0 ? 'on' : 'off') + '"><b>' + ksc + '</b>重点专科</div>' +
      '</div>' +
      '<button class="rowstar' + (isFav(r.id) ? ' on' : '') + '" data-fav="' + esc(r.id) + '" title="' +
        (isFav(r.id) ? '取消收藏' : '加入收藏') + '">' + svgIcon('star') + '</button>' +
    '</div>';
  }

  // --------------------------------------------------------------------------
  //  维度统计（"按行政区统计…"这类输入）：ECharts + 中文说明
  // --------------------------------------------------------------------------
  function renderStats(res) {
    var box = el('nlq_statsbox'), host = el('nlq_chart');
    if (!box || !host) return;
    if (!res || res.intent !== 'stats') {
      box.style.display = 'none';
      if (STAT_CHART) { try { STAT_CHART.clear(); } catch (e) { } }
      return;
    }
    box.style.display = '';
    setText('nlq_stats_title', (res.dimension_label || '维度') + '统计');

    var rows = (res.rows || []).filter(function (r) { return r.cnt; });
    if (!rows.length) {
      // 空结果也要说清楚，而不是悄悄把面板藏起来（用户会以为按钮没反应）
      if (STAT_CHART) { try { STAT_CHART.dispose(); } catch (e) { } STAT_CHART = null; }
      host.innerHTML = '<div class="empty"><div class="et">该维度下没有命中记录</div>' +
        '<div class="es">筛选条件可能偏窄，试着去掉名称关键词或减少限定条件后重试。</div></div>';
      return;
    }
    // 上一轮若是空结果，容器已被换成提示文案 → 需要重建画布再 init
    if (!host.querySelector('canvas') && STAT_CHART) {
      try { STAT_CHART.dispose(); } catch (e) { }
      STAT_CHART = null;
    }
    if (host.firstChild && host.firstChild.className === 'empty') host.innerHTML = '';

    if (typeof echarts === 'undefined') return;
    if (!STAT_CHART) STAT_CHART = echarts.init(host, null, { renderer: 'canvas' });
    var isPie = (res.chart === 'pie');
    var palette = [ACC, ACC2, VIO, WARN, PINK, CRIT, ACC2];
    STAT_CHART.setOption({
      backgroundColor: 'transparent',
      tooltip: Object.assign({ trigger: isPie ? 'item' : 'axis',
        axisPointer: { type: 'shadow' } }, TIP),
      grid: isPie ? undefined : { left: 108, right: 46, top: 8, bottom: 8 },
      xAxis: isPie ? undefined : Object.assign({ type: 'value' }, AXIS),
      yAxis: isPie ? undefined : Object.assign({ type: 'category',
        data: rows.map(function (r) { return r.name; }).reverse() }, AXIS),
      series: [isPie ? {
        type: 'pie', radius: ['42%', '68%'], center: ['50%', '52%'],
        data: rows.map(function (r, i) {
          return { name: r.name, value: r.cnt, itemStyle: { color: palette[i % palette.length] } };
        }),
        label: { color: INK, fontSize: 11, formatter: function (p) { return p.name + '\n' + p.value; } },
        labelLine: { lineStyle: { color: EDGE2 } },
        itemStyle: { borderColor: PANEL, borderWidth: 2.5 },
      } : {
        type: 'bar',
        data: rows.map(function (r) { return r.cnt; }).reverse(),
        itemStyle: { color: ACC2, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', color: INK, fontSize: 10,
          formatter: function (p) { return p.value; } },
        barMaxWidth: 18,
      }],
    }, true);
    setTimeout(function () { try { STAT_CHART.resize(); } catch (e) { } }, 60);
  }

  // --------------------------------------------------------------------------
  //  结果地图：区县底色 = 命中数量，散点 = 命中的机构
  // --------------------------------------------------------------------------
  function drawMap(res) {
    var host = el('nlq_map'), diag = el('nlq_map_diag');
    if (!host) return;
    if (typeof echarts === 'undefined') { if (diag) diag.textContent = 'ECharts 未加载'; return; }
    if (!DATA || !DATA.geojson) { if (diag) diag.textContent = '快照缺少地图数据'; return; }
    if (!CH) {
      CH = echarts.init(host, null, { renderer: 'canvas' });
      CH.on('click', function (p) {
        if (p.data && p.data.instId != null) { openDrawer(p.data.instId); return; }
      });
      CH.on('mouseover', function (p) {
        if (p.seriesType === 'effectScatter' && p.data && p.data.instId != null) hoverMap(p.data.instId, true);
      });
      CH.on('mouseout', function (p) {
        if (p.seriesType === 'effectScatter' && p.data && p.data.instId != null) hoverMap(p.data.instId, false);
      });
    }

    var pool = ALL || (CUR && CUR.items) || [];
    var byDist = {};
    pool.forEach(function (r) { byDist[r.district || '未标注'] = (byDist[r.district || '未标注'] || 0) + 1; });
    var maxN = 0;
    Object.keys(byDist).forEach(function (k) { if (byDist[k] > maxN) maxN = byDist[k]; });

    var inB = function (r) {
      return r.lng != null && r.lat != null &&
        +r.lng > 115.35 && +r.lng < 117.50 && +r.lat > 39.40 && +r.lat < 41.10;
    };
    var pts = pool.filter(inB).slice(0, 3000);
    SCATTER = {};
    pts.forEach(function (r, i) { SCATTER[String(r.id)] = i; });

    CH.setOption({
      backgroundColor: 'transparent', textStyle: { color: INK },
      tooltip: Object.assign({ trigger: 'item' }, TIP),
      geo: {
        map: 'beijing', roam: true, zoom: 1.02,
        layoutCenter: ['50%', '50%'], layoutSize: '97%', aspectScale: 0.9,
        label: { show: true, color: MAP_LBL, fontSize: 10 },
        itemStyle: { borderColor: MAP_BD, borderWidth: 1, areaColor: MAP_AREA },
        emphasis: { label: { color: INK_STRONG }, itemStyle: { areaColor: MAP_HI } },
      },
      visualMap: {
        min: 0, max: Math.max(1, maxN), show: false,
        inRange: { color: MAP_RAMP },
      },
      series: [
        { name: '命中机构', type: 'map', geoIndex: 0, data: Object.keys(byDist).map(function (k) {
            return { name: k, value: byDist[k] };
          }) },
        {
          name: '机构点位', type: 'effectScatter', coordinateSystem: 'geo', zlevel: 2,
          symbolSize: function (v) { return v[2] === '三级' ? 7 : v[2] === '二级' ? 5 : 3; },
          rippleEffect: { period: 4, scale: 2.6, brushType: 'stroke' },
          itemStyle: { color: function (v) {
            return v[2] === '三级' ? CRIT : v[2] === '二级' ? WARN : ACC2;
          }, cursor: 'pointer' },
          showEffectOn: 'render',
          data: pts.map(function (r) {
            return { name: r.name, value: [r.lng, r.lat, r.level || '其他'], instId: r.id, inst: r };
          }),
          tooltip: Object.assign({ trigger: 'item', formatter: scatterTipFmt }, TIP),
        },
      ],
    }, true);

    if (diag) {
      diag.style.display = pool.length ? 'none' : '';
      if (!pool.length) diag.textContent = '暂无命中点位';
      else diag.textContent = '命中 ' + TOTAL.toLocaleString() + ' 家 · 地图展示其中 ' + pts.length + ' 家';
      diag.style.opacity = '.7';
    }
  }

  function hoverRow(id, on) {
    if (!CH) return;
    var i = SCATTER[String(id)];
    if (i == null) return;
    try {
      CH.dispatchAction({ type: on ? 'highlight' : 'downplay', seriesIndex: 1, dataIndex: i });
      CH.dispatchAction(on ? { type: 'showTip', seriesIndex: 1, dataIndex: i } : { type: 'hideTip' });
    } catch (e) { }
  }
  function hoverMap(id, on) {
    var key = String(id);
    if (on && HOVER === key) return;
    if (!on && HOVER !== key) return;
    HOVER = on ? key : null;
    var e = ROW_EL[key];
    if (!e) return;
    e.classList.toggle('hl', !!on);
    if (on && e.scrollIntoView) { try { e.scrollIntoView({ block: 'nearest' }); } catch (err) { } }
  }

  // --------------------------------------------------------------------------
  //  数据来源说明（每个数字都可追溯）
  // --------------------------------------------------------------------------
  function renderSource(host, ds) {
    if (!host) return;
    ds = ds || offlineSourceNote();
    host.innerHTML =
      '<h3>数据来源与口径说明 <span class="tag">SOURCE</span></h3>' +
      '<div class="nlqsrc-grid">' +
        '<div class="ibox"><div class="k">数据来源</div><div class="v">' + esc(ds.database || '—') + '</div></div>' +
        '<div class="ibox"><div class="k">机构记录</div><div class="v">' +
          (ds.institutions == null ? '—' : Number(ds.institutions).toLocaleString()) + ' 条</div></div>' +
        '<div class="ibox"><div class="k">数据快照</div><div class="v">' + esc(ds.batch_date || '—') + '</div></div>' +
        '<div class="ibox"><div class="k">源文件组合</div><div class="v">' +
          (ds.source_files == null ? '—' : Number(ds.source_files).toLocaleString()) + ' 种</div></div>' +
      '</div>' +
      '<div class="nlqsrc-detail">' + esc(ds.detail || '') + '</div>' +
      (ds.note ? '<div class="nlqsrc-note">' + svgIcon('warn') + ' ' + esc(ds.note) + '</div>' : '');
  }

  // --------------------------------------------------------------------------
  //  条件筛选通道：控件 → 条件
  // --------------------------------------------------------------------------
  function fillSelect(id, opts, firstLabel) {
    var s = el(id); if (!s) return;
    s.innerHTML = '<option value="">' + esc(firstLabel) + '</option>' +
      (opts || []).map(function (o) { return '<option value="' + esc(o) + '">' + esc(o) + '</option>'; }).join('');
  }

  function buildCondControls() {
    var lex = (window.NLQ && NLQ.lex) || null;
    var meta = (DATA && DATA.meta) || {};
    var districts = lex ? lex.districts : (meta.districts || []).map(function (d) { return d.district; });
    var levels = lex ? lex.levels : ['三级', '二级', '一级', '未定级'];
    var cats = lex ? lex.categories : (meta.categories || []).map(function (c) { return c.category; });
    var owns = lex ? lex.ownerships : ['公立', '民营', '未标注'];
    var srcs = lex ? lex.source_rules.map(function (r) { return r.label; }) : [];

    fillSelect('q_district', districts, '全部行政区');
    fillSelect('q_level', levels, '全部等级');
    fillSelect('q_cat', cats, '全部机构类型');
    fillSelect('q_own', owns, '全部所有制');
    fillSelect('q_source', srcs, '全部数据来源');
    var srt = el('q_sort');
    if (srt) {
      var labels = (lex && lex.sort_label) || (typeof SORT_LABEL !== 'undefined' ? SORT_LABEL : {});
      srt.innerHTML = ['score', 'distance', 'level', 'depts', 'name'].map(function (k) {
        return '<option value="' + k + '">' + esc(labels[k] || k) + '</option>';
      }).join('');
    }
  }

  // 从界面控件收条件
  function collectCond() {
    var c = {};
    var d = el('q_district'), l = el('q_level'), t = el('q_cat'), o = el('q_own'),
        s = el('q_source'), k = el('q_kw'), so = el('q_sort');
    if (d && d.value) c.district = [d.value];
    if (l && l.value) c.level = [l.value];
    if (t && t.value) c.category = [t.value];
    if (o && o.value) c.ownership = [o.value];
    if (s && s.value) {
      // 下拉里给的是人类可读的 label，转回内部 key
      var lex = (window.NLQ && NLQ.lex) || null;
      var rules = lex ? lex.source_rules : [];
      var hit = rules.filter(function (r) { return r.label === s.value; })[0];
      c.source = [hit ? hit.key : s.value];
    }
    if (k && (k.value || '').trim()) c.kw = k.value.trim();
    if (so && so.value && so.value !== 'score') c._sort = so.value;
    return c;
  }

  // 把条件回填到控件（删除条件卡片后保持界面与状态一致）
  function syncCondControls() {
    var lex = (window.NLQ && NLQ.lex) || null;
    var rules = lex ? lex.source_rules : [];
    var set = function (id, v) { var e = el(id); if (e) e.value = v || ''; };
    set('q_district', (COND.district || []).join(','));
    set('q_level', (COND.level || [])[0]);
    set('q_cat', (COND.category || [])[0]);
    set('q_own', (COND.ownership || [])[0]);
    var sk = (COND.source || [])[0];
    var r = rules.filter(function (x) { return x.key === sk; })[0];
    set('q_source', r ? r.label : (sk || ''));
    set('q_kw', COND.kw || '');
    set('q_sort', COND._sort || 'score');
  }

  function resetCondControls() {
    ['q_district', 'q_level', 'q_cat', 'q_own', 'q_source', 'q_kw'].forEach(function (id) {
      var e = el(id); if (e) e.value = '';
    });
    var s = el('q_sort'); if (s) s.value = 'score';
  }

  // --------------------------------------------------------------------------
  //  标签页
  // --------------------------------------------------------------------------
  function switchTab(name) {
    Array.prototype.forEach.call(document.querySelectorAll('#nlq_tabs .nlqtab'), function (b) {
      var on = b.getAttribute('data-ntab') === name;
      b.classList.toggle('active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    var a = el('nlq_pane_nl'), b2 = el('nlq_pane_cond');
    if (a) a.classList.toggle('active', name === 'nl');
    if (b2) b2.classList.toggle('active', name === 'cond');
  }

  // --------------------------------------------------------------------------
  //  事件绑定
  // --------------------------------------------------------------------------
  function bind() {
    Array.prototype.forEach.call(document.querySelectorAll('#nlq_tabs .nlqtab'), function (b) {
      b.addEventListener('click', function () { switchTab(b.getAttribute('data-ntab')); });
    });

    var input = el('f_ai'), run = el('btn_ai'), clr = el('btn_ai_clear');
    if (run) run.addEventListener('click', submitNL);
    if (input) {
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); submitNL(); }
      });
      input.addEventListener('input', function () {
        if (clr) clr.style.display = input.value ? '' : 'none';
      });
    }
    if (clr) clr.addEventListener('click', function () {
      if (input) input.value = '';
      clr.style.display = 'none';
      if (input) input.focus();
    });

    // 语音输入（仅 localhost，Web Speech 在 file:// 与 https 分享页不可用）
    var mic = el('btn_voice_ai');
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (mic && SR) {
      mic.addEventListener('click', function () {
        if (!(window.ENV && ENV.http && LOCAL_HOST)) {
          toast(svgIcon('warn') + ' 语音输入需要在本机 http://localhost:5001 下使用');
          return;
        }
        var rec = new SR();
        rec.lang = 'zh-CN'; rec.interimResults = false; rec.maxAlternatives = 1;
        mic.classList.add('on');
        rec.onresult = function (ev) {
          var t = ev.results[0][0].transcript || '';
          if (input) input.value = t;
          submitNL();
        };
        rec.onerror = function () { toast(svgIcon('warn') + ' 语音识别未成功，请改用键盘输入'); };
        rec.onend = function () { mic.classList.remove('on'); };
        try { rec.start(); toast('请开始说话…'); } catch (e) { mic.classList.remove('on'); }
      });
    } else if (mic) {
      mic.addEventListener('click', function () {
        toast(svgIcon('warn') + ' 当前浏览器不支持语音识别，请改用键盘输入');
      });
    }

    var qrun = el('q_run'), qreset = el('q_reset');
    if (qrun) qrun.addEventListener('click', function () {
      var c = collectCond();
      if (!Object.keys(c).length) { toast(svgIcon('warn') + ' 请至少选择 1 个条件'); return; }
      COND = c;
      execute({ conditions: c });
    });
    if (qreset) qreset.addEventListener('click', function () {
      resetCondControls(); COND = {}; CUR = null;
      renderReply({ ok: false, message: '条件已重置，请重新选择。' }, null);
      renderResult(null); renderStats(null);
    });

    var pv = el('nlq_prev'), nx = el('nlq_next');
    if (pv) pv.addEventListener('click', function () { turnPage(-1); });
    if (nx) nx.addEventListener('click', function () { turnPage(1); });

    var go = el('nlq_goto_inst');
    if (go) go.addEventListener('click', handoffToInstitutions);
  }

  function submitNL() {
    var input = el('f_ai');
    var q = input ? (input.value || '').trim() : '';
    if (!q) { toast(svgIcon('warn') + ' 请先描述您想查找的机构条件'); if (input) input.focus(); return; }
    execute({ q: q });
  }

  function turnPage(d) {
    var totalPg = Math.max(1, Math.ceil(TOTAL / PAGE_SIZE));
    var np = Math.min(totalPg, Math.max(1, PAGE + d));
    if (np === PAGE) return;
    PAGE = np;
    if (ALL) { renderListPage(); drawMap(CUR); }
    else if (backend()) {
      // 联网形态每页单独向后端取（分页在数据库侧完成，不在前端切片）
      jsonPost('/api/nlq/query', { conditions: Object.assign({}, COND, { _page: PAGE, _page_size: PAGE_SIZE }) })
        .then(function (res) {
          if (!res || res.ok === false) return;
          CUR = res; renderListPage(); drawMap(CUR);
        });
    }
    scrollTo(el('nlq_list'));
  }

  // 把当前条件交给「机构查询」页继续操作（那边有完整的排序 / 对比 / 收藏 / 分页）
  function handoffToInstitutions() {
    if (!COND || !Object.keys(COND).length) { toast(svgIcon('warn') + ' 请先执行一次筛选'); return; }
    var set = function (id, v) { var e = el(id); if (e) e.value = v || ''; };
    set('f_district', (COND.district || [])[0]);
    set('f_level', (COND.level || [])[0]);
    set('f_cat', (COND.category || [])[0]);
    set('f_kw', COND.kw || '');
    if (typeof setSort === 'function' && COND._sort) setSort(COND._sort, null, true);
    switchView('institutions');
    try { PAGE = 1; applyFilter(); } catch (e) { }
    toast(svgIcon('ok') + ' 已把当前条件带到「机构查询」页');
  }

  function scrollTo(node) {
    if (!node || !node.scrollIntoView) return;
    try { node.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) { }
  }

  // --------------------------------------------------------------------------
  //  生命周期
  // --------------------------------------------------------------------------
  // 词表装载：优先用构建时内联的 window.__NLQ_LEX__（单文件形态），
  // 其次找同目录的 nlq_lexicon.json（本地开发用），两者都没有就退回受限的默认词表。
  // 注意：nlq_lexicon.json 的外层是 {meta, lex}（meta 记录生成时间与来源文件，便于追溯），
  // 真正的词表在 .lex 里——两处都要解包，否则 NLQ.init 会拿到一个空壳。
  function unwrap(p) { return (p && p.lex) ? p.lex : p; }

  function ensureLex() {
    if (!window.NLQ) return Promise.resolve(false);
    if (window.__NLQ_LEX__) { NLQ.init(unwrap(window.__NLQ_LEX__)); return Promise.resolve(true); }
    if (NLQ.lex) return Promise.resolve(true);
    return fetch('nlq_lexicon.json')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j) { NLQ.init(unwrap(j)); return true; } return false; })
      .catch(function () { return false; });
  }

  function init() {
    if (INITED) return;
    INITED = true;
    ensureLex().then(function (ok) {
      if (!ok) console.warn('[NLQ_UI] 未找到自然语言词表，离线解析能力受限');
      buildCondControls();
      bind();
      boot();
    });
  }

  function boot() {
    var qb = el('nlq_examples');
    if (qb) {
      qb.innerHTML = EXAMPLES.map(function (t) {
        return '<button class="chip acc" type="button" data-ex="' + esc(t) + '">' + esc(t) + '</button>';
      }).join('');
      qb.addEventListener('click', function (e) {
        var b = e.target && e.target.closest ? e.target.closest('[data-ex]') : null;
        if (!b) return;
        var input = el('f_ai');
        if (input) input.value = b.getAttribute('data-ex');
        switchTab('nl');
        submitNL();
      });
    }
    var scope = el('nlq_scope');
    if (scope) {
      var note = (window.NLQ && NLQ.lex && NLQ.lex.scope_note) ||
        'AI 只负责理解中文描述并生成结构化筛选条件；所有数字来自数据库真实查询结果。';
      scope.innerHTML = svgIcon('warn') + ' ' + esc(note) +
        ' <b>本系统不提供疾病诊断、用药建议或就诊推荐。</b>';
    }
    renderResult(null);
    renderStats(null);
  }
  function enter() {
    init();
    if (!ENTERED) {
      ENTERED = true;
      setTimeout(function () { drawMap(CUR); }, 80);
    } else {
      setTimeout(function () { try { if (CH) CH.resize(); } catch (e) { } }, 80);
    }
  }

  function resize() { if (CH) { try { CH.resize(); } catch (e) { } } if (STAT_CHART) { try { STAT_CHART.resize(); } catch (e) { } } }

  // 主题切换后必须按新令牌重绘（ECharts 读不到 CSS 变量）
  function redraw() { if (CH) drawMap(CUR); if (STAT_CHART && CUR && CUR.intent === 'stats') renderStats(CUR); }

  return {
    init: init, enter: enter, resize: resize, redraw: redraw,
    run: execute,
    get conditions() { return COND; },
    get result() { return CUR; },
  };
})();

window.__NLQ_UI__ = NLQ_UI;
window.__NLQ_RESIZE__ = function () { NLQ_UI.resize(); };
