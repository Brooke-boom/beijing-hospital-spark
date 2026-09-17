// ============================================================================
//  北京市医疗机构资源整合与多维筛选可视化系统 — 交互式 SPA
//  数据来源：window.__SNAPSHOT__（内嵌）或 snapshot_data.json（HTTP）
//  设计原则：离线优先。file:// 打开时全功能降级但绝不报错、绝不发网络请求。
// ============================================================================
'use strict';

// ---------- 设计令牌（运行期从 dashboard.html 的 CSS 变量读取，故支持 白天/黑夜 双主题） ----------
// 这些名字在数百处图表配置里被引用，故统一声明为 let，由 loadTokens() 集中刷新；
// 切换主题时先 loadTokens() 再重绘图表，颜色即随主题改变。
// 注意：ECharts 的颜色是喂给 canvas 的，不能写 var(--x)，必须用这里解析后的实值。
let BG, PANEL, PANEL2, EDGE, EDGE2, INK, INK_STRONG, SUB, DIM, FAINT, MAP_BD;
let ACC, ACC2, WARN, CRIT, VIO, VIO2, PINK, ACC_RGB;
let CHART_AXIS, CHART_SPLIT, TIP_BG, TIP_BD, TIP_SH, BODY2;
let MAP_LBL, MAP_AREA, MAP_HI, MAP_RAMP;
let AXIS, TIP, LEGEND, LV_COLOR;

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
  'flask': 'M9 3h6M10 3v6l-5 9a2 2 0 002 3h10a2 2 0 002-3l-5-9V3M7.5 15h9',
  'star': 'M12 3.6l2.62 5.31 5.86.86-4.24 4.13 1 5.84L12 17.02l-5.24 2.72 1-5.84L3.52 9.77l5.86-.86z',
  'mic': 'M12 3a3 3 0 013 3v6a3 3 0 01-6 0V6a3 3 0 013-3zM5 11a7 7 0 0014 0M12 18v3M8.5 21h7',
  'spark': 'M9 9h6v6H9zM4 10v4M20 10v4M10 4h4M10 20h4M6.5 7.5L4 9M17.5 7.5L20 9M6.5 16.5L4 15M17.5 16.5L20 15'
};
function svgIcon(name) {
  var p = ICONS[name];
  if (!p) return '';
  return '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' + p + '"/></svg>';
}


const BASE_POINTS = {
  tiananmen:       { name: '天安门',   lng: 116.397, lat: 39.909 },
  capital_airport: { name: '首都机场', lng: 116.609, lat: 40.080 },
  daxing_airport:  { name: '大兴机场', lng: 116.411, lat: 39.510 },
  geo:             { name: '我的位置', lng: null,    lat: null },
};
const LEVEL_RANK = { '三级': 4, '二级': 3, '一级': 2, '未定级': 1 };
// 等级配色：全局唯一口径，禁止靠数组下标隐式配色（排序一变颜色就错位，把「一级」染成红色）
// 取值由 loadTokens() 按当前主题生成（见下方）
const W_LEVEL = 0.5, W_DIST = 0.3, W_DEPT = 0.2;
const DASHBOARD_VERSION = 'v4.0-ui-refresh-20260911';
const GUAhAO_114 = 'https://www.114yygh.com/';

// ---------- 全局状态 ----------
let DATA = null;
let DIST_LEVEL = {};
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
let ROW_EL_BY_ID = {}, SCATTER_IDX = {}, HOVER_ID = null;   // 地图 ↔ 列表 悬停互指
let CH_OWN, CH_FEAT, CH_NET, CH_LVOWN, CH_TOPSP, CH_DEPTOP, CH_DISTLV, CH_COORD;
let A_KW, A_DIST, A_TRIAGE, A_DAILY, A_DENSITY, A_LEVEL, A_SPEC, A_NET, A_OWN, A_CAT, A_FEAT;

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


// ============================================================================
//  0.5 收藏清单（localStorage 持久化 · 离线可用 · 刷新不丢）
//     定位：先"收藏"再"对比"的两段式决策流——收藏是长期候选池，对比是短期决策台。
// ============================================================================
const FAV_KEY = 'bjyy_favs_v1';
const FAVS = new Set();
let FAVS_OK = true;                     // localStorage 不可用时降级为内存态（不报错）

function loadFavs() {
  try {
    const raw = localStorage.getItem(FAV_KEY);
    if (raw) JSON.parse(raw).forEach(x => FAVS.add(String(x)));
  } catch (e) { FAVS_OK = false; }
}
function saveFavs() {
  if (!FAVS_OK) return;
  try { localStorage.setItem(FAV_KEY, JSON.stringify(Array.from(FAVS))); }
  catch (e) { FAVS_OK = false; }
}
function isFav(id) { return FAVS.has(String(id)); }

function toggleFav(id, silent) {
  id = String(id);
  const on = !FAVS.has(id);
  if (on) FAVS.add(id); else FAVS.delete(id);
  saveFavs();
  syncFavUI();
  if (!silent) {
    toast(on ? svgIcon('star') + ' 已加入收藏清单' : '已从收藏清单移除');
    track('fav', id, on ? 'add' : 'remove', FAVS.size);
  }
}

// 只更新星标/计数，不整表重绘——保持列表滚动位置不跳动
function syncFavUI() {
  const n = FAVS.size;
  const el = $('fav_n'); if (el) el.textContent = n;
  const b = $('btn_favs'); if (b) b.classList.toggle('on', n > 0);
  Array.prototype.forEach.call(document.querySelectorAll('[data-fav]'), btn => {
    const on = FAVS.has(String(btn.getAttribute('data-fav')));
    btn.classList.toggle('on', on);
    btn.title = on ? '取消收藏' : '加入收藏';
  });
  const df = $('dw_fav');
  if (df && DW_CUR) {
    const on = FAVS.has(String(DW_CUR.id));
    df.classList.toggle('on', on);
    df.innerHTML = svgIcon('star') + (on ? ' 已收藏' : ' 收藏');
  }
  const fw = $('favwrap');
  if (fw && fw.classList.contains('show')) renderFavList();
}

function favRows() {
  if (!DATA) return [];
  return Array.from(FAVS).map(id => DATA.institutions.find(x => String(x.id) === String(id))).filter(Boolean);
}

function openFavs() {
  if (!FAVS.size) {
    toast(svgIcon('star') + ' 收藏清单还空着：在机构列表里点右侧的 ★ 就能收藏', 4200);
    return;
  }
  renderFavList();
  $('favwrap').classList.add('show');
}
function closeFavs() { $('favwrap').classList.remove('show'); }

function renderFavList() {
  const rows = favRows();
  $('fav_sub').textContent = '共 ' + rows.length + ' 家机构 · 可一键加入对比（对比上限 ' + PICK_MAX + ' 家）';
  if (!rows.length) {
    $('fav_list').innerHTML = '<div class="favempty">' + svgIcon('star') +
      '收藏清单为空<br>在机构列表点 ★ 即可收藏，刷新页面也不会丢失</div>';
    return;
  }
  $('fav_list').innerHTML = rows.map(r => {
    const dist = r._dist == null ? '距离 —' : r._dist.toFixed(1) + ' km';
    return '<div class="favcard">' +
      '<div class="fn">' + esc(r.name) + '</div>' +
      '<div class="fm">' + levelBadge(r.level) + ownBadge(r.ownership) +
        '<span>' + esc(r.district || '—') + '</span><span>' + (r.dept_count || 0) + ' 个科室</span><span>' + dist + '</span></div>' +
      '<div class="fa">' +
        '<span class="chip pick" data-fopen="' + esc(r.id) + '">查看详情</span>' +
        '<span class="chip pick" data-fpick="' + esc(r.id) + '">' +
          (PICKED.has(String(r.id)) ? svgIcon('ok') + ' 已在对比' : '加入对比') + '</span>' +
        '<span class="chip pick" data-frm="' + esc(r.id) + '">移除</span>' +
      '</div></div>';
  }).join('');
}

function initFavs() {
  loadFavs();
  $('btn_favs').addEventListener('click', openFavs);
  $('fav_close').addEventListener('click', closeFavs);
  $('favwrap').addEventListener('click', e => { if (e.target.id === 'favwrap') closeFavs(); });
  $('fav_clear').addEventListener('click', () => {
    if (!FAVS.size) return;
    if (!window.confirm('确定清空收藏清单（' + FAVS.size + ' 家）？此操作不可撤销。')) return;
    FAVS.clear(); saveFavs(); syncFavUI(); renderFavList(); renderList();
    toast('收藏清单已清空');
  });
  $('fav_all_cmp').addEventListener('click', () => {
    let added = 0, skipped = 0;
    favRows().forEach(r => {
      const id = String(r.id);
      if (PICKED.has(id)) return;
      if (PICKED.size >= PICK_MAX) { skipped++; return; }
      PICKED.add(id); added++;
    });
    renderPickBar(); renderFavList(); syncFavUI(); renderList();
    toast(added ? svgIcon('ok') + ' 已加入对比 ' + added + ' 家' +
        (skipped ? '，' + skipped + ' 家超出对比上限（' + PICK_MAX + '）' : '')
      : svgIcon('warn') + ' 对比已满或收藏均已选入对比');
  });
  $('fav_list').addEventListener('click', e => {
    const op = e.target.closest('[data-fopen]');
    if (op) { closeFavs(); openDrawer(op.getAttribute('data-fopen')); return; }
    const pk = e.target.closest('[data-fpick]');
    if (pk) {
      const id = pk.getAttribute('data-fpick');
      togglePick(id);
      renderFavList();
      toast(PICKED.has(String(id)) ? svgIcon('ok') + ' 已加入对比' : '已移出对比');
      return;
    }
    const rm = e.target.closest('[data-frm]');
    if (rm) { toggleFav(rm.getAttribute('data-frm'), true); renderFavList(); toast('已从收藏清单移除'); }
  });
  const df = $('dw_fav');
  if (df) df.addEventListener('click', () => { if (DW_CUR) toggleFav(DW_CUR.id); });
  syncFavUI();
}

// ============================================================================
//  0.6 筛选区：已选条件 chips / 常用预设 / 实时命中计数
// ============================================================================
const FLT_FIELDS = [
  ['f_kw', '关键词'], ['f_dept', '科室'], ['f_district', '区域'], ['f_level', '等级'],
  ['f_cat', '类型'], ['f_net', '协作网络'], ['f_base', '距离基准点'], ['f_sort', '排序'],
];
const FLT_DEFAULT = { f_base: '', f_sort: 'score' };   // 距离基准默认空：进页自动定位，或输入任意地址
// 排序 = 维度 × 方向；距离维度的语义就是「近 → 远」，固定为升序
const SORT_LABEL = { score: '综合评分', distance: '距离', level: '医院等级', depts: '科室数量', name: '机构名称' };
const SORT_DIR_DEFAULT = { score: 'desc', distance: 'asc', level: 'desc', depts: 'desc', name: 'asc' };
const SORT_FIXED_ASC = { distance: true };
let SORT_DIR = 'desc';

