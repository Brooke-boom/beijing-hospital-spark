// ========== 北京市医院资源系统 - 可交互 SPA ==========
// 数据来源：snapshot_data.json（2.6MB，含 9791 家机构 + 4 张概览 + 15 专科组 + 北京 geoJSON）

const BG='#0b1530', PANEL='#14213d', EDGE='#1f3a68', INK='#e8eefc', SUB='#8aa1c8';
const ACC='#3aa0ff', ACC2='#5fd3c0', WARN='#f7b955', CRIT='#ff6b6b', VIO='#a78bfa';

const BASE_POINTS = {
  tiananmen:       {name:'天安门',       lng:116.397, lat:39.909},
  capital_airport: {name:'首都机场',     lng:116.609, lat:40.080},
  daxing_airport:  {name:'大兴机场',     lng:116.411, lat:39.510},
  custom:          {name:'自定义',       lng:116.397, lat:39.909},
};
const LEVEL_RANK = {'三级':4, '二级':3, '一级':2, '未定级':1};

// 评分权重
const W_LEVEL = 0.4, W_DIST = 0.3, W_DEPT = 0.2, W_BED = 0.1;

let DATA = null;          // 全量数据
let FILTERED = [];        // 筛选后
let PAGE = 1;
let PAGE_SIZE = 20;
let MAP_CHART, CH1, CH2, CH3, MODAL_CHART;

// ========== 1. 加载数据 ==========
async function loadData() {
  try {
    const resp = await fetch('snapshot_data.json');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    DATA = await resp.json();
    console.log('数据加载完成:', DATA.total, '家');
    init();
  } catch (e) {
    document.getElementById('loading').innerHTML =
      '❌ 数据加载失败：' + e.message + '<br>请确保 <code>snapshot_data.json</code> 与 HTML 在同一目录';
  }
}

// ========== 2. 初始化 ==========
function init() {
  document.getElementById('loading').classList.add('hide');
  document.getElementById('m_total').textContent = DATA.total.toLocaleString();
  document.getElementById('m_time').textContent = DATA.snapshot_time;

  // 填充下拉
  fillSelect('f_district', DATA.meta.districts.map(d => d.district), '全部 16 区');
  fillSelect('f_level',     DATA.meta.levels.map(d => d.level), '全部等级');
  fillSelect('f_cat',       DATA.meta.categories.map(d => d.category), '全部类型');

  bindEvents();
  applyFilter();
  renderSpecGrid();
  initCharts();
}

// ========== 3. 填充下拉 ==========
function fillSelect(id, opts, firstLabel) {
  const el = document.getElementById(id);
  el.innerHTML = `<option value="">${firstLabel}</option>` +
    opts.map(o => `<option value="${o}">${o}</option>`).join('');
}

