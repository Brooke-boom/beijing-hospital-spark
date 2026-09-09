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
const W_LEVEL = 0.5, W_DIST = 0.3, W_DEPT = 0.2;

const DASHBOARD_VERSION = 'v3.5-20260909-net-integration';
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
    // 科室维度（第 6 维）：选项取自有覆盖数据的标准科室，匹配 feature（诊疗科室）与 key_depts（登记科目）
    fillSelect('f_dept',      DATA.meta.depts.map(d => d.dept_name), '全部科室');

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
  ['f_kw','f_district','f_level','f_cat','f_dept','f_net','f_base','f_sort'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => { PAGE = 1; applyFilter(); });
    document.getElementById(id).addEventListener('change', () => { PAGE = 1; applyFilter(); });
  });
  document.getElementById('btn_reset').addEventListener('click', resetFilter);
  // 自然语言解析：回车或点按钮触发
  const aiInput = document.getElementById('f_ai');
  if (aiInput) {
    aiInput.addEventListener('keydown', e => { if (e.key === 'Enter') applyNLQ(); });
  }
  const btnAi = document.getElementById('btn_ai');
  if (btnAi) btnAi.addEventListener('click', applyNLQ);
  const btnAiClear = document.getElementById('btn_ai_clear');
  if (btnAiClear) btnAiClear.addEventListener('click', clearNLQ);
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
  const dsel = document.getElementById('f_dept'); if (dsel) dsel.value = '';
  const nsel = document.getElementById('f_net'); if (nsel) nsel.value = '';
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

// ========== 4.8 自然语言解析（规则引擎 + 可选大模型增强） ==========
// 大模型兜底开关，默认关闭：离线版与默认在线版都走规则引擎，零外部依赖。
if (typeof window.__AI_LLM_ON__ === 'undefined') window.__AI_LLM_ON__ = false;
// 设计原则：
//   1) 规则引擎为默认路径，纯前端、完全离线可用，答辩现场零依赖；
//   2) 大模型为可选增强，默认关闭（window.__AI_LLM_ON__ = false），仅在规则零命中时异步兜底；
//   3) 解析结果必须「可解释回显」，用户可对照纠错，避免黑箱决策。

// 标准科室 → 口语/症状同义词（匹配时按词长降序，保证"妇幼保健院"优先于"医院"）
const NLQ_DEPT_SYNONYMS = [
  ['心血管内科', ['心脏病','心脏','心血管','心悸','胸闷','胸痛','高血压','血压高','冠心病','心梗','心肌梗死','心绞痛','心律不齐','房颤','心衰','心力衰竭']],
  ['呼吸内科',   ['咳嗽','咳喘','哮喘','肺炎','肺病','呼吸困难','气喘','支气管炎','慢阻肺','肺气肿','喘不上气','呼吸']],
  ['消化内科',   ['胃病','肠胃','消化','腹泻','拉肚子','腹痛','肚子疼','反酸','胃溃疡','肠胃炎','便秘','恶心','呕吐','消化不良']],
  ['神经内科',   ['头痛','头疼','偏头痛','头晕','神经内科','脑梗','脑血栓','中风','偏瘫','癫痫','帕金森','面瘫','脑血管','神经痛','眩晕','抽搐','手脚麻木']],
  ['肾内科',     ['肾病','肾脏','尿毒症','肾炎','肾功能','蛋白尿','肾衰']],
  ['内分泌科',   ['糖尿病','血糖','内分泌','甲亢','甲状腺','肥胖','减肥','痛风','尿酸','高血脂','血脂']],
  ['血液内科',   ['贫血','白血病','血友病','血小板','淋巴瘤','血液病']],
  ['老年病科',   ['老年病','老年人','老人']],
  ['普内科',     ['内科','感冒','发烧','发热','普通内科']],
  ['全科医疗科', ['全科','家庭医生']],
  ['普通外科',   ['外科','普外','阑尾','阑尾炎','疝气','胆囊','胆结石','外伤','缝合']],
  ['骨科',       ['骨折','骨头','腰椎','颈椎','关节','腰痛','腰疼','腿疼','脖子疼','骨刺','骨质疏松','扭伤','脱位','脊柱','半月板','腰椎间盘','关节炎']],
  ['神经外科',   ['脑外科','脑肿瘤','脑外伤','脑出血','颅脑','脑瘤']],
  ['心胸外科',   ['心脏手术','搭桥','胸腔','开胸','心脏搭桥','肺手术']],
  ['泌尿外科',   ['泌尿','结石','肾结石','前列腺','尿频','尿急','尿路','膀胱','尿失禁']],
  ['肛肠外科',   ['痔疮','肛肠','肛门','便血','肛裂','肛瘘']],
  ['妇产科',     ['妇科','产科','怀孕','孕检','生孩子','月经','白带','妇科炎症','子宫','卵巢','产检','分娩','孕妇','备孕','流产','不孕']],
  ['儿科',       ['儿科','小孩','儿童','宝宝','小儿','孩子','幼儿','新生儿','婴儿']],
  ['肿瘤科',     ['肿瘤','癌症','癌','化疗','放疗','恶性']],
  ['精神心理科', ['精神','心理','抑郁','焦虑','失眠','神经衰弱','心理咨询']],
  ['眼科',       ['眼科','眼睛','近视','视力','白内障','青光眼','眼底','红眼']],
  ['耳鼻咽喉科', ['耳鼻喉','耳朵','听力','鼻炎','咽炎','扁桃体','咽喉','鼻子','耳鸣','中耳炎','打鼾','嗓子']],
  ['口腔科',     ['牙科','牙齿','口腔','洗牙','补牙','拔牙','牙疼','牙痛','正畸','种植牙','牙医','牙']],
  ['皮肤科',     ['皮肤病','皮肤','湿疹','过敏','皮疹','青春痘','痤疮','牛皮癣','荨麻疹','瘙痒','皮炎']],
  ['中医内科',   ['中医内科','中医','调理','中药','把脉','气血']],
  ['中医骨伤科', ['中医骨科','骨伤','正骨','跌打']],
  ['针灸推拿科', ['针灸','推拿','按摩','拔罐','艾灸','针灸推拿']],
  ['感染科',     ['感染','传染病','传染','结核','发热门诊']],
  ['肝病科',     ['肝病','肝炎','乙肝','丙肝','肝硬化','脂肪肝','肝功能']],
  ['急诊科',     ['急诊','急救','急症']],
  ['重症医学科', ['重症','危重','重症监护']],
  ['康复医学科', ['康复','康复训练','理疗','康复科']],
];

