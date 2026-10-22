/* User-facing workflows; all data work stays local to the existing snapshot. */
(function (root) {
  'use strict';
  const STORAGE_KEY = 'bjyy_saved_searches_v2';
  const FIELDS = ['kw','district','level','cat','dept','net','level_sub','evidence','radius'];
  const VIEWS = {
    institutions: ['查询与筛选','机构查询','组合条件查找机构，查看来源，收藏并对比。'],
    filter: ['智能助手','智能问答','用一句话查找机构，了解区域分布与科室资源。'],
    overview: ['资源分析','数据总览','了解北京市医疗机构的规模、分布与资源结构。'],
    analytics: ['资源分析','医疗资源分析','查看当前筛选范围内的资源结构，点击图表继续查阅。'],
    integration: ['数据治理','数据整合','查看公开数据来源、处理流程与更新批次。'],
    quality: ['数据治理','数据质量','核对完整率、坐标精度与当前批次统计口径。'],
    doctors: ['查询与筛选','找医生','按医院、科室、姓名和行政区查找已收录的医生资料。'],
    help: ['系统信息','使用帮助','快速上手、操作方法与常见问题。'],
    about: ['系统信息','系统说明','了解数据边界、使用方式与系统实现。']
  };
  let initialized = false, saved = [], pendingUndo = null, restoringURL = false, helpPreviousView = 'institutions';
  const layers = [];
  const byId = id => document.getElementById(id);
  function csvCell(value) {
    let text = String(value == null ? '' : value);
    if (/^[\s]*[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }
  function buildCSV(rows, snapshotDate) {
    const header = ['机构名称','行政区','等级','等级等次','机构类型','办别','地址','电话','坐标精度','有来源记录的科室','快照日期'];
    return '\uFEFF' + [header, ...rows.map(r => [r.name,r.district,r.level,r.level_sub,r.category,r.ownership,r.addr,r.phone,
      ({high:'高精度',rough:'粗精度',missing:'缺失'})[r.coord_precision] || '未收录',r.recorded_depts,snapshotDate])]
      .map(row => row.map(csvCell).join(',')).join('\r\n');
  }
  function normalizeSaved(value) {
    if (!Array.isArray(value)) return [];
    return value.filter(x => x && typeof x.id === 'string' && typeof x.title === 'string' && x.state && typeof x.state === 'object')
      .slice(0, 8).map(x => ({id:x.id.slice(0,80),title:x.title.slice(0,32),state:x.state}));
  }
  function request(url, options, timeout) {
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),timeout||12000);
    return root.fetch(url,{...(options||{}),signal:controller.signal}).finally(()=>clearTimeout(timer));
  }
  function clipboard(text, label) {
    const fallback = () => {
      const box = byId('ux_copy_text'); box.value = text;
      byId('copywrap').classList.add('show'); openLayer('copywrap', 'ux_copy_text');
      box.focus(); box.select();
      byId('ux_copy_title').textContent = label + ' · 手动复制';
    };
    if (navigator.clipboard && root.isSecureContext) {
      return navigator.clipboard.writeText(text).then(() => toast(svgIcon('ok') + ' 已复制' + esc(label)), fallback);
    }
    fallback(); return Promise.resolve();
  }
  function capture() {
    const state = {};
    FIELDS.forEach(k => { const e=byId('f_'+k); if(e && e.value) state[k]=e.value; });
    state.sort=curSort(); state.dir=curDir();
    if (BASE_NOW) state.base = { name:BASE_NOW.name, lng:BASE_NOW.lng, lat:BASE_NOW.lat };
    if (LOOKUP_SCOPE) {state.scope = LOOKUP_SCOPE.conditions;state.scope_base=LOOKUP_SCOPE.base;}
    return state;
  }
  function restore(state) {
    state = state || {};
    clearConditionsSilent();
    FIELDS.forEach(k => { const e=byId('f_'+k); if(e) e.value=typeof state[k] === 'string' ? state[k] : ''; });
    if (state.base && Number.isFinite(state.base.lng) && Number.isFinite(state.base.lat)
        && Math.abs(state.base.lng)<=180 && Math.abs(state.base.lat)<=90) setBase(state.base, true);
    else { BASE_NOW=null; byId('f_base').value=''; }
    const allowed = ['score','distance','level','depts','name'];
    setSort(allowed.includes(state.sort) ? state.sort : 'score', state.dir==='asc' ? 'asc' : 'desc', true);
    if (state.scope) setLookupScope(state.scope,state.scope_base);
    PAGE=1; refreshBaseSummary(); applyFilter(); switchView('institutions');
  }
  function persistSaved() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(saved)); return true; }
    catch (_) { toast('浏览器未能保存方案，本次会话仍可使用。'); return false; }
  }
  function renderSaved() {
    const host=byId('ux_saved_list'); if(!host) return;
    host.innerHTML=saved.length ? saved.map(s=>'<div class="saved-item"><button type="button" data-load-search="'+esc(s.id)+'">'+svgIcon('folder')+esc(s.title)+'</button><button class="saved-remove" type="button" data-remove-search="'+esc(s.id)+'" aria-label="删除筛选方案 '+esc(s.title)+'">×</button></div>').join('')
      : '<p class="quiet">还没有保存方案。设置条件后，可将常用组合保存在当前浏览器。</p>';
    byId('ux_saved_count').textContent=saved.length;
  }
  function saveSearch() {
    const title=byId('ux_save_name').value.trim().slice(0,32);
    if(!title){byId('ux_save_error').textContent='请为这组条件起一个名称。';byId('ux_save_name').focus();return;}
    const state=capture();
    if(saved.length>=8){byId('ux_save_error').textContent='最多保存 8 个方案，请先删除不用的方案。';return;}
    saved.unshift({id:Date.now().toString(36)+Math.random().toString(36).slice(2,7),title,state});
    persistSaved(); renderSaved(); byId('ux_save_form').hidden=true;
    byId('ux_save_toggle').setAttribute('aria-expanded','false');
    toast('已保存「'+esc(title)+'」。方案仅保存在当前浏览器。');
  }
  function exportResults() {
    if (LOOKUP_ERROR) { toast('请先修正筛选条件，再导出结果。');return; }
    if(!FILTERED.length){toast('当前没有可导出的机构，请调整筛选条件。');return;}
    const blob = new Blob([buildCSV(FILTERED, DATA.snapshot_time)],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=url;a.download='北京医疗机构-'+DATA.snapshot_time+'-'+FILTERED.length+'家.csv';a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast('已导出当前 '+num(FILTERED.length)+' 家机构。文件含快照日期和来源科室口径。');
  }
  function copyConditions() {
    const c=readLookupConditions(), parts=QueryAudit.fields.filter(f=>c[f[0]]!==''&&c[f[0]]!=null)
      .map(f=>f[1]+'：'+(f[0]==='dept_evidence'?'仅有来源记录':c[f[0]]));
    if(LOOKUP_SCOPE) parts.unshift('智能筛选范围：'+NLQ.describe(LOOKUP_SCOPE.conditions).map(x=>x.label+'='+x.text).join('；'));
    const text='北京市医疗机构筛选条件\n'+(parts.join('\n')||'全部机构')+'\n距离参考点：'+curBase().name+
      '\n匹配：'+FILTERED.length+' 家\n数据快照：'+DATA.snapshot_time+'\n距离为直线距离，来源科室记录不等于实时在营确认。';
    clipboard(text,'筛选条件');
  }
  function openLayer(id, initial) {
    const element=byId(id);if(!element)return;
    const existing=layers.findIndex(x=>x.id===id);
    const returnFocus=existing>=0?layers[existing].returnFocus:document.activeElement;
    if(existing>=0) layers.splice(existing,1);
    layers.push({id,returnFocus});
    element.setAttribute('aria-hidden','false');
    document.body.classList.add('ux-modal-open');
    // Only the top dialog is accessible; the background stays inert until all close.
    document.querySelectorAll('.maincol > :not(.cmpwrap), .sidebar, .fab, .ux-mobile-nav, .ux-nav-backdrop').forEach(e=>e.inert=true);
    layers.slice(0,-1).forEach(layer=>{byId(layer.id).inert=true;});element.inert=false;
    const target=initial && byId(initial) || element.querySelector('button, input, textarea, [tabindex="0"]');
    if(target) target.focus({preventScroll:true});
  }
  function closeLayer(id) {
    const index=layers.findIndex(x=>x.id===id);if(index<0)return;
    const layer=layers.splice(index,1)[0];const el=byId(id);
    el.setAttribute('aria-hidden','true');el.inert=true;
    const top=layers[layers.length-1];
    if(top) byId(top.id).inert=false;
    else {
      document.body.classList.remove('ux-modal-open');
      document.querySelectorAll('.maincol > :not(.cmpwrap), .sidebar, .fab, .ux-mobile-nav, .ux-nav-backdrop').forEach(e=>e.inert=false);
      byId('sidebar').inert=root.matchMedia('(max-width: 700px)').matches&&!document.body.classList.contains('ux-nav-open');
    }
    if(layer.returnFocus && layer.returnFocus.isConnected && !layer.returnFocus.closest('[aria-hidden="true"]')) layer.returnFocus.focus({preventScroll:true});
    else {const fallback=top?byId(top.id).querySelector('button'):byId('ux_page_title');if(fallback)fallback.focus({preventScroll:true});}
  }
  function topLayer() {return layers.length ? layers[layers.length-1].id : null;}
  function closeTop() {
    const id=topLayer();
    if(id==='drawer')closeDrawer();else if(id==='favwrap')closeFavs();else if(id==='cmpwrap')closeCompare();
    else if(id==='copywrap'){byId(id).classList.remove('show');closeLayer(id);}
  }
  function navOpen(on) {
    document.body.classList.toggle('ux-nav-open',on);
    byId('ux_menu').setAttribute('aria-expanded',String(on));
    const mobile=root.matchMedia('(max-width: 700px)').matches;
    byId('sidebar').inert=mobile&&!on;
    const main=document.querySelector('.maincol');if(main)main.inert=mobile&&on;
    byId('fab_nlq').inert=mobile&&on;byId('ux_mobile_nav').inert=mobile&&on;
    if(on){byId('sidebar').querySelector('button')?.focus();}
    else if(mobile){byId('ux_menu').focus();}
  }
  function viewChanged(view, focus) {
    const info=VIEWS[view]||VIEWS.institutions;
    const hub=['help','integration','quality','about'].includes(view);
    if(!hub)helpPreviousView=view;
    document.body.classList.toggle('ux-help-view',hub);
    document.querySelectorAll('[data-help-tab]').forEach(t=>{const on=t.dataset.helpTab===view;t.setAttribute('aria-selected',String(on));t.tabIndex=on?0:-1;});
    document.body.classList.toggle('ux-doctors-view',view==='doctors');
    byId('ux_breadcrumb').textContent=hub?'帮助与数据说明':info[0];byId('ux_page_title').textContent=hub?'帮助与数据说明':info[1];byId('ux_page_desc').textContent=info[2];
    document.title='基于Spark的北京市医疗机构资源整合与多维筛选可视化系统';
    document.body.classList.toggle('ux-query-view',view==='institutions');
    document.body.classList.toggle('ux-analysis-view',view==='analytics');
    document.body.classList.toggle('ux-overview-view',view==='overview');
    navOpen(false);
    const shownView=view;
    document.querySelectorAll('[data-mobile-view]').forEach(b=>{
      const on=b.dataset.mobileView===shownView;b.classList.toggle('active',on);
      if(on)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
    });
    if(byId('ux_page_reset')){byId('ux_page_reset').textContent=view==='filter'?'清空对话':'一键清空';byId('ux_page_reset').setAttribute('aria-label',view==='filter'?'清空当前对话和输入':'一键清空当前页面条件');}
    resultsChanged();
    if(focus)byId('ux_page_title').focus({preventScroll:true});
  }
  function resultsChanged() {
    if(!initialized)return;
    const count=FILTERED.length,base=curBase();
    const active=byId('ux_active_conditions');if(active){const doctor=CUR_VIEW==='doctors';const pairs=doctor&&window.Doctors?Object.entries(Doctors.state()).filter(x=>x[1]).map(([k,v])=>[({name:'姓名',district:'行政区',hospital:'医院',department:'科室',grade:'等级'})[k],k==='hospital'?(byId('doctor_hospital')?.selectedOptions?.[0]?.textContent||v):v]):FLT_FIELDS.filter(x=>!['f_base','f_sort'].includes(x[0])).map(([k,label])=>[label,byId(k)?.value]).filter(x=>x[1]);active.innerHTML='<span>'+ (doctor?'医生查询条件':'机构与分析条件')+'</span>'+pairs.map(([k,v])=>'<span class="condition-tag">'+esc(k)+'：'+esc(v)+'</span>').join('')+(!doctor&&LOOKUP_SCOPE?'<span class="condition-tag">智能范围：'+esc(NLQ.describe(LOOKUP_SCOPE.conditions).map(x=>x.text).join('、'))+'</span>':'')+(pairs.length||(!doctor&&LOOKUP_SCOPE)?'':'<span>全部范围</span>')+(doctor?'<small>医生筛选独立于机构与分析筛选</small>':'');}

    byId('ux_results_summary').textContent=LOOKUP_ERROR?'请修正筛选条件':num(count)+' 家机构'+(LOOKUP_SCOPE?'（智能范围 '+num(LOOKUP_SCOPE.rows.length)+' 家中）':'')+' · 第 '+PAGE+' 页';
    byId('ux_export').disabled=!!LOOKUP_ERROR||count===0;
    byId('ux_filter_status').textContent=LOOKUP_ERROR?'筛选未执行：'+LOOKUP_ERROR:'当前命中 '+num(count)+' 家机构';
    const changed=!!LOOKUP_SCOPE||QueryAudit.fields.some(f=>{const value=readLookupConditions()[f[0]];return value!==''&&value!=null;});
    byId('ux_context_note').textContent=changed?(CUR_VIEW==='overview'?'总量卡片显示全量；地图与图表使用当前筛选（'+num(count)+' 家）':'当前筛选范围：'+num(count)+' 家机构'):'当前显示全量 '+num(DATA.institutions.length)+' 家机构';
    byId('ux_result_range').textContent= count ? '显示 '+((PAGE-1)*PAGE_SIZE+1)+'–'+Math.min(PAGE*PAGE_SIZE,count)+' / '+num(count)+' 家' : '暂无结果';
    byId('ux_base_status').textContent='距离参考点：'+base.name+' · 直线距离';
    byId('ux_scope').hidden=!LOOKUP_SCOPE;
    if(LOOKUP_SCOPE){const cityCount=fullQueryCount();byId('ux_scope_text').textContent='查询范围受限：'+NLQ.describe(LOOKUP_SCOPE.conditions).map(x=>x.text).join('、')+'。当前 '+num(count)+' 家 / 原结果 '+num(LOOKUP_SCOPE.rows.length)+' 家；不是全市结果。'+(cityCount===null?'请先修正当前筛选条件。':'保留当前条件在全市查询可得 '+num(cityCount)+' 家。');}
    syncStickyOffsets();
    const actions=byId('ux_bottom_pager');
    byId('ux_prev').disabled=PAGE<=1;byId('ux_next').disabled=PAGE*PAGE_SIZE>=count;
    actions.hidden=LOOKUP_ERROR||count===0;
    byId('ux_page_number').textContent=PAGE+' / '+Math.max(1,Math.ceil(count/PAGE_SIZE));
  }
  function showUndo(message, fn) {
    pendingUndo=fn;
    const undo=()=>{if(pendingUndo!==fn)return;pendingUndo=null;fn();toast('已撤销。');};
    const modal=topLayer()&&byId(topLayer());
    const footer=modal&&modal.querySelector('.cmpfoot, .dw-ft');
    if(footer){
      const previous=footer.querySelector('.ux-inline-undo');if(previous)previous.remove();
      const line=document.createElement('div');line.className='ux-inline-undo';
      const text=document.createElement('span');text.textContent=message;
      const button=document.createElement('button');button.type='button';button.className='btn ghost sm';button.textContent='撤销';
      button.addEventListener('click',()=>{undo();line.remove();});line.appendChild(text);line.appendChild(button);footer.appendChild(line);
      setTimeout(()=>line.remove(),6000);toast(esc(message));return;
    }
    toast(esc(message)+' <button type="button" id="ux_undo">撤销</button>',6000);
    byId('ux_undo').addEventListener('click',undo);
  }
  function syncStickyOffsets(){
    const style=document.documentElement?.style;if(!style||!style.setProperty)return;
    const header=document.querySelector('.topbar');const context=byId('ux_active_conditions');
    const height=header?.getBoundingClientRect?.().height||78;
    const contextHeight=context?.getBoundingClientRect?.().height||0;
    style.setProperty('--header-height',height+'px');style.setProperty('--sticky-offset',(height+contextHeight+12)+'px');
  }
  function init() {
    if(initialized)return;initialized=true;
    if(typeof root.ResizeObserver==='function'){const chartObserver=new root.ResizeObserver(entries=>{entries.forEach(({target})=>{const chart=root.echarts?.getInstanceByDom?.(target);if(chart&&target.clientWidth&&target.clientHeight)chart.resize({width:'auto',height:'auto'});});});document.querySelectorAll('.achart,.direction-chart,#map,#ch1,#ch2,#ch3').forEach(node=>chartObserver.observe(node));}
    if(typeof root.ResizeObserver==='function'){const observer=new root.ResizeObserver(syncStickyOffsets);const header=document.querySelector('.topbar'),context=byId('ux_active_conditions');if(header)observer.observe(header);if(context)observer.observe(context);}syncStickyOffsets();
    document.addEventListener('click',event=>{const b=event.target.closest('[data-phone-copy]');if(b)clipboard(b.dataset.phoneCopy,'电话号码');});
    byId('ux_page_reset').addEventListener('click',()=>{
      if(CUR_VIEW==='filter'){
        if(root.__CHAT__)root.__CHAT__.clear();
        const input=byId('ai_in');if(input){input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();}
        return;
      }
      if(CUR_VIEW==='doctors'&&root.Doctors){Doctors.reset();return;}
      for(const [id,value] of [['an_region_focus','all'],['an_region_measure','count'],['an_region_metric','total']]){const sel=byId(id);if(sel){sel.value=value;if(sel.selectedIndex<0)sel.selectedIndex=0;}}
      AN_REGION_METRIC='total';resetFilter();
      toast('已清空筛选条件，恢复全部范围');
    });
    byId('ux_menu').addEventListener('click',()=>navOpen(!document.body.classList.contains('ux-nav-open')));
    byId('ux_nav_backdrop').addEventListener('click',()=>navOpen(false));
    byId('ux_menu_close').addEventListener('click',()=>navOpen(false));
    document.querySelectorAll('[data-mobile-view],[data-go-view]').forEach(btn=>btn.addEventListener('click',()=>switchView(btn.dataset.mobileView||btn.dataset.goView)));
    document.querySelectorAll('[data-help-tab]').forEach(b=>b.addEventListener('click',()=>switchView(b.dataset.helpTab)));
    byId('help_hub_tabs').addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;const tabs=[...document.querySelectorAll('[data-help-tab]')],i=tabs.indexOf(document.activeElement);if(i<0)return;e.preventDefault();const j=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[j].click();tabs[j].focus();});
    byId('ux_help_return').addEventListener('click',()=>switchView(helpPreviousView));
    byId('ux_help_reset').addEventListener('click',()=>{resetFilter();switchView('institutions');});
    document.querySelectorAll('[data-help-question]').forEach(btn=>btn.addEventListener('click',()=>{smartDockSet(true);byId('ai_in').value=btn.dataset.helpQuestion;byId('ai_in').focus();}));
    byId('ux_ask').addEventListener('click',()=>smartDockSet(true));
    byId('ux_to_query').addEventListener('click',()=>{switchView('institutions');byId('f_kw').focus();});
    byId('ux_export').addEventListener('click',exportResults);byId('ux_copy').addEventListener('click',copyConditions);
    byId('ux_copy_close').addEventListener('click',()=>{byId('copywrap').classList.remove('show');closeLayer('copywrap');});
    byId('ux_save_toggle').addEventListener('click',()=>{
      const form=byId('ux_save_form');form.hidden=!form.hidden;
      byId('ux_save_toggle').setAttribute('aria-expanded',String(!form.hidden));
      byId('ux_save_error').textContent='';if(!form.hidden)byId('ux_save_name').focus();
    });
    byId('ux_save_form').addEventListener('submit',event=>{event.preventDefault();saveSearch();});
    byId('ux_save_cancel').addEventListener('click',()=>{byId('ux_save_form').hidden=true;byId('ux_save_toggle').setAttribute('aria-expanded','false');byId('ux_save_toggle').focus();});
    try{saved=normalizeSaved(JSON.parse(localStorage.getItem(STORAGE_KEY)||'[]'));}catch(_){saved=[];}
    renderSaved();
    byId('ux_saved_list').addEventListener('click',event=>{
      const load=event.target.closest('[data-load-search]');
      if(load){const item=saved.find(x=>x.id===load.dataset.loadSearch);if(item){try{restore(item.state);toast('已应用「'+esc(item.title)+'」。');}catch(e){toast('方案无法应用：'+esc(e.message));}}return;}
      const remove=event.target.closest('[data-remove-search]');if(remove){const previous=saved.slice();saved=saved.filter(x=>x.id!==remove.dataset.removeSearch);persistSaved();renderSaved();showUndo('已删除筛选方案。',()=>{saved=previous;persistSaved();renderSaved();});}
    });
    byId('ux_scope_clear').addEventListener('click',clearLookupScope);
    byId('ux_prev').addEventListener('click',()=>byId('pg_prev').click());byId('ux_next').addEventListener('click',()=>byId('pg_next').click());
    ['drawer','favwrap','cmpwrap','copywrap'].forEach(id=>{byId(id).inert=true;byId(id).setAttribute('aria-hidden','true');});
    document.addEventListener('keydown',event=>{
      if(event.key==='Escape'){
        if(topLayer()){event.preventDefault();event.stopImmediatePropagation();closeTop();return;}
        if(document.body.classList.contains('ux-nav-open')){event.preventDefault();navOpen(false);return;}
        if(CUR_VIEW==='filter'){event.preventDefault();event.stopImmediatePropagation();smartDockSet(false);return;}
      }
      if(event.key==='Tab' && !topLayer() && document.body.classList.contains('ux-nav-open')){
        const focusable=[...byId('sidebar').querySelectorAll('button:not([disabled]),a[href]')].filter(x=>x.getClientRects().length);
        const first=focusable[0],last=focusable[focusable.length-1];
        if(first&&event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
        else if(last&&!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
      }
      if(event.key==='Tab' && topLayer()){
        const el=byId(topLayer());const focusable=[...el.querySelectorAll('button:not([disabled]),input:not([disabled]),textarea,a[href],select,[tabindex="0"]')].filter(x=>x.getClientRects().length&&!x.closest('[hidden]'));
        const first=focusable[0],last=focusable[focusable.length-1];if(!first)return;
        if(event.shiftKey&&(document.activeElement===first||!el.contains(document.activeElement))){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&(document.activeElement===last||!el.contains(document.activeElement))){event.preventDefault();first.focus();}
      }
      const input=/INPUT|TEXTAREA|SELECT/.test(event.target.tagName)||event.target.isContentEditable;
      if(!input && !topLayer() && (event.key==='/' || ((event.ctrlKey||event.metaKey)&&event.key==='k'))){event.preventDefault();smartDockSet(false);switchView('institutions');byId('f_kw').focus();}
    },true);
    root.addEventListener('resize',()=>{if(topLayer())return;const small=root.matchMedia('(max-width: 700px)').matches;if(!small)navOpen(false);else byId('sidebar').inert=!document.body.classList.contains('ux-nav-open');});
    root.addEventListener('hashchange',restoreFromURL);root.addEventListener('popstate',restoreFromURL);
    viewChanged(CUR_VIEW,false);resultsChanged();
    connectionChanged();
    if(location.protocol==='file:'){
      byId('btn_locate').disabled=true;byId('btn_locate').title='当前为离线文件，可输入机构名或选择内置参考点。定位需 HTTPS 或 localhost 服务。';
    }
  }
  function connectionChanged(){const mode=byId('ux_mode');if(mode)mode.textContent=ENV.api?'已连接服务 · 快照查阅':'离线可用 · 本地快照';}
  let lastRestored='';
  function restoreFromURL(){
    if(location.hash===lastRestored)return;lastRestored=location.hash;
    const st=readState();
    restoringURL=true;
    try{
      const state={...st};if(st.base){const match=/^([^|]+)\|(-?[\d.]+),(-?[\d.]+)$/.exec(st.base);state.base=match?{name:match[1],lng:+match[2],lat:+match[3]}:null;}
      if(st.scope)state.scope=JSON.parse(st.scope);if(st.scopeBase)state.scope_base=JSON.parse(st.scopeBase);restore(state);
      if(window.Doctors)Doctors.restoreState(st);
      if(st.v && VIEWS[st.v]) switchView(st.v);
    }catch(e){toast('无法恢复这组条件：'+esc(e.message));}
    finally{restoringURL=false;lastRestored=location.hash;}
  }
  const api={init,request,connectionChanged,viewChanged,resultsChanged,openLayer,closeLayer,topLayer,closeTop,clipboard,showUndo,capture,restore,buildCSV,csvCell,normalizeSaved,noteHash(hash){lastRestored=hash;},get restoringURL(){return restoringURL;}};
  root.UX=api;
  if(typeof module!=='undefined'&&module.exports)module.exports={buildCSV,csvCell,normalizeSaved};
})(typeof window!=='undefined'?window:globalThis);
