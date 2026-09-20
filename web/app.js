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

// 办别在线核实来源 → 详情抽屉标注（build_ownership_online.py 的 ownership_src 口径）
const OWN_SRC_LABEL = {
  baike_nature: '百科信息栏 · 在线核实',
  baike_econ: '百科经济类型 · 在线核实',
  baike_profit: '百科经营性质 · 在线核实',
  baike_regulator: '百科主管单位 · 在线核实',
  rule_military: '军队医院 · 官方口径',
  rule_soe: '国企事业办 · 官方口径',
  rule_affiliated: '公立高校附属 · 官方口径',
  rule_community: '政府办社区机构',
  rule_district: '区属政府办',
};


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
  // ⚠️ tiananmen 的经纬度必须与后端 web/nlq.py 的 DEFAULT_BASE **逐位相同**。
  // 这里曾是三位小数（116.397 / 39.909），与后端的六位小数不同，
  // 于是"距市中心"的距离在前端本地算与后端 SQL 算之间会有第三位小数的差异——
  // 单看不错，但双端一致性校验一比就露馅。改这里等于改所有距离值，谨慎。
  tiananmen:       { name: '天安门',   lng: 116.397428, lat: 39.90923 },
  capital_airport: { name: '首都机场', lng: 116.609, lat: 40.080 },
  daxing_airport:  { name: '大兴机场', lng: 116.411, lat: 39.510 },
  geo:             { name: '我的位置', lng: null,    lat: null },
};
const LEVEL_RANK = { '三级': 4, '二级': 3, '一级': 2, '未定级': 1 };
// 等级配色：全局唯一口径，禁止靠数组下标隐式配色（排序一变颜色就错位，把「一级」染成红色）
// 取值由 loadTokens() 按当前主题生成（见下方）
const W_LEVEL = 0.5, W_DIST = 0.3, W_DEPT = 0.2;
const DASHBOARD_VERSION = 'v6.2-smart-filter-20260919';
const GUAhAO_114 = 'https://www.114yygh.com/';

// ---------- 全局状态 ----------
let DATA = null;
let DIST_LEVEL = {};
let FILTERED = [];
let PAGE = 1, PAGE_SIZE = 20;
const PICKED = new Set();                 // 对比已选机构 id（最多 3）
const PICK_MAX = 3;
// 是否值得去探后端。
// 静态托管（GitHub Pages 等）与 file:// 都没有 /api，探测只会拿到 404 并在控制台
// 留下一串红字——分享出去的页面看着就像坏了。所以只在「本机地址 + Flask 端口」上探活：
// 本机跑静态服务（换端口预览产物）时同样不会误探。
const LOCAL_HOST = /^(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)$/.test(location.hostname)
  || /^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(location.hostname);
const ENV = {
  http: location.protocol === 'http:' || location.protocol === 'https:',
  // Flask 默认 5001（macOS 的 5000 被 AirPlay 占用）；port 为空表示走的是 80/443
  backend: LOCAL_HOST && (location.port === '5001' || location.port === ''),
  api: false,          // /api/health 探活结果
  amap: false,
};
// ⚠️ 必须显式挂到 window 上：`const ENV` 只创建**全局词法绑定**，不会成为 window 的属性。
// web/app.nlq.ui.js 里判的是 window.ENV（语音门禁、后端兜底），一旦为 undefined，
// 这些功能会在"后端明明正常"的情况下静默失效：语音永远提示"需要在本机使用"，
// 智能筛选永远走本地分支 —— 且不报错、不白屏，只有对比结果才看得出来。
window.ENV = ENV;
const SID = 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