// 等级 / 类型 / 排序 / 性质 的口语映射
const NLQ_LEVEL = [['三级',['三级甲等','三甲','三级','三等甲级']],
                   ['二级',['二级','二甲']],
                   ['一级',['一级','一甲','社区医院']]];
const NLQ_CAT   = [['妇幼保健',['妇幼保健院','妇产医院','妇幼']],
                   ['急救中心',['急救中心','急救站']],
                   ['体检中心',['体检中心','体检']],
                   ['门诊部',['门诊部']],
                   ['诊所',['诊所']],
                   ['医院',['医院']]];
const NLQ_SORT  = [['distance',['离家近','离我近','最近','附近','周边','旁边','距离近','近一点']],
                   ['level',   ['最好','等级高','评级高','最强','档次高']],
                   ['depts',   ['科室全','科室多']]];
const NLQ_OWN   = [['公立',['公立','公办','国立']], ['民营',['民营','私立','民办']]];
// 命中后从原文剔除的停用词，避免污染关键词
const NLQ_STOP  = ['的','了','看','找','想','要','有','吗','啊','呀','呢','我','家','去','在','和','与','或','请','帮','推荐','一下','哪里','哪个','哪些','什么','怎么','附近','周边','最近','离家近','离我近'];

// 把 [[目标,[词...]]...] 拍平成按词长降序的匹配表（长词优先，避免子串误吞）
// includeSelf=true 时把科室标准名本身也纳入匹配，解决"骨科""神经外科"等自称未收录的问题
function nlqBuildTable(pairs, includeSelf) {
  const t = [];
  pairs.forEach(([target, words]) => {
    if (includeSelf && target) t.push({ w: target, target });
    words.forEach(w => t.push({ w, target }));
  });
  t.sort((a, b) => b.w.length - a.w.length);
  return t;
}
let _NLQ_TABLES = null;
function nlqTables() {
  if (_NLQ_TABLES) return _NLQ_TABLES;
  _NLQ_TABLES = {
    dept:  nlqBuildTable(NLQ_DEPT_SYNONYMS, true),
    level: nlqBuildTable(NLQ_LEVEL),
    cat:   nlqBuildTable(NLQ_CAT),
    sort:  nlqBuildTable(NLQ_SORT),
  };
  return _NLQ_TABLES;
}

