// ============================================================================
//  北京市医院医疗资源整合与多维筛选可视化系统 — 交互式 SPA
//  数据来源：window.__SNAPSHOT__（内嵌）或 snapshot_data.json（HTTP）
//  设计原则：离线优先。file:// 打开时全功能降级但绝不报错、绝不发网络请求。
// ============================================================================
'use strict';

// ---------- 设计令牌（与 dashboard.html 的 CSS 变量保持一致） ----------
const BG = '#0a0b0d', PANEL = '#131419', PANEL2 = '#171922', EDGE = 'rgba(255,255,255,.08)';
const INK = '#ededee', SUB = '#a0a2aa', DIM = '#73757e', FAINT = '#4c4e57';
const ACC = '#6b8cff', ACC2 = '#46c08a', WARN = '#e0a23b', CRIT = '#e0697e', VIO = '#9a8cf0', PINK = '#e69ab5';

const ICONS = {
  'overview': 'M4 4h7v7H4zM11 4h9v4h-9zM11 10h9v10h-9zM4 13h7v7H4z',
  'analytics': 'M4 20V10M9 20V4M14 20v-7M19 20v-12',
  'triage': 'M3 12h4l2-6 4 12 2-6h6',
  'admin': 'M3 4h18v12H3zM3 16l3 4h12l3-4M9 20h6',
  'about': 'M12 3a9 9 0 100 18 9 9 0 000-18zM12 10v6M12 7.5h.01',
  'hospital': 'M4 21V6l8-3 8 3v15M9 21v-4h6v4M12 8v5M9.5 10.5h5',
  'location': 'M12 21s7-6.5 7-12a7 7 0 10-14 0c0 5.5 7 12 7 12zM12 9a3 3 0 100 6 3 3 0 000-6z',
  'brain': 'M9 9h6v6H9zM4 10v4M20 10v4M10 4h4M10 20h4M6.5 7.5L4 9M17.5 7.5L20 9M6.5 16.5L4 15M17.5 16.5L20 15',
  'phone': 'M5 4h3l2 5-2 1a11 11 0 005 5l1-2 5 2v3a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2z',
  'compass': 'M12 3a9 9 0 100 18 9 9 0 000-18zM15.5 8.5l-2 5-5 2 2-5z',
  'clipboard': 'M9 4h6v2H9zM6 6h12v14H6z',
  'metro': 'M7 4h10a3 3 0 013 3v8a3 3 0 01-3 3H7a3 3 0 01-3-3V7a3 3 0 013-3zM7 14h10M9 17l-2 3M15 17l2 3M9 11h.01M15 11h.01',
  'parking': 'M6 4h8a4 4 0 010 8H9v8H6zM9.5 7.5H13a2.5 2.5 0 010 5H9.5',
  'bus': 'M5 5h14a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2zM5 11h14M8 17v2M16 17v2M8.5 14h.01M15.5 14h.01',
  'warn': 'M12 3l9 16H3zM12 9v5M12 16.5h.01',
  'err': 'M12 3a9 9 0 100 18 9 9 0 000-18zM9 9l6 6M15 9l-6 6',
  'ok': 'M12 3a9 9 0 100 18 9 9 0 000-18zM8.5 12l2.5 2.5 4.5-5',
  'close': 'M6 6l12 12M18 6L6 18',
  'gov': 'M3 21h18M4 21V10l8-5 8 5v11M9 21v-6h6v6M12 5v-2',
  'folder': 'M3 6h6l2 2h10v11H3z',
  'map': 'M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14',
  'user': 'M12 12a4 4 0 100-8 4 4 0 000 8zM5 21a7 7 0 0114 0',
  'flask': 'M9 3h6M10 3v6l-5 9a2 2 0 002 3h10a2 2 0 002-3l-5-9V3M7.5 15h9'
};
function svgIcon(name) {
  var p = ICONS[name];
  if (!p) return '';
  return '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + p + '</svg>';
}


const BASE_POINTS = {
  tiananmen:       { name: '天安门',   lng: 116.397, lat: 39.909 },
  capital_airport: { name: '首都机场', lng: 116.609, lat: 40.080 },
  daxing_airport:  { name: '大兴机场', lng: 116.411, lat: 39.510 },
  geo:             { name: '我的位置', lng: null,    lat: null },
};
const LEVEL_RANK = { '三级': 4, '二级': 3, '一级': 2, '未定级': 1 };
// 等级配色：全局唯一口径，禁止靠数组下标隐式配色（排序一变颜色就错位，把「一级」染成红色）
const LV_COLOR = { '三级': '#e0697e', '二级': '#e0a23b', '一级': '#6b8cff', '未定级': '#9a8cf0', '不适用': '#73757e' };
const W_LEVEL = 0.5, W_DIST = 0.3, W_DEPT = 0.2;
const DASHBOARD_VERSION = 'v4.0-ui-refresh-20260911';
const GUAhAO_114 = 'https://www.114yygh.com/';

// ---------- 全局状态 ----------
let DATA = null;
let FILTERED = [];
let PAGE = 1, PAGE_SIZE = 20;
const PICKED = new Set();                 // 对比已选机构 id（最多 3）
const PICK_MAX = 3;
const ENV = {
  http: location.protocol === 'http:' || location.protocol === 'https:',
  api: false,          // /api/health 探活结果
  amap: false,
};
const SID = 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

// 图表实例
let MAP_CHART, CH1, CH2, CH3;
let CH_OWN, CH_FEAT, CH_NET, CH_LVOWN, CH_TOPSP, CH_DEPTOP, CH_DISTLV, CH_COORD;
let A_KW, A_DIST, A_TRIAGE, A_DAILY, A_DENSITY, A_LEVEL, A_SPEC, A_NET, A_OWN, A_CAT;

// ============================================================================
//  0. 基础工具
// ============================================================================
const $ = id => document.getElementById(id);
function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function num(n) { return (n === null || n === undefined || n === '') ? '—' : Number(n).toLocaleString(); }
function pct(a, b) { return b ? (a / b * 100).toFixed(1) + '%' : '0%'; }
function trunc(s, n) { s = String(s || ''); return s.length > n ? s.slice(0, n) + '…' : s; }
function setText(id, v) { const e = $(id); if (e) e.textContent = v; }
let _toastT;
function toast(msg, ms) {
  const t = $('toast'); if (!t) return;
  t.innerHTML = msg; t.classList.add('show');
  clearTimeout(_toastT);
  _toastT = setTimeout(() => t.classList.remove('show'), ms || 3400);
}
// 埋点：只在有后端时上报，失败静默（埋点绝不能影响主流程）
function track(ev, k1, k2, n) {
  if (!ENV.http) return;
  try {
    const p = new URLSearchParams({ ev: ev, sid: SID });
    if (k1) p.set('k1', k1);
    if (k2) p.set('k2', k2);
    if (n !== undefined && n !== null) p.set('num', n);
    fetch('/api/track?' + p.toString(), { keepalive: true }).catch(() => {});
  } catch (e) { /* ignore */ }
}

// ECharts 统一主题片段
const AXIS = {
  axisLine: { lineStyle: { color: 'rgba(255,255,255,.14)' } },
  axisTick: { show: false },
  axisLabel: { color: '#8b8d96', fontSize: 10 },
  splitLine: { lineStyle: { color: 'rgba(255,255,255,.06)' } },
};
const TIP = {
  backgroundColor: 'rgba(19,20,25,.96)', borderColor: 'rgba(255,255,255,.14)', borderWidth: 1,
  textStyle: { color: INK, fontSize: 11.5 }, extraCssText: 'border-radius:9px;box-shadow:0 10px 30px -10px rgba(0,0,0,.8)',
};
const LEGEND = { textStyle: { color: SUB, fontSize: 10.5 }, itemWidth: 10, itemHeight: 10, itemGap: 12 };

