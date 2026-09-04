// ========== 北京市医院资源系统 - 可交互 SPA ==========
// 数据来源：snapshot_data.json（2.6MB，含 9791 家机构 + 4 张概览 + 15 专科组 + 北京 geoJSON）

const BG='#0b1530', PANEL='#14213d', EDGE='#1f3a68', INK='#e8eefc', SUB='#8aa1c8';
const ACC='#3aa0ff', ACC2='#5fd3c0', WARN='#f7b955', CRIT='#ff6b6b', VIO='#a78bfa';

const BASE_POINTS = {
  tiananmen:       {name:'天安门',       lng:116.397, lat:39.909},
  capital_airport: {name:'首都机场',     lng:116.609, lat:40.080},
  daxing_airport:  {name:'大兴机场',     lng:116.411, lat:39.510},
  geo:             {name:'我的位置',     lng:null,    lat:null},
};
const LEVEL_RANK = {'三级':4, '二级':3, '一级':2, '未定级':1};

// 评分权重
const W_LEVEL = 0.4, W_DIST = 0.3, W_DEPT = 0.2, W_BED = 0.1;

const DASHBOARD_VERSION = 'v3.3-20260904-1930-spec-polish';
console.log('[dashboard] 加载版本:', DASHBOARD_VERSION);
console.log('[dashboard] BASE_POINTS 初始值:', JSON.stringify(BASE_POINTS, null, 2));
let FILTERED = [];        // 筛选后
let PAGE = 1;
let PAGE_SIZE = 20;
let MAP_CHART, CH1, CH2, CH3, MODAL_CHART;