function curSort() { const e = $('f_sort'); return (e && e.value) || 'score'; }
function curDir() { return SORT_FIXED_ASC[curSort()] ? 'asc' : SORT_DIR; }
// 排序方向按钮：距离维度禁用（语义固定），其余维度一键升降序
function syncDirUI() {
  const b = $('f_dir'); if (!b) return;
  const k = curSort(), fixed = !!SORT_FIXED_ASC[k], d = curDir();
  b.textContent = d === 'asc' ? '\u2191' : '\u2193';
  b.setAttribute('data-dir', d);
  b.disabled = fixed;
  b.title = fixed
    ? '距离维度固定为「近 \u2192 远」，无需切换方向'
    : ('当前 ' + SORT_LABEL[k] + (d === 'asc' ? ' 升序' : ' 降序') + '，点击切换');
}
function setSort(key, dir, silent) {
  const e = $('f_sort'); if (e) e.value = key;
  SORT_DIR = dir || SORT_DIR_DEFAULT[key] || 'desc';
  syncDirUI();
  if (!silent) { PAGE = 1; applyFilter(); }
}
// 预设生效后让被改动的控件脉冲高亮一次
function flashControls(ids) {
  (ids || []).forEach(id => {
    const el = $(id); if (!el) return;
    const box = el.closest('.rangebox') || el;
    box.classList.remove('flash'); void box.offsetWidth; box.classList.add('flash');
    setTimeout(() => box.classList.remove('flash'), 1900);
  });
}
function syncKwClear() {
  const i = $('f_kw'), b = i && i.closest('.kwbox');
  if (b) b.classList.toggle('has-val', !!(i.value || '').trim());
}
function syncAiClear() {
  const i = $('f_ai'), b = i && i.closest('.nlq-field');
  if (b) b.classList.toggle('has-val', !!(i.value || '').trim());
}
const NET_LABEL = {
  ped_core: '儿科医联体·核心', ped_member: '儿科医联体·成员', stroke: '卒中中心',
  neonatal: '危重新生儿·市级', maternal: '危重孕产妇·市级',
};
const PRESETS = {
  l3: { f_level: '三级' }, l2: { f_level: '二级' }, l1: { f_level: '一级' },
  near3: { f_level: '三级', f_sort: 'distance' },
  net: { f_net: 'stroke' },
  depttop: { f_sort: 'depts' },
};

function renderFilterChips() {
  const box = $('flt_chips'); if (!box) return;
  const chips = [];
  FLT_FIELDS.forEach(([id, label]) => {
    const el = $(id); if (!el) return;
    const v = (el.value || '').trim();
    if (!v || (FLT_DEFAULT[id] && v === FLT_DEFAULT[id])) return;
    const show = id === 'f_net' ? (NET_LABEL[v] || v)
      : id === 'f_sort' ? ((SORT_LABEL[v] || v) + (curDir() === 'asc' ? ' \u2191' : ' \u2193'))
      : v;
    chips.push('<span class="fchip"><em>' + esc(label) + '</em><b>' + esc(trunc(show, 16)) +
      '</b><i data-fclear="' + id + '" title="移除该条件">×</i></span>');
  });
  box.innerHTML = chips.length
    ? '<span class="fl">已选条件 ' + chips.length + ' 项</span>' + chips.join('') +
      '<button class="freset" type="button" data-freset="1" title="恢复默认：清空全部条件，距离基准回到市中心，排序回到综合评分">\u21ba 恢复默认</button>' +
      '<button class="fclear" type="button" data-fclear="__all__" title="只清空上方筛选条件，保留距离基准与排序设置">\u2715 清除条件</button>'
    : '';
  Array.prototype.forEach.call(box.querySelectorAll('[data-fclear]'), b =>
    b.addEventListener('click', () => {
      const k = b.getAttribute('data-fclear');
      if (k === '__all__') { clearConditions(); return; }
      const el = $(k); if (!el) return;
      el.value = FLT_DEFAULT[k] || '';
      if (k === 'f_base') { BASE_NOW = null; refreshBaseSummary(); }   // 清空基准 → 回落市中心
      if (k === 'f_kw') syncKwClear();
      if (k === 'f_sort') setSort('score', 'desc', true);
      PAGE = 1; applyFilter();
    }));
  const fr = box.querySelector('[data-freset]');
  if (fr) fr.addEventListener('click', resetFilter);
  // 有条件时，重置入口就放在条件条里，底部不再重复出现
  const br = $('btn_reset');
  if (br) br.style.display = chips.length ? 'none' : '';
  const cnt = $('flt_count');
  if (cnt) {
    const tot = DATA ? DATA.total.toLocaleString() : '—';
    cnt.textContent = chips.length
      ? ('已启用 ' + chips.length + ' 个条件 · 命中 ' + FILTERED.length.toLocaleString() + ' 家')
      : ('命中 ' + FILTERED.length.toLocaleString() + ' / ' + tot + ' 家');
  }
}

function syncPresetUI() {
  Array.prototype.forEach.call(document.querySelectorAll('[data-preset]'), b => {
    const spec = PRESETS[b.getAttribute('data-preset')] || {};
    const keys = Object.keys(spec);
    b.classList.toggle('on', keys.length > 0 &&
      keys.every(k => { const e = $(k); return e && e.value === spec[k]; }));
  });
}
// 预设是"一键切换"而非叠加：先清空筛选类字段，再套用，避免越点越乱
function applyPreset(key) {
  const spec = PRESETS[key]; if (!spec) return;
  if (key === 'near3' && BASE_NOW === BASE_POINTS.geo &&
      (BASE_POINTS.geo.lng == null || BASE_POINTS.geo.lat == null)) locateMe();
  ['f_level', 'f_cat', 'f_dept', 'f_district', 'f_net'].forEach(k => { const e = $(k); if (e) e.value = ''; });
  setSort('score', 'desc', true);
  Object.keys(spec).forEach(k => { const e = $(k); if (e) e.value = spec[k]; });
  if (spec.f_sort) SORT_DIR = SORT_DIR_DEFAULT[spec.f_sort] || SORT_DIR;
  syncDirUI();
  flashControls(Object.keys(spec));   // 让用户看清系统改动了哪些控件
  PAGE = 1;
  track('preset', key);
  applyFilter();
}

const NLQ_EXAMPLES = [
  ['朝阳·心脏病·三级', '朝阳区看心脏病的三级医院'],
  ['海淀·儿科·最近', '海淀区离我最近的儿科'],
  ['延庆区医院', '延庆区有哪些医院'],
  ['科室最全的三级', '想找科室最全的三级医院'],
  ['西城·口腔科', '西城区口腔科'],
];
function initAiQuick() {
  const bar = $('ai_quick'); if (!bar) return;
  bar.innerHTML = '<span class="qlab">猜你想搜：</span>' + NLQ_EXAMPLES.map(function(p){
    return '<button class="qb" data-nlq="' + esc(p[1]) + '" title="' + esc(p[1]) + '">' + esc(p[0]) + '</button>';
  }).join('');
  Array.prototype.forEach.call(bar.querySelectorAll('[data-nlq]'), b =>
    b.addEventListener('click', () => {
      $('f_ai').value = b.getAttribute('data-nlq');
      syncAiClear();
      applyNLQ();
    }));
}

function initPresets() {
  Array.prototype.forEach.call(document.querySelectorAll('[data-preset]'), b =>
    b.addEventListener('click', () => applyPreset(b.getAttribute('data-preset'))));
}

// ---- 排序控件：维度下拉 × 方向一键切换 ----
function initSortCtl() {
  const sel = $('f_sort'), btn = $('f_dir');
  if (sel) sel.addEventListener('change', () => {
    SORT_DIR = SORT_DIR_DEFAULT[sel.value] || 'desc';
    syncDirUI();
  });
  if (btn) btn.addEventListener('click', () => {
    if (SORT_FIXED_ASC[curSort()]) return;   // 距离固定近 → 远
    SORT_DIR = curDir() === 'asc' ? 'desc' : 'asc';
    syncDirUI();
    PAGE = 1; applyFilter();
  });
  syncDirUI();
}

// ---- 距离基准摘要：当前生效基准写进 title，便于随时核对 ----
function refreshBaseSummary() {
  const inp = $('f_base'); if (!inp) return;
  const b = curBase();
  const pos = (b.lng != null && b.lat != null)
    ? (b.lng.toFixed(4) + ', ' + b.lat.toFixed(4)) : '尚未确定坐标';
  inp.title = (BASE_NOW
      ? '当前距离基准：' + b.name + '（' + pos + '）'
      : '距离基准未设置 —— 默认按市中心（天安门）估算；点「定位」自动获取，或直接输入地址')
    + '\n支持任意地址（如：海淀区中关村大街27号 / 回龙观 / 潘家园）回车解析';
}

// ---- AI 面板折叠（状态本地记忆） ----
const NLQ_FOLD_KEY = 'bjyy_nlq_fold_v1';
function setNlqFold(fold, persist) {
  const bar = $('nlqbar'), main = $('fltmain'), btn = $('btn_nlq_fold');
  if (!bar) return;
  bar.classList.toggle('collapsed', !!fold);
  if (main) main.classList.toggle('nlq-folded', !!fold);
  if (btn) {
    btn.setAttribute('aria-expanded', fold ? 'false' : 'true');
    btn.title = fold ? '展开 AI 面板' : '折叠 AI 面板';
  }
  if (persist) { try { localStorage.setItem(NLQ_FOLD_KEY, fold ? '1' : '0'); } catch (e) { } }
  if (typeof resizeAll === 'function') setTimeout(resizeAll, 90);
}
function initNlqFold() {
  const btn = $('btn_nlq_fold'); if (!btn) return;
  let fold = false;
  try { fold = localStorage.getItem(NLQ_FOLD_KEY) === '1'; } catch (e) { }
  setNlqFold(fold, false);
  btn.addEventListener('click', () => setNlqFold(!$('nlqbar').classList.contains('collapsed'), true));
}