// 图表实例
let MAP_CHART, CH1, CH2, CH3;
let ROW_EL_BY_ID = {}, SCATTER_IDX = {}, HOVER_ID = null;   // 地图 ↔ 列表 悬停互指
let CH_OWN, CH_FEAT, CH_NET, CH_LVOWN, CH_TOPSP, CH_DEPTOP, CH_DISTLV, CH_COORD;
let A_KW, A_DIST, A_TRIAGE, A_DAILY, A_DENSITY, A_LEVEL, A_SPEC, A_NET, A_OWN, A_CAT, A_FEAT;
let OV_OWN_CHART, QCOORD_CHART;   // 数据总览·办别构成 / 数据质量·坐标精度（七视图改版新增）

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
  if (!ENV.backend) return;
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
        '<span>' + esc(r.district || '—') + '</span>' + deptLabel(r) + '<span>' + dist + '</span></div>' +
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
const SORT_LABEL = { score: '条件匹配度', distance: '距离', level: '医院等级', depts: '科室数量', name: '机构名称' };
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
      '<button class="freset" type="button" data-freset="1" title="恢复默认：清空全部条件，距离基准回到市中心，排序回到条件匹配度">\u21ba 恢复默认</button>' +
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
  if (top) p.push('条件匹配度最高的是<b>' + esc(top.name) + '</b>（' + esc(top.district || '—') +
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
    sort: (SORT_LABEL[curSort()] || '条件匹配度') + (curDir() === 'asc' ? ' 升序' : ' 降序'),
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
    initDrawer();
    initCompare();
    initFavs();
    initPresets();
    initSortCtl();
    initKwAC();
    initOverSummary();
    initAIState();
    initBase();
    if (window.__NLQ_UI__) window.__NLQ_UI__.init();   // 智能筛选页（自然语言 + 条件双通道）
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
    renderOverviewKPI();   // 数据总览 4 张 KPI + 办别构成图（全量口径，不随筛选变化）
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
  // 没有后端就不发探测请求（静态托管下 404 会在控制台留红字），直接标成走本地规则
  if (!ENV.backend) { if (el) el.innerHTML = 'AI 兜底 <b>本地规则</b>'; return; }
  fetch('/api/health', { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .then(j => {
      ENV.api = !!(j && j.status === 'ok');
      if (el) el.innerHTML = ENV.api
        ? ('后端连接 <b>正常</b> · ' + num(j.institutions) + ' 家')
        : '后端 <b>未连接</b>';
      // 运营后台视图已在七视图改版中移除，不再启动拉取行为统计（renderAdmin 保留为死代码）
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
          '<span>' + esc(r.district) + '</span><span style="color:' + FAINT + '">·</span>' + deptLabel(r) + '</div>' +
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
    if ($('ch_ov_own')) OV_OWN_CHART = echarts.init($('ch_ov_own'));
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
   A_KW, A_DIST, A_TRIAGE, A_DAILY, A_DENSITY, A_LEVEL, A_SPEC, A_NET, A_OWN, A_CAT, DW_CHART,
   OV_OWN_CHART, QCOORD_CHART
  ].forEach(c => { if (c) { try { c.resize(); } catch (e) { } } });
  // 智能筛选页有自己的结果地图与维度统计图（app.nlq.ui.js），一并跟随窗口变化
  if (window.__NLQ_RESIZE__) { try { window.__NLQ_RESIZE__(); } catch (e) { } }
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
  try { drawOverviewOwn(); } catch (e) { }
  try {
    const vq = $('view-quality');
    if (vq && vq.classList.contains('active')) renderQuality(true);
  } catch (e) { }
  try { if (window.__NLQ_UI__) window.__NLQ_UI__.redraw(); } catch (e) { }
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
    if (v === 'integration') renderIntegration();
    if (v === 'quality') renderQuality();
    // 智能筛选页的结果地图要等容器可见后才能正确取到尺寸，所以放在切换时初始化
    if (v === 'filter' && window.__NLQ_UI__) { try { window.__NLQ_UI__.enter(); } catch (e) { console.error('[nlq]', e); } }
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
  $('dw_ft_note').textContent = ENV.api ? '' : '离线模式 · 周边配套与 AI 数据解读需本地服务';
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
      box('医院等级', levelBadge(r.level) + '<div class="mini" style="color:' + FAINT + ';font-size:11px;margin-top:4px">' + esc(r.level === '不适用医院分级' ? '该类型不参加等级评审' : r.level) + '</div>' +
        (r.level_src === 'baike_level' ? '<div style="color:' + FAINT + ';font-size:10px;margin-top:3px">百科信息栏 · 在线核实</div>' : '')) +
      box('办别性质', (r.ownership || '未标注') + (r.ownership_basis ? '<div style="color:' + FAINT + ';font-size:10px;margin-top:3px">依据 ' + esc(r.ownership_basis) + '</div>' : OWN_SRC_LABEL[r.ownership_src] || '')) +
      box('科室数量', num(r.dept_count) + ' 个' +
        (r.dept_count_src === 'baike_claim'
          ? '<div style="color:' + FAINT + ';font-size:10px;margin-top:3px">官网口径 · 在线核实</div>'
          : r.dept_count_src === 'baike_table'
            ? '<div style="color:' + FAINT + ';font-size:10px;margin-top:3px">百科科室表 · 在线核实</div>'
            : '')) +
      box('重点专科', num(r.key_specialty_count) + ' 项') +
      box('距' + (BASE_NOW ? base.name : '市中心'), dist) +
    '</div>' +
    '<div class="blk"><h4><span class="bar"></span>协作网络</h4><div class="deptchips">' +
      (netDetail(r) ? netDetail(r).split('、').map(x => '<span class="chip acc">' + esc(x) + '</span>').join('')
                    : '<span style="color:' + DIM + ';font-size:12px">未纳入市级协作网络</span>') +
    '</div></div>' +
    '<div class="blk"><h4><span class="bar"></span>同区同类机构 · 距离对标 <span class="r">红色为本机构</span></h4>' +
      '<div class="dwscope" id="dw_scope"></div>' +
      '<div class="dwchart" id="dw_chart" style="height:292px"></div>' +
      '<div class="dwfoot" id="dw_foot"></div></div>';
  paintDwChart(r);
  // 离线单文件（file://）没有后端，联系方式必须用快照里的 addr/phone 本地渲染，
  // 否则面板会永远停在「正在获取联系方式…」——这是必须避免的空转假象。
  $('pane-contact').innerHTML = ENV.api ? '<div class="empty">正在获取联系方式…</div>' : contactLocalHTML(r);
  $('pane-spec').innerHTML = specialtyHTML(r) + deptsLocalHTML(r);
  $('pane-near').innerHTML = aroundPlaceholder(r);
}

// 离线快照的「科室明细」。
// 快照里带的是科室**名录**（dwd_dept_relation_clean 按机构聚合后的结果），
// 不含「是否重点专科 / 归属来源」两列——那两列要连本地服务才有。
// 这一段的意义：用户在智能筛选里按科室筛出机构后，点进来能看见同一批科室名，
// 而不是"筛得到、详情里却看不到"。
// 科室数的展示口径。
// dept_count 有三种来源，列表里直接甩一个数字会误导：
//   ① 在线核实（dept_count_src）：机构官网 / 百科词条自述，最接近真实；
//   ② 登记诊疗科目（specialty / key_depts）：来自医疗机构登记的诊疗科目；
//   ③ 规则推导（rule_dept_count）：源数据没收录时，按「机构等级 × 类型」套的一份
//      通用清单（如三级医院 19 个），**不是**这家机构真实的科室构成。
// 另有一批头部医院在源数据里只登记到 1~5 个科室（宣武医院只登记了「神经内科」一条
// 国家级重点专科），此时把收录条数当科室数展示反而误导，统一回落为「科室资料待补全」。
function deptLabel(r) {
  const n = Number(r.dept_count || 0);
  if (!n) return '';
  const src = String(r.dept_count_src || '');
  const rule = Number(r.rule_dept_count || 0);
  const lv = String(r.level || '');
  if (src) {
    return '<span title="在线核实：来自机构官网 / 百科词条的科室设置，共 ' + n + ' 个">' +
      n + ' 个科室</span>';
  }
  if (rule >= n) {
    return '<span title="源数据未收录该机构的科室设置，当前数量按「' + (lv || '同类型') +
      '」通用科室清单推导，仅供筛选参考，不代表真实科室构成">' + n + ' 个科室</span>';
  }
  if ((lv === '三级' || lv === '二级') && n <= 5) {
    return '<span title="源数据仅收录到 ' + n + ' 个科室，与该院实际规模不符，故不展示具体数字">' +
      '科室资料待补全</span>';
  }
  return '<span title="来自医疗机构登记的诊疗科目，共 ' + n + ' 个">' + n + ' 个科室</span>';
}

function deptsLocalHTML(r) {
  const ds = String(r.depts || '').split(';').filter(Boolean);
  if (!ds.length) return '';
  return '<div class="blk"><h4><span class="bar"></span>科室明细 <span class="r">共 ' + ds.length +
    ' 个科室</span></h4><div class="deptchips">' +
    ds.map(x => '<span class="chip">' + esc(x) + '</span>').join('') + '</div>' +
    '<div style="color:' + FAINT + ';font-size:10.5px;margin-top:9px">科室名录来自 ' +
    'dwd_dept_relation_clean（Spark 数仓 DWD 层，随离线快照内嵌）；' +
    '「是否重点专科 / 归属来源」两列在本地服务在线时展示。</div></div>';
}

// 离线模式的「联系方式与导航」面板：只用快照数据，不依赖任何接口
function contactLocalHTML(r) {
  const items = [];
  items.push(linkCard(svgIcon('gov'), '北京市预约挂号统一平台（114）', '官方信息入口 · 外链跳转，本系统不抓取号源与排班', GUAhAO_114, false));
  if (r.phone) items.push(linkCard(svgIcon('phone'), '机构电话 ' + r.phone, '公开数据收录的联系电话（以机构公布为准）', 'tel:' + r.phone, false));
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
    '<div class="notice" style="margin-top:14px">当前为<b>离线单文件</b>模式：地址、电话与导航均可正常使用；' +
    '周边配套（最近地铁站 / 停车场 / 公交站）与 AI 数据解读需本地 Flask 服务支持。<br>' +
    '本系统只呈现<b>机构资源数据</b>，不涉及号源、出诊与候诊信息。</div>';
}

// 同区同类机构 · 距离对标（同区 + 同类型 + 同等级的可比机构，按与基准点的距离排）
// ---------------------------------------------------------------------------
// 这里**刻意不再用「科室数」做横向对比**。dept_count 由三种不可比的口径拼成：
//   ① 源数据只登记了 1~2 个科室（7,500+ 家基层机构），反映的是收录深度；
//   ② 102 家机构的「19 个科室」在源数据里是 source=rule / raw_name=推导，
//      即规则补出的一份通用名单，不是该机构真实的科室设置；
//   ③ 45 家为百科自述口径（dept_count_src=baike_claim），机构自己声明的数字。
// 三者同图比高矮，比出来的是「数据怎么来的」，不是机构规模 —— 会误导读者，
// 也答不了「我该不该去这家」。换成**距离**：由坐标实时算出、口径统一，
// 且正是使用者选机构时最在意的量；再给出本机构在同类中的位次。
let DW_CHART = null;

function dwMedian(arr) {
  if (!arr.length) return 0;
  const a = arr.slice().sort((x, y) => x - y), m = a.length >> 1;
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}

// 可比机构池：同区 + 同类型 + 同等级；不足 6 家时逐级放宽，并把实际口径写进界面
function dwPeerSet(r) {
  const all = DATA.institutions.filter(x => x.district === r.district && x.lng != null && x.lat != null);
  const cat = all.filter(x => x.category === r.category);
  const lvl = cat.filter(x => String(x.level) === String(r.level));
  if (lvl.length >= 6) return { rows: lvl, scope: '同区 · 同类型 · 同等级' };
  if (cat.length >= 6) return { rows: cat, scope: '同区 · 同类型' };
  return { rows: all, scope: '同区全部机构' };
}

// 机构名标签：超过 n 字自动折成两行（"首都医科大学附属北京世纪坛医院" 这类长名，
// 一刀截断会把几家不同的医院都变成同一个前缀）；折行后仍撞车的加序号。
function dwLabels(list, n) {
  const wrap = s => {
    s = String(s || '');
    if (s.length <= n) return s;
    if (s.length <= n * 2) return s.slice(0, n) + '\n' + s.slice(n);
    return s.slice(0, n) + '\n' + s.slice(n, n * 2 - 1) + '…';
  };
  const labels = list.map(x => wrap(x.name)), seen = {};
  labels.forEach((s, i) => {
    seen[s] = (seen[s] || 0) + 1;
    if (seen[s] > 1) labels[i] = s + '(' + seen[s] + ')';
  });
  return labels;
}

function paintDwChart(r) {
  const el = $('dw_chart'), sc = $('dw_scope'), ft = $('dw_foot');
  if (DW_CHART) { try { DW_CHART.dispose(); } catch (e) { } DW_CHART = null; }
  if (!el || typeof echarts === 'undefined') return;
  const base = curBase();
  const anchor = BASE_NOW ? '距' + BASE_NOW.name : '距市中心（天安门）';
  if (r.lng == null || r.lat == null) {
    if (sc) sc.textContent = '';
    if (ft) ft.textContent = '';
    el.innerHTML = '<div class="empty">该机构缺经纬度，无法与同类机构做距离对标</div>';
    return;
  }
  const peers = dwPeerSet(r);
  const rows = peers.rows.map(x => ({
    id: x.id, name: x.name, level: x.level, category: x.category,
    km: Math.round(haversine(base.lng, base.lat, x.lng, x.lat) * 10) / 10,
  })).sort((a, b) => a.km - b.km);
  const idx = rows.findIndex(x => String(x.id) === String(r.id));
  if (sc) {
    sc.innerHTML = '对标范围：' + esc(r.district) + ' · ' + esc(peers.scope) + ' · 共 <b>' + rows.length +
      '</b> 家 · 按' + esc(anchor) + '由近到远';
  }
  if (rows.length < 3 || idx < 0) {
    if (ft) ft.textContent = '同类机构样本不足 3 家，暂不做距离对标。';
    el.innerHTML = '<div class="empty">可比机构太少，不做距离对标</div>';
    return;
  }
  const mine = rows[idx], kms = rows.map(x => x.km);
  const mid = dwMedian(kms), far = kms[kms.length - 1];
  // 图上画「最近的 8 家 + 本机构」；本机构若不在前 8 名则补一张柱子，保证它一定可见
  const shown = rows.slice(0, 8);
  if (idx >= 8) shown.push(mine);
  const labels = dwLabels(shown, 11);
  if (ft) {
    ft.innerHTML = '本机构 <b>' + mine.km.toFixed(1) + ' km</b> · 在 ' + rows.length + ' 家同类机构中排<b>第 ' +
      (idx + 1) + ' 近</b>' +
      '<span class="sub">' + esc(anchor) + '：最近 ' + kms[0].toFixed(1) + ' km / 中位 ' + mid.toFixed(1) +
      ' km / 最远 ' + far.toFixed(1) + ' km　·　图中为最近 ' + (shown.length - 1) + ' 家 + 本机构' +
      '　·　只比地理位置，不含医疗水平评价；同类机构不足 6 家时逐级放宽对标范围</span>';
  }
  if (!DW_CHART) DW_CHART = echarts.init(el);
  DW_CHART.setOption({
    tooltip: Object.assign({
      trigger: 'axis', axisPointer: { type: 'shadow' },
      // 注意：formatter 传函数时 ECharts **不会**替换 {b}/{c} 模板，必须自己拼字符串
      formatter: function (ps) {
        const p = ps[0], d = shown[p.dataIndex];
        if (!d) return '';
        return d.name + '<br/>' + anchor + ' ' + d.km.toFixed(1) + ' km<br/>' + d.level + ' · ' + d.category;
      },
    }, TIP),
    // bottom 留出横轴刻度位（刻度画在网格下方，bottom 太小会被画布裁掉）
    grid: { left: 122, right: 56, top: 8, bottom: 20 },
    xAxis: Object.assign({ type: 'value', min: 0 }, AXIS, {
      axisLabel: Object.assign({}, AXIS.axisLabel, { formatter: '{value} km' }),
    }),
    // inverse: 让最近的机构落在最上面，读起来与「由近到远」一致
    // lineHeight: 机构名可能折成两行，不给显式行高两行会叠在一起
    yAxis: Object.assign({ type: 'category', inverse: true, data: labels }, AXIS, {
      axisLabel: Object.assign({}, AXIS.axisLabel, { lineHeight: 12 }),
    }),
    series: [{
      type: 'bar', barMaxWidth: 13,
      data: shown.map(x => ({
        value: x.km,
        itemStyle: { color: String(x.id) === String(r.id) ? CRIT : ACC, borderRadius: [0, 4, 4, 0] },
      })),
      label: {
        show: true, position: 'right', color: INK, fontSize: 10,
        formatter: function (p) { return Number(p.value).toFixed(1); },
      },
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

  // 重点专科清单就是"数据"，不往"找专家 / 挂号"的方向引。
  // 本系统不含医生、号源、出诊信息，硬凑入口只会误导使用者。
  h += '<div class="blk"><h4><span class="bar"></span>重点专科清单 · 口径说明 <span class="r">来源：官方公示名单</span></h4>' +
    '<div style="color:' + DIM + ';font-size:11.5px;line-height:1.75;margin-bottom:10px">' +
    '重点专科名称来自国家 / 北京市卫健委公示名单及医院官网公开信息，用于刻画该机构的<b>学科资源分布</b>。' +
    '本系统<b>不收录医生姓名、职称、出诊时间与号源信息</b>——公开数据中没有可靠来源，且这类信息属于诊疗范畴，' +
    '不属于本系统的职责范围。</div>' +
    '<div class="taglist">' +
      (nat.concat(mun).length ? nat.concat(mun).slice(0, 6).map(d =>
        '<div class="tagrow"><span class="tk" style="background:rgba(var(--crit-rgb),.16);color:var(--t-crit-fg);border:1px solid rgba(var(--crit-rgb),.34)">' + esc(d.trim()) + '</span>' +
        '<span class="tv">' + (nat.indexOf(d) >= 0 ? '国家级' : '北京市级') + '重点专科 · 已计入该机构的重点专科数量统计</span></div>').join('')
        : '<div style="color:' + DIM + ';font-size:12px">该机构未收录重点专科记录</div>') +
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

// 说明：早期版本这里有一组"候诊状态 / 号源"的模拟数据。本系统的定位是
// **机构资源数据的查询与筛选**，不掌握也不模拟任何挂号、候诊、号源信息，
// 模拟数据只会让使用者把它当成实时信息，因此整段删除（后端 _mock_status 同步移除）。
function _removedMockStatus(r) {
  return null;
}

// 接口返回后补全：联系方式 / 官方信息入口 / 周边配套
function paintDrawerFull(d) {
  const c = d.contact || {}, L = d.links || {};

  // 联系方式与导航（系统只提供公开数据里的联系方式与外链导航，不涉及号源）
  const items = [];
  items.push(linkCard(svgIcon('gov'), '北京市预约挂号统一平台（114）', '官方信息入口 · 外链跳转，本系统不抓取号源与排班', L.guahao_114, false));
  if (L.hospital_tel_link) items.push(linkCard(svgIcon('phone'), '机构电话 ' + L.hospital_phone, '公开数据收录的联系电话（以机构公布为准）', L.hospital_tel_link, false));
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
      '<b>关于外链：</b>114 统一平台为 JS 单页应用，不存在可构造的「按医院直达」链接，因此本系统只提供官方入口 + 机构名复制，' +
      '不伪造深链（伪造会得到死链）。点击「复制名称」后到该平台粘贴检索即可。' +
      '本系统<b>不抓取、不缓存、不展示</b>任何号源与排班数据。' +
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
  wrap.innerHTML = '<div class="who">' + svgIcon('brain') + ' AI 数据解读 <span class="chip eng">仅基于本页真实字段生成 · 禁止编造</span></div>' +
    '<div class="typing"><i></i><i></i><i></i> 正在生成…</div>';
  btn.disabled = true;
  fetch('/api/ai/advice?id=' + encodeURIComponent(DW_CUR.id))
    .then(r => r.ok ? r.json() : null)
    .then(j => {
      if (j && j.ok) {
        wrap.innerHTML = '<div class="who">' + svgIcon('brain') + ' AI 数据解读 <span class="chip eng">' + esc(j.model || 'Agnes') + ' · 仅基于真实字段</span></div>' +
          '<div>' + esc(j.advice) + '</div>' +
          '<div style="color:' + FAINT + ';font-size:10.5px;margin-top:9px">约束：只描述本页真实字段构成的机构数据画像；不允许输出就诊建议、科室推荐、医生姓名、号源或任何未经核实的数字。</div>';
      } else {
        wrap.innerHTML = '<div class="who">' + svgIcon('brain') + ' AI 数据解读</div><div style="color:' + WARN + '">' +
          esc((j && (j.hint || j.detail)) || '生成失败，请稍后重试') + '</div>';
      }
    })
    .catch(() => { wrap.innerHTML = '<div class="who">' + svgIcon('brain') + ' AI 数据解读</div><div style="color:' + WARN + '">网络异常，生成失败</div>'; })
    .then(() => { btn.disabled = false; });
}

// ============================================================================
//  12. 对比
// ============================================================================
function initCompare() {
  $('cmp_clear').addEventListener('click', clearPicks);
  $('cmp_go').addEventListener('click', openCompare);
  $('cmp_close').addEventListener('click', closeCompare);
  $('cmp_add').addEventListener('click', () => { closeCompare(); switchView('institutions'); toast('请在机构列表里勾选更多机构（最多 ' + PICK_MAX + ' 家）'); });
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
    (navLink(r) ? '<a class="btn ghost sm" href="' + navLink(r) + '" target="_blank" rel="noopener">地图导航</a>' : '') +
    (r.addr || r.distance_km != null ? '<button class="btn ghost sm" data-cmp-detail="' + esc(r.id) + '">查看详情</button>' : '') +
    '</div></td>').join('') + '</tr>';

  $('cmp_table').querySelector('tbody').innerHTML = body + linkRow;
  Array.prototype.forEach.call($('cmp_table').querySelectorAll('[data-cmp-detail]'), b =>
    b.addEventListener('click', () => { closeCompare(); openDrawer(b.getAttribute('data-cmp-detail')); }));
}

function closeCompare() { $('cmpwrap').classList.remove('show'); }

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
      : '尚无行为数据：使用一段时间后（搜索 / 筛选 / 自然语言查询 / 查看详情）这里会自动累积');
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
//  14.6 七视图改版：数据总览 KPI / 智能筛选预览 / 数据整合 / 数据质量
//        本屏所有汇总数字均来自真实治理结果（data/processed/data_quality_report.md
//        由 etl 治理脚本对 70 个源文件真实计算），不使用演示数据。
// ============================================================================

// 多源数据整合真实口径（医保局 4,876 / 社区 1,972 为用户确认的来源口径，
// 其余 6,955 条为区级卫健委名录与重点专科 / 协作网络公示等专题文件；三者合计 13,803）
// 运行时优先使用快照 DATA.overviews.data_quality（build_spa.sh 注入），DQ 仅为离线兜底常量。
const DQ = {
  sourceFiles: 70,          // 去重后源文件数（含 3 个统计表 / 排除文件，读取失败 0）
  rawRecords: 13803,        // 合并前累计原始记录
  finalInst: 9791,          // 去重合并后主表机构数（治理报告口径）
  dupNames: 3139,           // 涉及多来源重复的机构名
  dupMaxSources: 9,         // 单个机构最多被 9 个来源重复收录
  crossVerified: 657,       // src_count>=3 的多源交叉验证机构
  keyDeptInst: 20,          // 临床重点专科覆盖机构数
  sources: [
    { name: '市 / 区医保局定点医疗机构名单', count: 4876, desc: '市医保局及东城、平谷、延庆、顺义等区定点医药机构文件' },
    { name: '社区卫生服务机构名录', count: 1972, desc: '社区卫生服务中心与社区卫生服务站名单' },
    { name: '区级卫健委及专题公开数据', count: 6955, desc: '密云 / 通州 / 房山 / 朝阳 / 怀柔等区医疗机构名录、重点专科与协作网络公示、业务统计表' },
  ],
  // 完整率以主表 9,791 家为分母；快照 data_quality.fields 同构覆盖
  fields: [
    { field: 'district', label: '行政区', nonnull: 9749, pct: 99.6 },
    { field: 'addr', label: '地址', nonnull: 8762, pct: 89.5 },
    { field: 'profit', label: '经济类型（办别）', nonnull: 8328, pct: 85.1 },
    { field: 'key_depts', label: '重点专科 / 擅长科室', nonnull: 831, pct: 8.5 },
    { field: 'level', label: '医院等级', nonnull: 1172, pct: 12.0 },
    { field: 'phone', label: '联系电话', nonnull: 570, pct: 5.8 },
    { field: 'beds', label: '床位数', nonnull: 35, pct: 0.4 },
    { field: 'traffic', label: '交通导引', nonnull: 17, pct: 0.2 },
  ],
};
// 快照注入的蛇形 / 不同结构字段归一到 DQ 同构形式
function dqv() {
  const snap = (DATA && DATA.overviews && DATA.overviews.data_quality) || null;
  if (!snap) return DQ;
  const fields = (snap.fields || []).map(f =>
    Array.isArray(f) ? { field: f[0], label: f[1], nonnull: f[2], pct: f[3] } : f);
  return {
    sourceFiles: snap.source_files != null ? snap.source_files : DQ.sourceFiles,
    rawRecords: snap.raw_records != null ? snap.raw_records : DQ.rawRecords,
    finalInst: snap.final_inst != null ? snap.final_inst : DQ.finalInst,
    dupNames: snap.dup_names != null ? snap.dup_names : DQ.dupNames,
    dupMaxSources: snap.dup_max_sources != null ? snap.dup_max_sources : DQ.dupMaxSources,
    crossVerified: snap.cross_verified != null ? snap.cross_verified : DQ.crossVerified,
    keyDeptInst: snap.key_dept_inst != null ? snap.key_dept_inst : DQ.keyDeptInst,
    sources: snap.sources && snap.sources.length ? snap.sources : DQ.sources,
    fields: fields.length ? fields : DQ.fields,
  };
}
function dqFieldColor(p) {
  return p >= 85 ? ACC2 : p >= 50 ? ACC : p >= 15 ? WARN : CRIT;
}

// ---------- 数据总览：4 张 KPI（全量口径，不随筛选变化）+ 办别构成环形图 ----------
function renderOverviewKPI() {
  if (!DATA) return;
  setText('v_total', num(DATA.total));
  const inst = DATA.institutions || [];
  // 医院：category_norm 已把综合 / 专科 / 中医医院归一为「医院」（真实快照口径 732 家）；
  // 社区机构：归一类别里没有单独口径，按机构名称真实匹配社区卫生服务中心 / 站
  // （部分原始行是「中心+下属站」合并名，按主表一行一家计）
  const hospN = inst.filter(r => r.category === '医院').length;
  const commN = inst.filter(r => /社区卫生服务(站|中心)/.test(r.name || '')).length;
  setText('v_hospitals', num(hospN));
  setText('v_community', num(commN));
  setText('v_sources', num(dqv().sourceFiles));
  drawOverviewOwn();
}
function drawOverviewOwn() {
  if (!OV_OWN_CHART || !DATA) return;
  const own = {};
  DATA.institutions.forEach(r => { const k = r.ownership || '未标注'; own[k] = (own[k] || 0) + 1; });
  OV_OWN_CHART.setOption(pieOpt([
    ['公立', own['公立'] || 0, ACC2],
    ['民营', own['民营'] || 0, WARN],
    ['未标注', own['未标注'] || 0, DIM],
  ]));
}

// ---------- 数据整合中心：数据源 + Spark 处理流程 + 处理结果 + ETL 批次时效 ----------
let _integRendered = false;
function renderIntegration() {
  if (_integRendered) return;
  _integRendered = true;
  const Q = dqv();

  const srcEl = $('integration_sources');
  if (srcEl) {
    srcEl.innerHTML = Q.sources.map(s =>
      '<div class="integ-item"><div class="ii-top"><span class="ii-name">' + esc(s.name) + '</span>' +
      '<span class="ii-count">' + num(s.count) + ' <em>条</em></span></div>' +
      '<div class="ii-desc">' + esc(s.desc) + '</div></div>').join('') +
      '<div class="integ-item total"><div class="ii-top"><span class="ii-name">合计原始记录</span>' +
      '<span class="ii-count">' + num(Q.rawRecords) + ' <em>条</em></span></div>' +
      '<div class="ii-desc">共 ' + Q.sourceFiles + ' 个去重源文件（含 3 个无机构名称列的统计表，已排除出主表）</div></div>';
  }

  // 复用关于页同一套 PIPELINE 真实清洗步骤（8 步）
  const pipeEl = $('integration_pipeline');
  if (pipeEl) {
    pipeEl.innerHTML = PIPELINE.map(p =>
      '<div class="tstep"><div class="num">' + p.step + '</div><div class="tc">' +
      '<div class="tn">' + esc(p.name) + '</div><div class="tt">' + esc(p.tool) + '</div>' +
      '<div class="td">' + esc(p.desc) + '</div></div></div>').join('');
  }

  const resEl = $('integration_results');
  if (resEl) {
    resEl.innerHTML =
      box('源文件数', num(Q.sourceFiles) + ' 个') +
      box('原始记录', num(Q.rawRecords) + ' 条') +
      box('重复机构名', num(Q.dupNames) + ' 个') +
      box('多源交叉验证', '≥3 源 · ' + num(Q.crossVerified) + ' 家') +
      box('去重后主表', num(Q.finalInst) + ' 家') +
      box('重点专科覆盖', num(Q.keyDeptInst) + ' 家');
  }

  // ETL 批次时效：来自 Spark ADS 层 ads_etl_snapshot 快照，离线同样可看
  const etlEl = $('integration_etl_tbl');
  if (etlEl) {
    const rows = ((DATA.overviews || {}).etl_snapshots || []);
    etlEl.innerHTML = rows.length
      ? '<table class="etltbl"><thead><tr><th>批次日期</th><th>机构数</th><th>三级</th><th>二级</th>' +
        '<th>一级</th><th>未定级</th><th>覆盖区</th><th>坐标可用</th></tr></thead><tbody>' +
        rows.map(r => '<tr><td>' + esc(r.batch_date) + '</td><td>' + num(r.inst_count) + '</td><td>' +
          num(r.level_3) + '</td><td>' + num(r.level_2) + '</td><td>' + num(r.level_1) + '</td><td>' +
          num(r.level_none) + '</td><td>' + num(r.district_count) + '</td><td>' + num(r.coord_ok) +
          '</td></tr>').join('') + '</tbody></table>'
      : '<div class="empty">暂无批次数据</div>';
  }
}

// ---------- 数据质量：字段完整率 + 坐标精度 + 去重统计 + 类别构成 ----------
let _qualRendered = false;
function renderQuality(force) {
  if (_qualRendered && !force) return;
  _qualRendered = true;
  const Q = dqv();

  // 1) 关键字段完整率（治理脚本真实计算；分母为主表 9,791 家）
  const ft = $('qual_field_table');
  if (ft) {
    ft.innerHTML =
      '<table class="qtable"><thead><tr><th>字段</th><th style="text-align:right">非空数</th>' +
      '<th style="text-align:right">完整率</th></tr></thead><tbody>' +
      Q.fields.map(f =>
        '<tr><td><span class="mono">' + esc(f.field) + '</span> ' + esc(f.label) + '</td>' +
        '<td style="text-align:right">' + num(f.nonnull) + '</td>' +
        '<td style="text-align:right"><div class="qbar"><i style="width:' + Math.max(f.pct, 1.5) +
          '%;background:' + dqFieldColor(f.pct) + '"></i><b>' + f.pct.toFixed(1) + '%</b></div></td></tr>').join('') +
      '</tbody></table>' +
      '<div class="notice" style="margin-top:10px">电话 / 床位 / 交通导引在公开数据中覆盖率极低，系统遵循「宁缺勿伪」原则：' +
      '床位数已从展示与评分中移除，不以估算值填充；等级字段仅医院参加评审，基层机构按「不适用分级」展示。</div>';
  }

  // 2) 坐标精度分布（全量真实数据，与医疗资源分析页同口径）
  const qc = $('ch_qcoord');
  if (qc) {
    if (!QCOORD_CHART) QCOORD_CHART = echarts.init(qc);
    const cp = { high: 0, rough: 0, missing: 0 };
    (DATA.institutions || []).forEach(r => { cp[r.coord_precision || 'missing']++; });
    QCOORD_CHART.setOption(pieOpt([
      ['高精度', cp.high, ACC2], ['粗略', cp.rough, WARN], ['缺失', cp.missing, CRIT],
    ]));
    setTimeout(() => { if (QCOORD_CHART) QCOORD_CHART.resize(); }, 0);
  }

  // 3) 去重与多源交叉验证
  const ds = $('qual_dup_stats');
  if (ds) {
    const reduced = Q.rawRecords - Q.finalInst;
    ds.innerHTML =
      '<div class="infogrid">' +
        box('多源重复机构名', num(Q.dupNames) + ' 个') +
        box('单机构最多来源数', num(Q.dupMaxSources) + ' 个') +
        box('多源交叉验证机构', num(Q.crossVerified) + ' 家') +
        box('合并压缩记录', num(reduced) + ' 条') +
      '</div>' +
      '<div class="notice" style="margin-top:11px">同一机构被多个来源重复收录时，按<b>名称标准化 → 实体匹配 → 属性合并</b>去重；' +
      '被 3 个及以上来源同时收录的 ' + num(Q.crossVerified) + ' 家机构经多源交叉验证，可信度最高。' +
      '原始 ' + num(Q.rawRecords) + ' 条记录去重后形成 ' + num(Q.finalInst) + ' 家主表；' +
      'ADS 在线服务表当前为 ' + num(DATA.total) + ' 家，差额 ' + (Q.finalInst - DATA.total) +
      ' 家为治理后未入表的少量样本，两口径均可在数据整合页核验。</div>';
  }

  // 4) 机构类别构成（按当前 ADS 服务表真实快照，随数据更新自动重算）
  const ct = $('qual_cat_table');
  if (ct) {
    const cats = (DATA.meta && DATA.meta.categories || []).slice().sort((a, b) => b.inst_count - a.inst_count);
    const denom = DATA.total || cats.reduce((s, c) => s + c.inst_count, 0);
    ct.innerHTML = cats.length
      ? '<table class="qtable"><thead><tr><th>类别</th><th style="text-align:right">数量</th>' +
        '<th style="text-align:right">占比</th></tr></thead><tbody>' +
        cats.map(c => {
          const p = denom ? (c.inst_count / denom * 100) : 0;
          return '<tr><td>' + esc(c.category) + '</td><td style="text-align:right">' + num(c.inst_count) +
            '</td><td style="text-align:right"><div class="qbar"><i style="width:' + Math.max(p, 1.5) +
            '%;background:' + VIO + '"></i><b>' + p.toFixed(1) + '%</b></div></td></tr>';
        }).join('') + '</tbody></table>' +
        '<div class="notice" style="margin-top:10px">口径：ADS 服务表 ' + num(DATA.total) + ' 家（快照日期 ' +
        esc(DATA.snapshot_time || '—') + '）。</div>'
      : '<div class="empty">暂无类别数据</div>';
  }
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
      (c.specialty_rows ? box('重点专科挂牌记录', num(c.specialty_rows) + ' 条') : '') +
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
      dept_relations: c.dept_relations, specialty_rows: c.specialty_rows, tables: c.tables,
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
        dim_disease_dept: '症状-科室映射字典（历史遗留，未参与筛选链路）', dim_ai_cache: '大模型结果缓存',
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
  { step: 8, name: '服务与可视化', tool: 'Flask + ECharts + Docker Compose', desc: 'Flask 提供自然语言筛选 / 条件筛选 / 维度统计 / 详情 / 对比 / 概览接口，ECharts 渲染地图与多维分析图表，并导出零依赖离线单文件。' },
];
const SOURCES = [
  { icon: svgIcon('gov'), name: '北京市卫生健康委员会', url: 'https://wjw.beijing.gov.cn/', desc: '医疗机构名录、重点专科公示名单、协作网络名单' },
  { icon: svgIcon('folder'), name: '北京市政务数据资源网', url: 'https://data.beijing.gov.cn/', desc: '医疗机构基础信息开放数据' },
  { icon: svgIcon('map'), name: '高德开放平台', url: 'https://lbs.amap.com/', desc: '地理编码补全与周边配套（地铁站 / 停车场 / 公交站）POI 查询' },
];
const UPDATES = [
  { date: '2026-09-20', desc: '「就医决策 / 智能导诊」下线，主线重构为「自然语言智能筛选」：中文条件解析 → 真实数据查询 → 维度统计；AI 定位收敛为机构数据筛选助手。' },
  { date: '2026-09-11', desc: '新增机构详情抽屉（联系方式 / 地图导航 / 重点专科 / 周边配套）、机构横向对比、运营后台与关于页；前端视觉体系重构。' },
  { date: '2026-09-11', desc: '智能导诊接入本地症状-科室知识库（262 条），保留大模型零命中兜底（该模块已于 2026-09-20 随主线重构下线）。' },
  { date: '2026-09-08', desc: '快照数据更新至 9,789 家机构；修正机构更名（空军特色医学中心、北京通用航天医院）与别名映射。' },
  { date: '2026-09-05', desc: '新增医疗协作网络维度（儿科医联体 / 卒中中心 / 危重新生儿 / 危重孕产妇）。' },
  { date: '2026-09-04', desc: '完成数据治理列贯通（办别归属、类别细分、擅长科室三级分级），筛选维度扩展至 7 维。' },
];
const WAREHOUSE = [
  ['ODS 原始层', 'ods_institution / ods_dept_dict / ods_dept_relation / ods_specialty / ods_geocode', '接入原始多源数据'],
  ['DWD 明细层', 'dwd_institution_clean / dwd_dept_relation_clean / dwd_specialty_clean', '清洗、去重、标准化'],
  ['DWS 汇总层', 'dws_inst_by_district / dws_inst_by_level / dws_inst_by_category / dws_dept_coverage', '按区域 / 等级 / 类型 / 科室汇总'],
  ['ADS 应用层', 'ads_inst_search / ads_district_overview / ads_level_overview / ads_specialty_hospital', '直接服务前端查询'],
  ['维度 / 支撑表', 'dim_disease_dept / dim_ai_cache / dim_poi_cache / fact_user_event', '症状映射字典（遗留）、模型缓存、POI 缓存、行为日志'],
];

// ============================================================================
//  启动
// ============================================================================
console.log('[dashboard] 版本', DASHBOARD_VERSION);
loadData();