// ========== 1. 加载数据 ==========
// 内嵌模式：从 window.__SNAPSHOT__ 读取（已注入到本 HTML 之前）
// HTTP-only 模式：从 fetch snapshot_data.json 读取
function loadData() {
  try {
    if (window.__SNAPSHOT__) {
      DATA = window.__SNAPSHOT__;
      console.log('✅ 数据加载完成（内嵌）:', DATA.total, '家');
      init();
      return;
    }
    // 兜底走 fetch
    fetch('snapshot_data.json').then(r => {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(d => {
      DATA = d;
      console.log('✅ 数据加载完成（fetch）:', DATA.total, '家');
      init();
    }).catch(e => showLoadError(e));
  } catch (e) {
    showLoadError(e);
  }
}
function showLoadError(e) {
  console.error('loadData 失败:', e);
  const html = document.documentElement.outerHTML.length;
  document.getElementById('loading').innerHTML =
    '<div style="text-align:left;font-size:13px;line-height:1.6;color:#ff9b9b">' +
    '❌ <b>' + (e.message || e) + '</b><br><br>' +
    '<b>诊断：</b><br>' +
    '• HTML 总长: ' + (html/1024).toFixed(0) + ' KB<br>' +
    '• 当前 URL: ' + location.href + '<br>' +
    '• document.lastModified: ' + (document.lastModified || '未知') + '<br><br>' +
    '<b>🔧 解决：</b><br>' +
    '1. <b>硬刷新</b> Mac <code>Cmd+Shift+R</code> / Win <code>Ctrl+F5</code><br>' +
    '2. 地址栏加 <code>?v=' + Date.now() + '</code><br>' +
    '3. 用离线版 <code>file://...web/dashboard_offline.html</code></div>';
}

// ========== 2. 初始化 ==========
function init() {
  try {
    document.getElementById('loading').classList.add('hide');
    document.getElementById('m_total').textContent = DATA.total.toLocaleString();
    document.getElementById('m_time').textContent = DATA.snapshot_time;

    // 填充下拉
    fillSelect('f_district', DATA.meta.districts.map(d => d.district), '全部 16 区');
    fillSelect('f_level',     DATA.meta.levels.map(d => d.level), '全部等级');
    fillSelect('f_cat',       DATA.meta.categories.map(d => d.category), '全部类型');

    bindEvents();
    initCharts();     // 必须先初始化图表实例
    applyFilter();    // 再筛选并更新图表
  } catch (e) {
    console.error('[init] 初始化失败:', e);
    setMapDiag('err', '初始化失败: ' + (e.message || e) + '<br>请打开浏览器 Console 查看详细错误');
  }
}

function setMapDiag(cls, html) {
  const el = document.getElementById('map_diag');
  if (!el) return;
  el.className = cls === 'err' ? 'err' : '';
  el.innerHTML = html;
}

// ========== 3. 填充下拉 ==========
function fillSelect(id, opts, firstLabel) {
  const el = document.getElementById(id);
  el.innerHTML = `<option value="">${firstLabel}</option>` +
    opts.map(o => `<option value="${o}">${o}</option>`).join('');
}

// ========== 4. 事件绑定 ==========
function bindEvents() {
  ['f_kw','f_district','f_level','f_cat','f_base','f_sort'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => { PAGE = 1; applyFilter(); });
    document.getElementById(id).addEventListener('change', () => { PAGE = 1; applyFilter(); });
  });
  document.getElementById('btn_reset').addEventListener('click', resetFilter);
  document.getElementById('pg_prev').addEventListener('click', () => { if (PAGE>1) { PAGE--; renderList(); } });
  document.getElementById('pg_next').addEventListener('click', () => { if (PAGE*PAGE_SIZE<FILTERED.length) { PAGE++; renderList(); } });
  document.getElementById('pg_size').addEventListener('change', e => { PAGE_SIZE = +e.target.value; PAGE = 1; renderList(); });
  document.getElementById('f_base').addEventListener('change', e => {
    if (e.target.value === 'geo' && (BASE_POINTS.geo.lng == null || BASE_POINTS.geo.lat == null)) {
      // 用户直接选了我的位置但还没定位过，自动调一次
      locateMe();
    }
  });
  // Esc 关闭弹窗
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
  document.getElementById('modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });
}

function resetFilter() {
  document.getElementById('f_kw').value = '';
  document.getElementById('f_district').value = '';
  document.getElementById('f_level').value = '';
  document.getElementById('f_cat').value = '';
  document.getElementById('f_base').value = 'tiananmen';
  document.getElementById('f_sort').value = 'score';
  PAGE = 1;
  applyFilter();
}

// ========== 4.5 用户定位 ==========
// MVP 极简版：点击 → 浏览器授权 → 拿经纬度 → 切基准点到"我的位置" → 重算距离
// 注意：file:// 协议下浏览器拒绝授权，必须用 http://localhost 跑
function locateMe() {
  const btn = document.getElementById('btn_locate');
  if (!navigator.geolocation) {
    alert('当前浏览器不支持定位 API\n建议使用 Chrome / Safari / Edge 最新版');
    return;
  }
  const oldText = btn.textContent;
  btn.disabled = true;
  btn.textContent = '⏳ 定位中…';
  navigator.geolocation.getCurrentPosition(
    pos => {
      const lng = +pos.coords.longitude.toFixed(6);
      const lat = +pos.coords.latitude.toFixed(6);
      const acc = Math.round(pos.coords.accuracy);
      BASE_POINTS.geo.lng = lng;
      BASE_POINTS.geo.lat = lat;
      BASE_POINTS.geo.name = `我的位置(±${acc}m)`;
      // 启用"我的位置" option，更新 select 值
      const opt = document.getElementById('opt_geo');
      opt.disabled = false;
      opt.textContent = '📍 ' + BASE_POINTS.geo.name;
      document.getElementById('f_base').value = 'geo';
      // 提示并重算
      btn.textContent = '✅ 已定位';
      setTimeout(() => { btn.textContent = '📍 重新定位'; btn.disabled = false; }, 1200);
      // 【关键】自动切到"距离↑"排序，让定位结果一眼可见
      document.getElementById('f_sort').value = 'distance';
      applyFilter();
      // 顶部显式反馈
      showLocateToast(lng, lat, acc);
      console.log('[定位成功]', {lng, lat, accuracy: acc, baseKey: 'geo'});
    },
    err => {
      btn.textContent = oldText;
      btn.disabled = false;
      let msg = '定位失败：';
      if (err.code === 1) msg += '用户拒绝授权';
      else if (err.code === 2) msg += '位置不可用（GPS/网络问题）';
      else if (err.code === 3) msg += '请求超时';
      else msg += err.message;
      msg += '\n\n请确认：\n1) 浏览器允许位置权限\n2) 用 http://localhost 打开（不是 file://）\n3) 系统设置里开启了位置服务';
      alert(msg);
      console.warn('[定位失败]', err);
    },
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
  );
}

// 定位成功后顶部显式反馈条
function showLocateToast(lng, lat, acc) {
  let toast = document.getElementById('locate_toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'locate_toast';
    toast.style.cssText = 'position:fixed;top:12px;left:50%;transform:translateX(-50%);' +
      'background:linear-gradient(90deg,#1f3a68,#14213d);color:#5fd3c0;border:1px solid #5fd3c0;' +
      'padding:10px 20px;border-radius:6px;z-index:9999;font-size:13px;box-shadow:0 4px 12px rgba(0,0,0,0.4);' +
      'transition:opacity 0.4s';
    document.body.appendChild(toast);
  }
  toast.innerHTML = `📍 已定位：<b>${lng}, ${lat}</b>（精度 ±${acc}m） · 已自动按距离升序排序，列表显示距你最近的医院`;
  toast.style.opacity = '1';
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { toast.style.opacity = '0'; }, 5000);
}