// ============================================================================
//  0.65 关键词输入联想（离线索引 9,789 家机构名 / 地址，零网络请求）
// ============================================================================
let AC_IDX = null, AC_ITEMS = [], AC_ACT = -1;
function buildAcIndex() {
  AC_IDX = ((DATA && DATA.institutions) || []).map(r => ({
    n: r.name || '', a: r.addr || '', d: r.district || '',
  }));
}
function acQuery(q) {
  q = (q || '').trim().toLowerCase();
  if (!q || !AC_IDX) return [];
  const out = [];
  for (let i = 0; i < AC_IDX.length && out.length < 320; i++) {
    const r = AC_IDX[i];
    if ((r.n + ' ' + r.a).toLowerCase().indexOf(q) < 0) continue;
    out.push(r);
  }
  out.sort((x, y) => {
    const xn = x.n.toLowerCase().indexOf(q) >= 0 ? 0 : 1;
    const yn = y.n.toLowerCase().indexOf(q) >= 0 ? 0 : 1;
    if (xn !== yn) return xn - yn;        // 名称命中排在地址命中之前
    return x.n.length - y.n.length;       // 名称更短的更可能是目标
  });
  return out.slice(0, 8);
}
function acMark(name, q) {
  if (!q) return esc(name);
  const i = name.toLowerCase().indexOf(q);
  if (i < 0) return esc(name);
  return esc(name.slice(0, i)) + '<mark>' + esc(name.slice(i, i + q.length)) + '</mark>'
    + esc(name.slice(i + q.length));
}
function acRender(list, q) {
  const box = $('kw_ac'); if (!box) return;
  AC_ITEMS = list; AC_ACT = -1;
  if (!list.length) {
    box.innerHTML = '<div class="acempty">没有匹配的机构，换个关键词试试</div>';
    box.classList.add('show');
    return;
  }
  box.innerHTML = list.map((r, i) =>
    '<div class="acitem" data-i="' + i + '">' +
      '<span class="an">' + acMark(r.n, q) + '</span>' +
      '<span class="am">' + esc(r.d) + '</span>' +
    '</div>').join('');
  box.classList.add('show');
}
function acClose() {
  const box = $('kw_ac');
  if (box) { box.classList.remove('show'); box.innerHTML = ''; }
  AC_ITEMS = []; AC_ACT = -1;
}
function acMove(d) {
  const box = $('kw_ac'), n = AC_ITEMS.length;
  if (!box || !n) return;
  AC_ACT = (AC_ACT + d + n) % n;
  Array.prototype.forEach.call(box.querySelectorAll('.acitem'), (el, i) =>
    el.classList.toggle('act', i === AC_ACT));
  const act = box.querySelector('.acitem.act');
  if (act && act.scrollIntoView) act.scrollIntoView({ block: 'nearest' });
}
function acPick(i) {
  const r = AC_ITEMS[i]; if (!r) return;
  const inp = $('f_kw');
  inp.value = r.n;
  syncKwClear();
  acClose();
  PAGE = 1; applyFilter();
}
function initKwAC() {
  const box = $('kw_ac'), inp = $('f_kw');
  if (!box || !inp) return;
  const openAc = () => {
    const q = inp.value.trim();
    if (!q) { acClose(); return; }
    acRender(acQuery(q), q.toLowerCase());
  };
  inp.addEventListener('input', () => { if (inp.value.trim()) openAc(); else acClose(); });
  inp.addEventListener('focus', () => { if (inp.value.trim()) openAc(); });
  inp.addEventListener('keydown', e => {
    if (!box.classList.contains('show')) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); acMove(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); acMove(-1); }
    else if (e.key === 'Enter') {
      if (AC_ACT >= 0) { e.preventDefault(); acPick(AC_ACT); } else acClose();
    } else if (e.key === 'Escape') acClose();
  });
  inp.addEventListener('blur', () => setTimeout(acClose, 140));
  box.addEventListener('mousedown', e => {
    const it = e.target.closest ? e.target.closest('.acitem') : null;
    if (!it) return;
    e.preventDefault();
    acPick(+it.getAttribute('data-i'));
  });
}

// ============================================================================
//  0.7 语音输入（Web Speech API · 演示亮点）
//     限制：浏览器要求安全上下文，file:// 下麦克风被禁用 → 给明确指引而非静默失败。
// ============================================================================
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
function initVoice(btnId, inputId, after) {
  const btn = $(btnId), inp = $(inputId);
  if (!btn || !inp) return;
  if (!SR) {
    btn.classList.add('off');
    btn.title = '当前浏览器不支持语音识别（建议 Chrome / Edge）';
    btn.addEventListener('click', () => toast(svgIcon('warn') + ' 当前浏览器不支持语音识别，请用 Chrome / Edge 打开'));
    return;
  }
  let rec = null, listening = false;
  btn.addEventListener('click', () => {
    if (!ENV.http) {
      toast(svgIcon('warn') + ' 语音输入需要安全上下文：请运行 <code>bash web/start.sh</code> 后访问 <b>http://localhost:5001</b>（file:// 下浏览器会禁用麦克风）', 5600);
      return;
    }
    if (listening) { try { rec.stop(); } catch (e) { } return; }
    rec = new SR();
    rec.lang = 'zh-CN'; rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 1;
    let finalTxt = '';
    rec.onstart = () => {
      listening = true; btn.classList.add('rec'); inp.classList.add('listening');
      toast(svgIcon('mic') + ' 正在聆听…请直接说出你的需求', 9000);
    };
    rec.onresult = e => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalTxt += t; else interim += t;
      }
      inp.value = (finalTxt + interim).trim();
    };
    rec.onerror = ev => {
      const m = {
        'not-allowed': '麦克风权限被拒绝，请在地址栏允许麦克风后重试',
        'service-not-allowed': '浏览器拒绝了语音服务（需 HTTPS 或 localhost）',
        'audio-capture': '没有检测到麦克风设备',
        'no-speech': '没有听到声音，请靠近麦克风再说一次',
        'network': '语音识别服务网络不可用，请检查网络',
      }[ev.error] || ('语音识别出错：' + ev.error);
      toast(svgIcon('warn') + ' ' + m, 4400);
    };
    rec.onend = () => {
      listening = false; btn.classList.remove('rec'); inp.classList.remove('listening');
      const v = (finalTxt || inp.value || '').trim();
      if (!v) return;
      inp.value = v;
      if (after) { after(); return; }
      PAGE = 1; applyFilter(); toast(svgIcon('ok') + ' 已按语音内容筛选');
    };
    try { rec.start(); } catch (e) { toast(svgIcon('warn') + ' 语音启动失败：' + (e.message || e)); }
  });
}

// ============================================================================
//  0.8 生成式总结（本地模板打底 + Agnes 润色 · 三级降级：LLM → 缓存 → 本地）
//     离线优先：没有后端时本地模板照样给出一段总结，绝不空白。
// ============================================================================
function summaryShell(status, body) {
  return '<div class="ah"><span class="lb">' + svgIcon('spark') + ' 生成式总结</span>' +
    '<span class="st">' + esc(status) + '</span></div><div class="tx">' + body + '</div>';
}
function genSummary(facts, localHtml, mount) {
  if (!mount) return;
  mount.style.display = '';
  mount.innerHTML = summaryShell('正在生成…',
    '<span class="typing"><i></i><i></i><i></i></span> 正在综合结构化结果…');
  const show = (html, tag, note) => {
    mount.innerHTML = summaryShell(tag, html + '<span class="caret"></span>');
    if (note) mount.insertAdjacentHTML('beforeend',
      '<div class="hint" style="margin-top:7px;color:' + DIM + '">' + esc(note) + '</div>');
    setTimeout(() => { const c = mount.querySelector('.caret'); if (c) c.remove(); }, 1500);
  };
  if (!ENV.api) { show(localHtml, '本地模板（离线可用）'); return; }
  const url = '/api/ai/summary?facts=' + encodeURIComponent(JSON.stringify(facts)) +
              '&local=' + encodeURIComponent(localHtml);
  fetch(url).then(r => r.ok ? r.json() : null)
    .then(j => {
      if (!j || !j.summary) { show(localHtml, '本地模板'); return; }
      const llm = j.engine === 'llm';
      show(llm ? esc(j.summary).replace(/\n+/g, '<br>') : j.summary,
           llm ? 'Agnes 大模型润色' : '本地模板', j.note || '');
      track('summary', String(facts['场景'] || ''), j.engine, 1);
    })
    .catch(() => show(localHtml, '本地模板'));
}

// 多维筛选结果的本地总结（只用真实字段，不编造）
function localSummary(rows, meta) {
  if (!rows || !rows.length) return '当前条件下没有匹配到机构，建议放宽区域或等级限制后重试。';
  const lv = {};
  rows.forEach(r => { const k = r.level || '未知'; lv[k] = (lv[k] || 0) + 1; });
  const lvTxt = Object.keys(lv).sort((a, b) => (LEVEL_RANK[b] || 0) - (LEVEL_RANK[a] || 0))
    .map(k => k + ' ' + lv[k] + ' 家').join('、');
  const scope = [meta.district, meta.level, (meta.depts || []).join('、'), meta.kw].filter(Boolean).join(' · ') || '全部范围';
  const near = rows.filter(r => r._dist != null).sort((a, b) => a._dist - b._dist)[0];
  const top = rows.slice().sort((a, b) => (b._score || 0) - (a._score || 0))[0];
  const keyN = rows.filter(r => (r.key_specialty_count || 0) > 0).length;
  const p = [];
  p.push('在<b>' + esc(scope) + '</b>条件下共匹配到 <b>' + meta.total + '</b> 家机构，' +
         '当前页等级构成为 ' + esc(lvTxt) + '。');
  if (top) p.push('综合评分最高的是<b>' + esc(top.name) + '</b>（' + esc(top.district || '—') +
    ' · ' + (top._score || 0).toFixed(3) + ' 分）' +
    (top.key_specialty_count ? '，含 ' + top.key_specialty_count + ' 项重点专科' : '') + '。');
  if (near && near._dist != null) p.push('距' + esc(meta.baseName || '基准点') + '最近的是<b>' +
    esc(near.name) + '</b>（' + near._dist.toFixed(1) + ' km）。');
  if (keyN) p.push('其中 <b>' + keyN + '</b> 家拥有重点专科认定，可优先纳入候选。');
  return p.join('');
}
function currentScopeMeta() {
  const base = curBase();
  return {
    district: $('f_district').value || '', level: $('f_level').value || '',
    depts: $('f_dept').value ? [$('f_dept').value] : [],
    kw: ($('f_kw').value || '').trim(),
    sort: (SORT_LABEL[curSort()] || '综合评分') + (curDir() === 'asc' ? ' 升序' : ' 降序'),
    baseName: BASE_NOW ? base.name : '市中心', total: FILTERED.length,
  };
}
function ovFacts(rows, meta) {
  const lv = {};
  rows.forEach(r => { const k = r.level || '未知'; lv[k] = (lv[k] || 0) + 1; });
  const near = rows.filter(r => r._dist != null).sort((a, b) => a._dist - b._dist)[0];
  const top = rows.slice().sort((a, b) => (b._score || 0) - (a._score || 0))[0];
  return {
    '场景': '多维筛选结果总结',
    '筛选条件': { 关键词: meta.kw || null, 科室: meta.depts, 区域: meta.district || '全部',
                 等级: meta.level || '全部', 排序: meta.sort },
    '命中机构数': meta.total, '参与总结的样本数': rows.length, '等级构成': lv,
    '评分最高': top ? { 名称: top.name, 区域: top.district,
                       评分: +(top._score || 0).toFixed(3),
                       重点专科数: top.key_specialty_count || 0 } : null,
    '距离最近': near ? { 名称: near.name, 距离km: +near._dist.toFixed(1), 基准点: meta.baseName } : null,
    '含重点专科机构数': rows.filter(r => (r.key_specialty_count || 0) > 0).length,
  };
}
function initOverSummary() {
  const btn = $('btn_ov_sum'); if (!btn) return;
  btn.addEventListener('click', () => {
    if (!FILTERED.length) { toast(svgIcon('warn') + ' 当前没有可总结的结果，请先放宽筛选条件'); return; }
    const meta = currentScopeMeta();
    const rows = FILTERED.slice(0, 30);
    genSummary(ovFacts(rows, meta), localSummary(rows, meta), $('ov_sum'));
    track('summary_click', 'filter', null, rows.length);
  });
}

