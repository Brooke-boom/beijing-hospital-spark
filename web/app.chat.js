// ============================================================================
//  悬浮球智能问答窗口（2026-10-18 重构）—— 单文件形态的 AI 问答界面层
// ----------------------------------------------------------------------------
//  定位（用户拍板）：
//    悬浮球的「智能筛选」窗口不再显示条件卡片 / 结果列表 / 地图 —— 只做
//    「用户提问 → AI 回答」的聊天窗口，AI 一律走 Agnes（OpenAI 兼容接口）。
//
//  防幻觉三层设计（与 /api/ai/chat 的提示词配套，缺一层就会被答辩追问打穿）：
//    ① 拒答在本地：NLQ.parse 判定病征 / 空输入 → 直接给拒答气泡，不进模型；
//    ② 事实在本地：同一句话先用 NLQ 引擎（与 nlq.py 逐字段同源）真实查一遍，
//       把机构清单 / 维度统计拼成 facts 交给模型 —— 数字与机构名全部来自查询，
//       模型只负责组织语言，不产出任何事实；
//    ③ 兜底在本地：后端不可达（file:// / Pages）或未配 Agnes 密钥 / 限流时，
//       降级为本地模板回答，气泡明确标注「离线模板」，绝不冒充 AI 生成。
// ============================================================================
'use strict';