// ============================================================================
//  1. 数据加载
// ============================================================================
function loadData() {
  try {
    if (window.__SNAPSHOT__) {
      DATA = window.__SNAPSHOT__;
      init();
      return;
    }
    fetch('snapshot_data.json').then(r => {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(d => { DATA = d; init(); }).catch(showLoadError);
  } catch (e) { showLoadError(e); }
}

function showLoadError(e) {
  const el = $('loading'); if (!el) return;
  el.classList.remove('hide');
  el.style.background = '#e0697e';
  el.innerHTML = svgIcon('err') + ' 数据加载失败：' + esc(e && e.message ? e.message : e) +
    ' &nbsp;·&nbsp; 请硬刷新（Mac <b>Cmd+Shift+R</b> / Win <b>Ctrl+F5</b>）' +
    '；或改用离线单文件 <code>web/dashboard_offline.html</code>';
}

// ============================================================================
//  2. 初始化
// ============================================================================
function init() {
  try {
    $('loading').classList.add('hide');
    setText('m_total', DATA.total.toLocaleString());
    setText('m_time', DATA.snapshot_time);
    setText('m_time2', DATA.snapshot_time);

    fillSelect('f_district', DATA.meta.districts.map(d => d.district), '全部 16 区');
    fillSelect('f_level', DATA.meta.levels.map(d => d.level), '全部等级');
    fillSelect('f_cat', DATA.meta.categories.map(d => d.category), '全部类型');
    fillSelect('f_dept', DATA.meta.depts.map(d => d.dept_name), '全部科室');
    fillSelect('t_district', DATA.meta.districts.map(d => d.district), '全部区域');
    fillSelect('t_level', DATA.meta.levels.map(d => d.level), '全部等级');

    bindEvents();
    initCharts();
    initAnalyticsCharts();
    initAdminCharts();
    initNav();
    initTriageChat();
    initDrawer();
    initCompare();
    initAIState();
    applyFilter();
    loadAbout();
  } catch (e) {
    console.error('[init] 失败:', e);
    setMapDiag('err', svgIcon('err') + ' 初始化失败：' + esc(e.message || e) + '<br>请打开浏览器 Console 查看详情');
  }
}

// 后端探活（离线版永不执行）
function initAIState() {
  const el = $('ai_state');
  if (!ENV.http) { if (el) el.innerHTML = 'AI 兜底 <b>离线模式</b>'; return; }
  fetch('/api/health', { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .then(j => {
      ENV.api = !!(j && j.status === 'ok');
      if (el) el.innerHTML = ENV.api
        ? ('后端连接 <b>正常</b> · ' + num(j.institutions) + ' 家')
        : '后端 <b>未连接</b>';
      if (ENV.api) renderAdmin();     // 后端可用才拉行为统计
    })
    .catch(() => { if (el) el.innerHTML = '后端 <b>未连接</b>'; });
}

function setMapDiag(cls, html) {
  const el = $('map_diag'); if (!el) return;
  el.className = cls === 'err' ? 'err' : '';
  el.innerHTML = html;
}

function fillSelect(id, opts, firstLabel) {
  const el = $(id); if (!el) return;
  el.innerHTML = '<option value="">' + firstLabel + '</option>' +
    opts.map(o => '<option value="' + esc(o) + '">' + esc(o) + '</option>').join('');
}

// ============================================================================
//  3. 事件绑定
// ============================================================================
let _kwT;
function bindEvents() {
  ['f_district', 'f_level', 'f_cat', 'f_dept', 'f_net', 'f_base', 'f_sort'].forEach(id => {
    const el = $(id); if (!el) return;
    el.addEventListener('input', () => { PAGE = 1; applyFilter(); });
    el.addEventListener('change', () => {
      PAGE = 1;
      if (id === 'f_district') { const v = el.value; if (v) track('filter_district', v); }
      if (id === 'f_dept') { const v = el.value; if (v) track('filter_dept', v); }
      if (id === 'f_level') { const v = el.value; if (v) track('filter_level', v); }
      if (id === 'f_net') { const v = el.value; if (v) track('filter_net', v); }
      applyFilter();
    });
  });
  // 关键词输入做防抖埋点（不干扰实时筛选）
  const kwEl = $('f_kw');
  kwEl.addEventListener('input', () => {
    PAGE = 1; applyFilter();
    clearTimeout(_kwT);
    _kwT = setTimeout(() => { const v = kwEl.value.trim(); if (v.length >= 2) track('search', v); }, 1100);
  });

  $('btn_reset').addEventListener('click', resetFilter);
  $('btn_clear_pick').addEventListener('click', clearPicks);

  const aiInput = $('f_ai');
  if (aiInput) aiInput.addEventListener('keydown', e => { if (e.key === 'Enter') applyNLQ(); });
  const bAi = $('btn_ai'); if (bAi) bAi.addEventListener('click', applyNLQ);
  const bAc = $('btn_ai_clear'); if (bAc) bAc.addEventListener('click', clearNLQ);

  $('pg_prev').addEventListener('click', () => { if (PAGE > 1) { PAGE--; renderList(); } });
  $('pg_next').addEventListener('click', () => { if (PAGE * PAGE_SIZE < FILTERED.length) { PAGE++; renderList(); } });
  $('pg_size').addEventListener('change', e => { PAGE_SIZE = +e.target.value; PAGE = 1; renderList(); });

  $('f_base').addEventListener('change', e => {
    if (e.target.value === 'geo' && (BASE_POINTS.geo.lng == null || BASE_POINTS.geo.lat == null)) locateMe();
  });

  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if ($('cmpwrap').classList.contains('show')) closeCompare();
    else if ($('drawer').classList.contains('show')) closeDrawer();
  });
}

function resetFilter() {
  $('f_kw').value = ''; $('f_district').value = ''; $('f_level').value = '';
  $('f_cat').value = ''; $('f_dept').value = ''; $('f_net').value = '';
  $('f_base').value = 'tiananmen'; $('f_sort').value = 'score';
  PAGE = 1; applyFilter();
}

// ============================================================================
//  4. 地理定位
// ============================================================================
function locateMe() {
  const btn = $('btn_locate');
  if (!navigator.geolocation) { toast(svgIcon('warn') + ' 当前浏览器不支持定位 API'); return; }
  if (!ENV.http) { toast(svgIcon('warn') + ' 需通过 http://localhost:5001 打开才能授权定位（file:// 被浏览器禁止）', 5200); return; }
  const old = btn.textContent;
  btn.disabled = true; btn.textContent = '⏳ 定位中…';
  navigator.geolocation.getCurrentPosition(
    pos => {
      const lng = +pos.coords.longitude.toFixed(6), lat = +pos.coords.latitude.toFixed(6);
      const acc = Math.round(pos.coords.accuracy);
      BASE_POINTS.geo.lng = lng; BASE_POINTS.geo.lat = lat;
      BASE_POINTS.geo.name = '我的位置(±' + acc + 'm)';
      const opt = $('opt_geo'); opt.disabled = false; opt.textContent = '已定位 · ' + BASE_POINTS.geo.name;
      $('f_base').value = 'geo';
      btn.textContent = '已定位';
      setTimeout(() => { btn.textContent = '重新定位'; btn.disabled = false; }, 1300);
      $('f_sort').value = 'distance';
      applyFilter();
      toast(svgIcon('location') + ' 已定位 ' + lng + ', ' + lat + '（±' + acc + 'm） · 已按距离升序排序', 5200);
      track('locate', null, null, acc);
    },
    err => {
      btn.textContent = old; btn.disabled = false;
      const m = { 1: '用户拒绝授权', 2: '位置不可用', 3: '请求超时' }[err.code] || err.message;
      toast(svgIcon('warn') + ' 定位失败：' + m + ' —— 请确认浏览器允许位置权限', 5200);
    },
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
  );
}

// ============================================================================
//  5. 自然语言解析（规则引擎 + 可选大模型兜底）
// ============================================================================
if (typeof window.__AI_LLM_ON__ === 'undefined') window.__AI_LLM_ON__ = false;

const NLQ_DEPT_SYNONYMS = [
  ['心血管内科', ['心脏病', '心脏', '心血管', '心悸', '胸闷', '胸痛', '高血压', '血压高', '冠心病', '心梗', '心肌梗死', '心绞痛', '心律不齐', '房颤', '心衰', '心力衰竭']],
  ['呼吸内科', ['咳嗽', '咳喘', '哮喘', '肺炎', '肺病', '呼吸困难', '气喘', '支气管炎', '慢阻肺', '肺气肿', '喘不上气', '呼吸']],
  ['消化内科', ['胃病', '肠胃', '消化', '腹泻', '拉肚子', '腹痛', '肚子疼', '反酸', '胃溃疡', '肠胃炎', '便秘', '恶心', '呕吐', '消化不良']],
  ['神经内科', ['头痛', '头疼', '偏头痛', '头晕', '神经内科', '脑梗', '脑血栓', '中风', '偏瘫', '癫痫', '帕金森', '面瘫', '脑血管', '神经痛', '眩晕', '抽搐', '手脚麻木']],
  ['肾内科', ['肾病', '肾脏', '尿毒症', '肾炎', '肾功能', '蛋白尿', '肾衰']],
  ['内分泌科', ['糖尿病', '血糖', '内分泌', '甲亢', '甲状腺', '肥胖', '减肥', '痛风', '尿酸', '高血脂', '血脂']],
  ['血液内科', ['贫血', '白血病', '血友病', '血小板', '淋巴瘤', '血液病']],
  ['老年病科', ['老年病', '老年人', '老人']],
  ['普内科', ['内科', '感冒', '发烧', '发热', '普通内科']],
  ['全科医疗科', ['全科', '家庭医生']],
  ['普通外科', ['外科', '普外', '阑尾', '阑尾炎', '疝气', '胆囊', '胆结石', '外伤', '缝合']],
  ['骨科', ['骨折', '骨头', '腰椎', '颈椎', '关节', '腰痛', '腰疼', '腿疼', '脖子疼', '骨刺', '骨质疏松', '扭伤', '脱位', '脊柱', '半月板', '腰椎间盘', '关节炎']],
  ['神经外科', ['脑外科', '脑肿瘤', '脑外伤', '脑出血', '颅脑', '脑瘤']],
  ['心胸外科', ['心脏手术', '搭桥', '胸腔', '开胸', '心脏搭桥', '肺手术']],
  ['泌尿外科', ['泌尿', '结石', '肾结石', '前列腺', '尿频', '尿急', '尿路', '膀胱', '尿失禁']],
  ['肛肠外科', ['痔疮', '肛肠', '肛门', '便血', '肛裂', '肛瘘']],
  ['妇产科', ['妇科', '产科', '怀孕', '孕检', '生孩子', '月经', '白带', '妇科炎症', '子宫', '卵巢', '产检', '分娩', '孕妇', '备孕', '流产', '不孕']],
  ['儿科', ['儿科', '小孩', '儿童', '宝宝', '小儿', '孩子', '幼儿', '新生儿', '婴儿']],
  ['肿瘤科', ['肿瘤', '癌症', '癌', '化疗', '放疗', '恶性']],
  ['精神心理科', ['精神', '心理', '抑郁', '焦虑', '失眠', '神经衰弱', '心理咨询']],
  ['眼科', ['眼科', '眼睛', '近视', '视力', '白内障', '青光眼', '眼底', '红眼']],
  ['耳鼻咽喉科', ['耳鼻喉', '耳朵', '听力', '鼻炎', '咽炎', '扁桃体', '咽喉', '鼻子', '耳鸣', '中耳炎', '打鼾', '嗓子']],
  ['口腔科', ['牙科', '牙齿', '口腔', '洗牙', '补牙', '拔牙', '牙疼', '牙痛', '正畸', '种植牙', '牙医', '牙']],
  ['皮肤科', ['皮肤病', '皮肤', '湿疹', '过敏', '皮疹', '青春痘', '痤疮', '牛皮癣', '荨麻疹', '瘙痒', '皮炎']],
  ['中医内科', ['中医内科', '中医', '调理', '中药', '把脉', '气血']],
  ['中医骨伤科', ['中医骨科', '骨伤', '正骨', '跌打']],
  ['针灸推拿科', ['针灸', '推拿', '按摩', '拔罐', '艾灸', '针灸推拿']],
  ['感染科', ['感染', '传染病', '传染', '结核', '发热门诊']],
  ['肝病科', ['肝病', '肝炎', '乙肝', '丙肝', '肝硬化', '脂肪肝', '肝功能']],
  ['急诊科', ['急诊', '急救', '急症']],
  ['重症医学科', ['重症', '危重', '重症监护']],
  ['康复医学科', ['康复', '康复训练', '理疗', '康复科']],
];
const NLQ_LEVEL = [['三级', ['三级甲等', '三甲', '三级', '三等甲级']], ['二级', ['二级', '二甲']], ['一级', ['一级', '一甲', '社区医院']]];
const NLQ_CAT = [['妇幼保健', ['妇幼保健院', '妇产医院', '妇幼']], ['急救中心', ['急救中心', '急救站']],
                 ['体检中心', ['体检中心', '体检']], ['门诊部', ['门诊部']], ['诊所', ['诊所']], ['医院', ['医院']]];
const NLQ_SORT = [['distance', ['离家近', '离我近', '最近', '附近', '周边', '旁边', '距离近', '近一点']],
                  ['level', ['最好', '等级高', '评级高', '最强', '档次高']], ['depts', ['科室全', '科室多']]];
const NLQ_STOP = ['的', '了', '看', '找', '想', '要', '有', '吗', '啊', '呀', '呢', '我', '家', '去', '在', '和', '与', '或', '请', '帮', '推荐', '一下', '哪里', '哪个', '哪些', '什么', '怎么', '附近', '周边', '最近', '离家近', '离我近'];

function nlqBuildTable(pairs, includeSelf) {
  const t = [];
  pairs.forEach(([target, words]) => {
    if (includeSelf && target) t.push({ w: target, target: target });
    words.forEach(w => t.push({ w: w, target: target }));
  });
  t.sort((a, b) => b.w.length - a.w.length);
  return t;
}
let _NLQ_TABLES = null;
function nlqTables() {
  if (_NLQ_TABLES) return _NLQ_TABLES;
  _NLQ_TABLES = {
    dept: nlqBuildTable(NLQ_DEPT_SYNONYMS, true),
    level: nlqBuildTable(NLQ_LEVEL), cat: nlqBuildTable(NLQ_CAT), sort: nlqBuildTable(NLQ_SORT),
  };
  return _NLQ_TABLES;
}
function nlqMatch(table, text, used) {
  for (let i = 0; i < table.length; i++) {
    const item = table[i];
    const idx = text.indexOf(item.w);
    if (idx < 0) continue;
    const clash = used.some(u => !(idx + item.w.length <= u.s || idx >= u.e));
    if (clash) continue;
    return { target: item.target, word: item.w, index: idx, s: idx, e: idx + item.w.length };
  }
  return null;
}
function parseNLQ(raw) {
  const text = (raw || '').trim();
  const out = { district: '', level: '', cat: '', dept: '', sort: '', kw: '', hits: [], engine: 'rule' };
  if (!text) return out;
  const T = nlqTables();
  const used = [];
  const take = m => { if (m) { used.push({ s: m.s, e: m.e }); out.hits.push(m); } return m; };

  if (DATA && DATA.meta && DATA.meta.districts) {
    let best = null;
    DATA.meta.districts.forEach(d => {
      const full = d.district, short = full.replace(/[市区县]$/, '');
      [full, short].forEach(form => {
        const i = text.indexOf(form);
        if (i >= 0 && (!best || form.length > best.form.length)) best = { form: form, name: full, i: i };
      });
    });
    if (best) {
      out.district = best.name;
      used.push({ s: best.i, e: best.i + best.form.length });
      out.hits.push({ target: best.name, word: best.form, kind: 'district' });
    }
  }
  const lv = nlqMatch(T.level, text, used); if (lv) { take(lv); out.level = lv.target; lv.kind = 'level'; }
  const ct = nlqMatch(T.cat, text, used);   if (ct) { take(ct); out.cat = ct.target;  ct.kind = 'cat'; }
  const dp = nlqMatch(T.dept, text, used);  if (dp) { take(dp); out.dept = dp.target; dp.kind = 'dept'; }
  const st = nlqMatch(T.sort, text, used);  if (st) { take(st); out.sort = st.target; st.kind = 'sort'; }

  let rest = text;
  used.slice().sort((a, b) => b.s - a.s).forEach(u => { rest = rest.slice(0, u.s) + ' '.repeat(u.e - u.s) + rest.slice(u.e); });
  [T.dept, T.level, T.cat, T.sort].forEach(tb => tb.forEach(it => { if (rest.indexOf(it.w) >= 0) rest = rest.split(it.w).join(' '); }));
  NLQ_STOP.forEach(w => { rest = rest.split(w).join(' '); });
  rest = rest.replace(/[\s，。、,.!！？?；;：:（）()"'']+/g, '');
  if (rest.length >= 2) out.kw = rest;
  return out;
}

function applyNLQ() {
  const raw = ($('f_ai').value || '').trim();
  const echo = $('ai_echo');
  if (!raw) { if (echo) echo.style.display = 'none'; return; }
  const r = parseNLQ(raw);
  if (window.__AI_LLM_ON__ && r.hits.length === 0) {
    fetch('/api/ai/parse?q=' + encodeURIComponent(raw))
      .then(x => x.ok ? x.json() : null)
      .then(j => {
        if (j && j.ok && j.conditions) { Object.assign(r, j.conditions, { engine: 'llm' }); }
        commitNLQ(r, raw);
      }).catch(() => commitNLQ(r, raw));
    return;
  }
  if (r.hits.length || r.kw) track('nlq', raw, null, r.hits.length);
  commitNLQ(r, raw);
}

function commitNLQ(r, raw) {
  const echo = $('ai_echo');
  const setSel = (id, v) => { const el = $(id); if (el && v) el.value = v; };
  setSel('f_district', r.district); setSel('f_level', r.level); setSel('f_cat', r.cat);
  setSel('f_dept', r.dept); setSel('f_sort', r.sort || 'score');
  if (r.kw) $('f_kw').value = r.kw;

  const chips = [];
  if (r.district) chips.push('区域：' + r.district);
  if (r.level) chips.push('等级：' + r.level);
  if (r.cat) chips.push('类型：' + r.cat);
  if (r.dept) chips.push('科室：' + r.dept);
  if (r.kw) chips.push('关键词：' + r.kw);
  if (r.sort) chips.push('排序：' + ({ score: '综合评分', distance: '距离最近', level: '等级优先', depts: '科室最多', name: '名称' }[r.sort] || r.sort));

  const tip = r.engine === 'llm' ? '（大模型解析）' : '（规则引擎解析 · 离线可用）';
  if (echo) {
    echo.style.display = 'block';
    echo.innerHTML = chips.length === 0
      ? '<span style="color:' + WARN + '">' + svgIcon('warn') + ' 没识别出筛选条件。</span>可以试试：<b>朝阳区看心脏病的三级医院</b> / <b>海淀区儿科诊所</b> / <b>离家最近的二甲医院</b>'
      : '<b style="color:' + INK + '">我理解为</b> <span style="color:' + DIM + '">' + tip + '</span><br>' +
        chips.map(c => '<span class="chip">' + esc(c) + '</span>').join('') +
        '<br><span style="color:' + FAINT + '">解析结果已填入下方筛选项，可直接手工修改纠错。</span>';
  }
  PAGE = 1; applyFilter();
}
function clearNLQ() {
  $('f_ai').value = '';
  const e = $('ai_echo'); if (e) e.style.display = 'none';
  resetFilter();
}

// ============================================================================
//  6. 筛选核心
// ============================================================================
function haversine(lng1, lat1, lng2, lat2) {
  const R = 6371, rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad, dLng = (lng2 - lng1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function applyFilter() {
  if (!DATA) return;
  const kw = ($('f_kw').value || '').trim().toLowerCase();
  const district = $('f_district').value, level = $('f_level').value, cat = $('f_cat').value;
  const dept = $('f_dept').value, net = $('f_net').value, sort = $('f_sort').value;
  const baseKey = $('f_base').value;
  if (!BASE_POINTS[baseKey]) $('f_base').value = 'tiananmen';
  let base = BASE_POINTS[$('f_base').value] || BASE_POINTS.tiananmen;
  // 防御：选了「我的位置」但尚未定位成功（lng 为空）时回退到天安门，
  // 否则 haversine 会算出 NaN，导致距离列与排序全部失效。
  if (base.lng == null || base.lat == null) base = BASE_POINTS.tiananmen;

  FILTERED = DATA.institutions.filter(r => {
    if (kw && (r.name + ' ' + r.district + ' ' + (r.addr || '')).toLowerCase().indexOf(kw) < 0) return false;
    if (district && r.district !== district) return false;
    if (level && r.level !== level) return false;
    if (cat && r.category !== cat) return false;
    if (net) {
      if (net === 'ped_core' && r.net_pediatric !== '核心') return false;
      if (net === 'ped_member' && r.net_pediatric !== '成员') return false;
      if (net === 'stroke' && r.net_stroke !== '1') return false;
      if (net === 'neonatal' && r.net_neonatal !== '市级') return false;
      if (net === 'maternal' && r.net_maternal !== '市级') return false;
    }
    if (dept) {
      const pool = (r.feature || '') + ';' + (r.key_depts || '');
      if (pool.indexOf(dept) < 0) return false;
    }
    r._dist = (r.lng != null && r.lat != null) ? haversine(base.lng, base.lat, r.lng, r.lat) : null;
    return true;
  });

  let maxDept = 0, maxDist = 0;
  FILTERED.forEach(r => {
    if (r.dept_count) maxDept = Math.max(maxDept, r.dept_count);
    if (r._dist != null) maxDist = Math.max(maxDist, r._dist);
  });
  FILTERED.forEach(r => {
    const lv = (LEVEL_RANK[r.level] || 1) / 4;
    const ds = r._dist == null ? 0.5 : Math.max(0, 1 - r._dist / (maxDist || 1));
    const dp = (r.dept_count || 0) / (maxDept || 1);
    r._score = W_LEVEL * lv + W_DIST * ds + W_DEPT * dp;
  });

  const cmp = {
    score:    (a, b) => b._score - a._score,
    distance: (a, b) => (a._dist == null ? 9e9 : a._dist) - (b._dist == null ? 9e9 : b._dist),
    level:    (a, b) => (LEVEL_RANK[b.level] || 0) - (LEVEL_RANK[a.level] || 0),
    depts:    (a, b) => (b.dept_count || 0) - (a.dept_count || 0),
    name:     (a, b) => String(a.name).localeCompare(String(b.name), 'zh-CN'),
  }[sort] || ((a, b) => b._score - a._score);
  FILTERED.sort(cmp);

  renderKPI();
  renderList();
  updateCharts();
  updateAnalyticsCharts();
}

function renderKPI() {
  setText('v_match', FILTERED.length.toLocaleString());
  setText('v_l3', FILTERED.filter(r => r.level === '三级').length.toLocaleString());
  setText('v_coord', FILTERED.filter(r => r.lng != null).length.toLocaleString());
  const avg = FILTERED.length ? (FILTERED.reduce((s, r) => s + (r.dept_count || 0), 0) / FILTERED.length).toFixed(1) : '0';
  setText('v_dept', avg);
  setText('v_feat', FILTERED.filter(r => (r.key_specialty_count || 0) > 0).length.toLocaleString());
  const netN = FILTERED.filter(r => r.net_pediatric || r.net_stroke === '1' || r.net_neonatal === '市级' || r.net_maternal === '市级').length;
  setText('v_net', netN.toLocaleString());
  setText('listTag', 'LIST · 共 ' + FILTERED.length.toLocaleString() + ' 家');
}

// ============================================================================
//  7. 列表渲染
// ============================================================================
function levelBadge(lv) {
  if (lv === '不适用医院分级') {
    return '<span class="badge b-l0" title="该机构类型不参加医院等级评审（诊所 / 村卫生室 / 门诊部 / 社区卫生服务站 / 医务室等）">不适用分级</span>';
  }
  const cls = lv === '三级' ? 'b-l3' : lv === '二级' ? 'b-l2' : lv === '一级' ? 'b-l1' : 'b-l0';
  return '<span class="badge ' + cls + '">' + esc(lv || '未知') + '</span>';
}
function catBadge(c) { return c ? '<span class="badge b-l0">' + esc(c) + '</span>' : ''; }
function ownBadge(o) {
  if (o === '公立') return '<span class="badge b-pub" title="判定依据：登记注册类型 / 政府办属性">公立</span>';
  if (o === '民营') return '<span class="badge b-pri" title="判定依据：营利性 / 私有 / 非政府办属性">民营</span>';
  return '';
}
const FEAT_LABEL = { 1: '重点专科', 2: '优势科室', 3: '诊疗科室' };
function featLine(r) {
  if (!r.feature) return '';
  const lv = r.feature_level || '3';
  if (lv === '3') return '';
  const depts = r.feature.split(';').filter(x => x);
  if (!depts.length) return '';
  const show = depts.slice(0, 5).join(' / ') + (depts.length > 5 ? ' 等' + depts.length + '项' : '');
  return '<div class="feat" title="' + esc(depts.join(' / ')) + '">' +
    '<span class="fk f' + lv + '">' + (FEAT_LABEL[lv] || '擅长') + '</span>' +
    '<span class="ft">' + esc(show) + '</span></div>';
}
function netLine(r) {
  const t = [];
  if (r.net_pediatric === '核心') t.push(['儿科医联体·核心', CRIT]);
  else if (r.net_pediatric === '成员') t.push(['儿科医联体·成员', WARN]);
  if (r.net_stroke === '1') t.push(['卒中中心', ACC2]);
  if (r.net_neonatal === '市级') t.push(['新生儿救治·市级', VIO]);
  if (r.net_maternal === '市级') t.push(['孕产妇救治·市级', PINK]);
  if (!t.length) return '';
  return '<div class="netline">' + t.map(x =>
    '<span class="nt" style="border-color:' + x[1] + '55;color:' + x[1] + ';background:' + x[1] + '14">' + x[0] + '</span>'
  ).join('') + '</div>';
}
function netDetail(r) {
  const n = [];
  if (r.net_pediatric === '核心') n.push('儿科医联体·核心医院');
  else if (r.net_pediatric === '成员') n.push('儿科医联体·成员机构');
  if (r.net_stroke === '1') n.push('卒中中心');
  if (r.net_neonatal === '市级') n.push('危重新生儿救治中心（市级）');
  if (r.net_maternal === '市级') n.push('危重孕产妇救治中心（市级）');
  return n.length ? n.join('、') : '';
}
function kwMark(s) {
  const kw = ($('f_kw').value || '').trim();
  const safe = esc(s);
  if (!kw) return safe;
  const re = new RegExp('(' + kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
  return safe.replace(re, '<mark>$1</mark>');
}

function renderList() {
  const start = (PAGE - 1) * PAGE_SIZE;
  const page = FILTERED.slice(start, start + PAGE_SIZE);
  const totalPg = Math.max(1, Math.ceil(FILTERED.length / PAGE_SIZE));
  setText('pg_info', PAGE + ' / ' + totalPg);
  $('pg_prev').disabled = PAGE <= 1;
  $('pg_next').disabled = PAGE >= totalPg;
  const box = $('list');
  if (!page.length) {
    box.innerHTML = '<div class="empty">没有符合条件的机构，试试放宽筛选条件</div>';
    return;
  }
  const baseKey = $('f_base').value;
  const baseNow = BASE_POINTS[baseKey] || BASE_POINTS.tiananmen;
  const distLabel = (baseKey === 'geo' && (baseNow.lng == null || baseNow.lat == null)) ? svgIcon('warn') + ' 请先点定位' : ('距' + baseNow.name);

  box.innerHTML = page.map(r => {
    const dist = r._dist == null ? '—' : r._dist.toFixed(1) + ' km';
    const on = PICKED.has(String(r.id));
    const ksc = r.key_specialty_count || 0;
    return '<div class="row' + (on ? ' sel' : '') + '" data-id="' + esc(r.id) + '">' +
      '<div class="pick" data-pick="' + esc(r.id) + '" title="加入对比（最多 ' + PICK_MAX + ' 家）">' + svgIcon('ok') + '</div>' +
      '<div class="body">' +
        '<div class="name">' + kwMark(r.name) + '</div>' +
        '<div class="meta">' + levelBadge(r.level) + catBadge(r.category) + ownBadge(r.ownership) +
          '<span>' + esc(r.district) + '</span><span style="color:' + FAINT + '">·</span><span>' + (r.dept_count || 0) + ' 个科室</span></div>' +
        featLine(r) + netLine(r) +
      '</div>' +
      '<div class="side">' +
        '<div class="dist">' + dist + '<div style="color:' + DIM + ';font-size:10px;font-weight:400">' + distLabel + '</div></div>' +
        '<div class="score">' + (r._score || 0).toFixed(3) + '</div>' +
        '<div class="ksc ' + (ksc > 0 ? 'on' : 'off') + '"><b>' + ksc + '</b>重点专科</div>' +
      '</div>' +
    '</div>';
  }).join('');

  Array.prototype.forEach.call(box.querySelectorAll('.row'), el => {
    el.addEventListener('click', ev => {
      if (ev.target.closest('[data-pick]')) return;
      openDrawer(el.getAttribute('data-id'));
    });
  });
  Array.prototype.forEach.call(box.querySelectorAll('[data-pick]'), el => {
    el.addEventListener('click', ev => { ev.stopPropagation(); togglePick(el.getAttribute('data-pick')); });
  });
}

// ============================================================================
//  8. 概览图表
// ============================================================================
function initCharts() {
  try {
    const mapDiv = $('map');
    if (typeof echarts === 'undefined') throw new Error('ECharts 库未加载');
    if (!DATA || !DATA.geojson) throw new Error('数据中缺少 geojson');
    setMapDiag('', '⏳ 正在初始化 ECharts 地图…');

    MAP_CHART = echarts.init(mapDiv, null, { renderer: 'canvas' });
    echarts.registerMap('beijing', DATA.geojson);
    const reg = echarts.getMap && echarts.getMap('beijing');
    if (!reg || !reg.geoJson) throw new Error('registerMap("beijing") 失败');

    MAP_CHART.setOption({
      backgroundColor: 'transparent', textStyle: { color: INK },
      tooltip: Object.assign({ trigger: 'item' }, TIP),
      geo: {
        map: 'beijing', roam: true, zoom: 1, layoutCenter: ['50%', '50%'], layoutSize: '96%', aspectScale: 0.9,
        label: { show: true, color: '#8b94ad', fontSize: 10 },
        itemStyle: { borderColor: 'rgba(255,255,255,.14)', borderWidth: 1, areaColor: '#171922' },
        emphasis: { label: { color: '#fff' }, itemStyle: { areaColor: '#2a3550' } },
        select: { itemStyle: { areaColor: '#2a3550' }, label: { color: '#fff' } },
      },
      visualMap: { min: 0, max: 1300, show: false,
        inRange: { color: ['#171922', '#2a3550', '#4a5680', '#6b8cff', '#9a8cf0'] } },
      series: [{
        name: '机构数', type: 'map', geoIndex: 0,
        data: DATA.overviews.districts.map(d => ({ name: d.district, value: d.inst_count })),
      }],
    });
    MAP_CHART.resize();
    MAP_CHART.on('click', p => {
      if (p.name) { $('f_district').value = p.name; PAGE = 1; track('filter_district', p.name, 'map'); applyFilter(); }
    });

    CH1 = echarts.init($('ch1')); CH2 = echarts.init($('ch2')); CH3 = echarts.init($('ch3'));
    window.addEventListener('resize', () => resizeAll());

    setMapDiag('', svgIcon('ok') + ' 地图就绪 · ' + (DATA.geojson.features || []).length + ' 个行政区 · 点击区名可直接筛选');
    setTimeout(() => { const el = $('map_diag'); if (el) el.style.opacity = '.25'; }, 5200);
  } catch (e) {
    console.error('[initCharts]', e);
    setMapDiag('err', svgIcon('err') + ' 地图初始化失败<br><b>' + esc(e.message || e) + '</b><br>请按 Cmd+Shift+R 硬刷新');
  }
}

function resizeAll() {
  [MAP_CHART, CH1, CH2, CH3, CH_OWN, CH_FEAT, CH_NET, CH_LVOWN, CH_TOPSP, CH_DEPTOP, CH_DISTLV, CH_COORD,
   A_KW, A_DIST, A_TRIAGE, A_DAILY, A_DENSITY, A_LEVEL, A_SPEC, A_NET, A_OWN, A_CAT, DW_CHART
  ].forEach(c => { if (c) { try { c.resize(); } catch (e) { } } });
}

function updateCharts() {
  if (!CH1 || !CH2 || !CH3) return;
  const lvCount = {};
  FILTERED.forEach(r => { if (r.level === '不适用医院分级') return; lvCount[r.level] = (lvCount[r.level] || 0) + 1; });
  CH1.setOption({
    tooltip: Object.assign({ trigger: 'item', formatter: '{b}：{c} 家（{d}%）' }, TIP),
    legend: Object.assign({ bottom: 0 }, LEGEND),
    series: [{
      type: 'pie', radius: ['46%', '70%'], center: ['50%', '43%'],
      data: Object.entries(lvCount).map(x => ({ name: x[0], value: x[1], itemStyle: { color: LV_COLOR[x[0]] || DIM } })),
      label: { color: INK, fontSize: 11, formatter: '{b}\n{c}' }, labelLine: { lineStyle: { color: 'rgba(255,255,255,.18)' } },
      itemStyle: { borderColor: PANEL, borderWidth: 2.5 },
    }],
  });

  const catCount = {};
  FILTERED.forEach(r => catCount[r.category] = (catCount[r.category] || 0) + 1);
  const catS = Object.entries(catCount).sort((a, b) => b[1] - a[1]).slice(0, 8);
  CH2.setOption({
    tooltip: Object.assign({ trigger: 'axis', axisPointer: { type: 'shadow' } }, TIP),
    grid: { left: 92, right: 34, top: 8, bottom: 8 },
    xAxis: Object.assign({ type: 'value' }, AXIS),
    yAxis: Object.assign({ type: 'category', data: catS.map(c => c[0]).reverse() }, AXIS),
    series: [{
      type: 'bar', data: catS.map(c => c[1]).reverse(),
      itemStyle: { color: ACC2, borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', color: INK, fontSize: 10 }, barMaxWidth: 15,
    }],
  });

  const dCount = {};
  FILTERED.forEach(r => dCount[r.district] = (dCount[r.district] || 0) + 1);
  const dS = Object.entries(dCount).sort((a, b) => b[1] - a[1]);
  CH3.setOption({
    tooltip: Object.assign({ trigger: 'axis', axisPointer: { type: 'shadow' } }, TIP),
    grid: { left: 46, right: 16, top: 14, bottom: 52 },
    xAxis: Object.assign({ type: 'category', data: dS.map(c => c[0]) }, AXIS,
      { axisLabel: { color: '#8b8d96', fontSize: 9.5, rotate: 38, interval: 0 } }),
    yAxis: Object.assign({ type: 'value' }, AXIS),
    series: [{
      type: 'bar', data: dS.map(c => c[1]),
      itemStyle: { color: ACC, borderRadius: [4, 4, 0, 0] },
      label: { show: true, position: 'top', color: INK, fontSize: 9.5 },
    }],
  });

  try {
    const inB = r => r.lng != null && r.lat != null && +r.lng > 115.35 && +r.lng < 117.50 && +r.lat > 39.40 && +r.lat < 41.10;
    const points = FILTERED.filter(inB).slice(0, 3000);
    MAP_CHART.setOption({
      series: [
        { type: 'map', geoIndex: 0 },
        {
          type: 'effectScatter', coordinateSystem: 'geo', zlevel: 2,
          data: points.map(r => ({ name: r.name, value: [r.lng, r.lat, r.level || '其他'] })),
          symbolSize: v => v[2] === '三级' ? 6.5 : v[2] === '二级' ? 4.5 : 2.6,
          rippleEffect: { period: 4, scale: 2.6, brushType: 'stroke' },
          itemStyle: { color: v => v[2] === '三级' ? CRIT : v[2] === '二级' ? WARN : ACC2 },
          showEffectOn: 'render',
        },
      ],
    });
  } catch (e) { console.error('[updateCharts] 散点:', e); }
}

// ============================================================================
//  9. 多维分析图表
// ============================================================================
function grp(arr, key) { const m = {}; arr.forEach(r => { const k = key(r); m[k] = (m[k] || 0) + 1; }); return m; }
function lvGroup(l) { return ['三级', '二级', '一级', '未定级'].indexOf(l) >= 0 ? l : '不适用'; }

function pieOpt(data) {
  return {
    tooltip: Object.assign({ trigger: 'item', formatter: '{b}：{c}（{d}%）' }, TIP),
    legend: Object.assign({ bottom: 0 }, LEGEND),
    series: [{
      type: 'pie', radius: ['42%', '70%'], center: ['50%', '44%'],
      data: data.map(d => ({ name: d[0], value: d[1], itemStyle: { color: d[2] } })),
      label: { color: INK, fontSize: 11 }, labelLine: { lineStyle: { color: 'rgba(255,255,255,.18)' } },
      itemStyle: { borderColor: PANEL, borderWidth: 2.5 },
    }],
  };
}
function barHOpt(pairs, colors) {
  const cols = Array.isArray(colors) ? colors : pairs.map(() => colors);
  return {
    tooltip: Object.assign({ trigger: 'axis', axisPointer: { type: 'shadow' } }, TIP),
    grid: { left: 122, right: 40, top: 8, bottom: 8 },
    xAxis: Object.assign({ type: 'value' }, AXIS),
    yAxis: Object.assign({ type: 'category', data: pairs.map(p => p[0]) }, AXIS),
    series: [{
      type: 'bar', barMaxWidth: 15,
      data: pairs.map((p, i) => ({ value: p[1], itemStyle: { color: cols[i] || ACC, borderRadius: [0, 4, 4, 0] } })),
      label: { show: true, position: 'right', color: INK, fontSize: 10 },
    }],
  };
}
function stackOpt(cats, series) {
  return {
    tooltip: Object.assign({ trigger: 'axis', axisPointer: { type: 'shadow' } }, TIP),
    legend: Object.assign({ bottom: 0 }, LEGEND),
    grid: { left: 50, right: 16, top: 8, bottom: 40 },
    xAxis: Object.assign({ type: 'category', data: cats }, AXIS,
      { axisLabel: { color: '#8b8d96', fontSize: 9, rotate: cats.length > 10 ? 38 : 0, interval: 0 } }),
    yAxis: Object.assign({ type: 'value' }, AXIS),
    series: series.map(s => Object.assign({ barMaxWidth: 26 }, s)),
  };
}

function initAnalyticsCharts() {
  const mk = id => { const el = $(id); return el ? echarts.init(el) : null; };
  CH_OWN = mk('ch_own'); CH_FEAT = mk('ch_feat'); CH_NET = mk('ch_net');
  CH_LVOWN = mk('ch_lvown'); CH_TOPSP = mk('ch_topsp'); CH_DEPTOP = mk('ch_deptop');
  CH_DISTLV = mk('ch_distlv'); CH_COORD = mk('ch_coord');
}

function updateAnalyticsCharts() {
  if (!CH_OWN) return;
  const F = FILTERED, tot = F.length || 1;
  setText('ak_pub', pct(F.filter(r => r.ownership === '公立').length, tot));
  setText('ak_l3', pct(F.filter(r => r.level === '三级').length, tot));
  setText('ak_feat', F.filter(r => (r.key_specialty_count || 0) > 0).length.toLocaleString());
  setText('ak_net', F.filter(r => r.net_pediatric || r.net_stroke === '1' || r.net_neonatal === '市级' || r.net_maternal === '市级').length.toLocaleString());

  const own = grp(F, r => r.ownership || '未标注');
  CH_OWN.setOption(pieOpt([['公立', own['公立'] || 0, ACC2], ['民营', own['民营'] || 0, WARN], ['未标注', own['未标注'] || 0, DIM]]));

  const fl = { L1: 0, L2: 0, L3: 0, none: 0 };
  F.forEach(r => { const v = r.feature_level; if (v === '1') fl.L1++; else if (v === '2') fl.L2++; else if (v === '3') fl.L3++; else fl.none++; });
  CH_FEAT.setOption(barHOpt([['重点专科 L1', fl.L1], ['优势科室 L2', fl.L2], ['诊疗科室 L3', fl.L3], ['无分级', fl.none]], [CRIT, WARN, ACC, DIM]));

  CH_NET.setOption(barHOpt([
    ['儿科医联体·核心', F.filter(r => r.net_pediatric === '核心').length],
    ['儿科医联体·成员', F.filter(r => r.net_pediatric === '成员').length],
    ['卒中中心', F.filter(r => r.net_stroke === '1').length],
    ['危重新生儿', F.filter(r => r.net_neonatal === '市级').length],
    ['危重孕产妇', F.filter(r => r.net_maternal === '市级').length],
  ], [VIO, '#6d5bd0', CRIT, ACC2, ACC]));

  const levels = ['三级', '二级', '一级', '未定级'], owns = ['公立', '民营', '未标注'];
  CH_LVOWN.setOption(stackOpt(levels, owns.map(o => ({
    name: o, type: 'bar', stack: 't', emphasis: { focus: 'series' },
    itemStyle: { color: o === '公立' ? ACC2 : o === '民营' ? WARN : DIM },
    data: levels.map(l => F.filter(r => r.level === l && (r.ownership || '未标注') === o).length),
  }))));

  const top = F.filter(r => (r.key_specialty_count || 0) > 0)
    .slice().sort((a, b) => b.key_specialty_count - a.key_specialty_count).slice(0, 10).reverse();
  CH_TOPSP.setOption(barHOpt(top.map(r => [trunc(r.name, 11), r.key_specialty_count]), CRIT));

  const dists = (DATA.meta.districts || []).map(d => d.district);
  const lvG = [['三级', CRIT], ['二级', WARN], ['一级', ACC], ['未定级', VIO], ['不适用', DIM]];
  CH_DISTLV.setOption(stackOpt(dists, lvG.map(g => ({
    name: g[0], type: 'bar', stack: 'd', emphasis: { focus: 'series' }, itemStyle: { color: g[1] },
    data: dists.map(dn => F.filter(r => r.district === dn && lvGroup(r.level) === g[0]).length),
  }))));

  const cp = grp(F, r => r.coord_precision || 'missing');
  CH_COORD.setOption(pieOpt([['高精度', cp['high'] || 0, ACC2], ['粗略', cp['rough'] || 0, WARN], ['缺失', cp['missing'] || 0, CRIT]]));

  const dc = {};
  F.forEach(r => {
    ((r.feature || '') + ';' + (r.key_depts || '')).split(';').forEach(x => { x = x.trim(); if (x) dc[x] = (dc[x] || 0) + 1; });
  });
  const td = Object.entries(dc).sort((a, b) => b[1] - a[1]).slice(0, 15).reverse();
  CH_DEPTOP.setOption(barHOpt(td.map(p => [trunc(p[0], 11), p[1]]), ACC));
}

// ============================================================================
//  10. 导航
// ============================================================================
function initNav() {
  const tabs = document.querySelectorAll('.navtab');
  Array.prototype.forEach.call(tabs, btn => btn.addEventListener('click', () => {
    const v = btn.getAttribute('data-view');
    Array.prototype.forEach.call(tabs, b => b.classList.toggle('active', b === btn));
    Array.prototype.forEach.call(document.querySelectorAll('.view'), s => s.classList.toggle('active', s.id === 'view-' + v));
    if (v === 'admin') renderAdmin();
    setTimeout(resizeAll, 60);
  }));
}
function switchView(v) {
  const btn = document.querySelector('.navtab[data-view="' + v + '"]');
  if (btn) btn.click();
}

// ============================================================================
//  11. 详情抽屉
// ============================================================================
let DW_CUR = null;

function initDrawer() {
  $('dw_close').addEventListener('click', closeDrawer);
  $('scrim').addEventListener('click', closeDrawer);
  Array.prototype.forEach.call(document.querySelectorAll('.dw-tab'), t => t.addEventListener('click', () => {
    Array.prototype.forEach.call(document.querySelectorAll('.dw-tab'), x => x.classList.toggle('active', x === t));
    Array.prototype.forEach.call(document.querySelectorAll('.dw-pane'), p => p.classList.toggle('active', p.id === 'pane-' + t.getAttribute('data-pane')));
  }));
  $('dw_copy').addEventListener('click', () => {
    if (!DW_CUR) return;
    const name = DW_CUR.name || '';
    if (navigator.clipboard) navigator.clipboard.writeText(name).then(() => toast(svgIcon('ok') + ' 已复制机构名称：' + esc(name)), () => toast(svgIcon('warn') + ' 复制失败'));
    else toast('机构名称：' + esc(name));
  });
  $('dw_pick').addEventListener('click', () => {
    if (!DW_CUR) return;
    togglePick(String(DW_CUR.id));
    $('dw_pick').innerHTML = PICKED.has(String(DW_CUR.id)) ? svgIcon('ok') + ' 已加入对比' : '＋ 加入对比';
  });
  $('dw_ai').addEventListener('click', () => runAIAdvice());
}

function closeDrawer() {
  $('drawer').classList.remove('show');
  $('scrim').classList.remove('show');
  if (DW_CHART) { try { DW_CHART.dispose(); } catch (e) { } DW_CHART = null; }
}

function openDrawer(id) {
  const local = DATA.institutions.find(x => String(x.id) === String(id));
  if (!local) return;
  DW_CUR = local;
  track('detail', local.name, local.district);

  // 先用本地数据即时渲染（不等接口），保证离线与弱网也秒开
  paintDrawerLocal(local);
  $('drawer').classList.add('show');
  $('scrim').classList.add('show');
  $('dw_pick').innerHTML = PICKED.has(String(local.id)) ? svgIcon('ok') + ' 已加入对比' : '＋ 加入对比';
  $('dw_ai').style.display = (window.__AI_LLM_ON__ && ENV.api) ? '' : 'none';
  $('dw_ft_note').textContent = ENV.api ? '' : '离线模式 · 周边配套与 AI 提示需本地服务';

  if (!ENV.api) return;
  fetch('/api/inst/' + encodeURIComponent(id) + '/detail')
    .then(r => r.ok ? r.json() : null)
    .then(j => { if (j && j.ok && DW_CUR && String(DW_CUR.id) === String(id)) paintDrawerFull(j); })
    .catch(() => { });
}

function paintDrawerLocal(r) {
  $('dw_name').textContent = r.name;
  $('dw_meta').innerHTML = levelBadge(r.level) + catBadge(r.category) + ownBadge(r.ownership) +
    '<span class="chip">' + esc(r.district) + '</span>' +
    (r.category_sub && r.category_sub !== '未细分' ? '<span class="chip">' + esc(r.category_sub) + '</span>' : '');
  const base = BASE_POINTS[$('f_base').value] || BASE_POINTS.tiananmen;
  const dist = (r.lng != null && r.lat != null) ? haversine(base.lng, base.lat, r.lng, r.lat).toFixed(1) + ' km' : '—';
  $('pane-ov').innerHTML =
    '<div class="infogrid">' +
      box('机构类型', esc(r.category || '—')) +
      box('医院等级', levelBadge(r.level) + '<div class="mini" style="color:' + FAINT + ';font-size:11px;margin-top:4px">' + esc(r.level === '不适用医院分级' ? '该类型不参加等级评审' : r.level) + '</div>') +
      box('办别性质', (r.ownership || '未标注') + (r.ownership_basis ? '<div style="color:' + FAINT + ';font-size:10px;margin-top:3px">依据 ' + esc(r.ownership_basis) + '</div>' : '')) +
      box('科室数量', num(r.dept_count) + ' 个') +
      box('重点专科', num(r.key_specialty_count) + ' 项') +
      box('距' + base.name, dist) +
    '</div>' +
    '<div class="blk"><h4><span class="bar"></span>实时状态 <span class="r">演示模拟数据</span></h4>' + statusHTML(mockStatus(r)) + '</div>' +
    '<div class="blk"><h4><span class="bar"></span>协作网络</h4><div class="deptchips">' +
      (netDetail(r) ? netDetail(r).split('、').map(x => '<span class="chip acc">' + esc(x) + '</span>').join('')
                    : '<span style="color:' + DIM + ';font-size:12px">未纳入市级协作网络</span>') +
    '</div></div>' +
    '<div class="blk"><h4><span class="bar"></span>同区科室数 TOP10 对比 <span class="r">红色为本机构</span></h4>' +
      '<div class="dwchart" id="dw_chart"></div></div>';
  paintDwChart(r);
  // 离线单文件（file://）没有后端，联系方式必须用快照里的 addr/phone 本地渲染，
  // 否则面板会永远停在「正在获取联系方式…」——这是必须避免的空转假象。
  $('pane-contact').innerHTML = ENV.api ? '<div class="empty">正在获取联系方式…</div>' : contactLocalHTML(r);
  $('pane-spec').innerHTML = specialtyHTML(r);
  $('pane-near').innerHTML = aroundPlaceholder(r);
}

// 离线模式的「就诊与挂号」面板：只用快照数据，不依赖任何接口
function contactLocalHTML(r) {
  const items = [];
  items.push(linkCard(svgIcon('gov'), '北京市预约挂号统一平台（114）', '官方统一平台 · 打开后按机构名检索', GUAhAO_114, false));
  items.push(linkCard(svgIcon('phone'), '电话预约挂号 010-114', '24 小时人工坐席', 'tel:010-114', false));
  if (r.phone) items.push(linkCard(svgIcon('phone'), '机构电话 ' + r.phone, '预约 / 咨询（以医院公布为准）', 'tel:' + r.phone, false));
  else items.push(linkCard(svgIcon('phone'), '机构电话未收录', '公开数据中无联系电话', '', true));
  const nav = navLink(r);
  if (nav) items.push(linkCard(svgIcon('compass'), '高德地图导航', '一键导航到该机构', nav, false));
  else items.push(linkCard(svgIcon('compass'), '暂无坐标', '缺少经纬度，无法导航', '', true));
  return '<div class="linklist">' + items.join('') + '</div>' +
    '<div class="blk"><h4><span class="bar"></span>联系方式 <span class="r">来源：数据快照</span></h4>' +
      '<div class="infogrid">' +
        box('联系电话', r.phone ? '<a href="tel:' + esc(r.phone) + '">' + esc(r.phone) + '</a>' : '<span style="color:' + FAINT + '">未收录</span>') +
        box('所属区域', esc(r.district)) +
        box('经纬度', r.lng != null ? (r.lng + ', ' + r.lat) : '<span style="color:' + FAINT + '">无坐标</span>') +
        box('坐标精度', esc(r.coord_precision || '—')) +
      '</div>' +
      '<div class="ibox" style="margin-top:10px"><div class="k">地址</div><div class="v">' + esc(r.addr || '未收录') + '</div></div>' +
    '</div>' +
    '<div class="notice" style="margin-top:14px">当前为<b>离线单文件</b>模式：地址、电话、导航与 114 挂号入口均可正常使用；' +
    '周边配套（最近地铁站 / 停车场 / 公交站）与 AI 就医提示需本地 Flask 服务支持。</div>';
}

// 同区科室数横向对比（在当前区县内看该机构的相对位置）
let DW_CHART = null;
function paintDwChart(r) {
  const el = $('dw_chart');
  if (!el || typeof echarts === 'undefined') return;
  const same = DATA.institutions.filter(x => x.district === r.district && x.dept_count);
  const top10 = same.slice().sort((a, b) => (b.dept_count || 0) - (a.dept_count || 0)).slice(0, 10);
  if (!top10.some(x => String(x.id) === String(r.id))) top10.push(r);
  top10.reverse();
  if (!DW_CHART) DW_CHART = echarts.init(el);
  DW_CHART.setOption({
    tooltip: Object.assign({ trigger: 'axis', axisPointer: { type: 'shadow' } }, TIP),
    grid: { left: 108, right: 34, top: 6, bottom: 6 },
    xAxis: Object.assign({ type: 'value' }, AXIS),
    yAxis: Object.assign({ type: 'category', data: top10.map(x => trunc(x.name, 12)) }, AXIS),
    series: [{
      type: 'bar', barMaxWidth: 13,
      data: top10.map(x => ({
        value: x.dept_count || 0,
        itemStyle: { color: String(x.id) === String(r.id) ? CRIT : ACC, borderRadius: [0, 4, 4, 0] },
      })),
      label: { show: true, position: 'right', color: INK, fontSize: 10 },
    }],
  }, true);
  setTimeout(() => { try { DW_CHART.resize(); } catch (e) { } }, 60);
}

function box(k, v) { return '<div class="ibox"><div class="k">' + esc(k) + '</div><div class="v">' + v + '</div></div>'; }

function specialtyHTML(r) {
  const nat = (r.national_specialty || '').split(';').filter(x => x.trim());
  const mun = (r.municipal_specialty || '').split(';').filter(x => x.trim());
  const feat = (r.feature || '').split(';').filter(x => x.trim());
  let h = '';
  if (nat.length) h += '<div class="blk"><h4><span class="bar"></span>国家级重点专科 <span class="r">' + nat.length + ' 项</span></h4><div class="deptchips">' +
    nat.map(x => '<span class="chip emg">' + esc(x.trim()) + '</span>').join('') + '</div></div>';
  if (mun.length) h += '<div class="blk"><h4><span class="bar"></span>北京市级重点专科 <span class="r">' + mun.length + ' 项</span></h4><div class="deptchips">' +
    mun.map(x => '<span class="chip" style="background:rgba(255,181,71,.14);color:' + WARN + ';border-color:rgba(255,181,71,.34)">' + esc(x.trim()) + '</span>').join('') + '</div></div>';
  if (feat.length) h += '<div class="blk"><h4><span class="bar"></span>擅长 / 诊疗科室 <span class="r">' + feat.length + ' 项</span></h4><div class="deptchips">' +
    feat.map(x => '<span class="chip">' + esc(x.trim()) + '</span>').join('') + '</div></div>';
  if (!h) h = '<div class="empty">该机构未收录重点专科或擅长科室信息</div>';

  // 专家团队入口：不伪造医生姓名，而是把「真实重点专科 → 官方挂号入口」打通
  h += '<div class="blk"><h4><span class="bar"></span>专家团队 · 挂号入口 <span class="r">真实数据 · 不展示未经核实的人员信息</span></h4>' +
    '<div style="color:' + DIM + ';font-size:11.5px;line-height:1.75;margin-bottom:10px">' +
    '本系统<b>不收录医生姓名与职称</b>（公开数据中无可靠来源，编造会在答辩与实用中造成误导）。' +
    '下方的重点专科清单来自官方公示名单，点击按钮可直达官方平台查询该机构、该专科的真实出诊专家。</div>' +
    '<div class="taglist">' +
      (nat.concat(mun).length ? nat.concat(mun).slice(0, 6).map(d =>
        '<div class="tagrow"><span class="tk" style="background:rgba(255,107,129,.16);color:#ffa4b3;border:1px solid rgba(255,107,129,.34)">' + esc(d.trim()) + '</span>' +
        '<span class="tv">该科室为' + (nat.indexOf(d) >= 0 ? '国家级' : '市级') + '重点专科 — ' +
        '<a href="' + GUAhAO_114 + '" target="_blank" rel="noopener">到 114 平台查询该科专家号 →</a></span></div>').join('')
        : '<div style="color:' + DIM + ';font-size:12px">暂无重点专科记录，可通过 114 平台按机构名检索</div>') +
    '</div></div>';
  return h;
}

function aroundPlaceholder(r) {
  const link = navLink(r);
  return '<div class="notice">周边配套（最近地铁站 / 停车场 / 公交站）通过高德开放平台实时查询，' +
    '需要本地 Flask 服务支持。<br>当前为离线模式，你仍可查看地址并使用导航。</div>' +
    '<div class="blk"><h4><span class="bar"></span>地址与导航</h4>' +
    '<div class="poilist"><div class="poi"><div class="pi" style="background:rgba(76,154,255,.14)">' + svgIcon('location') + '</div>' +
    '<div class="pb"><div class="pn">' + esc(r.addr || (r.district + '（详细地址未收录）')) + '</div>' +
    '<div class="ps">' + esc(r.district) + ' · ' + (r.lng != null ? (r.lng + ', ' + r.lat) : '无坐标') + '</div></div>' +
    (link ? '<a class="btn ghost sm" href="' + link + '" target="_blank" rel="noopener">导航</a>' : '') +
    '</div></div></div>';
}

function navLink(r) {
  if (r.lng == null || r.lat == null) return '';
  return 'https://uri.amap.com/marker?position=' + r.lng + ',' + r.lat +
    '&name=' + encodeURIComponent(r.name || '医院') + '&src=hospital-dashboard&coordinate=gaode&callnative=1';
}

// 与后端 _mock_status 同构的确定性模拟状态（离线可用；在线时以后端返回为准）
function mockStatus(r) {
  const s = String(r.id);
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  const labels = ['空闲', '较少', '中等', '较多', '繁忙'];
  let bias = { '三级': 2, '二级': 1, '一级': 0 }[r.level];
  if (bias === undefined) bias = -1;
  const idx = Math.min(4, Math.max(0, (h % 5) + bias - 1));
  const waits = [5, 12, 20, 35, 55];
  const slots = ['上午号源充足', '上午偏紧、下午充足', '当日号源偏紧', '当日号源紧张', '当日号源已满'];
  return { simulated: true, level: labels[idx], level_index: idx, wait_min: waits[idx], slots: slots[idx], note: '演示模拟数据 · 非医院实时候诊信息' };
}

function statusHTML(st) {
  const heat = [0, 1, 2, 3, 4].map(i => '<i class="' + (i <= st.level_index ? 'on' : '') + '"></i>').join('');
  return '<div class="statusbox">' +
    '<div class="sh"><span class="simtag">' + svgIcon('flask') + ' 演示模拟</span>' +
    '<span style="font-size:15px;font-weight:800;color:' + WARN + '">当前挂号排队：' + esc(st.level) + '</span>' +
    '<span style="color:' + SUB + ';font-size:12px">预计等候约 ' + st.wait_min + ' 分钟</span></div>' +
    '<div class="heats">' + heat + '</div>' +
    '<div style="color:' + DIM + ';font-size:11px;margin-top:9px">号源参考：' + esc(st.slots) + '</div>' +
    '<div style="color:' + FAINT + ';font-size:10.5px;margin-top:6px">' + esc(st.note) + '。真实号源请以 114 平台及医院官方公布为准。</div>' +
    '</div>';
}

// 接口返回后补全：联系方式 / 挂号入口 / 周边配套 / 权威状态
function paintDrawerFull(d) {
  const c = d.contact || {}, L = d.links || {};
  const st = d.status || mockStatus(DW_CUR);

  // 概览补状态（把本地模拟状态替换为后端权威返回值，两者口径一致）
  const sBox = $('pane-ov').querySelector('.statusbox');
  if (sBox) {
    const blk = sBox.closest('.blk');
    if (blk) blk.innerHTML = '<h4><span class="bar"></span>实时状态 <span class="r">演示模拟数据</span></h4>' + statusHTML(st);
  }

  // 就诊与挂号
  const items = [];
  items.push(linkCard(svgIcon('gov'), '北京市预约挂号统一平台（114）', '官方唯一统一平台 · 打开后按机构名检索', L.guahao_114, false));
  items.push(linkCard(svgIcon('phone'), '电话预约挂号 010-114', '24 小时人工坐席（按语音提示操作）', 'tel:010-114', false));
  if (L.hospital_tel_link) items.push(linkCard(svgIcon('phone'), '机构电话 ' + L.hospital_phone, '预约 / 咨询（以医院公布为准）', L.hospital_tel_link, false));
  else items.push(linkCard(svgIcon('phone'), '机构电话未收录', '该机构在公开数据中无联系电话', '', true));
  if (L.amap_nav) items.push(linkCard(svgIcon('compass'), '高德地图导航', '一键导航到该机构', L.amap_nav, false));
  else items.push(linkCard(svgIcon('compass'), '暂无坐标', '该机构缺少经纬度，无法导航', '', true));

  $('pane-contact').innerHTML =
    '<div class="linklist">' + items.join('') + '</div>' +
    '<div class="blk"><h4><span class="bar"></span>联系方式 <span class="r">来源：公开数据</span></h4>' +
      '<div class="infogrid">' +
        box('联系电话', c.phone ? '<a href="tel:' + esc(c.phone) + '">' + esc(c.phone) + '</a>' : '<span style="color:' + FAINT + '">未收录</span>') +
        box('邮政编码', c.postal ? esc(c.postal) : '<span style="color:' + FAINT + '">未收录</span>') +
        box('坐标精度', esc(c.coord_precision || '—')) +
        box('经纬度', c.lng != null ? (c.lng + ', ' + c.lat) : '<span style="color:' + FAINT + '">无坐标</span>') +
      '</div>' +
      '<div class="ibox" style="margin-top:10px"><div class="k">地址</div><div class="v">' + esc(c.addr || '未收录') + '</div></div>' +
    '</div>' +
    '<div class="notice" style="margin-top:14px">' +
      '<b>关于挂号：</b>114 统一平台为 JS 单页应用，不存在可构造的「按医院直达」链接，因此本系统只提供官方入口 + 机构名复制，' +
      '不伪造深链（伪造会得到死链）。点击「复制名称」后到 114 平台粘贴检索即可。' +
    '</div>';
  $('pane-contact').innerHTML += '<div class="blk"><h4><span class="bar"></span>快捷操作</h4>' +
    '<div class="linklist">' + linkCard(svgIcon('clipboard'), '复制机构名称', '到 114 平台粘贴检索', '#copy', false) + '</div></div>';
  const cp = $('pane-contact').querySelector('a[href="#copy"]');
  if (cp) cp.addEventListener('click', e => {
    e.preventDefault();
    const n = L.hospital_name || (DW_CUR && DW_CUR.name) || '';
    if (navigator.clipboard) navigator.clipboard.writeText(n).then(() => toast(svgIcon('ok') + ' 已复制：' + esc(n)), () => toast('复制失败'));
  });

  // 周边配套
  const a = d.around || {};
  let near = '';
  if (d.around_enabled === false) {
    near = '<div class="notice">未配置高德 Key，周边配套不可用。可在 <code>data/.amap_key.txt</code> 配置后重试。</div>';
  } else if (!d.around_online) {
    near = '<div class="notice">高德接口暂时不可用（网络或额度问题），已保留地址与导航入口。</div>';
  }
  near += poiBlock(svgIcon('metro'), '最近地铁站', a.metro, 'rgba(76,154,255,.16)') +
          poiBlock(svgIcon('parking'), '附近停车场', a.parking, 'rgba(255,181,71,.16)') +
          poiBlock(svgIcon('bus'), '附近公交站', a.bus, 'rgba(56,224,192,.16)');
  if (!a.metro && !a.parking && !a.bus) {
    near += '<div class="blk"><h4><span class="bar"></span>地址与导航</h4><div class="poilist">' +
      '<div class="poi"><div class="pi" style="background:rgba(76,154,255,.14)">' + svgIcon('location') + '</div>' + '<div class="pb">' +
      '<div class="pn">' + esc(c.addr || '未收录详细地址') + '</div>' +
      '<div class="ps">' + esc(c.lng != null ? (c.lng + ', ' + c.lat) : '无坐标') + '</div></div>' +
      (L.amap_nav ? '<a class="btn ghost sm" href="' + L.amap_nav + '" target="_blank" rel="noopener">导航</a>' : '') +
      '</div></div></div>';
  }
  near += '<div style="color:' + FAINT + ';font-size:10.5px;margin-top:12px">' +
    '周边配套来自高德开放平台 POI 实时查询（步行时间按 75 米/分钟估算），结果已按坐标网格缓存以避免重复请求。</div>';
  $('pane-near').innerHTML = near;

  // 专科页（接口版更完整，含科室明细）
  let sp = specialtyHTML(d.specialty ? {
    national_specialty: (d.specialty.national || []).join(';'),
    municipal_specialty: (d.specialty.municipal || []).join(';'),
    feature: (d.specialty.feature || []).join(';'),
  } : DW_CUR);
  if (d.depts && d.depts.length) {
    const rows = d.depts.slice(0, 40).map(x =>
      '<tr><td>' + esc(x.dept_name) + '</td><td>' + (String(x.is_key_specialty) === '1' || x.is_key_specialty === 1 || x.is_key_specialty === true ? '<span class="chip emg">重点专科</span>' : '<span style="color:' + DIM + '">普通</span>') + '</td>' +
      '<td class="mono">' + esc(x.source || '—') + '</td></tr>').join('');
    sp += '<div class="blk"><h4><span class="bar"></span>科室明细 <span class="r">共 ' + d.depts.length + ' 条（最多显示 40）</span></h4>' +
      '<div class="tblbox"><table class="tiny"><thead><tr><th>科室</th><th>是否重点</th><th>来源</th></tr></thead><tbody>' + rows + '</tbody></table></div></div>';
  }
  $('pane-spec').innerHTML = sp;
}

function linkCard(icon, title, sub, href, disabled) {
  const inner = '<div class="li">' + icon + '</div><div style="flex:1;min-width:0"><div class="lt">' + esc(title) + '</div>' +
    '<div class="ls">' + esc(sub) + '</div></div><div style="color:' + DIM + ';font-size:14px">↗</div>';
  if (disabled || !href) return '<div class="linkbtn dis">' + inner + '</div>';
  return '<a class="linkbtn" href="' + href + '" target="_blank" rel="noopener">' + inner + '</a>';
}
function poiBlock(icon, title, list, bg) {
  if (!list || !list.length) return '';
  return '<div class="blk"><h4><span class="bar"></span>' + title + ' <span class="r">共 ' + list.length + ' 个 · 按距离排序</span></h4>' +
    '<div class="poilist">' + list.map(p =>
      '<div class="poi"><div class="pi" style="background:' + bg + '">' + icon + '</div>' +
      '<div class="pb"><div class="pn">' + esc(p.name) + '</div>' +
      '<div class="ps">' + esc(trunc(p.address || p.type || '', 34)) + (p.tel ? ' · ' + esc(p.tel) : '') + '</div></div>' +
      '<div class="pd">' + (p.distance_m != null ? (p.distance_m >= 1000 ? (p.distance_m / 1000).toFixed(1) + ' km' : p.distance_m + ' m') : '—') +
      '<span>约 ' + (p.walk_min || '—') + ' 分钟</span></div>' +
      (p.lng != null ? '<a class="btn ghost sm" href="https://uri.amap.com/marker?position=' + p.lng + ',' + p.lat +
        '&name=' + encodeURIComponent(p.name) + '&coordinate=gaode&callnative=1" target="_blank" rel="noopener">导航</a>' : '') +
      '</div>').join('') + '</div></div>';
}

function runAIAdvice() {
  if (!DW_CUR) return;
  const btn = $('dw_ai'), adv = $('aiadv');
  const wrap = document.getElementById('aiadv') || document.createElement('div');
  wrap.id = 'aiadv'; wrap.className = 'aiadv';
  const pane = $('pane-ov');
  if (!wrap.parentElement) pane.appendChild(wrap);
  wrap.classList.add('show');
  wrap.innerHTML = '<div class="who">' + svgIcon('brain') + ' AI 就医提示 <span class="chip eng">仅基于本页真实字段生成 · 禁止编造</span></div>' +
    '<div class="typing"><i></i><i></i><i></i> 正在生成…</div>';
  btn.disabled = true;
  fetch('/api/ai/advice?id=' + encodeURIComponent(DW_CUR.id))
    .then(r => r.ok ? r.json() : null)
    .then(j => {
      if (j && j.ok) {
        wrap.innerHTML = '<div class="who">' + svgIcon('brain') + ' AI 就医提示 <span class="chip eng">' + esc(j.model || 'Agnes') + ' · 仅基于真实字段</span></div>' +
          '<div>' + esc(j.advice) + '</div>' +
          '<div style="color:' + FAINT + ';font-size:10.5px;margin-top:9px">约束：不允许输出医生姓名、职称、出诊时间、号源数量与任何未经核实的具体数字。</div>';
      } else {
        wrap.innerHTML = '<div class="who">' + svgIcon('brain') + ' AI 就医提示</div><div style="color:' + WARN + '">' +
          esc((j && (j.hint || j.detail)) || '生成失败，请稍后重试') + '</div>';
      }
    })
    .catch(() => { wrap.innerHTML = '<div class="who">' + svgIcon('brain') + ' AI 就医提示</div><div style="color:' + WARN + '">网络异常，生成失败</div>'; })
    .then(() => { btn.disabled = false; });
}

// ============================================================================
//  12. 对比
// ============================================================================
function initCompare() {
  $('cmp_clear').addEventListener('click', clearPicks);
  $('cmp_go').addEventListener('click', openCompare);
  $('cmp_close').addEventListener('click', closeCompare);
  $('cmp_add').addEventListener('click', () => { closeCompare(); switchView('overview'); toast('请在列表中勾选更多机构（最多 ' + PICK_MAX + ' 家）'); });
  $('cmpwrap').addEventListener('click', e => { if (e.target.id === 'cmpwrap') closeCompare(); });
  renderPickBar();
}

function togglePick(id) {
  id = String(id);
  if (PICKED.has(id)) PICKED.delete(id);
  else {
    if (PICKED.size >= PICK_MAX) { toast(svgIcon('warn') + ' 最多同时对比 ' + PICK_MAX + ' 家机构，请先移除已选项'); return; }
    PICKED.add(id);
  }
  renderPickBar();
  // 只更新受影响的那一行，避免整表重绘导致滚动位置跳动
  const row = document.querySelector('.row[data-id="' + id + '"]');
  if (row) row.classList.toggle('sel', PICKED.has(id));
  if (DW_CUR && String(DW_CUR.id) === id) $('dw_pick').innerHTML = PICKED.has(id) ? svgIcon('ok') + ' 已加入对比' : '＋ 加入对比';
}
function clearPicks() {
  PICKED.clear(); renderPickBar(); renderList();
  if (DW_CUR) $('dw_pick').innerHTML = '＋ 加入对比';
}
// 注意：对比浮条上的「×」用事件委托处理（renderPickBar 会重建浮条内容）
function renderPickBar() {
  const bar = $('cmpbar');
  $('cmp_n').textContent = PICKED.size;
  bar.classList.toggle('show', PICKED.size > 0);
  $('cmp_list').innerHTML = Array.from(PICKED).map(id => {
    const r = DATA && DATA.institutions.find(x => String(x.id) === String(id));
    const nm = r ? r.name : id;
    return '<span class="cp"><span title="' + esc(nm) + '">' + esc(trunc(nm, 13)) + '</span><b data-rm="' + esc(id) + '">×</b></span>';
  }).join('');
  Array.prototype.forEach.call($('cmp_list').querySelectorAll('[data-rm]'), b =>
    b.addEventListener('click', () => togglePick(b.getAttribute('data-rm'))));
  $('cmp_go').disabled = PICKED.size < 2;
  $('cmp_go').textContent = PICKED.size < 2 ? '再选 ' + (2 - PICKED.size) + ' 家' : '开始对比';
}

function openCompare() {
  if (PICKED.size < 2) { toast(svgIcon('warn') + ' 至少选择 2 家机构才能对比'); return; }
  const ids = Array.from(PICKED).join(',');
  track('compare', ids, null, PICKED.size);
  $('cmp_sub').textContent = '共 ' + PICKED.size + ' 家机构 · 逐项横向对比';
  $('cmpwrap').classList.add('show');

  const localRows = Array.from(PICKED).map(id => DATA.institutions.find(x => String(x.id) === String(id))).filter(Boolean);

  if (!ENV.api) {
    paintCompare(localRows.map(localCompareRow), true);
    return;
  }
  $('cmp_table').querySelector('tbody').innerHTML = '<tr><td colspan="' + (PICKED.size + 1) + '" style="color:' + DIM + '">正在加载对比数据…</td></tr>';
  fetch('/api/inst/compare?ids=' + encodeURIComponent(ids))
    .then(r => r.ok ? r.json() : null)
    .then(j => {
      if (j && j.ok && j.items && j.items.length) {
        j.items.forEach(it => {
          const lc = localRows.find(x => String(x.id) === String(it.id));
          it._dist_local = lc ? lc._dist : null;
        });
        paintCompare(j.items.map(apiCompareRow), false, j.fields);
      } else paintCompare(localRows.map(localCompareRow), true);
    })
    .catch(() => paintCompare(localRows.map(localCompareRow), true));
}

function localCompareRow(r) {
  let base = BASE_POINTS[$('f_base').value] || BASE_POINTS.tiananmen;
  if (base.lng == null || base.lat == null) base = BASE_POINTS.tiananmen;
  const dist = (r.lng != null && r.lat != null && base.lng != null) ? haversine(base.lng, base.lat, r.lng, r.lat) : null;
  return {
    id: r.id, name: r.name, level: r.level, category: r.category, ownership: r.ownership || '未标注',
    district: r.district, key_specialty_count: r.key_specialty_count || 0,
    national_specialty_count: r.national_specialty_count || 0, municipal_specialty_count: r.municipal_specialty_count || 0,
    dept_count: r.dept_count || 0, networks_text: netDetail(r) || '未纳入',
    national_specialty: r.national_specialty || '', municipal_specialty: r.municipal_specialty || '',
    feature: r.feature || '', addr: r.addr || '', phone: r.phone || '',
    distance_km: dist == null ? null : +dist.toFixed(1),
    distance_text: dist == null ? '—' : dist.toFixed(1) + ' km（距' + base.name + '）',
    coord_precision: r.coord_precision || '—',
  };
}

function apiCompareRow(it) {
  return {
    id: it.id, name: it.name, level: it.level, category: it.category, ownership: it.ownership || '未标注',
    district: it.district, key_specialty_count: it.key_specialty_count || 0,
    national_specialty_count: it.national_specialty_count || 0, municipal_specialty_count: it.municipal_specialty_count || 0,
    dept_count: it.dept_count || 0, networks_text: it.networks_text || '未纳入',
    national_specialty: it.national_specialty || '', municipal_specialty: it.municipal_specialty || '',
    feature: it.feature || '', addr: it.addr || '', phone: it.phone || '',
    distance_km: it.distance_km, distance_text: it.distance_text || '—',
    coord_precision: it.coord_precision || '—',
  };
}

// 需要"越大越好 / 越小越好"判定的数值行
const CMP_NUM = {
  key_specialty_count: 'high', national_specialty_count: 'high', municipal_specialty_count: 'high',
  dept_count: 'high', distance_km: 'low',
};
const CMP_ROWS = [
  ['level', '医院等级'], ['category', '机构类型'], ['ownership', '办别性质'], ['district', '所属区域'],
  ['key_specialty_count', '重点专科数'], ['national_specialty_count', '国家级重点专科'],
  ['municipal_specialty_count', '市级重点专科'], ['dept_count', '科室数量'],
  ['distance_km', '距离基准点'], ['networks_text', '协作网络'],
  ['national_specialty', '国家级专科清单'], ['municipal_specialty', '市级专科清单'],
  ['feature', '擅长科室'], ['addr', '地址'], ['phone', '联系电话'], ['coord_precision', '坐标精度'],
];

function paintCompare(rows, isLocal, fields) {
  const ths = ['对比项'].concat(rows.map(r => esc(r.name)));
  $('cmp_table').querySelector('thead').innerHTML = '<tr><th>' + esc('对比项') + '</th>' + rows.map(r => '<th>' + esc(r.name) + '</th>').join('') + '</tr>';

  const body = CMP_ROWS.map(([k, label]) => {
    const vals = rows.map(r => r[k]);
    let bestIdx = -1;
    if (CMP_NUM[k]) {
      const nums = vals.map(v => (v === null || v === undefined || v === '' ? null : Number(v)));
      const valid = nums.filter(v => v !== null && !isNaN(v));
      if (valid.length > 1) {
        const target = CMP_NUM[k] === 'high' ? Math.max.apply(null, valid) : Math.min.apply(null, valid);
        if (valid.filter(v => v === target).length < valid.length) bestIdx = nums.indexOf(target);
      }
    }
    const cells = rows.map((r, i) => {
      let v = r[k];
      let extra = '';
      if (k === 'level') v = esc(v || '—');
      else if (k === 'ownership') v = ownBadge(r.ownership) || esc(r.ownership);
      else if (k === 'distance_km') { v = esc(r.distance_text); extra = r.distance_km != null ? '<div class="mini">Haversine 球面距离</div>' : ''; }
      else if (k === 'national_specialty' || k === 'municipal_specialty' || k === 'feature') {
        const arr = String(r[k] || '').split(';').filter(x => x.trim());
        v = arr.length ? arr.map(x => '<span class="chip" style="margin:0 3px 3px 0">' + esc(x.trim()) + '</span>').join('') : '<span style="color:' + FAINT + '">—</span>';
      } else if (k === 'phone') v = r.phone ? '<a href="tel:' + esc(r.phone) + '">' + esc(r.phone) + '</a>' : '<span style="color:' + FAINT + '">未收录</span>';
      else if (k === 'addr') v = esc(r.addr || '未收录');
      else if (k === 'category' || k === 'district' || k === 'networks_text' || k === 'coord_precision') v = esc(v || '—');
      else v = '<b>' + esc(v) + '</b>';
      return '<td class="' + (i === bestIdx ? 'best' : '') + '">' + v + extra + '</td>';
    }).join('');
    return '<tr><th>' + esc(label) + (CMP_NUM[k] ? '<div class="mini" style="color:' + FAINT + ';font-size:9.5px;font-weight:400">' + (CMP_NUM[k] === 'high' ? '越高越好' : '越近越好') + '</div>' : '') + '</th>' + cells + '</tr>';
  }).join('');
  const linkRow = '<tr><th>操作</th>' + rows.map(r =>
    '<td><div style="display:flex;gap:6px;flex-wrap:wrap">' +
    '<a class="btn ghost sm" href="' + GUAhAO_114 + '" target="_blank" rel="noopener">114 挂号</a>' +
    (r.addr || r.distance_km != null ? '<button class="btn ghost sm" data-cmp-detail="' + esc(r.id) + '">查看详情</button>' : '') +
    '</div></td>').join('') + '</tr>';

  $('cmp_table').querySelector('tbody').innerHTML = body + linkRow;
  Array.prototype.forEach.call($('cmp_table').querySelectorAll('[data-cmp-detail]'), b =>
    b.addEventListener('click', () => { closeCompare(); openDrawer(b.getAttribute('data-cmp-detail')); }));
}

function closeCompare() { $('cmpwrap').classList.remove('show'); }

// ============================================================================
//  13. 智能导诊（多轮对话）
// ============================================================================
const TRIAGE_STATE = { ctx: [], extra: [], turn: 0, lastDepts: [], done: false };

function initTriageChat() {
  const input = $('t_in');
  input.addEventListener('keydown', e => { if (e.key === 'Enter') sendTriage(); });
  $('t_send').addEventListener('click', sendTriage);
  $('btn_triage_clear').addEventListener('click', resetTriage);
  if (!ENV.http) {
    $('triage_hint').innerHTML = svgIcon('warn') + ' 智能导诊需要本地服务：请运行 <code style="color:' + ACC + '">bash web/start.sh</code> 后访问 http://localhost:5001';
  }
  resetTriage();
}

function resetTriage() {
  TRIAGE_STATE.ctx = []; TRIAGE_STATE.extra = []; TRIAGE_STATE.turn = 0;
  TRIAGE_STATE.lastDepts = []; TRIAGE_STATE.done = false;
  $('chat_body').innerHTML = '';
  addBot(
    '<b>你好，我是智能导诊助手。</b><br>直接用大白话描述你的不舒服就可以了，' +
    '我会先判断该挂哪个科室，再结合<b>医院等级、与你的距离、科室匹配度</b>推荐机构，并把评分理由逐项摊开给你核对。' +
    '<div class="hint">主链路是本地疾病-科室知识库（完全离线可用）；只有在本地完全匹配不到时，才会调用大模型兜底。</div>',
    ['头痛伴呕吐', '孩子发烧咳嗽', '摔了一跤膝盖疼', '高血压复诊', '孕早期产检', '牙痛']
  );
  setEngineTag('local');
}

function setEngineTag(engine) {
  const el = $('eng_tag');
  if (!el) return;
  if (engine === 'llm') { el.textContent = 'AI 兜底'; el.className = 'chip ai'; }
  else { el.textContent = '本地知识库'; el.className = 'chip eng'; }
}

function addUser(text) {
  const d = document.createElement('div');
  d.className = 'msg me';
  d.innerHTML = '<div class="av2">' + svgIcon('user') + '</div>' + '<div class="bub">' + esc(text) + '</div>';
  $('chat_body').appendChild(d);
  scrollChat();
}
function addBot(html, quick, extras) {
  const d = document.createElement('div');
  d.className = 'msg';
  let q = '';
  if (quick && quick.length) {
    q = '<div class="chips">' + quick.map(x =>
      '<span class="chip pick" data-q="' + esc(x) + '">' + esc(x) + '</span>').join('') + '</div>';
  }
  if (extras && extras.length) {
    q += '<div class="chips">' + extras.map(x =>
      '<span class="chip pick acc" data-extra="' + esc(x) + '">＋ ' + esc(x) + '</span>').join('') + '</div>';
  }
  d.innerHTML = '<div class="av2">' + svgIcon('triage') + '</div>' + '<div class="bub">' + html + q + '</div>';
  $('chat_body').appendChild(d);
  Array.prototype.forEach.call(d.querySelectorAll('[data-q]'), c =>
    c.addEventListener('click', () => { $('t_in').value = c.getAttribute('data-q'); sendTriage(); }));
  Array.prototype.forEach.call(d.querySelectorAll('[data-extra]'), c =>
    c.addEventListener('click', () => pickExtra(c.getAttribute('data-extra'))));
  scrollChat();
  return d;
}
function addTyping() {
  const d = document.createElement('div');
  d.className = 'msg'; d.id = 'typing';
  d.innerHTML = '<div class="av2">' + svgIcon('triage') + '</div>' + '<div class="bub"><span class="typing"><i></i><i></i><i></i></span> 正在分析…</div>';
  $('chat_body').appendChild(d);
  scrollChat();
  return d;
}
function scrollChat() { const b = $('chat_body'); b.scrollTop = b.scrollHeight; }

function sendTriage() {
  const q = ($('t_in').value || '').trim();
  if (!q) return;
  $('t_in').value = '';
  if (!ENV.http) {
    addUser(q);
    addBot(svgIcon('warn') + ' 当前为离线打开模式（file://），智能导诊需要本地 Flask 服务支持。' +
      '请运行 <code>bash web/start.sh</code> 后访问 <b>http://localhost:5001</b>。');
    return;
  }
  addUser(q);
  TRIAGE_STATE.ctx.push(q);
  TRIAGE_STATE.turn++;
  track('triage', q, null, TRIAGE_STATE.turn);
  requestTriage();
}

// 追问快捷选项 → 作为 extra 参与科室匹配（不污染原始主诉）
function pickExtra(v) {
  TRIAGE_STATE.extra.push(v);
  addUser(v);
  requestTriage();
}

function requestTriage() {
  const typing = addTyping();
  const q = TRIAGE_STATE.ctx.join(' ');
  const extra = TRIAGE_STATE.extra.join(' ');
  let url = '/api/triage?q=' + encodeURIComponent(q) + '&top_n=6';
  if (extra) url += '&extra=' + encodeURIComponent(extra);
  const d = $('t_district').value, l = $('t_level').value;
  if (d) url += '&district=' + encodeURIComponent(d);
  if (l) url += '&level=' + encodeURIComponent(l);
  const g = $('t_use_geo');
  if (g && g.checked && BASE_POINTS.geo.lng != null) url += '&lng=' + BASE_POINTS.geo.lng + '&lat=' + BASE_POINTS.geo.lat;

  fetch(url).then(r => r.ok ? r.json() : null).then(j => {
    typing.remove();
    if (!j) { addBot(svgIcon('warn') + ' 服务异常，请确认 Flask 已启动（<code>bash web/start.sh</code>）。'); return; }
    setEngineTag(j.engine);
    if (!j.ok) {
      const ex = (j.examples || []).map(x => esc(x));
      let h = '<b style="color:' + WARN + '">没能识别出对应科室。</b><br>' + esc(j.hint || '');
      if (j.llm_attempted) h += '<div class="hint">已尝试 AI 兜底' + (j.llm_note ? '：' + esc(j.llm_note) : '') + '</div>';
      addBot(h, ex);
      return;
    }
    const chips = j.matched_depts.map(x =>
      '<span class="chip' + (x.emergency ? ' emg' : '') + (j.engine === 'llm' ? ' ai' : '') + '">' +
      esc(x.dept) + (x.emergency ? ' · 急诊' : '') + '</span>').join('');
    let html = '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:7px">' +
      (j.engine === 'llm' ? '<span class="chip ai">' + svgIcon('brain') + ' AI 理解</span>' : '<span class="chip eng">本地知识库</span>') +
      '<span style="color:' + DIM + ';font-size:11px">病情「' + esc(j.query) + '」对应科室</span></div>' + chips;
    if (j.engine === 'llm' && j.ai_note) html += '<div class="hint">AI 依据：' + esc(j.ai_note) + '</div>';
    if (j.extra) html += '<div class="hint">已结合补充信息：' + esc(j.extra) + '</div>';

    if (!j.hospitals.length) {
      html += '<div class="hint">暂无具备该科室的匹配机构，试试放宽区域/等级限制。</div>';
      addBot(html);
      return;
    }

    const emg = j.matched_depts.some(x => x.emergency);
    if (emg) {
      html += '<div style="margin-top:9px;padding:9px 12px;border-radius:10px;background:rgba(255,107,129,.12);border:1px solid rgba(255,107,129,.36);color:#ffa4b3;font-size:12px">' +
        svgIcon('warn') + ' 涉及急诊科室：如出现胸痛、意识不清、大出血、呼吸困难等急危症状，请<b>立即拨打 120 或直接前往最近医院急诊</b>，不要依赖线上筛选。</div>';
    }
    html += '<div style="margin-top:10px;color:' + DIM + ';font-size:11.5px">按 <b>等级 0.5 / 距离 0.3 / 科室匹配 0.2</b> 加权评分排序，为你推荐以下 ' + j.hospitals.length + ' 家：</div>';
    html += j.hospitals.map(h => recCard(h, j)).join('');
    addBot(html);

    // 多轮：先追问澄清，再给下一步引导
    if (!TRIAGE_STATE.done) {
      TRIAGE_STATE.done = true;
      const follow = buildFollowUp(j);
      if (follow) setTimeout(() => addBot(follow.text, null, follow.opts), 380);
    }
  }).catch(() => {
    typing.remove();
    addBot(svgIcon('warn') + ' 网络异常，请确认 Flask 已启动（<code>bash web/start.sh</code>）。');
  });
}

function recCard(h, j) {
  const sc = Math.round((h.score || 0) * 100);
  const dist = h.distance_km == null ? '距离未知' : (h.distance_km.toFixed(1) + ' km');
  const dchs = (h.matched_depts || []).map(x => '<span class="chip acc">' + esc(x) + '</span>').join('');
  const bars = (h.reason_detail || []).map(r =>
    '<div class="barrow"><span class="bk">' + esc(r.label) + '</span>' +
    '<span class="bt"><i style="width:' + Math.min(100, Math.round((r.score / (r.weight || 1)) * 100)) + '%"></i></span>' +
    '<span class="bv">' + esc(String(r.value)) + ' · +' + r.score + '</span></div>').join('');
  return '<div class="rec" data-detail="' + esc(h.id) + '">' +
    '<div class="rh"><span class="rn">' + esc(h.name) + '</span>' +
      (h.is_key_specialty ? '<span class="chip emg">重点专科</span>' : '') +
      '<span class="rs">' + sc + '<span style="font-size:10px;color:' + DIM + ';font-weight:400"> 分</span></span></div>' +
    '<div class="rm">' + levelBadge(h.level) + '<span>' + esc(h.district) + '</span><span style="color:' + FAINT + '">·</span><span>' + dist + '</span>' + dchs + '</div>' +
    '<div class="hint" style="color:' + DIM + ';font-size:10.5px;margin-top:3px">' + esc(h.reason || '') + '</div>' +
    '<div class="bars">' + bars + '</div>' +
    '<div style="display:flex;gap:6px;margin-top:9px;flex-wrap:wrap">' +
      '<span class="chip pick" data-open="' + esc(h.id) + '">查看详情</span>' +
      '<span class="chip pick" data-pick2="' + esc(h.id) + '">加入对比</span>' +
    '</div></div>';
}

function buildFollowUp(j) {
  const depts = j.matched_depts.map(x => x.dept);
  const opts = [];
  if (depts.length >= 2) {
    opts.push('症状持续 3 天以内', '症状持续 1 周以上', '伴随发热', '是老年人', '是儿童');
    return { text: '<b>再确认一下，好让推荐更准：</b><br>你命中多个科室（' + depts.slice(0, 3).join('、') + '），补充一点信息我可以收窄范围：', opts: opts };
  }
  opts.push('只要三级医院', '只要离我近的', '不限条件，看全部');
  return { text: '<b>结果出来了。</b>如果还想收窄，可以点下面的快捷条件，或直接在左侧限定区域 / 等级：', opts: opts };
}

// 事件委托：推荐卡片上的操作按钮
document.addEventListener('click', e => {
  const open = e.target.closest('[data-open]');
  if (open) { openDrawer(open.getAttribute('data-open')); return; }
  const pk = e.target.closest('[data-pick2]');
  if (pk) {
    const id = pk.getAttribute('data-pick2');
    togglePick(id);
    toast(PICKED.has(String(id)) ? svgIcon('ok') + ' 已加入对比' : '已移出对比');
    return;
  }
  // 点击推荐卡片空白处也打开详情
  const rc = e.target.closest('.rec');
  if (rc && !e.target.closest('.chip')) openDrawer(rc.getAttribute('data-detail'));
});

// ============================================================================
//  14. 运营后台
// ============================================================================
function initAdminCharts() {
  const mk = id => { const el = $(id); return el ? echarts.init(el) : null; };
  A_KW = mk('a_kw'); A_DIST = mk('a_dist'); A_TRIAGE = mk('a_triage'); A_DAILY = mk('a_daily');
  A_DENSITY = mk('a_density'); A_LEVEL = mk('a_level'); A_SPEC = mk('a_spec'); A_NET = mk('a_net');
  A_OWN = mk('a_own'); A_CAT = mk('a_cat');
}

let _adminBusy = false;
function renderAdmin() {
  renderAdminResources();       // 资源热度：完全由本地真实数据算，离线也有内容
  if (!ENV.api) {
    setText('ad_ev', '—'); setText('ad_ev30', '—'); setText('ad_kw_n', '—'); setText('ad_tbl', '—');
    setText('ad_note', '离线模式：用户行为分析需要本地 Flask 服务（行为日志存于 MySQL fact_user_event 表）');
    renderAdminEmpty('离线模式无法读取行为日志');
    return;
  }
  // 每次进入运营后台都重新拉取，保证刚产生的行为立即反映（接口只做 4 个聚合查询，开销极小）
  if (_adminBusy) return;
  _adminBusy = true;
  fetch('/api/admin/stats').then(r => r.ok ? r.json() : null).then(j => {
    if (!j || !j.ok) { renderAdminEmpty('行为统计获取失败'); return; }
    const b = j.behaviors || {};
    setText('ad_ev', num(b.total_events));
    const ev30 = (b.totals || []).reduce((s, x) => s + (x.n || 0), 0);
    setText('ad_ev30', num(ev30));
    setText('ad_kw_n', num((b.top_keywords || []).length));
    setText('ad_note', b.total_events
      ? ('埋点实时记录 · 累计 ' + num(b.total_events) + ' 条真实操作日志（窗口：近 30 天）')
      : '尚无行为数据：使用一段时间后（搜索 / 筛选 / 导诊 / 查看详情）这里会自动累积');
    const rows = {
      a_kw: [b.top_keywords, '搜索词', ACC], a_dist: [b.top_districts, '区域', ACC2],
      a_triage: [b.top_triage, '病情', VIO],
    };
    Object.keys(rows).forEach(k => {
      const chart = { a_kw: A_KW, a_dist: A_DIST, a_triage: A_TRIAGE }[k];
      const [data, , color] = rows[k];
      if (!chart) return;
      const arr = (data || []).slice(0, 10).reverse();
      chart.setOption(arr.length ? barHOpt(arr.map(x => [trunc(x.label, 12), x.n]), color) : emptyOpt('暂无数据'), !arr.length);
    });
    if (A_DAILY) {
      const daily = b.daily || [];
      if (!daily.length) { A_DAILY.setOption(emptyOpt('暂无数据'), true); }
      else A_DAILY.setOption({
        tooltip: Object.assign({ trigger: 'axis' }, TIP),
        grid: { left: 42, right: 18, top: 14, bottom: 34 },
        xAxis: Object.assign({ type: 'category', data: daily.map(x => String(x.d).slice(5)) }, AXIS,
          { axisLabel: { color: '#8b8d96', fontSize: 9.5, rotate: 30 } }),
        yAxis: Object.assign({ type: 'value' }, AXIS),
        series: [{
          type: 'line', smooth: true, data: daily.map(x => x.n), symbolSize: 6,
          lineStyle: { width: 2.5, color: ACC }, itemStyle: { color: ACC2 },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(76,154,255,.42)' }, { offset: 1, color: 'rgba(76,154,255,0)' }]) },
        }],
      });
    }
    // 表数量
    fetch('/api/about').then(r => r.ok ? r.json() : null).then(a2 => {
      if (a2 && a2.ok) setText('ad_tbl', num(a2.counts.tables));
    }).catch(() => { });
  }).catch(() => renderAdminEmpty('行为统计获取失败'))
    .then(() => { _adminBusy = false; });
}

function emptyOpt(msg) {
  return {
    title: { text: msg, left: 'center', top: 'middle', textStyle: { color: FAINT, fontSize: 12, fontWeight: 400 } },
    xAxis: { show: false }, yAxis: { show: false }, series: [],
  };
}
function renderAdminEmpty(msg) {
  [A_KW, A_DIST, A_TRIAGE, A_DAILY].forEach(c => { if (c) c.setOption(emptyOpt(msg), true); });
}

function renderAdminResources() {
  const o = DATA.overviews || {}, m = DATA.meta || {};
  const dens = (o.districts || []).slice(0, 16).slice().reverse();
  if (A_DENSITY) A_DENSITY.setOption(barHOpt(dens.map(d => [d.district, d.inst_count]), ACC));
  if (A_LEVEL) A_LEVEL.setOption(pieOpt((o.levels || []).map(d =>
    [d.level, d.inst_count, LV_COLOR[d.level] || DIM])));
  if (A_SPEC) A_SPEC.setOption(barHOpt((o.depts || []).slice(0, 12).map(d => [trunc(d.dept_name, 11), d.hospital_count]), ACC2));
  if (A_NET) {
    const nets = (DATA.institutions || []);
    A_NET.setOption(barHOpt([
      ['儿科医联体·核心', nets.filter(r => r.net_pediatric === '核心').length],
      ['儿科医联体·成员', nets.filter(r => r.net_pediatric === '成员').length],
      ['卒中中心', nets.filter(r => r.net_stroke === '1').length],
      ['危重新生儿', nets.filter(r => r.net_neonatal === '市级').length],
      ['危重孕产妇', nets.filter(r => r.net_maternal === '市级').length],
    ], [VIO, '#6d5bd0', CRIT, ACC2, PINK]));
  }
  if (A_OWN) {
    const own = {}; DATA.institutions.forEach(r => own[r.ownership || '未标注'] = (own[r.ownership || '未标注'] || 0) + 1);
    A_OWN.setOption(pieOpt([['公立', own['公立'] || 0, ACC2], ['民营', own['民营'] || 0, WARN], ['未标注', own['未标注'] || 0, DIM]]));
  }
  if (A_CAT) A_CAT.setOption(barHOpt((m.categories || []).slice(0, 10).map(c => [trunc(c.category, 10), c.inst_count]), VIO));
}

// ============================================================================
//  15. 关于页
// ============================================================================
function loadAbout() {
  const snap = DATA.snapshot_time;
  setText('ab_snap', snap);
  // 本地即可算出的规模指标（离线也有内容）
  const local = {
    institutions: DATA.total,
    with_coord: DATA.institutions.filter(r => r.lng != null).length,
    key_specialty_inst: DATA.institutions.filter(r => (r.key_specialty_count || 0) > 0).length,
    network_inst: DATA.institutions.filter(r => r.net_pediatric || r.net_stroke === '1' || r.net_neonatal === '市级' || r.net_maternal === '市级').length,
    districts: (DATA.meta.districts || []).length,
    depts: (DATA.meta.depts || []).length,
  };
  const paint = (c) => {
    $('ab_counts').innerHTML =
      box('机构总数', num(c.institutions) + ' 家') +
      box('含坐标机构', num(c.with_coord) + ' 家') +
      box('重点专科机构', num(c.key_specialty_inst) + ' 家') +
      box('协作网络机构', num(c.network_inst) + ' 家') +
      box('覆盖行政区', num(c.districts) + ' 个') +
      box('标准科室数', num(c.depts) + ' 个') +
      (c.dept_relations ? box('科室关联记录', num(c.dept_relations) + ' 条') : '') +
      (c.triage_dict ? box('导诊知识库词条', num(c.triage_dict) + ' 条') : '') +
      (c.tables ? box('数仓表数量', num(c.tables) + ' 张') : '');
  };
  paint(local);

  $('ab_pipeline').innerHTML = PIPELINE.map(p =>
    '<div class="tstep"><div class="num">' + p.step + '</div><div class="tc">' +
    '<div class="tn">' + esc(p.name) + '</div><div class="tt">' + esc(p.tool) + '</div>' +
    '<div class="td">' + esc(p.desc) + '</div></div></div>').join('');

  $('ab_sources').innerHTML = SOURCES.map(s =>
    '<a class="srccard" href="' + s.url + '" target="_blank" rel="noopener">' +
    '<div class="sn">' + s.icon + ' ' + esc(s.name) + '</div>' +
    '<div class="sd">' + esc(s.desc) + '</div>' +
    '<div class="su">' + esc(s.url) + '</div></a>').join('');

  $('ab_log').innerHTML = UPDATES.map(u =>
    '<div class="logrow"><span class="ld">' + esc(u.date) + '</span><span class="lx">' + esc(u.desc) + '</span></div>').join('');

  $('ab_tables').innerHTML = WAREHOUSE.map(t =>
    '<tr><td class="mono">' + esc(t[0]) + '</td><td class="mono">' + esc(t[1]) + '</td><td>' + esc(t[2]) + '</td></tr>').join('');

  if (!ENV.api) return;
  fetch('/api/about').then(r => r.ok ? r.json() : null).then(j => {
    if (!j || !j.ok) return;
    const c = j.counts || {};
    paint(Object.assign({}, local, {
      dept_relations: c.dept_relations, triage_dict: c.triage_dict, tables: c.tables,
      dwd_institutions: c.dwd_institutions,
    }));
    if (j.warehouse && j.warehouse.length) {
      const LAYER = name => name.indexOf('ods_') === 0 ? 'ODS 原始层'
        : name.indexOf('dwd_') === 0 ? 'DWD 明细层'
        : name.indexOf('dws_') === 0 ? 'DWS 汇总层'
        : name.indexOf('ads_') === 0 ? 'ADS 应用层' : '维度 / 日志表';
      const DESC = {
        ods_institution: '原始机构表（清洗前）', ods_dept_dict: '科室字典', ods_dept_relation: '机构-科室关联原始表',
        ods_specialty: '重点专科原始名单', ods_geocode: '地理编码结果',
        dwd_institution_clean: '机构明细清洗表（去重、办别判定、类别细分）',
        dwd_dept_relation_clean: '机构-科室关联清洗表（重点专科标记）',
        dwd_specialty_clean: '重点专科清洗表',
        dws_inst_by_district: '区域汇总', dws_inst_by_level: '等级汇总',
        dws_inst_by_category: '类型汇总', dws_dept_coverage: '科室覆盖度汇总',
        ads_inst_search: '筛选排序主表（前端数据源）', ads_district_overview: '区域概览',
        ads_level_overview: '等级概览', ads_specialty_hospital: '重点专科医院清单',
        dim_disease_dept: '疾病-科室导诊知识库维度表', dim_ai_cache: '大模型结果缓存',
        dim_poi_cache: '高德周边 POI 缓存', fact_user_event: '用户行为埋点日志',
      };
      $('ab_tables').innerHTML = j.warehouse.map(t =>
        '<tr><td class="mono">' + esc(LAYER(t.name)) + '</td><td class="mono">' + esc(t.name) + '</td>' +
        '<td>' + esc(DESC[t.name] || (t.comment || '—')) + '</td></tr>').join('');
    }
  }).catch(() => { });
}

const PIPELINE = [
  { step: 1, name: '数据采集', tool: '多源公开文件 · 去重后 70 个源文件', desc: '整合北京市卫健委公开数据、医疗机构名录、重点专科公示名单、协作网络名单等多源文件。' },
  { step: 2, name: '数据治理', tool: 'etl/govern_master.py', desc: '机构去重合并、办别归属判定（国有 + 集体全资 → 公立）、机构类型细分、机构更名与别名纠偏。' },
  { step: 3, name: '资源整合', tool: 'etl/integrate_networks.py', desc: '接入儿科医联体、卒中中心、危重新生儿 / 危重孕产妇救治中心等协作网络名单，形成网络维度。' },
  { step: 4, name: '数仓分层 ETL', tool: 'Spark 3.5.3 · spark/etl_hospital.py', desc: 'ODS 原始层 → DWD 明细清洗层 → DWS 汇总层 → ADS 应用层，四层建模，Spark SQL 完成清洗、关联与聚合。' },
  { step: 5, name: '地理编码与距离', tool: '高德地理编码 · Haversine 球面距离', desc: '补全机构经纬度（覆盖率 99.98%），支撑距离计算、距离排序、地图散点与周边配套查询。' },
  { step: 6, name: '索引优化', tool: 'etl/create_indexes.py', desc: '为筛选主表建立复合前缀索引（TEXT 列按 UTF-8 汉字 3 字节取前缀长度），实测典型多维筛选扫描行数由 9,777 降至 33。' },
  { step: 7, name: '服务与可视化', tool: 'Flask + ECharts + Docker Compose', desc: 'Flask 提供筛选 / 排序 / 详情 / 对比 / 导诊 / 埋点接口，ECharts 渲染地图与多维图表，并导出零依赖离线单文件。' },
];
const SOURCES = [
  { icon: svgIcon('gov'), name: '北京市卫生健康委员会', url: 'https://wjw.beijing.gov.cn/', desc: '医疗机构名录、重点专科公示名单、协作网络名单' },
  { icon: svgIcon('phone'), name: '北京市预约挂号统一平台（114）', url: GUAhAO_114, desc: '预约挂号官方入口，仅做链接跳转，不抓取号源与排班数据' },
  { icon: svgIcon('folder'), name: '北京市政务数据资源网', url: 'https://data.beijing.gov.cn/', desc: '医疗机构基础信息开放数据' },
  { icon: svgIcon('map'), name: '高德开放平台', url: 'https://lbs.amap.com/', desc: '地理编码补全与周边配套（地铁站 / 停车场 / 公交站）POI 查询' },
];
const UPDATES = [
  { date: '2026-09-11', desc: '新增机构详情抽屉（联系方式 / 挂号入口 / 重点专科 / 周边配套 / 实时状态）、机构横向对比、智能导诊多轮对话、运营后台与关于页；前端视觉体系重构。' },
  { date: '2026-09-11', desc: '智能导诊接入本地疾病-科室知识库（262 条），并保留大模型零命中兜底能力。' },
  { date: '2026-09-08', desc: '快照数据更新至 9,789 家机构；修正机构更名（空军特色医学中心、北京通用航天医院）与别名映射。' },
  { date: '2026-09-05', desc: '新增医疗协作网络维度（儿科医联体 / 卒中中心 / 危重新生儿 / 危重孕产妇）。' },
  { date: '2026-09-04', desc: '完成数据治理列贯通（办别归属、类别细分、擅长科室三级分级），筛选维度扩展至 7 维。' },
];
const WAREHOUSE = [
  ['ODS 原始层', 'ods_institution / ods_dept_dict / ods_dept_relation / ods_specialty / ods_geocode', '接入原始多源数据'],
  ['DWD 明细层', 'dwd_institution_clean / dwd_dept_relation_clean / dwd_specialty_clean', '清洗、去重、标准化'],
  ['DWS 汇总层', 'dws_inst_by_district / dws_inst_by_level / dws_inst_by_category / dws_dept_coverage', '按区域 / 等级 / 类型 / 科室汇总'],
  ['ADS 应用层', 'ads_inst_search / ads_district_overview / ads_level_overview / ads_specialty_hospital', '直接服务前端查询'],
  ['维度 / 支撑表', 'dim_disease_dept / dim_ai_cache / dim_poi_cache / fact_user_event', '导诊知识库、模型缓存、POI 缓存、行为日志'],
];

// ============================================================================
//  启动
// ============================================================================
console.log('[dashboard] 版本', DASHBOARD_VERSION);
loadData();