// ---------- 主题令牌装载：把 CSS 变量解析成 ECharts 能用的实值 ----------
function cssVar(name, fb) {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || (fb || '');
  } catch (e) { return fb || ''; }
}
function loadTokens() {
  BG = cssVar('--bg', '#0a0b0d'); PANEL = cssVar('--panel', '#131419'); PANEL2 = cssVar('--panel-2', '#171922');
  EDGE = cssVar('--line', 'rgba(255,255,255,.08)'); EDGE2 = cssVar('--line-2', 'rgba(255,255,255,.13)');
  INK = cssVar('--ink', '#ededee'); INK_STRONG = cssVar('--ink-strong', '#ffffff');
  SUB = cssVar('--ink-2', '#a0a2aa'); DIM = cssVar('--ink-3', '#73757e'); FAINT = cssVar('--ink-4', '#4c4e57');
  ACC = cssVar('--acc', '#6b8cff'); ACC_RGB = cssVar('--acc-rgb', '107,140,255');
  ACC2 = cssVar('--teal', '#46c08a'); WARN = cssVar('--warn', '#e0a23b');
  CRIT = cssVar('--crit', '#e0697e'); VIO = cssVar('--vio', '#9a8cf0');
  VIO2 = cssVar('--vio-2', VIO2); PINK = cssVar('--pink', '#e69ab5');
  CHART_AXIS = cssVar('--chart-axis', '#8b8d96'); CHART_SPLIT = cssVar('--chart-split', 'rgba(255,255,255,.06)');
  TIP_BG = cssVar('--tip-bg', 'rgba(19,20,25,.96)'); TIP_BD = cssVar('--tip-bd', 'rgba(255,255,255,.14)');
  TIP_SH = cssVar('--tip-sh', 'rgba(0,0,0,.8)'); BODY2 = cssVar('--body-2', '#c9cbd2');
  MAP_LBL = cssVar('--map-label', '#8b94ad'); MAP_AREA = cssVar('--map-area', '#171922');
  MAP_HI = cssVar('--map-hi', '#2a3550'); MAP_BD = cssVar('--map-bd', 'rgba(255,255,255,.09)');
  MAP_RAMP = [cssVar('--map-r1'), cssVar('--map-r2'), cssVar('--map-r3'),
              cssVar('--map-r4', '#5d74bb'), cssVar('--map-r5', '#6f64b8')];

  // ECharts 统一主题片段（每次装载重建，颜色随主题变化）
  AXIS = {
    axisLine: { lineStyle: { color: EDGE2 } },
    axisTick: { show: false },
    axisLabel: { color: CHART_AXIS, fontSize: 10 },
    splitLine: { lineStyle: { color: CHART_SPLIT } },
  };
  TIP = {
    backgroundColor: TIP_BG, borderColor: TIP_BD, borderWidth: 1,
    textStyle: { color: INK, fontSize: 11.5 },
    extraCssText: 'border-radius:9px;box-shadow:0 10px 30px -10px ' + TIP_SH,
  };
  LEGEND = { textStyle: { color: SUB, fontSize: 10.5 }, itemWidth: 10, itemHeight: 10, itemGap: 12 };
  LV_COLOR = { '三级': CRIT, '二级': WARN, '一级': ACC, '未定级': VIO, '不适用': DIM };
}

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
  el.style.background = cssVar('--crit', '#e0697e'); el.style.color = '#fff';
  el.innerHTML = svgIcon('err') + ' 数据加载失败：' + esc(e && e.message ? e.message : e) +
    ' &nbsp;·&nbsp; 请硬刷新（Mac <b>Cmd+Shift+R</b> / Win <b>Ctrl+F5</b>）' +
    '；或改用离线单文件 <code>web/dashboard_offline.html</code>';
}

// ============================================================================
//  2. 初始化
// ============================================================================
function init() {
  try {
    loadTokens();                       // 先按当前主题装载配色令牌，再画图
    $('loading').classList.add('hide');
    setText('m_total', DATA.total.toLocaleString());
    setText('m_time', DATA.snapshot_time);
    setText('m_time2', DATA.snapshot_time);
    buildAcIndex();                     // 关键词联想索引（离线）

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
    initTheme();
    initTriageChat();
    initDrawer();
    initCompare();
    initFavs();
    initPresets();
    initAiQuick();
    initSortCtl();
    initKwAC();
    initNlqFold();
    initVoice('btn_voice_ai', 'f_ai', applyNLQ);
    initVoice('btn_voice_t', 't_in', sendTriage);
    initOverSummary();
    initAIState();
    initBase();
    // URL 状态还原（deep link）：hash 携带的筛选 / 排序 / 基准优先于 localStorage
    const st = readState();
    _STATE_RESTORED = !!(st.kw || st.district || st.level || st.cat || st.dept || st.net || st.base || st.sort);
    if (st.kw) $('f_kw').value = st.kw;
    if (st.district) $('f_district').value = st.district;
    if (st.level) $('f_level').value = st.level;
    if (st.cat) $('f_cat').value = st.cat;
    if (st.dept) $('f_dept').value = st.dept;
    if (st.net) $('f_net').value = st.net;
    if (st.sort) setSort(st.sort, st.dir || 'asc', true);
    if (st.base) {
      const m = /^([^|]+)\|(-?[\d.]+),(-?[\d.]+)$/.exec(st.base);
      if (m) { BASE_POINTS.custom = { name: m[1], lng: +m[2], lat: +m[3] }; setBase(BASE_POINTS.custom, true); }
    }
    refreshBaseSummary();
    autoLocate();          // 进页默认自动定位（静默降级到市中心估算；deep link 携带状态时跳过）
    applyFilter();
    if (st.v && st.v !== 'overview' && document.querySelector('.navtab[data-view="' + st.v + '"]')) switchView(st.v);
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
  ['f_district', 'f_level', 'f_cat', 'f_dept', 'f_net', 'f_sort'].forEach(id => {
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
    syncKwClear();
    PAGE = 1; applyFilter();
    clearTimeout(_kwT);
    _kwT = setTimeout(() => { const v = kwEl.value.trim(); if (v.length >= 2) track('search', v); }, 1100);
  });

  $('btn_reset').addEventListener('click', resetFilter);
  $('btn_clear_pick').addEventListener('click', clearPicks);
  const bkw = $('btn_kw_clear');
  if (bkw) bkw.addEventListener('click', () => {
    const e = $('f_kw'); e.value = ''; syncKwClear(); PAGE = 1; applyFilter(); e.focus();
  });

  const aiInput = $('f_ai');
  if (aiInput) {
    aiInput.addEventListener('input', syncAiClear);
    aiInput.addEventListener('keydown', e => { if (e.key === 'Enter') applyNLQ(); });
  }
  const bAi = $('btn_ai'); if (bAi) bAi.addEventListener('click', applyNLQ);
  const bAc = $('btn_ai_clear'); if (bAc) bAc.addEventListener('click', clearNLQ);

  $('pg_prev').addEventListener('click', () => { if (PAGE > 1) { PAGE--; renderList(); } });
  $('pg_next').addEventListener('click', () => { if (PAGE * PAGE_SIZE < FILTERED.length) { PAGE++; renderList(); } });
  $('pg_size').addEventListener('change', e => { PAGE_SIZE = +e.target.value; PAGE = 1; renderList(); });

  // 距离基准输入框：回车 / 失焦 / 选下拉项时解析为坐标
  const fb = $('f_base');
  if (fb) {
    fb.addEventListener('change', () => resolveBase(fb.value));
    fb.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); resolveBase(fb.value); } });
  }

  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if ($('favwrap').classList.contains('show')) closeFavs();
    else if ($('cmpwrap').classList.contains('show')) closeCompare();
    else if ($('drawer').classList.contains('show')) closeDrawer();
  });
}

// 只清空筛选条件，保留距离基准与排序设置
function clearConditionsSilent() {
  ['f_kw', 'f_district', 'f_level', 'f_cat', 'f_dept', 'f_net']
    .forEach(k => { const e = $(k); if (e) e.value = ''; });
  syncKwClear();
}
function clearConditions() { clearConditionsSilent(); PAGE = 1; applyFilter(); }
// 恢复默认视图：条件 + 距离基准 + 排序全部回到初始状态（基准空 → 按市中心估算）
function resetFilter() {
  clearConditionsSilent();
  BASE_NOW = null;
  const fb = $('f_base'); if (fb) fb.value = '';
  setSort('score', 'desc', true);
  refreshBaseSummary();
  PAGE = 1; applyFilter();
}

// ============================================================================
//  4. 地理定位：进页自动定位（默认起点），「定位」按钮随时重定位
// ============================================================================
let AUTO_LOCATED = false;   // 本次会话只自动请求一次，避免反复弹授权

function _applyGeoFix(lng, lat, acc, opts) {
  // opts: {manual:bool} —— 自动定位与手动定位共用同一落地逻辑
  const manual = !!(opts && opts.manual);
  const hint = locateHint(lng, lat);
  const area = hint ? ('北京市' + hint.district) : null;
  BASE_POINTS.geo.lng = lng; BASE_POINTS.geo.lat = lat;
  BASE_POINTS.geo.name = '我的位置' + (area ? ' · ' + area : '') + '(±' + acc + 'm)';
  setBase(BASE_POINTS.geo, true);   // silent：统一由下方 setSort+applyFilter 触发一次重算
  refreshBaseSummary();
  setSort('distance', 'asc', true);
  applyFilter();
  const loc = hint
    ? (area + ' · 最近机构 ' + hint.near + '（约 ' + hint.nearKm.toFixed(1) + ' km）')
    : (lng + ', ' + lat);
  toast(svgIcon('location') + (manual ? ' 已定位到 ' : ' 已自动定位到 ') + loc +
    ' · 精度 ±' + acc + 'm · 已按距离升序排序（可输入任意地址替换起点）', 5600);
  track(manual ? 'locate' : 'locate_auto', null, null, acc);
}

function _geoRequest(onOk, onErr, opts) {
  navigator.geolocation.getCurrentPosition(
    pos => onOk(pos, opts),
    err => {
      const m = { 1: '用户拒绝授权', 2: '位置不可用', 3: '请求超时' }[err.code] || err.message;
      onErr(m, err);
    },
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
  );
}

function locateMe() {
  const btn = $('btn_locate');
  if (!navigator.geolocation) { toast(svgIcon('warn') + ' 当前浏览器不支持定位 API'); return; }
  if (!ENV.http) { toast(svgIcon('warn') + ' 需通过 http://localhost:5001 打开才能授权定位（file:// 被浏览器禁止）', 5200); return; }
  const old = btn.textContent;
  btn.disabled = true; btn.textContent = '⏳ 定位中…';
  _geoRequest(
    (pos) => {
      const lng = +pos.coords.longitude.toFixed(6), lat = +pos.coords.latitude.toFixed(6);
      const acc = Math.round(pos.coords.accuracy);
      _applyGeoFix(lng, lat, acc, { manual: true });
      btn.textContent = '已定位';
      setTimeout(() => { btn.textContent = '重新定位'; btn.disabled = false; }, 1300);
    },
    (m) => {
      btn.textContent = old; btn.disabled = false;
      toast(svgIcon('warn') + ' 定位失败：' + m + ' —— 也可直接在框内输入起始地址', 5200);
    });
}