var CHAT = (function () {
  var INITE = false, ENTERED = false, BUSY = false;
  var AI_ON = null;            // null=未探测 / true=Agnes 可用 / false=走本地模板
  var HISTORY = [];            // {role, content} 最近 6 条随请求带给模型
  var LOG = null;

  var EXAMPLES = [
    '海淀区的三级医院有哪些？',
    '开设有骨科的机构，按距离从近到远',
    '按行政区统计三级医院的数量',
    '朝阳区的社区卫生服务中心',
    '北京航空航天大学附近有医学影像科的机构',
  ];

  function el(id) { return document.getElementById(id); }
  function backend() { return !!(window.ENV && ENV.api); }
  // http(s) 页面才谈得上探测后端；file:// 一律离线模板
  function httpPage() { return location.protocol === 'http:' || location.protocol === 'https:'; }
  // 局部改名 hesc，避免遮蔽 app.js 的全局 esc；两套实现产出一致
  function hesc(s) { return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

  // 科室词表（与 app.nlq.ui.js 的 deptNames 同口径：离线形态给快照 meta）
  function deptNames() {
    var meta = (window.DATA && DATA.meta) || {};
    var ds = meta.depts || [];
    return ds.map(function (d) { return d.dept_name || d; }).filter(Boolean);
  }
  function basePoint() {
    return (typeof window.curBase === 'function') ? curBase() : null;
  }

  // --------------------------------------------------------------------------
  //  气泡渲染
  // --------------------------------------------------------------------------
  function addMsg(kind, html, meta) {
    if (!LOG) return;
    var b = document.createElement('div');
    b.className = 'chatmsg ' + kind;
    var inner = '<div class="chatwho">' + (meta || '') + '</div>' +
      '<div class="chatbody">' + html + '</div>';
    b.innerHTML = inner;
    LOG.appendChild(b);
    LOG.scrollTop = LOG.scrollHeight;
    return b;
  }
  function multiline(txt) {
    return hesc(txt).replace(/\n+/g, '<br>');
  }
  function typing() {
    return addMsg('ai wait', '<span class="chatdots"><i></i><i></i><i></i></span> 正在查询真实数据…', '…');
  }
  function welcome() {
    addMsg('sys',
      '在这里用一句话提问，AI 会基于平台<b>真实查询结果</b>回答机构分布、等级、科室等问题。<br>' +
      '系统只提供机构资源数据：不做疾病诊断、症状推断与用药建议。', '边界说明');
    addMsg('ai', '你好，我是本平台的 AI 问答助手（Agnes）。试试下面的问题，或直接输入你想找的机构条件。', 'AI');
  }

  function setStatus() {
    var dot = el('ai_dot'), txt = el('ai_status');
    if (!dot || !txt) return;
    if (AI_ON === true) { txt.textContent = 'Agnes 已连接'; dot.className = 'chatdot on'; }
    else if (AI_ON === false) { txt.textContent = '离线模板 · 未接入大模型'; dot.className = 'chatdot off'; }
    else { txt.textContent = '连接检测中…'; dot.className = 'chatdot'; }
  }

  // Agnes 探活：不发起真实推理（?probe=1 才会），只问密钥与开关状态。
  // file:// 下 fetch 直接失败 → 离线模板，与旧版门禁行为一致。
  function probe() {
    // 注意：ENV.api 是布尔且**异步**才就绪 —— init 时可能还没完成，所以 ask()
    // 前会重探一次（/api/ai/health 是轻接口，无推理开销）。file:// 直接离线。
    if (!httpPage()) { AI_ON = false; setStatus(); return Promise.resolve(false); }
    return fetch('/api/ai/health')
      .then(function (r) { return r.json(); })
      .then(function (j) { AI_ON = !!(j && j.ok && j.llm_enabled); setStatus(); return AI_ON; })
      .catch(function () { AI_ON = false; setStatus(); return false; });
  }

  // --------------------------------------------------------------------------
  //  本地引擎：把同一句话真实查一遍，产出 facts（防幻觉的根基）
  // --------------------------------------------------------------------------
  function localRun(q) {
    var parsed = window.NLQ.parse(q, deptNames());
    if (parsed && parsed.intent === 'unsupported') {
      return { refuse: true, message: parsed.message || '这句里没有可执行的机构条件。' };
    }
    var cond = parsed.conditions || {};
    if (parsed.intent === 'stats') {
      var st = window.NLQ.runStats(DATA.institutions, cond, parsed.dimension || 'district', basePoint());
      return { intent: 'stats', parsed: parsed, st: st,
               total: st.rows.reduce(function (a, b) { return a + (b.cnt || 0); }, 0) };
    }
    var r = window.NLQ.runFilter(DATA.institutions, cond, 1, 1e9, basePoint());
    return { intent: 'filter', parsed: parsed, r: r, total: r.total || 0 };
  }

  // facts 文本（服务端截断在 4000 字符，前端控制在 ~2600 以内）
  function buildFacts(res) {
    var lines = [];
    // 解析说明（检查词映射 / 就近参照）与参照点基准先交给模型，让它如实转述
    if (res.parsed && res.parsed.notice) lines.push(res.parsed.notice);
    if (res.r && res.r.near_note) lines.push(res.r.near_note);
    if (res.st && res.st.near_note) lines.push(res.st.near_note);
    if (res.intent === 'stats') {
      lines.push('维度统计（' + (res.st.label || res.st.dimension) + '），共 ' + res.total + ' 家命中：');
      res.st.rows.slice(0, 20).forEach(function (row) {
        lines.push('- ' + (row.name || row.label || row.key) + '：' + row.cnt + ' 家');
      });
    } else {
      var items = res.r.all || res.r.items || [];
      lines.push('共命中 ' + res.total + ' 家' + (res.r.sort ? '（排序：' + res.r.sort + '）' : '') + '，按当前排序前 10 家：');
      items.slice(0, 10).forEach(function (x, i) {
        lines.push((i + 1) + '. ' + x.name + '｜' + (x.district || '—') + '｜' +
          (x.level || '未定级') + '｜' + (x.category || '—') +
          (x.addr ? '｜地址：' + x.addr : ''));
      });
    }
    return lines.join('\n');
  }

  // 本地模板回答（与 AI 同样的素材、同样的边界，只是措辞是模板）
  function localAnswer(res) {
    // 解析说明（检查词映射 EXAM_NOTICE）与就近参照说明放最前面，如实转述
    var pre = [];
    if (res.parsed && res.parsed.notice) pre.push(res.parsed.notice);
    if (res.r && res.r.near_note) pre.push(res.r.near_note);
    if (res.st && res.st.near_note) pre.push(res.st.near_note);
    var head = pre.length ? pre.join('\n') + '\n' : '';
    var applied = (res.parsed && (res.parsed.applied || (window.NLQ.describe ? NLQ.describe(res.parsed.conditions || {}) : []))) || [];
    var condTxt = applied.map(function (a) {
      var v = Array.isArray(a.values) ? a.values.join(' / ') : (a.values || a.value || '');
      return a.label + '：' + v;
    }).join('；');
    if (res.intent === 'stats') {
      // st.summary 是引擎（nlq.py 同源）生成的统计摘要，直接复用，不另造口径
      var s = res.st.summary || '';
      var valid = res.st.rows.filter(function (r) { return r.cnt; });
      var rows = valid.slice(0, 8)
        .map(function (r) { return ((r.name || r.label || r.key)) + ' ' + r.cnt + ' 家'; }).join('，');
      return head + (s ? s + '\n' : '') + '明细：' + rows +
        (valid.length > 8 ? ' 等。' : '。') +
        '\n以上数字来自平台对真实数据的本次查询。';
    }
    var items = res.r.all || res.r.items || [];
    if (!res.total) {
      return head + '按' + (condTxt ? '条件（' + condTxt + '）' : '你的描述') + '没有查到匹配机构。' +
        '可以放宽条件试试：去掉行政区、放宽等级，或改用更常见的科室名。\n以上为平台真实查询结果。';
    }
    var top = items.slice(0, 5).map(function (x, i) {
      return (i + 1) + '. ' + x.name + '（' + (x.district || '—') + '·' + (x.level || '未定级') + '）';
    }).join('　');
    return head + '按' + (condTxt ? '条件（' + condTxt + '）' : '你的描述') + '共命中 ' + res.total + ' 家。' +
      (res.r.sort && res.r.sort.indexOf('dist') === 0 ? '按距离从近到远，' : '') +
      '排名靠前的有：' + top + '。\n以上数字与机构名来自平台真实查询，完整列表可在「机构查询」页按相同条件查看。';
  }

  // --------------------------------------------------------------------------
  //  主流程：提问 → 拒答/查询 → Agnes 或模板
  // --------------------------------------------------------------------------
  function ask(q) {
    q = String(q || '').trim().slice(0, 500);
    if (!q || BUSY) return Promise.resolve(null);
    addMsg('user', multiline(q));
    BUSY = true;
    var send = el('ai_send'); if (send) { send.disabled = true; }

    // 每次提问前重探：ENV.api 是异步就绪的，enter() 那次探测可能还没轮到
    var ready = httpPage() ? probe() : Promise.resolve(AI_ON = false);
    return ready.then(function () {
      var res;
      try { res = localRun(q); }
      catch (e) {
        BUSY = false; if (send) send.disabled = false;
        addMsg('sys', '本地查询出错：' + hesc(e && e.message || e));
        return null;
      }
      if (res.refuse) {                                   // ① 病征 / 空条件：本地拒答，不进模型
        BUSY = false; if (send) send.disabled = false;
        addMsg('refuse', multiline(res.message), '边界拒答');
        if (window.updateFabBadge) updateFabBadge(null);
        return null;
      }
      var facts = buildFacts(res);
      var t = typing();
      var done = function (html, meta) {
        if (t && t.parentNode) t.parentNode.removeChild(t);
        addMsg('ai', html, meta);
        BUSY = false; if (send) send.disabled = false;
        if (window.updateFabBadge) updateFabBadge(res.total);
      };
      if (AI_ON !== true) {                               // ③ 离线 / 未配密钥：本地模板兜底
        var la = localAnswer(res);
        done(multiline(la), '离线模板 · 未接入大模型');
        HISTORY.push({ role: 'user', content: q }, { role: 'assistant', content: la });
        HISTORY = HISTORY.slice(-6);
        return null;
      }
      return jsonPost('/api/ai/chat', {
        mode: 'data', question: q, facts: facts, history: HISTORY,
      }).then(function (j) {
        if (j && j.ok && j.reply) {
          done(multiline(j.reply),
            hesc(j.model || 'Agnes') + (j.cached ? ' · 缓存' : '') + ' · 仅基于真实查询结果');
          HISTORY.push({ role: 'user', content: q }, { role: 'assistant', content: j.reply });
          HISTORY = HISTORY.slice(-6);
          return j;
        }
        if (j && j.reason === 'llm_rate_limited') {
          done('Agnes 免费额度限流（约 1 次 / 30 秒），稍等片刻再试；相同问题命中缓存后秒回。<br>' +
            '<b>本次的真实查询结果：</b><br>' + multiline(localAnswer(res)), '限流提示 · 附本地结果');
          return j;
        }
        done(multiline(localAnswer(res)),
          '离线模板 · ' + ((j && j.hint) ? hesc(j.hint) : 'AI 暂不可用'));   // llm_disabled 等
        return j;
      }).catch(function (e) {
        done(multiline(localAnswer(res)), '离线模板 · AI 连接失败');
        return null;
      });
    });
  }

  function jsonPost(url, body) {
    return fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    }).then(function (r) { return r.json().catch(function () { return null; }); });
  }

  // --------------------------------------------------------------------------
  //  初始化与进入
  // --------------------------------------------------------------------------
  function init() {
    if (INITE) return; INITE = true;
    LOG = el('ai_log');
    var input = el('ai_in'), send = el('ai_send');
    welcome();
    if (send) send.addEventListener('click', function () {
      var v = input.value; input.value = ''; ask(v).then(function(){ input.focus(); });
    });
    if (input) input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); var v = input.value; input.value = ''; ask(v); }
    });
    var box = el('ai_ex');
    if (box) box.addEventListener('click', function (e) {
      var b = e.target && e.target.closest ? e.target.closest('[data-q]') : null;
      if (b) ask(b.getAttribute('data-q'));
    });
    var clr = el('ai_clear');
    if (clr) clr.addEventListener('click', function () {
      LOG.innerHTML = ''; HISTORY = []; welcome();
      if (window.updateFabBadge) updateFabBadge(null);
    });
    probe();
  }

  function enter() {
    if (!INITE) init();
    ENTERED = true;
    var input = el('ai_in');
    setTimeout(function () { if (input) input.focus(); }, 80);
  }

  window.__CHAT__ = { enter: enter, ask: ask, clear: function () { if (el('ai_clear')) el('ai_clear').click(); } };
  if (typeof module !== 'undefined' && module.exports) module.exports = { CHAT: CHAT };
  return { enter: enter, ask: ask };
})();