// 在一次解析中按词长优先匹配，返回 {target, word, index} 或 null
function nlqMatch(table, text, used) {
  for (const item of table) {
    const i = text.indexOf(item.w);
    if (i >= 0) {
      // 检查该区间是否已被先前命中的词占用
      const span = used.find(u => !(i + item.w.length <= u.s || i >= u.e));
      if (span) continue;
      return { target: item.target, word: item.w, index: i, s: i, e: i + item.w.length };
    }
  }
  return null;
}

// 规则解析主函数：自然语言 → 结构化筛选条件（完全离线）
function parseNLQ(raw) {
  const text = (raw || '').trim();
  const out = { district: '', level: '', cat: '', dept: '', sort: '', kw: '', hits: [], engine: 'rule' };
  if (!text) return out;

  const T = nlqTables();
  const used = [];   // 已占用区间，防止同一段文字被重复解释
  const take = (m) => { if (m) { used.push({ s: m.s, e: m.e }); out.hits.push(m); } return m; };

  // 1. 行政区（支持"朝阳区"与"朝阳"两种写法，取数据中的真实区名）
  if (DATA && DATA.meta && DATA.meta.districts) {
    let best = null;
    DATA.meta.districts.forEach(d => {
      const full = d.district;                 // 朝阳区
      const short = full.replace(/[市区县]$/, ''); // 朝阳
      [full, short].forEach(form => {
        const i = text.indexOf(form);
        if (i >= 0 && (!best || form.length > best.form.length)) best = { form, name: full, i };
      });
    });
    if (best) {
      out.district = best.name;
      used.push({ s: best.i, e: best.i + best.form.length });
      out.hits.push({ target: best.name, word: best.form, kind: 'district' });
    }
  }

  // 2. 等级 / 3. 类型 / 4. 科室 / 5. 排序（顺序即优先级，先占位者胜）
  const lv = nlqMatch(T.level, text, used);  if (lv)  { take(lv);  out.level = lv.target;  lv.kind = 'level'; }
  const ct = nlqMatch(T.cat,   text, used);  if (ct)  { take(ct);  out.cat   = ct.target;  ct.kind = 'cat'; }
  const dp = nlqMatch(T.dept,  text, used);  if (dp)  { take(dp);  out.dept  = dp.target;  dp.kind = 'dept'; }
  const st = nlqMatch(T.sort,  text, used);  if (st)  { take(st);  out.sort  = st.target;  st.kind = 'sort'; }

  // 6. 剩余文字作为关键词（剔除命中词与停用词）
  let rest = text;
  [...used].sort((a, b) => b.s - a.s).forEach(u => { rest = rest.slice(0, u.s) + ' '.repeat(u.e - u.s) + rest.slice(u.e); });
  // 同一维度已确定，残留的同义表达（如已定"感冒"又出现"发烧"）不必再进关键词
  [T.dept, T.level, T.cat, T.sort].forEach(tb => {
    tb.forEach(it => { if (rest.indexOf(it.w) >= 0) rest = rest.split(it.w).join(' '); });
  });
  NLQ_STOP.forEach(w => { rest = rest.split(w).join(' '); });
  // 直接删除分隔符与空白（而非替换为空格），避免残留纯空格被误判成关键词
  rest = rest.replace(/[\s，。、,.!！？?；;：:（）()"'']+/g, '');
  if (rest.length >= 2) out.kw = rest;

  return out;
}

// 把解析结果写入筛选控件并刷新；同时回显"我理解为…"供用户纠错
function applyNLQ() {
  const input = document.getElementById('f_ai');
  const echo = document.getElementById('ai_echo');
  const raw = (input.value || '').trim();
  if (!raw) { echo.className = 'ai-echo'; return; }

  const r = parseNLQ(raw);

  // 规则零命中且开启大模型增强时，尝试在线兜底（默认关闭，离线版永不触发）
  if (window.__AI_LLM_ON__ && r.hits.length === 0) {
    fetch('/api/ai/parse?q=' + encodeURIComponent(raw))
      .then(resp => resp.ok ? resp.json() : null)
      .then(j => {
        if (j && j.ok && j.conditions) {
          Object.assign(r, j.conditions, { engine: 'llm' });
          commitNLQ(r, raw);
        } else { commitNLQ(r, raw); }
      })
      .catch(() => commitNLQ(r, raw));
    return;
  }
  commitNLQ(r, raw);
}

function commitNLQ(r, raw) {
  const echo = document.getElementById('ai_echo');
  const setSel = (id, v) => { const el = document.getElementById(id); if (el && v) el.value = v; };
  setSel('f_district', r.district);
  setSel('f_level', r.level);
  setSel('f_cat', r.cat);
  setSel('f_dept', r.dept);
  setSel('f_sort', r.sort || 'score');
  if (r.kw) document.getElementById('f_kw').value = r.kw;

  // 可解释回显
  const chips = [];
  if (r.district) chips.push('区域：' + r.district);
  if (r.level)    chips.push('等级：' + r.level);
  if (r.cat)      chips.push('类型：' + r.cat);
  if (r.dept)     chips.push('科室：' + r.dept);
  if (r.kw)       chips.push('关键词：' + r.kw);
  if (r.sort)     chips.push('排序：' + ({score:'综合评分',distance:'距离最近',level:'等级优先',depts:'科室最多'}[r.sort] || r.sort));

  const engineTip = r.engine === 'llm' ? '（大模型解析）' : '（规则引擎解析 · 离线可用）';
  if (chips.length === 0) {
    echo.innerHTML = '<span class="warn">⚠ 未能识别出筛选条件。</span>可试试：朝阳区看心脏病的三级医院 / 海淀区儿科诊所 / 离家最近的二甲医院';
  } else {
    echo.innerHTML = '<b>我理解为</b> ' + engineTip + '<br>' +
      chips.map(c => '<span class="chip">' + c + '</span>').join('') +
      '<br><span style="color:#6b7a99">解析结果已填入下方筛选项，可直接修改纠错。</span>';
  }
  echo.className = 'ai-echo show';
  PAGE = 1;
  applyFilter();
}

function clearNLQ() {
  document.getElementById('f_ai').value = '';
  document.getElementById('ai_echo').className = 'ai-echo';
  resetFilter();
}

function applyFilter() {
  console.log('[applyFilter] 触发, baseKey=', JSON.stringify(document.getElementById('f_base').value), 'base=', JSON.stringify(BASE_POINTS[document.getElementById('f_base').value]));
  if (!DATA) return;
  const kw = document.getElementById('f_kw').value.trim().toLowerCase();
  const district = document.getElementById('f_district').value;
  const level = document.getElementById('f_level').value;
  const cat = document.getElementById('f_cat').value;
  const deptEl = document.getElementById('f_dept');
  const dept = deptEl ? deptEl.value : '';
  const netEl = document.getElementById('f_net');
  const net = netEl ? netEl.value : '';
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
    // 协作网络维度：儿科医联体(核心/成员) / 卒中中心 / 危重新生儿救治 / 危重孕产妇救治
    if (net) {
      if (net === 'ped_core'   && r.net_pediatric !== '核心') return false;
      if (net === 'ped_member' && r.net_pediatric !== '成员') return false;
      if (net === 'stroke'     && r.net_stroke !== '1') return false;
      if (net === 'neonatal'   && r.net_neonatal !== '市级') return false;
      if (net === 'maternal'   && r.net_maternal !== '市级') return false;
    }
    // 科室维度：匹配 feature（擅长/诊疗科室）与 key_depts（登记科目）
    if (dept) {
      const pool = (r.feature || '') + ';' + (r.key_depts || '');
      if (pool.indexOf(dept) < 0) return false;
    }
    if (r.lng != null && r.lat != null) {
      r._dist = haversine(baseSafe.lng, baseSafe.lat, r.lng, r.lat);
    } else {
      r._dist = null;
    }
    return true;
  });

  // 计算评分：归一化
  let maxDept = 0, maxDist = 0;
  FILTERED.forEach(r => {
    if (r.dept_count) maxDept = Math.max(maxDept, r.dept_count);
    if (r._dist != null) maxDist = Math.max(maxDist, r._dist);
  });
  FILTERED.forEach(r => {
    const lv = (LEVEL_RANK[r.level] || 1) / 4;
    const ds = r._dist == null ? 0.5 : Math.max(0, 1 - r._dist / (maxDist || 1));
    const dp = (r.dept_count || 0) / (maxDept || 1);
    r._score = W_LEVEL*lv + W_DIST*ds + W_DEPT*dp;
  });

  // 排序
  const cmp = {
    score:    (a,b) => b._score - a._score,
    distance: (a,b) => (a._dist==null?9e9:a._dist) - (b._dist==null?9e9:b._dist),
    level:    (a,b) => (LEVEL_RANK[b.level]||0) - (LEVEL_RANK[a.level]||0),
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
  // 只保留有重点科室数据的显示：L1 重点专科 / L2 优势科室；L3 诊疗科室多为规则推导，不在列表卡片展示
  if (lv === '3') return '';
  const show = depts.slice(0, 6).join(' / ') + (depts.length > 6 ? ` 等${depts.length}项` : '');
  const lab = FEAT_LABEL[lv] || '擅长';
  return `<div class="feat" title="${depts.join(' / ')}"><span class="fk f${lv}">${lab}</span><span class="ft">${show}</span></div>`;
}
// 医疗协作网络徽章（资源整合维度）：儿科医联体 / 卒中中心 / 危重新生儿救治 / 危重孕产妇救治
function netLine(r) {
  const t = [];
  if (r.net_pediatric === '核心') t.push(['儿科医联体·核心', '#ff6b6b']);
  else if (r.net_pediatric === '成员') t.push(['儿科医联体·成员', '#f7b955']);
  if (r.net_stroke === '1') t.push(['卒中中心', '#5fd3c0']);
  if (r.net_neonatal === '市级') t.push(['新生儿救治·市级', '#a78bfa']);
  if (r.net_maternal === '市级') t.push(['孕产妇救治·市级', '#f0a3c8']);
  if (!t.length) return '';
  return '<div class="netline">' + t.map(([n, c]) =>
    `<span style="display:inline-block;margin:3px 5px 0 0;padding:1px 7px;border:1px solid ${c}66;border-radius:10px;color:${c};font-size:10px;background:${c}18">${n}</span>`
  ).join('') + '</div>';
}
function netDetail(r) {
  const n = [];
  if (r.net_pediatric === '核心') n.push('儿科医联体·核心医院');
  else if (r.net_pediatric === '成员') n.push('儿科医联体·成员机构');
  if (r.net_stroke === '1') n.push('卒中中心');
  if (r.net_neonatal === '市级') n.push('危重新生儿救治中心（市级）');
  if (r.net_maternal === '市级') n.push('危重孕产妇救治中心（市级）');
  return n.length ? n.join('、') : '<span style="color:#8aa1c8">未纳入</span>';
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
        ${netLine(r)}
      </div>
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
        min:0, max:1300, type:'continuous',
        // 色阶条隐藏：仅用 inRange 给地图区县配色；显示用底部 HTML 图例(.maplg)
        show:false,
        orient:'vertical', left:'left', top:'bottom',
        inRange:{color:['#0b1530','#1f3a68','#3aa0ff','#5fd3c0']},
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
    <div><div class="l">协作网络</div><div class="v">${netDetail(r)}</div></div>
    <div><div class="l">办 别</div><div class="v">${ownBadge(r.ownership) || (r.ownership || '未标注')}${r.ownership_basis ? ` <span style="color:#8aa1c8;font-size:10px">依据 ${r.ownership_basis}</span>` : ''}</div></div>
    <div><div class="l">科 室 数</div><div class="v">${r.dept_count || 0}</div></div>
    <div><div class="l">重点专科数</div><div class="v">${r.key_specialty_count || 0}</div></div>
    <div><div class="l">国家重点专科</div><div class="v">${r.national_specialty_count ? `<span style="color:#f0c674;font-weight:600">${r.national_specialty_count} 个</span> <span style="color:#8aa1c8;font-size:10px">（国家级）</span>` : '<span style="color:#8aa1c8">—</span>'}</div></div>
    <div><div class="l">市级重点专科</div><div class="v">${r.municipal_specialty_count ? `<span style="color:#81c784;font-weight:600">${r.municipal_specialty_count} 项</span> <span style="color:#8aa1c8;font-size:10px">（北京市级）</span>${r.municipal_specialty ? ` <span title="${r.municipal_specialty.replace(/;/g,'、')}" style="color:#8aa1c8;font-size:10px;cursor:help">［清单］</span>` : ''}` : '<span style="color:#8aa1c8">—</span>'}</div></div>
    <div><div class="l">坐 标 精 度</div><div class="v">${r.coord_precision || '—'}</div></div>
    <div><div class="l">综 合 评 分</div><div class="v" style="color:#f7b955">${(r._score||0).toFixed(3)}</div></div>
  `;
  // 擅长科室：只保留有重点科室数据的显示（L1 重点专科 / L2 优势科室）；L3 诊疗科室多为规则推导，不在详情展示
  const featDepts = r.feature ? r.feature.split(/[;；]/).map(x => x.trim()).filter(x => x) : [];
  const keyDepts = r.key_depts ? r.key_depts.split(/[,,、;\s]+/).filter(x => x) : [];
  const lv = r.feature_level;
  if (featDepts.length && lv !== '3') {
    const lvColor = lv === '1' ? '#ff6b6b' : '#f7b955';
    const lvBg = lv === '1' ? '#ff6b6b22' : '#f7b95522';
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