// 进页默认自动定位（仅 http://localhost 全栈环境；file:// 离线版与已拒绝授权时静默跳过）
function autoLocate() {
  if (AUTO_LOCATED || _STATE_RESTORED || !ENV.http || !navigator.geolocation) return;
  try { if (localStorage.getItem(BASE_STORE_KEY)) return; } catch (e) { }  // 用户上次自选过起点则尊重
  AUTO_LOCATED = true;
  _geoRequest(
    (pos) => {
      const lng = +pos.coords.longitude.toFixed(6), lat = +pos.coords.latitude.toFixed(6);
      _applyGeoFix(lng, lat, Math.round(pos.coords.accuracy), { manual: false });
    },
    () => { /* 静默降级：保持「市中心」估算，不打扰 */ });
}

// ============================================================================
//  4.5 距离基准：内置地标 / 我的定位 / 自定义输入（地标 / 区名 / 机构名 / 地址）
//      解析完全在前端离线完成：区中心 = 区内机构坐标均值；机构 = 名称/地址匹配
// ============================================================================
let BASE_NOW = null;   // 当前生效基准点（必含 lng/lat；未生效时 curBase 回退天安门）
const BASE_STORE_KEY = 'bjyy_base_v1';

function curBase() {
  if (BASE_NOW && BASE_NOW.lng != null && BASE_NOW.lat != null) return BASE_NOW;
  return BASE_POINTS.tiananmen;
}
function setBase(p, silent) {
  BASE_NOW = p;
  const input = $('f_base');
  if (input) input.value = p.name;
  refreshBaseSummary();
  try { localStorage.setItem(BASE_STORE_KEY, JSON.stringify({ name: p.name, lng: p.lng, lat: p.lat })); } catch (e) { }
  if (!silent) {
    if (curSort() !== 'distance') setSort('distance', 'asc', true); else syncDirUI();
    PAGE = 1; applyFilter();
  }
}
function initBase() {
  try {
    const p = JSON.parse(localStorage.getItem(BASE_STORE_KEY) || 'null');
    if (p && p.name && p.lng != null && p.lat != null) {
      BASE_NOW = p;
      const i = $('f_base'); if (i) i.value = p.name;
    }
  } catch (e) { }
}
function resolveBase(q) {
  q = (q || '').trim();
  const input = $('f_base');
  const cur = BASE_NOW;
  const revert = () => { if (input) input.value = cur ? cur.name : ''; };
  if (!q || (cur && q === cur.name)) { revert(); return; }
  // 1) 内置地标
  for (const k in BASE_POINTS) {
    if (k !== 'geo' && BASE_POINTS[k].name === q) { setBase(BASE_POINTS[k]); return; }
  }
  // 2) 我的位置
  if (q.indexOf('我的位置') === 0) {
    if (BASE_POINTS.geo.lng == null) { toast(svgIcon('warn') + ' 还没有定位 —— 请先点右侧「定位」按钮', 4200); revert(); }
    else setBase(BASE_POINTS.geo);
    return;
  }
  if (!DATA || !DATA.institutions || !DATA.institutions.length) { revert(); return; }
  const ok = r => r.lng != null && r.lat != null;
  // 3) 区名 → 区内机构坐标均值（区中心）
  const pts = DATA.institutions.filter(r => ok(r) && r.district === q);
  if (pts.length >= 3) {
    const lng = pts.reduce((s, r) => s + r.lng, 0) / pts.length;
    const lat = pts.reduce((s, r) => s + r.lat, 0) / pts.length;
    setBase({ name: q + '(区中心)', lng: +lng.toFixed(4), lat: +lat.toFixed(4) });
    toast(svgIcon('location') + ' 距离基准：' + q + ' 区中心（区内 ' + pts.length.toLocaleString() + ' 家机构坐标均值）', 5200);
    track('base_custom', q);
    return;
  }
  // 4) 任意地址/小区/街道 → 后端高德地理编码（http://localhost 全栈可用，服务端缓存）；
  //    失败（无 Key / 超额 / 断网）或 file:// 离线时，降级为机构名匹配
  if (ENV.http) { geocodeAddress(q, function () { matchInstitutionBase(q, ok); }); return; }
  matchInstitutionBase(q, ok);
}

// 机构名 / 地址关键词本地匹配（离线兜底，file:// 也可用）→ 取等级最高的一家
function matchInstitutionBase(q, ok) {
  const input = $('f_base');
  const cur = BASE_NOW;
  const revert = () => { if (input) input.value = cur ? cur.name : ''; };
  if (!DATA || !DATA.institutions || !DATA.institutions.length) { revert(); return; }
  const ql = q.toLowerCase();
  let hits = DATA.institutions.filter(r => ok(r) && r.name === q);
  if (!hits.length) hits = DATA.institutions.filter(r => ok(r) && r.name.toLowerCase().indexOf(ql) === 0);
  if (!hits.length) hits = DATA.institutions.filter(r => ok(r) && r.name.toLowerCase().indexOf(ql) >= 0);
  if (!hits.length) hits = DATA.institutions.filter(r => ok(r) && (r.addr || '').toLowerCase().indexOf(ql) >= 0);
  if (hits.length) {
    hits.sort((a, b) => (LEVEL_RANK[b.level] || 0) - (LEVEL_RANK[a.level] || 0));
    const r = hits[0];
    setBase({ name: r.name, lng: r.lng, lat: r.lat });
    toast(svgIcon('location') + ' 距离基准：' + r.name + '（' + (r.district || '') + '）· 已按距离升序', 5200);
    track('base_custom', r.name);
    return;
  }
  toast(svgIcon('warn') + ' 没找到「' + trunc(q, 16) + '」—— 可输入 地址 / 区名 / 机构名，或点「定位」', 5200);
  revert();
}

// 任意地址解析（主路径）：调 /api/geocode（高德 Web 服务，结果服务端缓存）。
// 成功 → 设为基准点；失败（无 Key/超额/断网）→ onFail 兜底（机构名本地匹配），不白屏不卡死。
function geocodeAddress(q, onFail) {
  const input = $('f_base');
  const cur = BASE_NOW;
  const revert = () => { if (input) input.value = cur ? cur.name : ''; };
  if (input) input.disabled = true;
  fetch('/api/geocode?address=' + encodeURIComponent(q))
    .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
    .then(d => {
      if (!d || d.lng == null || d.lat == null) throw new Error((d && d.error) || 'empty');
      const name = (d.formatted && d.formatted.length <= 26) ? d.formatted : q;
      setBase({ name: name, lng: d.lng, lat: d.lat });
      toast(svgIcon('location') + ' 已解析「' + trunc(q, 16) + '」→ ' + (d.formatted || name) +
        (d.district ? '（' + d.district + '）' : '') + ' · 已按距离升序', 5200);
      track('base_geocode', q);
    })
    .catch(() => {
      if (onFail) { onFail(); return; }
      toast(svgIcon('warn') + ' 「' + trunc(q, 16) + '」地址解析失败 —— 可改用 机构名 / 区名，'
        + '或点「定位」自动获取', 5200);
      revert();
    })
    .then(() => { if (input) input.disabled = false; });
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
    const abtn = $('btn_ai');
    if (abtn) abtn.classList.add('loading');
    fetch('/api/ai/parse?q=' + encodeURIComponent(raw))
      .then(x => x.ok ? x.json() : null)
      .then(j => {
        if (j && j.ok && j.conditions) { Object.assign(r, j.conditions, { engine: 'llm' }); }
        commitNLQ(r, raw);
      }).catch(() => commitNLQ(r, raw))
      .then(() => { if (abtn) abtn.classList.remove('loading'); });
    return;
  }
  if (r.hits.length || r.kw) track('nlq', raw, null, r.hits.length);
  commitNLQ(r, raw);
}

function commitNLQ(r, raw) {
  const echo = $('ai_echo');
  const setSel = (id, v) => { const el = $(id); if (el && v) el.value = v; };
  setSel('f_district', r.district); setSel('f_level', r.level); setSel('f_cat', r.cat);
  setSel('f_dept', r.dept);
  if (r.sort) setSort(r.sort, SORT_DIR_DEFAULT[r.sort] || SORT_DIR, true); else syncDirUI();
  if (r.kw) $('f_kw').value = r.kw;
  syncKwClear();

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
  syncAiClear();
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

// 定位成功后反查所在区，把经纬度翻译成「北京市XX区」
function locateHint(lng, lat) {
  const rows = (DATA && DATA.institutions) || [];
  let best = null, bd = Infinity;
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    if (r.lng == null || r.lat == null) continue;
    const d = (r.lng - lng) * (r.lng - lng) + (r.lat - lat) * (r.lat - lat);
    if (d < bd) { bd = d; best = r; }
  }
  if (!best) return null;
  let sx = 0, sy = 0, n = 0;
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    if (r.lng == null || r.district !== best.district) continue;
    sx += r.lng; sy += r.lat; n++;
  }
  return {
    district: best.district,
    near: best.name,
    nearKm: haversine(lng, lat, best.lng, best.lat),
    centerKm: n ? haversine(lng, lat, sx / n, sy / n) : null,
  };
}

function applyFilter() {
  if (!DATA) return;
  const kw = ($('f_kw').value || '').trim().toLowerCase();
  const district = $('f_district').value, level = $('f_level').value, cat = $('f_cat').value;
  const dept = $('f_dept').value, net = $('f_net').value;
  let base = curBase();
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

  const ASC = {
    score:    (a, b) => a._score - b._score,
    distance: (a, b) => (a._dist == null ? 9e9 : a._dist) - (b._dist == null ? 9e9 : b._dist),
    level:    (a, b) => (LEVEL_RANK[a.level] || 0) - (LEVEL_RANK[b.level] || 0),
    depts:    (a, b) => (a.dept_count || 0) - (b.dept_count || 0),
    name:     (a, b) => String(a.name).localeCompare(String(b.name), 'zh-CN'),
  };
  const cmpAsc = ASC[curSort()] || ASC.score;
  const dirMul = curDir() === 'asc' ? 1 : -1;
  FILTERED.sort((a, b) => cmpAsc(a, b) * dirMul);

  renderKPI();
  renderList();
  updateCharts();
  updateAnalyticsCharts();
  renderFilterChips();
  syncPresetUI();
  writeState();   // 筛选状态写入 URL hash（deep link 可还原）
}