// ========== 5. 筛选核心 ==========
function haversine(lng1, lat1, lng2, lat2) {
  const R = 6371;
  const toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat/2)**2 + Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*Math.sin(dLng/2)**2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function applyFilter() {
  console.log('[applyFilter] 触发, baseKey=', JSON.stringify(document.getElementById('f_base').value), 'base=', JSON.stringify(BASE_POINTS[document.getElementById('f_base').value]));
  if (!DATA) return;
  const kw = document.getElementById('f_kw').value.trim().toLowerCase();
  const district = document.getElementById('f_district').value;
  const level = document.getElementById('f_level').value;
  const cat = document.getElementById('f_cat').value;
  const baseKey = document.getElementById('f_base').value;
  const sort = document.getElementById('f_sort').value;
  const base = BASE_POINTS[baseKey];
  // 防御：base 无效（极少见：缓存旧版）时回退到天安门并打印
  if (!base) {
    console.warn('[applyFilter] baseKey', JSON.stringify(baseKey), '无效，回退到天安门');
    document.getElementById('f_base').value = 'tiananmen';
  }
  const baseSafe = base || BASE_POINTS.tiananmen;

  FILTERED = DATA.institutions.filter(r => {
    if (kw) {
      const txt = (r.name + ' ' + r.district).toLowerCase();
      if (!txt.includes(kw)) return false;
    }
    if (district && r.district !== district) return false;
    if (level && r.level !== level) return false;
    if (cat && r.category !== cat) return false;
    if (r.lng != null && r.lat != null) {
      r._dist = haversine(baseSafe.lng, baseSafe.lat, r.lng, r.lat);
    } else {
      r._dist = null;
    }
    return true;
  });

  // 计算评分：归一化
  let maxBed = 0, maxDept = 0, maxDist = 0;
  FILTERED.forEach(r => {
    if (r.beds) maxBed = Math.max(maxBed, r.beds);
    if (r.dept_count) maxDept = Math.max(maxDept, r.dept_count);
    if (r._dist != null) maxDist = Math.max(maxDist, r._dist);
  });
  FILTERED.forEach(r => {
    const lv = (LEVEL_RANK[r.level] || 1) / 4;
    const ds = r._dist == null ? 0.5 : Math.max(0, 1 - r._dist / (maxDist || 1));
    const dp = (r.dept_count || 0) / (maxDept || 1);
    const bd = (r.beds || 0) / (maxBed || 1);
    r._score = W_LEVEL*lv + W_DIST*ds + W_DEPT*dp + W_BED*bd;
  });

  // 排序
  const cmp = {
    score:    (a,b) => b._score - a._score,
    distance: (a,b) => (a._dist==null?9e9:a._dist) - (b._dist==null?9e9:b._dist),
    level:    (a,b) => (LEVEL_RANK[b.level]||0) - (LEVEL_RANK[a.level]||0),
    beds:     (a,b) => (b.beds||0) - (a.beds||0),
    depts:    (a,b) => (b.dept_count||0) - (a.dept_count||0),
    name:     (a,b) => a.name.localeCompare(b.name, 'zh-CN'),
  }[sort] || ((a,b) => b._score - a._score);
  FILTERED.sort(cmp);

  renderCards();
  renderList();
  updateCharts();
}

