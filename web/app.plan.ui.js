// ============================================================================
//  就医决策工作台 —— 单文件形态的界面层
// ----------------------------------------------------------------------------
//  依赖（都在同一个 HTML 里，无需任何网络请求）：
//    window.__SNAPSHOT__   9,789 家机构快照（含坐标 / 等级 / 办别 / 科室数）
//    window.__PLAN_DATA__  主线数据包（科室实力指数 + 症状知识库 + 后端常量）
//    PlanEngine            app.plan.js 的离线复算引擎
//
//  设计要点：
//    · 有任务态：步骤 1→4 可回退、可重来，不是「点一下换个图」的看板。
//    · 有产出物：方案可复制 / 下载 / 打印 / 留痕，用户带得走。
//    · 留痕落 localStorage，字段与后端 user_plan 表同构，换到在线形态口径一致。
// ============================================================================
(function () {
  'use strict';

  const KEY_SAVED = 'bj_hospital_plan_saved_v1';
  const KEY_BASE = 'bj_hospital_plan_base_v1';

  // 就诊前准备（与 Vue 版 PlanView 的 PREP 同文）
  const PREP = [
    '携带本人身份证与医保卡；儿童就诊建议带出生证明或户口本',
    '带上既往病历、检查报告与正在服用的药物清单',
    '需要空腹的项目（抽血、腹部超声）请提前 8 小时禁食',
    '建议提前线上预约挂号，避开周一与上午早高峰',
    '发热患者先测量并记录体温变化，到院后主动告知分诊台',
  ];

  // 快捷示例：覆盖几类典型口语表达（人群词、部位、动作、孕产）
  const EXAMPLES = ['孩子反复发烧咳嗽三天了', '老人最近总心慌胸闷', '骨折了该去哪家',
    '眼睛看不清', '孕检挂什么科', '牙疼得厉害', '腰酸背痛'];

  const MAXKM = [[0, '距离不限'], [3, '3 公里内'], [5, '5 公里内'],
    [10, '10 公里内'], [20, '20 公里内'], [50, '50 公里内']];

  const ST = {
    step: 1, result: null, picked: [], primaryId: null, base: null, savedId: null,
  };
  let ENGINE = null, SNAP = null, BASES = [];

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  // --------------------------------------------------------------------------
  //  启动
  // --------------------------------------------------------------------------
  function boot() {
    if (!$('view-workbench')) return;

    const payload = window.__PLAN_DATA__;
    const snap = window.__SNAPSHOT__;
    if (!payload || !snap) { showUnavailable(); return; }

    SNAP = snap;
    try {
      ENGINE = PlanEngine.create(payload, SNAP.institutions);
    } catch (e) {
      console.error('[workbench] 引擎初始化失败', e);
      showUnavailable(); return;
    }

    buildBasePoints();
    buildPrefs(payload.const);
    buildLimits(payload.const);
    buildExamples();
    bindAll();
    restoreBase();
    renderSaved();
    setStep(1, true);
  }

  function showUnavailable() {
    const host = $('wb_cands');
    if (host) {
      host.innerHTML = '<div class="wb-empty">当前页面未内嵌主线数据包（offline_plan_data.json），'
        + '工作台不可用。<br>请使用 dashboard_standalone.html / dashboard_offline.html，'
        + '或通过 Flask 启动后访问。</div>';
    }
  }

  // --------------------------------------------------------------------------
  //  选项构建
  // --------------------------------------------------------------------------
  function buildBasePoints() {
    BASES = [
      { name: '天安门（默认）', lng: 116.397428, lat: 39.90923 },
      { name: '首都机场', lng: 116.609, lat: 40.080 },
      { name: '大兴机场', lng: 116.411, lat: 39.510 },
    ];
    // 各区中心取自快照内嵌的行政区划（geoJson 的 centroid），离线也能算距离
    const feats = (SNAP.geojson && SNAP.geojson.features) || [];
    feats.forEach((f) => {
      const p = f.properties || {};
      const c = p.centroid || p.center;
      if (c && p.name) BASES.push({ name: p.name + '中心', lng: c[0], lat: c[1] });
    });
    const sel = $('wb_base');
    if (!sel) return;
    sel.innerHTML = BASES.map((b, i) =>
      `<option value="${i}">${esc(b.name)}</option>`).join('');
    sel.addEventListener('change', () => {
      ST.base = BASES[+sel.value] || BASES[0];
      persistBase();
      updateBaseHint();
    });
  }

  function buildPrefs(C) {
    const host = $('wb_prefs');
    const keys = ['specialty', 'distance', 'level', 'balanced'];
    const DESC = { specialty: '看科室有多强', distance: '离家近优先', level: '等级高优先', balanced: '各方面都不偏废' };
    host.innerHTML = keys.map((k, i) =>
      `<button type="button" class="wb-pref${i === 0 ? ' on' : ''}" data-pref="${k}">
         ${esc(C.PLAN_PREFER_LABEL[k] || k)}<i>${DESC[k]}</i>
       </button>`).join('');
    host.addEventListener('click', (e) => {
      const b = e.target.closest('.wb-pref');
      if (!b) return;
      host.querySelectorAll('.wb-pref').forEach((x) => x.classList.toggle('on', x === b));
    });
  }

  function buildLimits(C) {
    $('wb_district').innerHTML = '<option value="">行政区不限</option>'
      + C.BJ_DISTRICTS.map((d) => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
    $('wb_level').innerHTML = '<option value="">等级不限</option>'
      + ['三级', '二级', '一级', '未定级'].map((d) => `<option value="${d}">${d}</option>`).join('');
    $('wb_maxkm').innerHTML = MAXKM.map(([v, t]) => `<option value="${v}">${t}</option>`).join('');
  }

  function buildExamples() {
    const host = $('wb_examples');
    host.innerHTML = '<span class="qlab">试试：</span>' + EXAMPLES.map((x) =>
      `<button type="button" class="qb">${esc(x)}</button>`).join('');
    host.addEventListener('click', (e) => {
      const b = e.target.closest('.qb');
      if (!b) return;
      $('wb_q').value = b.textContent;
      runPlan();
    });
  }

  // --------------------------------------------------------------------------
  //  事件绑定
  // --------------------------------------------------------------------------
  function bindAll() {
    $('wb_run').addEventListener('click', runPlan);
    $('wb_q').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) runPlan();
    });
    $('wb_home').addEventListener('click', resetAll);
    $('wb_back1').addEventListener('click', () => setStep(1));
    $('wb_back2').addEventListener('click', () => setStep(2));
    $('wb_pick3').addEventListener('click', () => {
      ST.picked = ST.result.candidates.slice(0, 3).map((c) => c.id);
      renderCands();
    });
    $('wb_to_cmp').addEventListener('click', () => { if (ST.picked.length >= 2) setStep(3); });
    $('wb_to_plan').addEventListener('click', () => {
      if (!ST.primaryId && ST.result.candidates.length) ST.primaryId = ST.result.candidates[0].id;
      setStep(4);
    });
    $('wb_locate').addEventListener('click', useMyLocation);
    $('wb_copy').addEventListener('click', copyPlan);
    $('wb_download').addEventListener('click', downloadPlan);
    $('wb_print').addEventListener('click', () => window.print());
    $('wb_save').addEventListener('click', savePlan);
    $('wb_clear_mine').addEventListener('click', clearSaved);

    $('wb_steps').addEventListener('click', (e) => {
      const b = e.target.closest('.wb-step');
      if (!b || b.disabled) return;
      setStep(+b.getAttribute('data-step'));
    });

    // 候选卡：加入对比 / 查看详情（委托）
    $('wb_cands').addEventListener('click', (e) => {
      const keep = e.target.closest('[data-act="keep"]');
      const more = e.target.closest('[data-act="more"]');
      if (keep) {
        togglePick(keep.getAttribute('data-id'));
      } else if (more) {
        const c = findCand(more.getAttribute('data-id'));
        if (c && typeof window.openDrawer === 'function') window.openDrawer(c.id);
      }
    });

    // 对比表：设为主选（委托）
    $('wb_cmp').addEventListener('click', (e) => {
      const b = e.target.closest('[data-act="primary"]');
      if (!b) return;
      ST.primaryId = b.getAttribute('data-id');
      renderCmp();
      renderCands();
    });

    // 我的方案（委托）
    $('wb_mine_list').addEventListener('click', (e) => {
      const del = e.target.closest('[data-act="del"]');
      const open = e.target.closest('[data-act="open"]');
      if (del) { removeSaved(del.getAttribute('data-id')); }
      else if (open) { openSaved(open.getAttribute('data-id')); }
    });
  }

  function findCand(id) {
    return ST.result && ST.result.candidates.find((c) => String(c.id) === String(id));
  }

  // --------------------------------------------------------------------------
  //  位置基准
  // --------------------------------------------------------------------------
  function restoreBase() {
    try {
      const b = JSON.parse(localStorage.getItem(KEY_BASE) || 'null');
      if (b && b.lng != null && b.lat != null) {
        const i = BASES.findIndex((x) => x.name === b.name);
        if (i >= 0) { $('wb_base').value = String(i); ST.base = BASES[i]; }
        else { BASES.push(b); $('wb_base').innerHTML += `<option value="${BASES.length - 1}">${esc(b.name)}</option>`; $('wb_base').value = String(BASES.length - 1); ST.base = b; }
      } else { ST.base = BASES[0]; }
    } catch (e) { ST.base = BASES[0]; }
    updateBaseHint();
  }

  function persistBase() {
    try {
      localStorage.setItem(KEY_BASE, JSON.stringify({ name: ST.base.name, lng: ST.base.lng, lat: ST.base.lat }));
    } catch (e) { /* 隐私模式下写不了，忽略 */ }
  }

  function updateBaseHint() {
    const el = $('wb_basehint');
    if (!ST.base || ST.base.lng == null) {
      el.textContent = '未设基准点时距离项权重会并入实力与等级，不影响排序可比性';
    } else {
      el.textContent = `已选：${ST.base.name} · 距离按两地直线距离计算`;
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) { toast('当前浏览器不支持定位'); return; }
    toast('正在定位…', 1600);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const b = { name: '我的位置', lng: pos.coords.longitude, lat: pos.coords.latitude };
        BASES.push(b);
        $('wb_base').innerHTML += `<option value="${BASES.length - 1}">我的位置</option>`;
        $('wb_base').value = String(BASES.length - 1);
        ST.base = b; persistBase(); updateBaseHint();
        toast('已设为「我的位置」，重新生成即可按距离排序');
      },
      () => toast('定位被拒绝或不可用（file:// 打开时浏览器通常不允许定位）'),
      { timeout: 8000 }
    );
  }

  // --------------------------------------------------------------------------
  //  步骤
  // --------------------------------------------------------------------------
  function setStep(n, silent) {
    const max = ST.result ? 4 : 1;
    ST.step = Math.min(n, max);
    $('wb_steps').querySelectorAll('.wb-step').forEach((b) => {
      const s = +b.getAttribute('data-step');
      b.classList.toggle('on', s === ST.step);
      b.classList.toggle('done', s < ST.step);
      b.disabled = s > max;
    });
    document.querySelectorAll('#view-workbench .wb-pane').forEach((p) => {
      p.classList.toggle('on', +p.getAttribute('data-pane') === ST.step);
    });
    $('wb_home').disabled = !(ST.result || ST.picked.length || ST.primaryId);

    if (ST.step === 2) renderTriage();
    if (ST.step === 2 || ST.step === 3) renderCands();
    if (ST.step === 3) renderCmp();
    if (ST.step === 4) renderPlan();
    if (!silent) {
      const el = document.querySelector('#view-workbench .wb-pane.on');
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
  }

  function resetAll() {
    ST.step = 1; ST.result = null; ST.picked = []; ST.primaryId = null; ST.savedId = null;
    $('wb_q').value = '';
    $('wb_district').value = ''; $('wb_level').value = ''; $('wb_maxkm').value = '0';
    $('wb_public').checked = false;
    const prefs = $('wb_prefs');
    prefs.querySelectorAll('.wb-pref').forEach((x, i) => x.classList.toggle('on', i === 0));
    // 清空上一步的渲染结果：只切 pane 的话 DOM 还留着（看不见但确实在），
    // 「重新开始」应当真的是干净的起始页，而不是把旧结果藏起来。
    $('wb_triage').innerHTML = '';
    $('wb_cands').innerHTML = '';
    $('wb_cmp').innerHTML = '';
    $('wb_plancard').innerHTML = '';
    $('wb_cand_tag').textContent = '—';
    $('wb_cmp_tag').textContent = '—';
    $('wb_to_cmp').disabled = true;
    $('wb_to_cmp').textContent = '下一步 · 对比选中的 0 家';
    $('wb_to_plan').disabled = true;
    setStep(1);
    toast('已回到起始页');
  }

  // --------------------------------------------------------------------------
  //  跑一次决策
  // --------------------------------------------------------------------------
  function runPlan() {
    const q = ($('wb_q').value || '').trim();
    if (!q) { toast('先说说哪里不舒服，或直接点下面的示例'); $('wb_q').focus(); return; }

    const preferEl = $('wb_prefs').querySelector('.wb-pref.on');
    const payload = {
      q: q,
      prefer: preferEl ? preferEl.getAttribute('data-pref') : 'specialty',
      district: $('wb_district').value || '',
      level: $('wb_level').value || '',
      max_km: +$('wb_maxkm').value || 0,
      public_only: $('wb_public').checked,
      top_n: 8,
    };
    if (ST.base && ST.base.lng != null) {
      payload.lng = ST.base.lng; payload.lat = ST.base.lat; payload.base_name = ST.base.name;
    }

    let res;
    try {
      res = ENGINE.run(payload);
    } catch (e) {
      console.error('[workbench] 复算失败', e);
      toast('计算失败：' + e.message);
      return;
    }
    if (!res.ok) {
      toast(res.hint || '没能生成方案');
      if (res.examples) $('wb_q').placeholder = '试试：' + res.examples.join(' / ');
      return;
    }

    ST.result = res;
    ST.picked = res.candidates.slice(0, 3).map((c) => c.id);   // 默认预选前 3 家
    ST.primaryId = res.candidates.length ? res.candidates[0].id : null;
    ST.savedId = null;
    setStep(2);
    toast(`已判断应就诊「${res.triage.target_depts.map((d) => d.name).join('、')}」，`
      + `共 ${res.stats.candidate_total} 家机构匹配`);
  }

  // --------------------------------------------------------------------------
  //  渲染：分诊结论
  // --------------------------------------------------------------------------
  function renderTriage() {
    const r = ST.result;
    const t = r.triage;
    const pills = t.target_depts.map((d) =>
      `<span class="wb-pill${d.is_emergency ? ' emg' : ''}">${esc(d.name)}`
      + `<small>权重 ${d.weight}</small></span>`).join('');

    const rows = [];
    rows.push(`<div class="wb-trirow"><span class="k">判断依据</span>`
      + `<span>命中「${t.target_depts.map((d) => esc(d.matched_by)).join('」「')}」</span></div>`);
    rows.push(`<div class="wb-trirow"><span class="k">需求原文</span><span>${esc(r.input.q)}</span></div>`);
    if (t.corrected_district) {
      rows.push(`<div class="wb-trirow"><span class="k">已纠正</span>`
        + `<span>「${esc(t.corrected_district.from)}」按「${esc(t.corrected_district.to)}」检索</span></div>`);
    }
    rows.push(`<div class="wb-trirow"><span class="k">排序偏好</span>`
      + `<span>${esc(r.input.prefer_label)}（科室实力 ${r.input.weights.strength} · 距离 ${r.input.weights.dist}`
      + ` · 等级 ${r.input.weights.level} · 协作网络 ${r.input.weights.net} · 科室契合 ${r.input.weights.dept}）</span></div>`);
    if (r.input.base_name) {
      rows.push(`<div class="wb-trirow"><span class="k">位置基准</span><span>${esc(r.input.base_name)}</span></div>`);
    }
    if (t.emergency) {
      rows.push(`<div class="wb-trirow"><span class="k" style="color:var(--crit)">急症提示</span>`
        + `<span style="color:var(--crit)">本次判断涉及急诊科，若症状急重请直接拨打 120 或前往最近医院急诊</span></div>`);
    }

    $('wb_triage').innerHTML = `
      <h3>分诊结论 <span class="tag">该挂哪个科</span></h3>
      <div class="wb-tri">
        <div style="flex:1;min-width:260px">
          <div class="wb-tridept">${pills}</div>
          ${rows.join('')}
        </div>
      </div>`;
  }

  // --------------------------------------------------------------------------
  //  渲染：候选机构
  // --------------------------------------------------------------------------
  function candHTML(c, i) {
    const picked = ST.picked.some((x) => String(x) === String(c.id));
    const isPrimary = String(ST.primaryId) === String(c.id);
    const cls = 'wb-cand' + (picked ? ' picked' : '') + (isPrimary ? ' primary' : '');
    const dist = c.distance_km != null
      ? `<span class="badge b-l0">${c.distance_km} km</span>` : '';
    const alias = c.alias_count
      ? `<span class="badge b-l0">另有 ${c.alias_count} 个院区/别名</span>` : '';
    const matched = c.matched_depts.length > 1
      ? `<span class="wb-mtags">同时命中：${c.matched_depts.map(esc).join('、')}</span>` : '';

    return `
      <div class="${cls}">
        <div class="wb-chd">
          <div class="wb-rank">${i + 1}</div>
          <div style="flex:1;min-width:0">
            <div class="wb-cname">${esc(c.name)}</div>
            <div class="wb-cmeta">
              ${window.levelBadge ? window.levelBadge(c.level_norm) : ''}
              ${window.ownBadge ? window.ownBadge(c.ownership) : ''}
              <span class="badge b-l0">${esc(c.district || '区未标注')}</span>
              <span class="badge b-l0">${esc(c.tier_label)} · ${c.strength} 分</span>
              ${dist}${alias}
            </div>
            ${matched}
          </div>
          <div class="wb-acts">
            <button class="btn sm${picked ? ' pri' : ''}" type="button" data-act="keep" data-id="${esc(c.id)}">
              ${picked ? '✓ 已选' : '加入对比'}
            </button>
            <button class="btn sm" type="button" data-act="more" data-id="${esc(c.id)}">详情</button>
          </div>
        </div>
        <div class="wb-score">
          <span class="wb-hint">匹配度</span>
          <div class="wb-bar"><i style="width:${Math.round(c.match_score * 100)}%"></i></div>
          <b>${c.match_score.toFixed(3)}</b>
        </div>
        <div class="wb-why">${c.reasons.map((x) => `<span>${esc(x)}</span>`).join('')}</div>
      </div>`;
  }

  function renderCands() {
    const r = ST.result;
    if (!r) return;
    $('wb_cand_tag').textContent = `返回 ${r.candidates.length} 家 · 共 ${r.stats.candidate_total} 家匹配`;
    $('wb_cands').innerHTML = r.candidates.map(candHTML).join('');
    $('wb_to_cmp').disabled = ST.picked.length < 2;
    $('wb_to_cmp').textContent = `下一步 · 对比选中的 ${ST.picked.length} 家`;
  }

  function togglePick(id) {
    const i = ST.picked.findIndex((x) => String(x) === String(id));
    if (i >= 0) ST.picked.splice(i, 1);
    else {
      if (ST.picked.length >= 4) { toast('最多同时对比 4 家'); return; }
      ST.picked.push(id);
    }
    renderCands();
  }

  // --------------------------------------------------------------------------
  //  渲染：横向对比
  // --------------------------------------------------------------------------
  const CMP_ROWS = [
    ['应就诊科室', (c) => esc(c.dept_name)],
    ['专科实力', (c) => `${esc(c.tier_label)}<span class="rs">${c.strength} 分</span>`],
    ['机构等级', (c) => esc(c.level_norm || '—')],
    ['办别', (c) => esc(c.ownership || '未标注')],
    ['所在区', (c) => esc(c.district || '—')],
    ['距离', (c) => (c.distance_km != null ? c.distance_km + ' km' : '—')],
    ['协作网络', (c) => (c.is_network ? '成员' : '—')],
    ['开设科室数', (c) => (c.dept_count != null ? c.dept_count : '—')],
    ['匹配度', (c) => `<b>${c.match_score.toFixed(3)}</b>`
      + `<span class="wb-bar" style="margin-top:5px;display:block"><i style="width:${Math.round(c.match_score * 100)}%"></i></span>`],
    ['推荐依据', (c) => c.reasons.map((x) => `<span class="rs">${esc(x)}</span>`).join('')],
    ['地址', (c) => esc(c.addr || '—')],
  ];

  function renderCmp() {
    const kept = ST.picked.map(findCand).filter(Boolean);
    $('wb_cmp_tag').textContent = `${kept.length} 家在比`;
    if (!kept.length) {
      $('wb_cmp').innerHTML = '<div class="wb-empty">还没有勾选机构，回到上一步勾选 2–4 家后再来对比。</div>';
      $('wb_to_plan').disabled = true;
      return;
    }
    const head = kept.map((c) => {
      const on = String(ST.primaryId) === String(c.id);
      return `<th>
        <div class="cmpname">${esc(c.name)}</div>
        <button class="btn sm${on ? ' pri' : ''}" type="button" data-act="primary" data-id="${esc(c.id)}">
          ${on ? '★ 主选' : '设为主选'}
        </button></th>`;
    }).join('');
    const body = CMP_ROWS.map(([label, fn]) =>
      `<tr><td class="ro">${label}</td>${kept.map((c) => `<td>${fn(c)}</td>`).join('')}</tr>`).join('');
    $('wb_cmp').innerHTML = `<table class="wb-cmp"><thead><tr><th class="ro">对比项</th>${head}</tr></thead>
      <tbody>${body}</tbody></table>`;
    $('wb_to_plan').disabled = kept.length < 1;
  }

  // --------------------------------------------------------------------------
  //  渲染：方案卡
  // --------------------------------------------------------------------------
  function primary() { return findCand(ST.primaryId); }

  function renderPlan() {
    const r = ST.result, p = primary();
    if (!r || !p) { $('wb_plancard').innerHTML = '<div class="wb-empty">还没有选定主选机构。</div>'; return; }
    const kept = ST.picked.map(findCand).filter(Boolean);
    const alts = (kept.length ? kept : r.candidates).filter((c) => String(c.id) !== String(p.id)).slice(0, 3);

    $('wb_plancard').innerHTML = `
      <div class="wb-ph">
        <div style="min-width:0">
          <div class="wb-ptitle">${esc(p.name)}</div>
          <div class="wb-pmeta">${esc(p.dept_name)} · ${esc(p.level_norm || '等级未标注')} · ${esc(p.ownership || '办别未标注')}</div>
        </div>
        <div class="wb-ptag">${esc(p.tier_label)}</div>
      </div>
      <div class="wb-ps">
        <div class="wb-prow"><label>地址</label><div>${esc(p.addr || '—')}</div></div>
        <div class="wb-prow"><label>电话</label><div>${esc(p.phone || '—')}</div></div>
        <div class="wb-prow"><label>距离</label><div>${
          p.distance_km != null ? p.distance_km + ' 公里（距' + esc(r.input.base_name || '基准点') + '）'
            : '未设置位置基准，无法计算'}</div></div>
        <div class="wb-prow"><label>需求</label><div>${esc(r.input.q)}</div></div>
      </div>
      <div class="wb-psec">
        <h5>为什么推荐这家</h5>
        <ul>${p.reasons.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
      </div>
      ${alts.length ? `<div class="wb-psec">
        <h5>备选机构（${alts.length}）</h5>
        ${alts.map((c, i) => `<div class="wb-alt"><b>${i + 2}. ${esc(c.name)}</b>
          <span class="rs" style="display:inline">${esc(c.dept_name)}</span>
          <span class="d">${c.distance_km != null ? c.distance_km + ' km' : '—'}</span></div>`).join('')}
      </div>` : ''}
      <div class="wb-psec">
        <h5>就诊前准备</h5>
        <ul>${PREP.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
      </div>
      <div class="wb-psec">
        <h5>预约挂号</h5>
        <ul>
          <li>北京市预约挂号统一平台：<a href="https://www.114yygh.com/" target="_blank" rel="noopener">www.114yygh.com</a>（电话 114）</li>
          <li>也可通过该院官方微信公众号 / 京医通等渠道预约</li>
        </ul>
      </div>
      <div class="wb-pft">
        生成时间：${esc(r.generated_at)} · 由系统基于公开数据本地生成，仅作就诊决策参考，不构成诊断意见；急危重症请直接拨打 120。
      </div>`;

    $('wb_save').textContent = ST.savedId ? '已保存到我的方案' : '保存到我的方案';
    $('wb_save').disabled = !!ST.savedId;
  }

  function planText() {
    const r = ST.result, p = primary();
    if (!r || !p) return '';
    const kept = ST.picked.map(findCand).filter(Boolean);
    const alts = (kept.length ? kept : r.candidates).filter((c) => String(c.id) !== String(p.id)).slice(0, 3);
    const L = [];
    L.push('《就医决策方案》');
    L.push('生成时间：' + r.generated_at);
    L.push('需求描述：' + (r.input.q || r.input.forced_dept || ''));
    if (r.input.base_name) L.push('位置基准：' + r.input.base_name);
    L.push('');
    L.push('【推荐就诊】');
    L.push(p.name + ' · ' + p.dept_name);
    L.push('地址：' + (p.addr || '—'));
    L.push('电话：' + (p.phone || '—'));
    if (p.distance_km != null) L.push('距离：' + p.distance_km + ' 公里');
    L.push('');
    L.push('【推荐依据】');
    p.reasons.forEach((x) => L.push('· ' + x));
    if (alts.length) {
      L.push('');
      L.push('【备选机构】');
      alts.forEach((c, i) => L.push((i + 2) + '. ' + c.name + ' · ' + c.dept_name
        + (c.distance_km != null ? '（' + c.distance_km + ' km）' : '')));
    }
    L.push('');
    L.push('【就诊前准备】');
    PREP.forEach((x) => L.push('· ' + x));
    L.push('');
    L.push('【预约挂号】');
    L.push('北京市预约挂号统一平台：https://www.114yygh.com/');
    L.push('');
    L.push('（本方案由系统基于公开数据生成，仅作就诊决策参考，不构成诊断意见；急危重症请直接拨打 120）');
    return L.join('\n');
  }

  function copyPlan() {
    const t = planText();
    if (!t) return;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(t).then(() => toast('方案已复制到剪贴板'), () => toast('复制失败，可改用「下载」'));
    } else { toast('当前环境不支持剪贴板，可改用「下载」'); }
  }

  function downloadPlan() {
    const t = planText();
    if (!t) return;
    const p = primary();
    const safe = (p ? p.name : '就医方案').replace(/[\\/:*?"<>|]/g, '_');
    const blob = new Blob([t], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `就医决策方案-${safe}.txt`;
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
    toast('方案已下载为文本文件');
  }

  // --------------------------------------------------------------------------
  //  我的方案（localStorage 留痕，字段与后端 user_plan 表同构）
  // --------------------------------------------------------------------------
  function loadSaved() {
    try { return JSON.parse(localStorage.getItem(KEY_SAVED) || '[]'); } catch (e) { return []; }
  }
  function writeSaved(list) {
    try { localStorage.setItem(KEY_SAVED, JSON.stringify(list.slice(0, 30))); }
    catch (e) { toast('本地存储不可用，方案未能保存'); }
  }

  function savePlan() {
    const r = ST.result, p = primary();
    if (!r || !p) { toast('先生成方案'); return; }
    const kept = ST.picked.map(findCand).filter(Boolean);
    const t = r.input.q || r.input.forced_dept;
    const rec = {
      id: 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
      created_at: r.generated_at,
      title: t + ' · ' + p.dept_name,
      query_text: t,
      depts: r.triage.target_depts.map((d) => d.name).join(','),
      chosen_id: String(p.id),
      chosen_name: p.name,
      candidate_cnt: r.stats.candidate_total,
      payload: {
        input: r.input, triage: r.triage, primary: p,
        alternatives: (kept.length ? kept : r.candidates).filter((c) => String(c.id) !== String(p.id)).slice(0, 3),
        prep: PREP,
      },
    };
    const list = loadSaved();
    list.unshift(rec);
    writeSaved(list);
    ST.savedId = rec.id;
    $('wb_save').textContent = '已保存到我的方案';
    $('wb_save').disabled = true;
    renderSaved();
    toast('已保存到「我的方案」，下次打开还能调出来');
  }

  function renderSaved() {
    const list = loadSaved();
    const host = $('wb_mine');
    if (!host) return;
    host.style.display = list.length ? '' : 'none';
    if (!list.length) return;
    $('wb_mine_list').innerHTML = list.map((r) => `
      <div class="wb-mi">
        <span class="t" title="${esc(r.title)}">${esc(r.title)}</span>
        <span class="m">${esc((r.created_at || '').slice(0, 16))}</span>
        <button class="btn sm" type="button" data-act="open" data-id="${esc(r.id)}">打开</button>
        <button class="btn sm" type="button" data-act="del" data-id="${esc(r.id)}">删除</button>
      </div>`).join('');
  }

  function removeSaved(id) {
    writeSaved(loadSaved().filter((r) => r.id !== id));
    renderSaved();
    toast('已删除该方案');
  }

  function clearSaved() {
    writeSaved([]);
    renderSaved();
    toast('已清空本地方案记录');
  }

  function openSaved(id) {
    const rec = loadSaved().find((r) => r.id === id);
    if (!rec) return;
    const pl = rec.payload || {};
    // 还原成与实时计算相同的结构，后续步骤（对比 / 方案）复用同一套渲染
    ST.result = {
      ok: true,
      generated_at: rec.created_at,
      input: pl.input || { q: rec.query_text },
      triage: pl.triage || { target_depts: [], emergency: false },
      stats: { candidate_total: rec.candidate_cnt, returned: 1 + (pl.alternatives || []).length },
      candidates: [pl.primary].concat(pl.alternatives || []).filter(Boolean),
    };
    ST.picked = ST.result.candidates.map((c) => c.id);
    ST.primaryId = pl.primary ? pl.primary.id : null;
    ST.savedId = rec.id;
    $('wb_q').value = rec.query_text || '';
    $('wb_triage').innerHTML = '';
    setStep(4);
    toast('已打开保存的方案');
  }

  // --------------------------------------------------------------------------
  //  与主壳衔接：navtab 点击切到工作台时，若还没结果就停在步骤 1
  // --------------------------------------------------------------------------
  function hookNav() {
    const btn = $('nav_workbench');
    if (!btn) return;
    btn.addEventListener('click', () => { if (!ST.result) setStep(1, true); });
  }

  function start() {
    hookNav();
    boot();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