function renderKPI() {
  setText('v_match', FILTERED.length.toLocaleString());
  const vmt = $('v_match');
  if (vmt) { vmt.classList.remove('pop'); void vmt.offsetWidth; vmt.classList.add('pop'); }
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
    const hasCond = ['f_kw', 'f_district', 'f_level', 'f_cat', 'f_dept', 'f_net']
      .some(k => { const e = $(k); return e && e.value; });
    box.innerHTML = '<div class="empty">' +
      '<svg class="eic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"'
      + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<circle cx="11" cy="11" r="7"/><path d="M16.4 16.4L21 21"/></svg>' +
      '<div class="et">没有符合条件的机构</div>' +
      '<div class="es">' + (hasCond
        ? '当前条件组合偏窄，试着减少 1–2 个条件，或放宽关键词'
        : '数据快照可能为空，请检查加载状态') + '</div>' +
      (hasCond ? '<button class="btn ghost sm" id="btn_empty_clear" type="button">清除全部条件</button>' : '') +
      '</div>';
    const bec = $('btn_empty_clear');
    if (bec) bec.addEventListener('click', clearConditions);
    return;
  }
  const baseNow = curBase();
  const distLabel = '距' + (BASE_NOW ? baseNow.name : '市中心');

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
      '<button class="rowstar' + (isFav(r.id) ? ' on' : '') + '" data-fav="' + esc(r.id) + '" title="' +
        (isFav(r.id) ? '取消收藏' : '加入收藏') + '">' + svgIcon('star') + '</button>' +
    '</div>';
  }).join('');

  ROW_EL_BY_ID = {}; HOVER_ID = null;
  Array.prototype.forEach.call(box.querySelectorAll('.row'), el => {
    const rid = String(el.getAttribute('data-id'));
    ROW_EL_BY_ID[rid] = el;
    el.addEventListener('click', ev => {
      if (ev.target.closest('[data-pick]') || ev.target.closest('[data-fav]')) return;
      openDrawer(el.getAttribute('data-id'));
    });
    el.addEventListener('mouseenter', () => hoverRowToMap(rid, true));
    el.addEventListener('mouseleave', () => hoverRowToMap(rid, false));
  });
  Array.prototype.forEach.call(box.querySelectorAll('[data-pick]'), el => {
    el.addEventListener('click', ev => { ev.stopPropagation(); togglePick(el.getAttribute('data-pick')); });
  });
  Array.prototype.forEach.call(box.querySelectorAll('[data-fav]'), el => {
    el.addEventListener('click', ev => { ev.stopPropagation(); toggleFav(el.getAttribute('data-fav')); });
  });
}

// ============================================================================
//  8. 概览图表
// ============================================================================
// 地图底图：独立成函数，便于切换主题时按新配色重绘
function drawMap() {
  if (!MAP_CHART || !DATA || !DATA.overviews) return;
  MAP_CHART.setOption({
      backgroundColor: 'transparent', textStyle: { color: INK },
      tooltip: Object.assign({ trigger: 'item', formatter: mapTipFmt }, TIP),
      geo: {
        map: 'beijing', roam: true, zoom: 1, layoutCenter: ['50%', '50%'], layoutSize: '96%', aspectScale: 0.9,
        label: { show: true, color: MAP_LBL, fontSize: 10 },
        itemStyle: { borderColor: MAP_BD, borderWidth: 1, areaColor: MAP_AREA },
        emphasis: { label: { color: INK_STRONG }, itemStyle: { areaColor: MAP_HI } },
        select: { itemStyle: { areaColor: MAP_HI }, label: { color: INK_STRONG } },
      },
      visualMap: { min: 0, max: 1300, show: false,
        inRange: { color: MAP_RAMP } },
      series: [{
        name: '机构数', type: 'map', geoIndex: 0,
        data: DATA.overviews.districts.map(d => ({ name: d.district, value: d.inst_count })),
      }],
    });
}