// ========== 4. 事件绑定 ==========
function bindEvents() {
  ['f_kw','f_district','f_level','f_cat','f_base','f_radius','f_sort'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => { PAGE = 1; applyFilter(); });
    document.getElementById(id).addEventListener('change', () => { PAGE = 1; applyFilter(); });
  });
  document.getElementById('btn_reset').addEventListener('click', resetFilter);
  document.getElementById('pg_prev').addEventListener('click', () => { if (PAGE>1) { PAGE--; renderList(); } });
  document.getElementById('pg_next').addEventListener('click', () => { if (PAGE*PAGE_SIZE<FILTERED.length) { PAGE++; renderList(); } });
  document.getElementById('pg_size').addEventListener('change', e => { PAGE_SIZE = +e.target.value; PAGE = 1; renderList(); });
  document.getElementById('f_base').addEventListener('change', e => {
    if (e.target.value === 'custom') {
      const lng = +prompt('请输入经度（如 116.40）', '116.40');
      const lat = +prompt('请输入纬度（如 39.90）', '39.90');
      if (!isNaN(lng) && !isNaN(lat)) {
        BASE_POINTS.custom.lng = lng; BASE_POINTS.custom.lat = lat;
        alert('自定义基准点已设置：' + lng + ', ' + lat);
      }
      applyFilter();
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
  document.getElementById('f_radius').value = 999;
  document.getElementById('f_sort').value = 'score';
  PAGE = 1;
  applyFilter();
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
  if (!DATA) return;
  const kw = document.getElementById('f_kw').value.trim().toLowerCase();
  const district = document.getElementById('f_district').value;
  const level = document.getElementById('f_level').value;
  const cat = document.getElementById('f_cat').value;
  const baseKey = document.getElementById('f_base').value;
  const radius = +document.getElementById('f_radius').value || 99999;
  const sort = document.getElementById('f_sort').value;
  const base = BASE_POINTS[baseKey];

  FILTERED = DATA.institutions.filter(r => {
    if (kw) {
      const txt = (r.name + ' ' + r.district).toLowerCase();
      if (!txt.includes(kw)) return false;
    }
    if (district && r.district !== district) return false;
    if (level && r.level !== level) return false;
    if (cat && r.category !== cat) return false;
    if (r.lng != null && r.lat != null) {
      r._dist = haversine(base.lng, base.lat, r.lng, r.lat);
      if (r._dist > radius) return false;
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
  const cls = lv==='三级'?'b-l3':lv==='二级'?'b-l2':lv==='一级'?'b-l1':'b-l0';
  return `<span class="badge ${cls}">${lv}</span>`;
}
function catBadge(c) {
  return c ? `<span class="badge b-l0" style="margin-left:4px">${c}</span>` : '';
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
    const dist = r._dist == null ? '—' : r._dist.toFixed(1) + ' km';
    const score = (r._score || 0).toFixed(3);
    return `<div class="row" data-id="${r.id}">
      <div>
        <div class="name">${r.name}</div>
        <div class="meta">${levelBadge(r.level)}${catBadge(r.category)} ${r.district} · ${r.dept_count||0} 科室</div>
      </div>
      <div class="num">${r.beds||'—'}<div class="meta" style="color:#8aa1c8">床位</div></div>
      <div class="dist">${dist}<div class="meta" style="color:#8aa1c8">距${BASE_POINTS[document.getElementById('f_base').value].name}</div></div>
      <div class="score">${score}</div>
      <div class="meta" style="color:#8aa1c8;text-align:right">${r.key_specialty_count||0}<br>重点专科</div>
    </div>`;
  }).join('');
  document.querySelectorAll('.row').forEach(el => {
    el.addEventListener('click', () => showDetail(el.dataset.id));
  });
}

// ========== 8. 图表初始化 ==========
function initCharts() {
  const baseOpt = { backgroundColor: PANEL, textStyle: {color: INK} };

  // 地图
  MAP_CHART = echarts.init(document.getElementById('map'));
  echarts.registerMap('beijing', DATA.geojson);
  const mapOpt = {
    backgroundColor: PANEL, textStyle: {color: INK},
    tooltip: {trigger:'item', backgroundColor:'#0b1530', borderColor:EDGE, textStyle:{color:INK}},
    visualMap: {
      min:0, max:1300, left:'left', bottom:20,
      text:['高','低'], calculable:true,
      inRange:{color:['#0b1530','#1f3a68','#3aa0ff','#5fd3c0']},
      textStyle:{color:SUB},
    },
    series: [{
      name: '机构数', type:'map', map:'beijing', roam:true, zoom:1.15,
      label:{show:true, color:INK, fontSize:10},
      itemStyle:{borderColor:EDGE, borderWidth:1, areaColor:'#14213d'},
      emphasis:{label:{color:'#fff'}, itemStyle:{areaColor:'#3aa0ff'}},
      data: DATA.overviews.districts.map(d => ({name:d.district, value:d.inst_count})),
    }],
  };
  MAP_CHART.setOption(mapOpt);
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
}

// ========== 9. 动态更新图表 ==========
function updateCharts() {
  // 等级环形
  const lvCount = {};
  FILTERED.forEach(r => lvCount[r.level] = (lvCount[r.level]||0) + 1);
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

  // 地图散点叠加（用 EFFECT SCATTER）
  const points = FILTERED.filter(r => r.lng != null).slice(0, 3000);
  MAP_CHART.setOption({
    series: [
      {type:'map', map:'beijing'},
      {type:'effectScatter', coordinateSystem:'geo',
        data: points.map(r => ({name:r.name, value:[r.lng, r.lat, r.level]})),
        symbolSize: v => v[2]==='三级'?6:v[2]==='二级'?4:2,
        rippleEffect:{period:4, scale:2.5, brushType:'stroke'},
        itemStyle:{color:v => v[2]==='三级'?CRIT:v[2]==='二级'?WARN:ACC2},
        showEffectOn:'render', zlevel:2},
    ],
  });
}

// ========== 10. 重点专科卡片 ==========
function renderSpecGrid() {
  const grid = document.getElementById('spec_grid');
  grid.innerHTML = DATA.specialty_groups.map(g => `
    <div class="spec" data-dept="${g.dept_name}">
      <div class="dn">${g.dept_name}</div>
      <div class="cnt">${g.hospital_count}<small>家</small></div>
      <div class="top">
        ${g.top_hospitals.map(h => `<div><span class="hn">${h.name}</span> · ${h.district}</div>`).join('')}
      </div>
    </div>
  `).join('');
  grid.querySelectorAll('.spec').forEach(el => {
    el.addEventListener('click', () => {
      const dept = el.dataset.dept;
      const ids = DATA.specialty_groups.find(g => g.dept_name === dept).top_hospitals.map(h => h.id);
      const idset = new Set(ids);
      // 滚动到顶部并筛出该专科
      document.getElementById('f_kw').value = '';
      document.getElementById('f_district').value = '';
      document.getElementById('f_level').value = '';
      document.getElementById('f_cat').value = '';
      // 临时筛选：仅显示该专科代表医院
      FILTERED = DATA.institutions.filter(r => idset.has(r.id));
      const base = BASE_POINTS[document.getElementById('f_base').value];
      let maxBed=0, maxDept=0, maxDist=0;
      FILTERED.forEach(r => {
        if (r.beds) maxBed=Math.max(maxBed,r.beds);
        if (r.dept_count) maxDept=Math.max(maxDept,r.dept_count);
        if (r.lng!=null) {
          r._dist = haversine(base.lng, base.lat, r.lng, r.lat);
          maxDist = Math.max(maxDist, r._dist);
        } else r._dist = null;
      });
      FILTERED.forEach(r => {
        const lv = (LEVEL_RANK[r.level]||1)/4;
        const ds = r._dist==null?0.5:Math.max(0, 1-r._dist/(maxDist||1));
        const dp = (r.dept_count||0)/(maxDept||1);
        const bd = (r.beds||0)/(maxBed||1);
        r._score = W_LEVEL*lv + W_DIST*ds + W_DEPT*dp + W_BED*bd;
      });
      PAGE = 1;
      renderCards();
      renderList();
      updateCharts();
      document.getElementById('list').scrollIntoView({behavior:'smooth', block:'start'});
    });
  });
}

// ========== 11. 详情弹窗 ==========
function showDetail(id) {
  const r = DATA.institutions.find(x => x.id === String(id));
  if (!r) return;
  document.getElementById('m_title').textContent = r.name;
  document.getElementById('m_info').innerHTML = `
    <div><div class="l">区 域</div><div class="v">${r.district}</div></div>
    <div><div class="l">等 级</div><div class="v">${levelBadge(r.level)} ${r.level}</div></div>
    <div><div class="l">类 型</div><div class="v">${r.category || '—'}</div></div>
    <div><div class="l">床 位</div><div class="v">${r.beds || '—'}</div></div>
    <div><div class="l">科 室 数</div><div class="v">${r.dept_count || 0}</div></div>
    <div><div class="l">重点专科数</div><div class="v">${r.key_specialty_count || 0}</div></div>
    <div><div class="l">坐 标 精 度</div><div class="v">${r.coord_precision || '—'}</div></div>
    <div><div class="l">综 合 评 分</div><div class="v" style="color:#f7b955">${(r._score||0).toFixed(3)}</div></div>
  `;
  const keyDepts = r.key_depts ? r.key_depts.split(/[,,、;\s]+/).filter(x => x) : [];
  document.getElementById('m_depts').innerHTML = keyDepts.length
    ? keyDepts.map(d => `<span>${d}</span>`).join('')
    : '<span style="color:#8aa1c8">无重点科室标注</span>';

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
