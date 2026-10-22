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
  var MODEL_COOLDOWN=0;
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
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

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
    LOG.setAttribute('data-empty','true');
    addMsg('sys','<div class="chat-start"><span class="chat-start-icon" aria-hidden="true">✦</span><h3>想了解哪里的医疗资源？</h3><p>输入区域、医院或科室，查询机构、医生，或比较资源分布。</p><div class="chat-start-grid">'+[
      ['找医院','海淀区的三级医院有哪些？'],['看分布','按行政区统计三级医院的数量'],['找医生','北京协和医院有哪些心内科医生？'],['查科室','朝阳区有哪些开设骨科的机构？']
    ].map(function(x){return '<button type="button" data-q="'+x[1]+'"><strong>'+x[0]+'</strong><span>'+x[1]+'</span><i aria-hidden="true">↗</i></button>';}).join('')+'</div><small>点击示例即可查询，也可以直接输入自己的问题。</small></div>','');
  }

  function setStatus() {
    var dot = el('ai_dot'), txt = el('ai_status');
    if (!dot || !txt) return;
    if (AI_ON === true) { txt.textContent = '智能说明已启用'; dot.className = 'chatdot on'; }
    else if (AI_ON === false) { txt.textContent = '本地查询可用'; dot.className = 'chatdot off'; }
    else { txt.textContent = '连接检测中…'; dot.className = 'chatdot'; }
  }

  // Agnes 探活：不发起真实推理（?probe=1 才会），只问密钥与开关状态。
  // file:// 下 fetch 直接失败 → 离线模板，与旧版门禁行为一致。
  function probe() {
    if(Date.now()<MODEL_COOLDOWN){AI_ON=false;setStatus();return Promise.resolve(false);}
    // 注意：ENV.api 是布尔且**异步**才就绪 —— init 时可能还没完成，所以 ask()
    // 前会重探一次（/api/ai/health 是轻接口，无推理开销）。file:// 直接离线。
    if (!httpPage() || !window.ENV || !ENV.backend) { AI_ON = false; setStatus(); return Promise.resolve(false); }
    return UX.request('/api/ai/health',{},4000)
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

  function scopeNote(res) {
    var cond=res.parsed.conditions||{},chips=window.NLQ.describe(cond)||[];
    var text='本次筛选条件：'+chips.map(function(x){return x.label+'：'+(x.text||(x.values||[]).join('、'));}).join('；')+'。';
    if((cond.level||[]).includes('三级')){
      var only=(cond.category||[]).length===1&&cond.category[0]==='医院';
      text+='本次口径：'+(only?'仅医院类型的三级记录':'当前类型条件下的三级记录（未限类型时包含院区、旧名及其他类型）')+'。';
      if(only){var all=Object.assign({},cond);delete all.category;var result=window.NLQ.runStats(DATA.institutions,all,'district',basePoint());text+='对照口径：保持其他条件，取消机构类型限制，全部三级机构记录为'+result.rows.filter(function(x){return x.cnt;}).map(function(x){return x.name+' '+x.cnt+' 条';}).join('、')+'。两者可能不同，不等同去重医院数。若要查全部记录，请将问题中的“三级医院”改为“三级机构”。';}
    }
    return text;
  }

  // facts 文本（服务端截断在 4000 字符，前端控制在 ~2600 以内）
  function buildFacts(res) {
    var lines = [scopeNote(res)];
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
      var valid = res.st.rows.filter(function (r) { return r.cnt; });
      var rows = valid.slice(0, 8).map(function(r,i){return (i+1)+'. '+(r.name||r.label||r.key)+'：'+r.cnt+' 条';}).join('\n');
      return head+'共找到 '+res.total+' 条机构记录，按'+(res.st.label||res.st.dimension)+'汇总。\n'+rows+(valid.length>8?'\n其余 '+(valid.length-8)+' 组未在此展开。':'')+'\n统计为机构记录数量，不代表医疗水平。';
    }
    var items = res.r.all || res.r.items || [];
    if (!res.total) {
      return head + '按' + (condTxt ? '条件（' + condTxt + '）' : '你的描述') + '没有查到匹配机构。' +
        '可以放宽条件试试：去掉行政区、放宽等级，或改用更常见的科室名。\n以上为平台真实查询结果。';
    }
    var top = items.slice(0, 3).map(function (x, i) {
      return (i + 1) + '. ' + x.name + '（' + (x.district || '—') + '·' + (x.level || '未定级') + '）';
    }).join('\n');
    return head + '按' + (condTxt ? '条件（' + condTxt + '）' : '你的描述') + '共命中 ' + res.total + ' 家。' +
      (res.r.sort && res.r.sort.indexOf('dist') === 0 ? '按距离从近到远，' : '') +
      '\n以下按当前查询顺序展示：\n' + top + '。\n以上数字与机构名来自平台真实查询，可点击下方按钮打开完整结果。';
  }

  // --------------------------------------------------------------------------
  //  主流程：提问 → 拒答/查询 → Agnes 或模板
  // --------------------------------------------------------------------------
  function setBusy(on){
    BUSY=on;
    var send=el('ai_send'),clear=el('ai_clear');
    if(send){send.disabled=on;send.textContent=on?'查询中…':'发送';}
    if(clear)clear.disabled=on;
    if(LOG)LOG.setAttribute('aria-busy',String(on));
    var box=el('ai_ex');if(box)box.querySelectorAll('button').forEach(function(b){b.disabled=on;});
  }
  var conversationEpoch=0;
  function ask(q) {
    q=String(q||'').trim().slice(0,500);
    if(!q||BUSY)return Promise.resolve(null);
    if(LOG.getAttribute&&LOG.getAttribute('data-empty')==='true')LOG.innerHTML='';
    LOG.setAttribute('data-empty','false');
    addMsg('user',multiline(q));setBusy(true);
    // Resource counts cannot substantiate clinical hospital rankings.
    if (/(排名|排行|最好|最强|最有名|top\s*\d*)/i.test(q) && !/按.{0,12}(数量|距离|科室数|专科数)/.test(q)) {
      var lookup=q.replace(/排名|排行榜?|最好|最强|最有名|top\s*\d*/ig,'').trim();
      addMsg('ai','<h4 class="chat-answer-title">可以查资源，暂不能评医疗水平</h4><p>系统没有疗效、手术质量或权威评审排名数据，不能据此给医院或医生排优劣。</p><p>你可以查看符合区域和科室条件的机构，或指定按距离、已收录科室数量比较。</p><div class="chat-actions"><button type="button" class="btn primary sm" data-q="'+hesc(lookup+'有哪些机构？')+'">查看符合条件的机构</button><button type="button" class="btn sm" data-q="'+hesc(lookup+'按距离从近到远')+'">按距离查询</button></div>','查询说明');
      setBusy(false);return Promise.resolve({intent:'ranking_boundary'});
    }
    if(window.Doctors){var doctorReply=Doctors.answer(q);if(doctorReply){addMsg('ai',doctorReply,'医生资料查询 · 医院官网');setBusy(false);return Promise.resolve({intent:'doctors'});}}
    var res;
    try{res=localRun(q);}catch(e){setBusy(false);addMsg('sys','暂时无法执行查询，请调整条件后重试。');return Promise.resolve(null);}
    if(res.refuse){setBusy(false);addMsg('refuse',multiline(res.message),'查询范围说明');if(window.updateFabBadge)updateFabBadge(null);return Promise.resolve(null);}
    var epoch=conversationEpoch,historySnapshot=HISTORY.slice();
    var answer=localAnswer(res),message=null;
    var historyReply={role:'assistant',content:answer};
    HISTORY.push({role:'user',content:q},historyReply);HISTORY=HISTORY.slice(-6);
    var scopeHTML='<details class="chat-query-scope"><summary>查看本次查询条件与统计口径</summary><p class="chat-scope-note">'+multiline(scopeNote(res))+'</p></details>';
    function paint(html,meta){
      if(epoch!==conversationEpoch)return;
      var follow=LOG&&(LOG.scrollHeight-LOG.scrollTop-LOG.clientHeight<100);
      if(message){message.querySelector('.chatbody').innerHTML=scopeHTML+html;message.querySelector('.chatwho').textContent=meta;}
      else{
        message=addMsg('ai',scopeHTML+html,meta);
        if(message&&res.intent==='filter'&&res.r&&!res.r.unsupported){
          var actions=document.createElement('div');actions.className='chat-actions';
          var button=document.createElement('button');button.type='button';button.className='btn primary sm';button.textContent='查看完整结果（'+res.total+' 家）';
          button.addEventListener('click',function(){if(window.useSmartResults)useSmartResults(res);});actions.appendChild(button);message.appendChild(actions);
          var preview=document.createElement('div');preview.className='chat-results-list';
          (res.r.items||[]).slice(0,3).forEach(function(row){var link=document.createElement('button');link.type='button';link.textContent=row.name+' · 查看详情';link.addEventListener('click',function(){openDrawer(row.id);});preview.appendChild(link);});message.appendChild(preview);
        }
      }
      if(LOG&&follow)LOG.scrollTop=LOG.scrollHeight;
    }
    function finish(reply,meta){
      if(epoch!==conversationEpoch)return;
      paint(multiline(reply),meta);
      historyReply.content=reply;
    }
    // Data results are immediately usable; language generation never blocks the result handoff.
    paint(multiline(answer),'查询已完成 · 可继续提问');
    setBusy(false); // 本地结果已完成，智能说明仅更新本条消息。
    if(window.updateFabBadge)updateFabBadge(res.total);
    var ready=httpPage()?probe():Promise.resolve(AI_ON=false);
    return ready.then(function(){
      if(epoch!==conversationEpoch)return null;
      if(AI_ON!==true){finish(answer,'本地查询结果');return null;}
      paint(multiline(answer),'真实查询结果 · 正在补充智能说明');
      return jsonPost('/api/ai/chat',{mode:'data',question:q,facts:buildFacts(res),history:historySnapshot}).then(function(j){
        if(j&&j.ok&&j.reply){finish(j.reply,'智能说明'+(j.cached?' · 已缓存':'')+' · 基于真实查询结果');return j;}
        AI_ON=false;setStatus();
        if(j&&j.reason==='llm_rate_limited'){MODEL_COOLDOWN=Date.now()+30000;finish(answer,'查询已完成 · 智能说明繁忙，可继续提问');}
        else finish(answer,'查询已完成 · 当前使用本地说明');
        return j;
      }).catch(function(){AI_ON=false;setStatus();finish(answer,'本地查询结果 · 智能说明连接失败');return null;});
    }).catch(function(){AI_ON=false;setStatus();finish(answer,'本地查询结果');return null;});
  }

  function jsonPost(url, body) {
    return UX.request(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    },18000).then(function (r) { return r.json().catch(function () { return null; }); });
  }

  // --------------------------------------------------------------------------
  //  初始化与进入
  // --------------------------------------------------------------------------
  function init() {
    if (INITE) return; INITE = true;
    LOG = el('ai_log');
    var input = el('ai_in'), send = el('ai_send');
    welcome();
    function updateInput(){var n=input.value.length;if(el('ai_count'))el('ai_count').textContent=n+'/500';input.style&&(input.style.height='auto');if(input.style)input.style.height=Math.min(160,Math.max(62,input.scrollHeight||62))+'px';}
    if(input)input.addEventListener('input',updateInput);
    if(LOG)LOG.addEventListener('click',function(e){var b=e.target&&e.target.closest?e.target.closest('[data-q]'):null;if(b)ask(b.getAttribute('data-q'));});
    if (send) send.addEventListener('click', function () {
      if(BUSY)return;var v = input.value;if(!v.trim()){input.focus();return;}input.value='';updateInput();ask(v);input.focus();
    });
    if (input) input.addEventListener('keydown', function (e) {
      if(e.isComposing||e.keyCode===229)return;
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault();if(BUSY)return; var v = input.value;if(!v.trim())return;input.value='';updateInput();ask(v); }
    });
    var box = el('ai_ex');
    if (box) box.addEventListener('click', function (e) {
      var b = e.target && e.target.closest ? e.target.closest('[data-q]') : null;
      if (b) ask(b.getAttribute('data-q'));
    });
    var clr = el('ai_clear');
    if (clr) clr.addEventListener('click', function () {
      if(BUSY)return;conversationEpoch++;LOG.innerHTML = ''; HISTORY = []; welcome();
      if (window.updateFabBadge) updateFabBadge(null);
    });
    probe();
  }

  function enter() {
    if (!INITE) init();
    ENTERED = true;
    var input = el('ai_in');
    setTimeout(function () { if (input && !(window.matchMedia && window.matchMedia('(max-width:700px)').matches)) input.focus(); }, 80);
  }

  window.__CHAT__ = { enter: enter, ask: ask, clear: function () { if (el('ai_clear')) el('ai_clear').click(); } };
  if (typeof module !== 'undefined' && module.exports) module.exports = { CHAT: CHAT };
  return { enter: enter, ask: ask };
})();