function initCharts() {
  try {
    const mapDiv = $('map');
    if (typeof echarts === 'undefined') throw new Error('ECharts 库未加载');
    if (!DATA || !DATA.geojson) throw new Error('数据中缺少 geojson');
    setMapDiag('', '⏳ 正在初始化 ECharts 地图…');

    MAP_CHART = echarts.init(mapDiv, null, { renderer: 'canvas' });
    echarts.registerMap('beijing', DATA.geojson);
    DIST_LEVEL = computeDistLevel();
    const reg = echarts.getMap && echarts.getMap('beijing');
    if (!reg || !reg.geoJson) throw new Error('registerMap("beijing") 失败');

    drawMap();
    MAP_CHART.resize();
    MAP_CHART.on('click', p => {
      if (p.seriesType === 'effectScatter' && p.data && p.data.instId != null) { openDrawer(p.data.instId); return; }
      if (p.name) { $('f_district').value = p.name; PAGE = 1; track('filter_district', p.name, 'map'); applyFilter(); }
    });
    // 悬停散点 -> 高亮列表对应行（点击仍然是打开详情 / 筛选区县）
    MAP_CHART.on('mouseover', p => {
      if (p.seriesType === 'effectScatter' && p.data && p.data.instId != null) hoverMapToList(p.data.instId, true);
    });
    MAP_CHART.on('mouseout', p => {
      if (p.seriesType === 'effectScatter' && p.data && p.data.instId != null) hoverMapToList(p.data.instId, false);
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

// ============================================================================
//  12. 白天 / 黑夜双主题
// ============================================================================
const THEME_KEY = 'bjyy_theme';
function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}
// 切主题 = 换 HTML 上的 data-theme（CSS 令牌整体切换）+ 用新令牌重绘所有图表
function applyTheme(name) {
  const th = (name === 'light') ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', th);
  try { localStorage.setItem(THEME_KEY, th); } catch (e) { }
  loadTokens();
  try { drawMap(); } catch (e) { console.error('[applyTheme] 地图', e); }
  try { updateCharts(); } catch (e) { console.error('[applyTheme] 总览图表', e); }
  try { updateAnalyticsCharts(); } catch (e) { console.error('[applyTheme] 分析图表', e); }
  try { renderKPI(); } catch (e) { }
  try { renderList(); } catch (e) { }
  try { renderFilterChips(); } catch (e) { }
  try { if (DW_CUR) openDrawer(DW_CUR.id); } catch (e) { }
  try {
    const va = $('view-admin');
    if (va && va.classList.contains('active')) renderAdmin();
  } catch (e) { }
  setTimeout(resizeAll, 40);
}
function toggleTheme() {
  const h = document.documentElement;
  h.classList.add('theming');
  applyTheme(currentTheme() === 'light' ? 'dark' : 'light');
  setTimeout(() => h.classList.remove('theming'), 450);
}
function initTheme() {
  const b = $('btn_theme');
  if (b) b.addEventListener('click', toggleTheme);
}

// ---------- 地图 ↔ 列表 悬停互指 ----------
// 列表行悬停 -> 地图上对应散点高亮 + 弹出气泡；地图散点悬停 -> 列表中对应行高亮并滚动到可视区
function hoverRowToMap(id, on) {
  if (!MAP_CHART) return;
  const i = SCATTER_IDX[String(id)];
  if (i == null) return;                      // 该机构不在当前地图散点集合内
  try {
    MAP_CHART.dispatchAction(on
      ? { type: 'highlight', seriesIndex: 1, dataIndex: i }
      : { type: 'downplay', seriesIndex: 1, dataIndex: i });
    MAP_CHART.dispatchAction(on
      ? { type: 'showTip', seriesIndex: 1, dataIndex: i }
      : { type: 'hideTip' });
  } catch (e) { }
}
function hoverMapToList(id, on) {
  const key = String(id);
  if (on && HOVER_ID === key) return;
  if (!on && HOVER_ID !== key) return;
  HOVER_ID = on ? key : null;
  const el = ROW_EL_BY_ID[key];
  if (!el) return;
  el.classList.toggle('hl', !!on);
  if (on && el.scrollIntoView) { try { el.scrollIntoView({ block: 'nearest' }); } catch (e) { } }
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
      label: { color: INK, fontSize: 11, formatter: '{b}\n{c}' }, labelLine: { lineStyle: { color: EDGE2 } },
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
      { axisLabel: { color: CHART_AXIS, fontSize: 9.5, rotate: 38, interval: 0 } }),
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
    SCATTER_IDX = {};                                   // 机构 id -> 散点 dataIndex
    points.forEach((r, i) => { SCATTER_IDX[String(r.id)] = i; });
    MAP_CHART.setOption({
      series: [
        { type: 'map', geoIndex: 0 },
        {
          type: 'effectScatter', coordinateSystem: 'geo', zlevel: 2,
          data: points.map(r => ({ name: r.name, value: [r.lng, r.lat, r.level || '其他'], instId: r.id, inst: r })),
          symbolSize: v => v[2] === '三级' ? 7 : v[2] === '二级' ? 5 : 3,
          rippleEffect: { period: 4, scale: 2.8, brushType: 'stroke' },
          itemStyle: { color: v => v[2] === '三级' ? CRIT : v[2] === '二级' ? WARN : ACC2, cursor: 'pointer' },
          showEffectOn: 'render',
          tooltip: Object.assign({ trigger: 'item', formatter: scatterTipFmt }, TIP),
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

function computeDistLevel() {
  const m = {};
  (DATA.institutions || []).forEach(r => {
    const dk = r.district || '未知';
    if (!m[dk]) m[dk] = { '三级':0, '二级':0, '一级':0, '未定级':0, '不适用':0 };
    m[dk][lvGroup(r.level)]++;
  });
  return m;
}

function mapTipFmt(p) {
  if (p.seriesType === 'effectScatter') return scatterTipFmt(p);
  const dl = DIST_LEVEL[p.name]; const total = p.value || 0;
  let s = '<b style="font-size:13px">' + esc(p.name) + '</b><br/>机构总数：<b style="color:' + ACC + '">' + total + '</b> 家';
  if (dl) s += '<div style="margin-top:4px;font-size:12px;color:' + SUB + '">' +
    '三级 ' + dl['三级'] + ' · 二级 ' + dl['二级'] + ' · 一级 ' + dl['一级'] + '<br/>' +
    '未定级 ' + dl['未定级'] + ' · 不适用 ' + dl['不适用'] + '</div>';
  s += '<div style="margin-top:5px;font-size:11px;color:' + DIM + '">点击该区可直接筛选</div>';
  return s;
}

function scatterTipFmt(p) {
  const r = p.data && p.data.inst; if (!r) return esc(p.name || '');
  const lvl = (r.level === '不适用医院分级') ? '不分级' : (r.level || '—');
  return '<div style="max-width:250px">' +
    '<b style="font-size:13px">' + esc(r.name) + '</b>' +
    '<div style="color:' + SUB + ';margin:3px 0 6px;font-size:12px">' + esc(r.district) + ' · ' + esc(lvl) + '</div>' +
    (r.addr ? '<div style="font-size:12px;color:' + BODY2 + ';line-height:1.4">' + esc(r.addr) + '</div>' : '') +
    '<div style="font-size:12px;color:' + BODY2 + ';margin-top:3px">科室 ' + num(r.dept_count) + ' 个 · 重点专科 ' + num(r.key_specialty_count) + ' 项</div>' +
    '<div style="font-size:11px;color:' + ACC + ';margin-top:6px">点击查看机构详情 →</div>' +
    '</div>';
}

function pieOpt(data) {
  return {
    tooltip: Object.assign({ trigger: 'item', formatter: '{b}：{c}（{d}%）' }, TIP),
    legend: Object.assign({ bottom: 0 }, LEGEND),
    series: [{
      type: 'pie', radius: ['42%', '70%'], center: ['50%', '44%'],
      data: data.map(d => ({ name: d[0], value: d[1], itemStyle: { color: d[2] } })),
      label: { color: INK, fontSize: 11 }, labelLine: { lineStyle: { color: EDGE2 } },
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
      { axisLabel: { color: CHART_AXIS, fontSize: 9, rotate: cats.length > 10 ? 38 : 0, interval: 0 } }),
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
  ], [VIO, VIO2, CRIT, ACC2, ACC]));

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
    CUR_VIEW = v;
    if (v === 'admin') renderAdmin();
    if (v === 'network') renderNetwork();
    writeState();
    setTimeout(resizeAll, 60);
  }));
}

// ============================================================================
//  10.5 协作网络页：四大网络 KPI + 成员机构 chips（点击联动总览筛选）
//       汇总数字来自 ads_network_summary（快照），成员列表由本地机构数据计算
// ============================================================================
let _netRendered = false;
const NET_DEFS = {
  pediatric: { pred: r => r.net_pediatric === '核心' || r.net_pediatric === '成员',
               isCore: r => r.net_pediatric === '核心',
               fnet: r => (r.net_pediatric === '核心' ? 'ped_core' : 'ped_member') },
  stroke:    { pred: r => r.net_stroke === '1',     isCore: () => false, fnet: () => 'stroke' },
  neonatal:  { pred: r => r.net_neonatal === '市级', isCore: () => false, fnet: () => 'neonatal' },
  maternal:  { pred: r => r.net_maternal === '市级', isCore: () => false, fnet: () => 'maternal' },
};
function renderNetwork() {
  if (_netRendered) return;
  _netRendered = true;
  const summaries = {};
  ((DATA.overviews || {}).networks || []).forEach(n => { summaries[n.network_key] = n; });
  Object.keys(NET_DEFS).forEach(key => {
    const def = NET_DEFS[key];
    const members = DATA.institutions.filter(def.pred)
      .sort((a, b) => (def.isCore(b) - def.isCore(a)) || (LEVEL_RANK[b.level] || 0) - (LEVEL_RANK[a.level] || 0));
    const s = summaries[key] || {};
    setText('net_k_' + key, num(s.member_count != null ? s.member_count : members.length));
    const core = key === 'pediatric' ? members.filter(def.isCore).length : (s.core_count || 0);
    const districts = s.district_count != null ? s.district_count : new Set(members.map(r => r.district)).size;
    const l3 = s.level_3_count != null ? s.level_3_count : members.filter(r => r.level === '三级').length;
    const m = $('netm_' + key);
    if (m) m.innerHTML =
      '<span class="nm">成员 <b>' + num(members.length) + '</b></span>' +
      (key === 'pediatric' ? '<span class="nm">核心 <b>' + num(core) + '</b></span>' : '') +
      '<span class="nm">覆盖区县 <b>' + num(districts) + '</b></span>' +
      '<span class="nm">三级医院 <b>' + num(l3) + '</b></span>';
    const c = $('netc_' + key);
    if (c) c.innerHTML = members.map(r =>
      '<button class="chip acc pick" type="button" data-net="' + def.fnet(r) + '" data-name="' +
      esc(r.name) + '" title="回总览按该网络筛选">' + esc(r.name) + '</button>').join('');
  });
  // 事件委托：成员 chips → 总览页按网络筛选
  Array.prototype.forEach.call(document.querySelectorAll('#view-network .deptchips'), box => {
    box.addEventListener('click', e => {
      const b = e.target && e.target.closest ? e.target.closest('[data-net]') : null;
      if (!b) return;
      const sel = $('f_net');
      if (sel) sel.value = b.getAttribute('data-net');
      switchView('overview');
      PAGE = 1; applyFilter();
      toast(svgIcon('ok') + ' 已筛选「' + esc(b.getAttribute('data-name')) + '」所在网络');
      track('network_jump', b.getAttribute('data-net'));
    });
  });
}

// ============================================================================
//  10.6 URL 状态还原（deep link）：视图 / 筛选 / 排序 / 距离基准 写入 location.hash，
//       刷新、分享、收藏链接均可还原现场。仅 replaceState，不产生历史记录。
// ============================================================================
let CUR_VIEW = 'overview';
let _STATE_RESTORED = false;

function writeState() {
  try {
    if (!DATA) return;
    const p = new URLSearchParams();
    p.set('v', CUR_VIEW || 'overview');
    const g = id => { const el = $(id); return el ? (el.value || '').trim() : ''; };
    ['kw', 'district', 'level', 'cat', 'dept', 'net'].forEach(k => { const v = g('f_' + k); if (v) p.set(k, v); });
    if (curSort() !== 'score') p.set('sort', curSort());
    if (curDir() !== 'asc') p.set('dir', curDir());
    const b = BASE_NOW;
    if (b && b.name && b.lng != null) p.set('base', b.name + '|' + b.lng + ',' + b.lat);
    const h = '#' + p.toString();
    if (location.hash !== h) history.replaceState(null, '', h);
  } catch (e) { /* 状态写入失败不影响主流程 */ }
}

function readState() {
  const st = {};
  try {
    if (!location.hash || location.hash.length < 2) return st;
    const p = new URLSearchParams(location.hash.slice(1));
    ['v', 'kw', 'district', 'level', 'cat', 'dept', 'net', 'sort', 'dir', 'base']
      .forEach(k => { const v = p.get(k); if (v) st[k] = v; });
  } catch (e) { }
  return st;
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
  syncFavUI();

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
  const base = curBase();
  const dist = (r.lng != null && r.lat != null) ? haversine(base.lng, base.lat, r.lng, r.lat).toFixed(1) + ' km' : '—';
  $('pane-ov').innerHTML =
    '<div class="infogrid">' +
      box('机构类型', esc(r.category || '—')) +
      box('医院等级', levelBadge(r.level) + '<div class="mini" style="color:' + FAINT + ';font-size:11px;margin-top:4px">' + esc(r.level === '不适用医院分级' ? '该类型不参加等级评审' : r.level) + '</div>') +
      box('办别性质', (r.ownership || '未标注') + (r.ownership_basis ? '<div style="color:' + FAINT + ';font-size:10px;margin-top:3px">依据 ' + esc(r.ownership_basis) + '</div>' : '')) +
      box('科室数量', num(r.dept_count) + ' 个' +
        (r.dept_count_src === 'baike_claim'
          ? '<div style="color:' + FAINT + ';font-size:10px;margin-top:3px">官网口径 · 在线核实</div>'
          : r.dept_count_src === 'baike_table'
            ? '<div style="color:' + FAINT + ';font-size:10px;margin-top:3px">百科科室表 · 在线核实</div>'
            : '')) +
      box('重点专科', num(r.key_specialty_count) + ' 项') +
      box('距' + (BASE_NOW ? base.name : '市中心'), dist) +
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
    mun.map(x => '<span class="chip" style="background:rgba(var(--warn-rgb),.14);color:' + WARN + ';border-color:rgba(var(--warn-rgb),.34)">' + esc(x.trim()) + '</span>').join('') + '</div></div>';
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
        '<div class="tagrow"><span class="tk" style="background:rgba(var(--crit-rgb),.16);color:var(--t-crit-fg);border:1px solid rgba(var(--crit-rgb),.34)">' + esc(d.trim()) + '</span>' +
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
    '<div class="poilist"><div class="poi"><div class="pi" style="background:rgba(var(--acc-rgb),.14)">' + svgIcon('location') + '</div>' +
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
  near += poiBlock(svgIcon('metro'), '最近地铁站', a.metro, 'rgba(var(--acc-rgb),.16)') +
          poiBlock(svgIcon('parking'), '附近停车场', a.parking, 'rgba(var(--warn-rgb),.16)') +
          poiBlock(svgIcon('bus'), '附近公交站', a.bus, 'rgba(var(--teal-rgb),.16)');
  if (!a.metro && !a.parking && !a.bus) {
    near += '<div class="blk"><h4><span class="bar"></span>地址与导航</h4><div class="poilist">' +
      '<div class="poi"><div class="pi" style="background:rgba(var(--acc-rgb),.14)">' + svgIcon('location') + '</div>' + '<div class="pb">' +
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
  let base = curBase();
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
const TRIAGE_STATE = { ctx: [], extra: [], turn: 0, lastDepts: [], done: false, noClarify: false };

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
  TRIAGE_STATE.lastDepts = []; TRIAGE_STATE.done = false; TRIAGE_STATE.noClarify = false;
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
  else if (engine === 'clarify') { el.textContent = '澄清中'; el.className = 'chip clo'; }
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
  if (TRIAGE_STATE.noClarify) url += '&nocl=1';
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
    // 意图纠错可视化：把"我纠正了什么"明确告诉用户，而不是悄悄改掉
    if (j.correction) {
      html += '<div class="hint" style="color:' + WARN + '">' + svgIcon('warn') + ' 已把「' + esc(j.correction.from) +
        '」理解为「<b>' + esc(j.correction.to) + '</b>」，并据此限定了区域。</div>';
    }
    if (j.engine === 'llm' && j.ai_note) html += '<div class="hint">AI 依据：' + esc(j.ai_note) + '</div>';
    if (j.extra) html += '<div class="hint">已结合补充信息：' + esc(j.extra) + '</div>';

    if (!j.hospitals.length) {
      html += '<div class="hint">暂无具备该科室的匹配机构，试试放宽区域/等级限制。</div>';
      addBot(html);
      return;
    }

    const emg = j.matched_depts.some(x => x.emergency);
    if (emg) {
      html += '<div style="margin-top:9px;padding:9px 12px;border-radius:10px;background:rgba(var(--crit-rgb),.12);border:1px solid rgba(var(--crit-rgb),.36);color:var(--t-crit-fg);font-size:12px">' +
        svgIcon('warn') + ' 涉及急诊科室：如出现胸痛、意识不清、大出血、呼吸困难等急危症状，请<b>立即拨打 120 或直接前往最近医院急诊</b>，不要依赖线上筛选。</div>';
    }
    html += '<div style="margin-top:10px;color:' + DIM + ';font-size:11.5px">' +
      esc(j.weight_profile || '按科室优先加权评分排序') + '，为你推荐以下 ' + j.hospitals.length + ' 家：</div>';
    html += j.hospitals.map(h => recCard(h, j)).join('');
    const node = addBot(html);

    // 生成式总结：把结构化推荐写成一段话（本地模板打底，Agnes 可用时润色）
    const mount = document.createElement('div');
    mount.className = 'aibox';
    node.querySelector('.bub').appendChild(mount);
    genSummary(triageFacts(j), localTriageSummary(j), mount);

    // 歧义澄清优先于通用追问：先确认科室，再谈收窄条件
    if (j.clarify) {
      const cnode = addBot(clarifyHtml(j.clarify), null);
      cnode.querySelector('.bub').insertAdjacentHTML('beforeend', clarifyChips(j.clarify));
      Array.prototype.forEach.call(cnode.querySelectorAll('[data-clarify]'), c =>
        c.addEventListener('click', () => {
          Array.prototype.forEach.call(cnode.querySelectorAll('[data-clarify]'), x => x.classList.add('off'));
          pickExtra(c.getAttribute('data-clarify'));
        }));
      Array.prototype.forEach.call(cnode.querySelectorAll('[data-clarify-skip]'), c =>
        c.addEventListener('click', () => {
          TRIAGE_STATE.noClarify = true;
          Array.prototype.forEach.call(cnode.querySelectorAll('[data-clarify]'), x => x.classList.add('off'));
          addUser('不限科室，都看看');
          requestTriage();
        }));
    } else if (!TRIAGE_STATE.done) {
      TRIAGE_STATE.done = true;
      const follow = buildFollowUp(j);
      if (follow) setTimeout(() => addBot(follow.text, null, follow.opts), 380);
    }
  }).catch(() => {
    typing.remove();
    addBot(svgIcon('warn') + ' 网络异常，请确认 Flask 已启动（<code>bash web/start.sh</code>）。');
  });
}


// ---- 歧义澄清（反问）与导诊生成式总结 ----
function clarifyHtml(c) {
  return '<b>' + svgIcon('brain') + ' 需要再确认一下——</b><br>' + esc(c.question) +
    '<div class="hint">同一症状可能对应不同科室，确认后我会把范围收窄，推荐会更准；' +
    '也可以选「都看看」跳过这一步。</div>';
}
function clarifyChips(c) {
  return '<div class="chips">' + c.options.map(o =>
    '<span class="chip pick acc" data-clarify="' + esc(o.dept) + '">' + esc(o.label) + '</span>').join('') +
    '<span class="chip pick" data-clarify-skip="1">都看看，不限科室</span></div>';
}
function triageFacts(j) {
  const hs = j.hospitals || [];
  const lv = {}; hs.forEach(h => { const k = h.level || '未知'; lv[k] = (lv[k] || 0) + 1; });
  const near = hs.filter(h => h.distance_km != null).sort((a, b) => a.distance_km - b.distance_km)[0];
  const top = hs.slice().sort((a, b) => (b.score || 0) - (a.score || 0))[0];
  return {
    '场景': '智能导诊推荐结果总结',
    '用户主诉': j.query,
    '纠错': j.correction || null,
    '命中科室': (j.matched_depts || []).map(x => x.dept),
    '解析引擎': j.engine === 'llm' ? 'Agnes 大模型兜底' : '本地疾病-科室知识库',
    '推荐机构数': hs.length, '等级构成': lv,
    '评分最高': top ? { 名称: top.name, 区域: top.district,
                       评分: Math.round((top.score || 0) * 100) / 100,
                       专科实力: top.specialty_label || '无专科标注',
                       重点专科: !!top.is_key_specialty } : null,
    '距离最近': near ? { 名称: near.name, 距离km: near.distance_km,
                       基准: j.located ? '用户定位' : '市中心（用户未定位）' } : null,
    '评分权重': j.weight_profile || '科室优先加权评分',
    '含急诊科室': (j.matched_depts || []).some(x => x.emergency),
  };
}
function localTriageSummary(j) {
  const hs = j.hospitals || [];
  if (!hs.length) return '暂未匹配到具备该科室的机构，可放宽区域或等级限制后再试。';
  const depts = (j.matched_depts || []).map(x => x.dept);
  const near = hs.filter(h => h.distance_km != null).sort((a, b) => a.distance_km - b.distance_km)[0];
  const top = hs.slice().sort((a, b) => (b.score || 0) - (a.score || 0))[0];
  const keyN = hs.filter(h => h.specialty_label && /重点专科/.test(h.specialty_label)).length;
  const ref = j.located ? '距您' : '距市中心';
  const p = [];
  p.push('针对「' + esc(j.query || '') + '」，系统从' +
    (j.engine === 'llm' ? '大模型兜底' : '本地疾病-科室知识库') + '命中 <b>' + esc(depts.join('、')) +
    '</b>，筛出 <b>' + hs.length + '</b> 家具备该科室的机构。');
  if (top) p.push('按<b>科室优先</b>加权评分（' + esc(j.weight_profile || '') + '），<b>' + esc(top.name) +
    '</b> 评分最高（' + Math.round((top.score || 0) * 100) + ' 分' +
    (top.specialty_label ? '，该院为' + esc(top.specialty_label) : '') + '）。');
  if (near && near.distance_km != null) {
    p.push(near === top ? '它同时也是' + ref + '最近的一家，约 ' + near.distance_km.toFixed(1) + ' km。'
      : ref + '最近的是<b>' + esc(near.name) + '</b>，约 ' + near.distance_km.toFixed(1) + ' km。');
  }
  if (keyN) p.push('其中 ' + keyN + ' 家在该科室上有国家级/市级重点专科认定，可优先考虑。');
  if (hs.some(h => (h.matched_depts || []).some(x => /急诊/.test(x)))) {
    p.push('如出现胸痛、意识不清、大出血、呼吸困难等急危症状，请<b>立即拨打 120</b>，不要依赖线上筛选。');
  }
  return p.join('');
}

function recCard(h, j) {
  const sc = Math.round((h.score || 0) * 100);
  // 只有真正拿到用户坐标时才说"距您"，否则基准点只是市中心参照物
  const near = !!(j && j.located);
  const dist = h.distance_km == null ? '距离未知'
    : (h.distance_km.toFixed(1) + ' km' + (near ? '' : '（距市中心）'));
  const spec = h.specialty_label
    ? '<span class="chip emg">' + svgIcon('ok') + ' ' + esc(h.specialty_label) + '</span>' : '';
  const alias = h.alias_count
    ? '<span class="chip">另有 ' + h.alias_count + ' 个院区</span>' : '';
  const dchs = (h.matched_depts || []).map(x => '<span class="chip acc">' + esc(x) + '</span>').join('');
  const bars = (h.reason_detail || []).map(r =>
    '<div class="barrow"><span class="bk">' + esc(r.label) + '</span>' +
    '<span class="bt"><i style="width:' + Math.min(100, Math.round((r.score / (r.weight || 1)) * 100)) + '%"></i></span>' +
    '<span class="bv">' + esc(String(r.value)) + ' · +' + r.score + '</span></div>').join('');
  return '<div class="rec" data-detail="' + esc(h.id) + '">' +
    '<div class="rh"><span class="rn">' + esc(h.name) + '</span>' +
      (spec || (h.is_key_specialty ? '<span class="chip emg">重点专科</span>' : '')) +
      '<span class="rs">' + sc + '<span style="font-size:10px;color:' + DIM + ';font-weight:400"> 分</span></span></div>' +
    '<div class="rm">' + levelBadge(h.level) + '<span>' + esc(h.district) + '</span><span style="color:' + FAINT + '">·</span><span>' + dist + '</span>' + dchs + alias + '</div>' +
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
  A_OWN = mk('a_own'); A_CAT = mk('a_cat'); A_FEAT = mk('a_feature');
}

let _adminBusy = false;
function renderAdmin() {
  renderAdminResources();       // 资源热度：完全由本地真实数据算，离线也有内容
  renderAdminEtl();             // 数据治理：ETL 批次时效 + 功能使用结构（快照驱动，离线可看）
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
          { axisLabel: { color: CHART_AXIS, fontSize: 9.5, rotate: 30 } }),
        yAxis: Object.assign({ type: 'value' }, AXIS),
        series: [{
          type: 'line', smooth: true, data: daily.map(x => x.n), symbolSize: 6,
          lineStyle: { width: 2.5, color: ACC }, itemStyle: { color: ACC2 },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(' + ACC_RGB + ',.42)' }, { offset: 1, color: 'rgba(' + ACC_RGB + ',0)' }]) },
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

// 数据治理区块：ETL 批次时效（表格）+ 功能使用结构（横向条形图）。
// 均来自 Spark ADS 层结果（ads_etl_snapshot / ads_time_feature），随快照分发，离线可看。
function renderAdminEtl() {
  const ov = (DATA && DATA.overviews) || {};
  const el = $('etl_tbl');
  if (el) {
    const rows = ov.etl_snapshots || [];
    el.innerHTML = rows.length
      ? '<table class="etltbl"><thead><tr><th>批次日期</th><th>机构数</th><th>三级</th><th>二级</th>' +
        '<th>一级</th><th>未定级</th><th>覆盖区</th><th>坐标可用</th></tr></thead><tbody>' +
        rows.map(r => '<tr><td>' + esc(r.batch_date) + '</td><td>' + num(r.inst_count) + '</td><td>' +
          num(r.level_3) + '</td><td>' + num(r.level_2) + '</td><td>' + num(r.level_1) + '</td><td>' +
          num(r.level_none) + '</td><td>' + num(r.district_count) + '</td><td>' + num(r.coord_ok) +
          '</td></tr>').join('') + '</tbody></table>'
      : '<div class="empty">暂无批次数据</div>';
  }
  const feats = ov.time_feature || [];
  if (A_FEAT) {
    A_FEAT.setOption(feats.length
      ? barHOpt(feats.map(f => [trunc(f.feature, 12), f.event_count]), ACC2)
      : emptyOpt('暂无行为数据'), !feats.length);
  }
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
    ], [VIO, VIO2, CRIT, ACC2, PINK]));
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
  { step: 4, name: '数据入湖', tool: 'HDFS 3.3.6 · etl/upload_to_hdfs.py', desc: '治理后 CSV 与用户行为日志统一上传至 HDFS /hospital/ods/raw，作为后续分析数据的唯一来源。' },
  { step: 5, name: '数仓分层与维度分析', tool: 'Spark 3.5.3 · spark/jobs/ 按维度拆分', desc: 'ODS 原始层 → DWD 明细清洗层 → DWS 五维汇总层（空间 / 类型等级 / 科室 / 协作网络 / 时间）→ ADS 服务层；ODS/DWD/DWS 以 Parquet 存于 HDFS，仅 ADS 服务层结果落 MySQL。' },
  { step: 6, name: '地理编码与距离', tool: '高德地理编码 · Haversine 球面距离', desc: '补全机构经纬度（覆盖率 99.98%），支撑距离计算、距离排序、地图散点与周边配套查询。' },
  { step: 7, name: '索引优化', tool: 'etl/create_indexes.py', desc: '为筛选主表建立复合前缀索引（TEXT 列按 UTF-8 汉字 3 字节取前缀长度），实测典型多维筛选扫描行数由 9,777 降至 33。' },
  { step: 8, name: '服务与可视化', tool: 'Flask + ECharts + Docker Compose', desc: 'Flask 提供筛选 / 排序 / 详情 / 对比 / 导诊 / 埋点接口，ECharts 渲染地图与多维图表，并导出零依赖离线单文件。' },
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