// ========== 6. 统计卡 ==========
function renderCards() {
  document.getElementById('v_match').textContent = FILTERED.length.toLocaleString();
  document.getElementById('v_l3').textContent = FILTERED.filter(r => r.level === '三级').length.toLocaleString();
  document.getElementById('v_coord').textContent = FILTERED.filter(r => r.lng != null).length.toLocaleString();
  const avg = FILTERED.length ? (FILTERED.reduce((s,r) => s + (r.dept_count||0), 0) / FILTERED.length).toFixed(1) : '0';
  document.getElementById('v_dept').textContent = avg;
  document.getElementById('listTag').textContent = `LIST · 共 ${FILTERED.length.toLocaleString()} 家`;
}

// ========== 7. 列表渲染 ==========
function levelBadge(lv) {
  // 不参加医院等级评审的机构（诊所/卫生室/门诊部/服务站等）单独标注，避免误读为"未定级"
  if (lv === '不适用医院分级') {
    return `<span class="badge b-l0" title="该机构类型不参加医院等级评审（如诊所、村卫生室、门诊部、社区卫生服务站、医务室等）">不适用分级</span>`;
  }
  const cls = lv==='三级'?'b-l3':lv==='二级'?'b-l2':lv==='一级'?'b-l1':'b-l0';
  return `<span class="badge ${cls}">${lv}</span>`;
}
function catBadge(c) {
  return c ? `<span class="badge b-l0" style="margin-left:4px">${c}</span>` : '';
}
// 公立/民营徽章（govern_master.py 规则引擎产出；「未标注」不显示，避免噪音）
function ownBadge(o) {
  if (o === '公立') return `<span class="badge b-pub" title="依据：登记注册类型/政府办属性">公立</span>`;
  if (o === '民营') return `<span class="badge b-pri" title="依据：营利性/私有/非政府办属性">民营</span>`;
  return '';
}
// 擅长科室三级分级（权威优先）：L1 重点专科 > L2 登记诊疗科目 > L3 普通临床科室
const FEAT_LABEL = {1: '重点专科', 2: '优势科室', 3: '诊疗科室'};
function featLine(r) {
  if (!r.feature) return '';
  const depts = r.feature.split(';').filter(x => x);
  if (!depts.length) return '';
  const lv = r.feature_level || '3';
  const show = depts.slice(0, 6).join(' / ') + (depts.length > 6 ? ` 等${depts.length}项` : '');
  return `<div class="feat" title="${depts.join(' / ')}"><span class="fk f${lv}">${FEAT_LABEL[lv] || '擅长'}</span><span class="ft">${show}</span></div>`;
}
// 关键词命中高亮（不转义，name 来自可信数据）
function escHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function kwMark(s) {
  const kw = (document.getElementById('f_kw').value || '').trim();
  const safe = escHtml(s);
  if (!kw) return safe;
  const re = new RegExp('(' + kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
  return safe.replace(re, '<mark>$1</mark>');
}
// 重点专科数字块：有重点专科(>0)时红/主题色突出，无则灰显
function kscBlock(r) {
  const n = r.key_specialty_count || 0;
  const on = n > 0;
  return `<div class="ksc ${on ? 'on' : 'off'}"><div class="n">${n}</div><div class="t">重点专科</div></div>`;
}
function renderList() {
  const start = (PAGE - 1) * PAGE_SIZE;
  const end = Math.min(start + PAGE_SIZE, FILTERED.length);
  const page = FILTERED.slice(start, end);
  const totalPg = Math.max(1, Math.ceil(FILTERED.length / PAGE_SIZE));
  document.getElementById('pg_info').textContent = `${PAGE} / ${totalPg}`;
  document.getElementById('pg_prev').disabled = PAGE <= 1;
  document.getElementById('pg_next').disabled = PAGE >= totalPg;
  if (!page.length) {
    document.getElementById('list').innerHTML =
      '<div style="padding:40px;text-align:center;color:#8aa1c8;font-size:13px">没有符合条件的机构，试试放宽筛选条件</div>';
    return;
  }
  document.getElementById('list').innerHTML = page.map(r => {
    const baseNow = BASE_POINTS[document.getElementById('f_base').value] || BASE_POINTS.tiananmen;
    const baseName = baseNow.name || '天安门';
    const dist = r._dist == null ? '—' : r._dist.toFixed(1) + ' km';
    const distMeta = (document.getElementById('f_base').value === 'geo' && (baseNow.lng == null || baseNow.lat == null))
      ? '⚠️ 请点 📍 定位'
      : `距${baseName}`;
    const score = (r._score || 0).toFixed(3);
    const kwActive = (document.getElementById('f_kw').value || '').trim();
    const hitCls = kwActive ? ' hit' : '';
    return `<div class="row${hitCls}" data-id="${r.id}">
      <div>
        <div class="name">${kwMark(r.name)}</div>
        <div class="meta">${levelBadge(r.level)}${catBadge(r.category)}${ownBadge(r.ownership)} ${r.district} · ${r.dept_count||0} 科室</div>
        ${featLine(r)}
      </div>
      <div class="num">${r.beds||'—'}<div class="meta" style="color:#8aa1c8">床位</div></div>
      <div class="dist">${dist}<div class="meta" style="color:#8aa1c8">${distMeta}</div></div>
      <div class="score">${score}</div>
      ${kscBlock(r)}
    </div>`;
  }).join('');
  document.querySelectorAll('.row').forEach(el => {
    el.addEventListener('click', () => showDetail(el.dataset.id));
  });
}

// ========== 8. 图表初始化 ==========
function initCharts() {
  try {
    const mapDiv = document.getElementById('map');
    if (!mapDiv) throw new Error('找不到 #map 容器');
    setMapDiag('', '⏳ 正在初始化 ECharts 地图…');

    if (typeof echarts === 'undefined') throw new Error('ECharts 库未加载（检查 CDN 或网络）');
    if (!DATA || !DATA.geojson) throw new Error('数据中缺少 geojson');

    MAP_CHART = echarts.init(mapDiv);
    echarts.registerMap('beijing', DATA.geojson);

    // 验证地图注册成功
    const reg = echarts.getMap && echarts.getMap('beijing');
    if (!reg || !reg.geoJson) throw new Error('registerMap("beijing") 失败');

    const mapOpt = {
      backgroundColor: PANEL, textStyle: {color: INK},
      tooltip: {trigger:'item', backgroundColor:'#0b1530', borderColor:EDGE, textStyle:{color:INK}},
      geo: {
        map:'beijing', roam:true, zoom:1,
        // 让整个北京地图贴合容器并居中，避免放大超边界被裁切（密云/怀柔贴边）
        layoutCenter:['50%','50%'], layoutSize:'96%', aspectScale:0.9,
        label:{show:true, color:INK, fontSize:10},
        itemStyle:{borderColor:EDGE, borderWidth:1, areaColor:'#14213d'},
        emphasis:{label:{color:'#fff'}, itemStyle:{areaColor:'#3aa0ff'}},
      },
      visualMap: {
        min:0, max:1300, left:12, bottom:16, itemWidth:10, itemHeight:130,
        text:['高','低'], calculable:true,
        inRange:{color:['#0b1530','#1f3a68','#3aa0ff','#5fd3c0']},
        textStyle:{color:SUB, fontSize:10},
      },
      series: [{
        name: '机构数', type:'map', geoIndex:0,
        data: DATA.overviews.districts.map(d => ({name:d.district, value:d.inst_count})),
      }],
    };
    MAP_CHART.setOption(mapOpt);
    MAP_CHART.resize();
    MAP_CHART.on('click', params => {
      if (params.name) {
        document.getElementById('f_district').value = params.name;
        applyFilter();
      }
    });

    CH1 = echarts.init(document.getElementById('ch1'));
    CH2 = echarts.init(document.getElementById('ch2'));
    CH3 = echarts.init(document.getElementById('ch3'));

    window.addEventListener('resize', () => {
      [MAP_CHART, CH1, CH2, CH3].forEach(c => c && c.resize());
      if (MODAL_CHART) MODAL_CHART.resize();
    });

    const featCount = (DATA.geojson.features || []).length;
    setMapDiag('', '✅ 地图初始化完成：' + featCount + ' 个区 · ' + FILTERED.length + ' 家机构<br>' +
      '<span style="color:#8aa1c8">提示：地图可缩放拖拽，点击区名可筛选</span>');
    // 5 秒后淡出诊断横幅
    setTimeout(() => {
      const el = document.getElementById('map_diag');
      if (el) el.style.opacity = '0.3';
    }, 5000);
  } catch (e) {
    console.error('[initCharts] 地图初始化失败:', e);
    setMapDiag('err', '❌ 地图初始化失败<br><b>' + (e.message || e) + '</b><br><br>' +
      '🔧 请尝试：<br>' +
      '1. 按 <b>Cmd+Shift+R</b> 硬刷新<br>' +
      '2. 地址栏加 <code>?v=' + Date.now() + '</code><br>' +
      '3. 打开浏览器 Console 截图红字错误');
    throw e;
  }
}

// ========== 9. 动态更新图表 ==========
function updateCharts() {
  if (!CH1 || !CH2 || !CH3 || !MAP_CHART) {
    console.warn('[updateCharts] 图表实例尚未初始化，跳过');
    return;
  }
  // 等级环形
  // 口径：仅统计参加医院等级评审的机构；level='不适用医院分级'（诊所/村卫生室/门诊部/
  // 社区卫生服务站/医务室/急救/疾控/体检等）制度上无等级，计入会形成假性"未定级"
  const lvCount = {};
  FILTERED.forEach(r => {
    if (r.level === '不适用医院分级') return;
    lvCount[r.level] = (lvCount[r.level]||0) + 1;
  });
  CH1.setOption({
    series:[{type:'pie', radius:['42%','70%'],
      data: Object.entries(lvCount).map(([n,v])=>({name:n, value:v})),
      label:{color:INK, fontSize:11}, labelLine:{lineStyle:{color:SUB}},
      itemStyle:{borderColor:PANEL, borderWidth:2},
      color:[CRIT, WARN, ACC, ACC2]}],
    legend:{bottom:0, textStyle:{color:INK, fontSize:11}},
  });

  // 类型柱状
  const catCount = {};
  FILTERED.forEach(r => catCount[r.category] = (catCount[r.category]||0) + 1);
  const catSorted = Object.entries(catCount).sort((a,b)=>b[1]-a[1]);
  CH2.setOption({
    grid:{left:90, right:20, top:10, bottom:20},
    xAxis:{type:'value', axisLine:{lineStyle:{color:EDGE}}, axisLabel:{color:SUB, fontSize:10}},
    yAxis:{type:'category', data:catSorted.map(c=>c[0]), axisLine:{lineStyle:{color:EDGE}}, axisLabel:{color:INK, fontSize:10}},
    series:[{type:'bar', data:catSorted.map(c=>c[1]), itemStyle:{color:ACC},
      label:{show:true, position:'right', color:INK, fontSize:10}}],
  });

  // 各区柱状
  const dCount = {};
  FILTERED.forEach(r => dCount[r.district] = (dCount[r.district]||0) + 1);
  const dSorted = Object.entries(dCount).sort((a,b)=>b[1]-a[1]);
  CH3.setOption({
    grid:{left:80, right:20, top:10, bottom:30},
    xAxis:{type:'category', data:dSorted.map(c=>c[0]), axisLine:{lineStyle:{color:EDGE}},
      axisLabel:{color:INK, fontSize:9, rotate:30}},
    yAxis:{type:'value', axisLine:{lineStyle:{color:EDGE}}, axisLabel:{color:SUB, fontSize:10}},
    series:[{type:'bar', data:dSorted.map(c=>c[1]), itemStyle:{color:ACC2},
      label:{show:true, position:'top', color:INK, fontSize:10}}],
  });

  // 地图散点叠加（用 effectScatter 叠在 geo 上）
  try {
    // 防御：剔除落在北京地图可视范围之外的点（经纬度越界会被画出版图，形成孤点）
    const inBbox = r => {
      if (r.lng == null || r.lat == null) return false;
      const lng = +r.lng, lat = +r.lat;
      // 北京 admin 边界实测：lng 115.4~117.5, lat 39.4~41.1（含密云/平谷最东）
      return lng > 115.35 && lng < 117.50 && lat > 39.40 && lat < 41.10;
    };
    const points = FILTERED.filter(inBbox).slice(0, 3000);
    MAP_CHART.setOption({
      series: [
        {type:'map', geoIndex:0},
        {type:'effectScatter', coordinateSystem:'geo',
          data: points.map(r => ({name:r.name, value:[r.lng, r.lat, r.level||'其他']})),
          symbolSize: v => v[2]==='三级'?6:v[2]==='二级'?4:2,
          rippleEffect:{period:4, scale:2.5, brushType:'stroke'},
          itemStyle:{
            color: v => v[2]==='三级'?CRIT:v[2]==='二级'?WARN:ACC2,
            shadowBlur:8, shadowColor:'#3aa0ff'
          },
          showEffectOn:'render', zlevel:2},
      ],
    });
  } catch (e) {
    console.error('[updateCharts] 散点更新失败:', e);
  }
}

// ========== 11. 详情弹窗 ==========
function showDetail(id) {
  const r = DATA.institutions.find(x => x.id === String(id));
  if (!r) return;
  document.getElementById('m_title').textContent = r.name;
  document.getElementById('m_info').innerHTML = `
    <div><div class="l">区 域</div><div class="v">${r.district}</div></div>
    <div><div class="l">等 级</div><div class="v">${levelBadge(r.level)} ${r.level === '不适用医院分级' ? '（该机构类型不参加医院等级评审）' : r.level}</div></div>
    <div><div class="l">类 型</div><div class="v">${r.category || '—'}${r.category_sub && r.category_sub !== '未细分' ? ' · ' + r.category_sub : ''}</div></div>
    <div><div class="l">办 别</div><div class="v">${ownBadge(r.ownership) || (r.ownership || '未标注')}${r.ownership_basis ? ` <span style="color:#8aa1c8;font-size:10px">依据 ${r.ownership_basis}</span>` : ''}</div></div>
    <div><div class="l">床 位</div><div class="v">${r.beds || '—'}</div></div>
    <div><div class="l">科 室 数</div><div class="v">${r.dept_count || 0}</div></div>
    <div><div class="l">重点专科数</div><div class="v">${r.key_specialty_count || 0}</div></div>
    <div><div class="l">坐 标 精 度</div><div class="v">${r.coord_precision || '—'}</div></div>
    <div><div class="l">综 合 评 分</div><div class="v" style="color:#f7b955">${(r._score||0).toFixed(3)}</div></div>
  `;
  // 擅长科室：权威优先三级分级（L1 重点专科 > L2 优势科室 > L3 诊疗科室），无 feature 时回退 key_depts
  const featDepts = r.feature ? r.feature.split(/[;；]/).map(x => x.trim()).filter(x => x) : [];
  const keyDepts = r.key_depts ? r.key_depts.split(/[,,、;\s]+/).filter(x => x) : [];
  const lv = r.feature_level;
  if (featDepts.length) {
    const lvColor = lv === '1' ? '#ff6b6b' : lv === '2' ? '#f7b955' : '#8aa1c8';
    const lvBg = lv === '1' ? '#ff6b6b22' : lv === '2' ? '#f7b95522' : '#8aa1c826';
    document.getElementById('m_depts').innerHTML =
      `<span style="color:#8aa1c8;font-size:10px;width:100%;display:inline-block;margin-bottom:4px">` +
      `${FEAT_LABEL[lv] || '擅长'}（权威度分级 L${lv}，共 ${featDepts.length} 项）` +
      `${r.key_specialty_count ? ` · 其中重点专科 ${r.key_specialty_count} 项` : ''}：</span>` +
      featDepts.map(d =>
        `<span style="border:1px solid ${lvColor}44;background:${lvBg};color:${lvColor};font-weight:600">${d}</span>`
      ).join('');
  } else if (keyDepts.length) {
    document.getElementById('m_depts').innerHTML =
      `<span style="color:#8aa1c8;font-size:10px;width:100%">诊疗科目（共 ${keyDepts.length} 项）：</span>` +
      keyDepts.map(d => `<span>${d}</span>`).join('');
  } else {
    document.getElementById('m_depts').innerHTML = '<span style="color:#8aa1c8">无重点科室/科室标注</span>';
  }

  // 弹窗里的 mini chart：当前机构在所属区的科室数对比
  const sameDist = DATA.institutions.filter(x => x.district === r.district && x.dept_count);
  const top10 = sameDist.sort((a,b) => (b.dept_count||0) - (a.dept_count||0)).slice(0, 10);
  const highlight = top10.find(x => x.id === r.id);
  document.getElementById('modal').classList.add('show');
  setTimeout(() => {
    if (!MODAL_CHART) MODAL_CHART = echarts.init(document.getElementById('modalChart'));
    MODAL_CHART.setOption({
      backgroundColor: PANEL, textStyle:{color:INK},
      title:{text:`同区 TOP 10 科室数对比 · 当前位置：${highlight?'★':'·'}`, textStyle:{color:ACC, fontSize:12}, left:6, top:4},
      grid:{left:120, right:20, top:36, bottom:20},
      xAxis:{type:'value', axisLine:{lineStyle:{color:EDGE}}, axisLabel:{color:SUB, fontSize:10}},
      yAxis:{type:'category', data:top10.map(x=>x.name.slice(0,18)).reverse(),
        axisLine:{lineStyle:{color:EDGE}}, axisLabel:{color:INK, fontSize:10}},
      series:[{type:'bar',
        data: top10.map(x => ({value: x.dept_count, itemStyle:{color: x.id===r.id?CRIT:ACC}})).reverse(),
        label:{show:true, position:'right', color:INK, fontSize:10}}],
    });
  }, 50);
}

function closeModal() {
  document.getElementById('modal').classList.remove('show');
}

// ========== 启动 ==========
loadData();
