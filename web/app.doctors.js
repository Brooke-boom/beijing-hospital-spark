/* Doctor directory: reviewed official records, shared by the offline UI and chat. */
(function(root){
  'use strict';
  const BOOKING='https://www.114yygh.com/', PAGE_SIZE=12;
  let directory=root.__DOCTORS__||null,initialized=false,page=1;
  const initialState=new URLSearchParams(location.hash.slice(1));
  const id=x=>document.getElementById(x);
  const escape=x=>String(x==null?'':x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const norm=x=>String(x||'').trim().replace(/心血管内科|心血管科|心脏科|心内科/g,'心内科');
  function departments(value){const parts=String(value||'').split(/[、；;]/).map(x=>x.trim());return parts.length>1&&parts.every(x=>/科|部|中心|门诊|病房|病区|研究所/.test(x))?parts:[String(value||'')];}
  function institutions(){return typeof DATA!=='undefined'&&DATA?DATA.institutions||[]:[];}
  let hospitalRows=null,hospitalIndex=new Map();
  function hospital(h){const rows=institutions();if(rows!==hospitalRows){hospitalRows=rows;hospitalIndex=new Map(rows.map(r=>[String(r.id),r]));}return hospitalIndex.get(String(h));}
  function canonical(h){const v=(directory?.hospitals||[]).find(r=>String(r.institution_id)===String(h)||(r.campus_ids||[]).includes(String(h)));return v?String(v.institution_id):String(h||'');}
  function records(){return (directory?.doctors||[]).filter(d=>d.status==='published'&&hospital(d.institution_id)?.level==='三级');}
  function filter(c){c=c||{};return records().filter(d=>{
    const h=hospital(d.institution_id),selected=c.hospital?hospital(c.hospital):null;
    return (c.grade!=='三甲'||(selected||h).level_sub==='甲等')&&(!c.name||d.name.includes(c.name.trim()))&&(!c.hospital||canonical(c.hospital)===String(d.institution_id))&&(!c.department||departments(d.department).some(dep=>norm(dep)===norm(c.department)))&&(!c.district||(selected?selected.district:h.district)===c.district);
  }).sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')||a.id.localeCompare(b.id));}
  function entryLabel(h){if(!directory)return '医生资料载入中';return filter({hospital:String(h)}).length?'查看已收录医生 →':'医生资料待补录 →';}
  function source(d){try{const u=new URL(d.source_url);return u.protocol==='https:'&&(directory?.source_hosts?.[d.institution_id]||[]).includes(u.hostname)?u.href:'';}catch(_){return '';}}
  function dateNote(d){const days=(Date.now()-Date.parse(d.verified_on+'T00:00:00+08:00'))/86400000;return days>90?' · 已超过90天，请核实最新资料':'';}
  function card(d,compact){const h=hospital(d.institution_id),url=source(d);return '<article class="doctor-card"><div class="doctor-card-heading"><span class="doctor-avatar" aria-hidden="true">'+escape(d.name.slice(-2))+'</span><div><h4>'+escape(d.name)+' <span>'+escape(d.title)+'</span></h4><p>'+escape(d.department)+'</p></div></div><p class="doctor-hospital">'+escape(h?.name)+' · '+escape(h?.district)+'</p><p class="doctor-specialty"><span>专业方向</span>'+escape(d.specialty||'官网未明确列出')+'</p><details class="doctor-source-details"><summary>来源与核验日期</summary><p class="doctor-source">'+(url?'<a href="'+escape(url)+'" target="_blank" rel="noopener noreferrer">'+escape(d.source_name)+' ↗</a>':'来源暂不可用')+'<span>'+(d.source_published_on?'发布 '+escape(d.source_published_on)+' · ':'')+'核验 '+escape(d.verified_on)+escape(dateNote(d))+'</span></p></details><div class="doctor-actions">'+(!compact?'<button class="btn sm" type="button" data-doctor-hospital="'+escape(d.institution_id)+'">医院详情</button>':'')+'<button class="btn sm" type="button" data-doctor-copy="'+escape(d.id)+'">复制预约信息</button><a class="btn primary sm" href="'+BOOKING+'" target="_blank" rel="noopener noreferrer">北京114预约 ↗</a></div></article>';}
  function state(){return {name:id('doctor_name').value,district:id('doctor_district').value,hospital:id('doctor_hospital').value,department:id('doctor_department').value,grade:id('doctor_aaa').checked?'三甲':''};}
  function option(v,t){const o=document.createElement('option');o.value=v;o.textContent=t;return o;}
  function populate(){const hs=institutions().filter(r=>r.level==='三级').sort((a,b)=>a.name.localeCompare(b.name,'zh-CN'));id('doctor_hospital').replaceChildren(option('','全部三级机构（180条）'));
    hs.forEach(h=>id('doctor_hospital').appendChild(option(String(h.id),h.name+' · '+h.category+(filter({hospital:String(h.id)}).length?'（'+filter({hospital:String(h.id)}).length+'条已收录）':'（待补录）'))));
    id('doctor_district').replaceChildren(option('','全部行政区'));[...new Set(hs.map(h=>h.district).filter(Boolean))].sort().forEach(d=>id('doctor_district').appendChild(option(d,d)));
    id('doctor_department').replaceChildren(option('','全部科室'));[...new Set(records().flatMap(d=>departments(d.department).map(norm)))].sort().forEach(d=>id('doctor_department').appendChild(option(d,d==='心内科'?'心内科 / 心血管内科':d)));
    const summary=id('doctor_summary');if(summary)summary.textContent='已收录 '+records().length+' 条医生资料 · '+hs.filter(h=>filter({hospital:String(h.id)}).length>0).length+' 条机构已有部分资料，'+hs.filter(h=>!filter({hospital:String(h.id)}).length).length+' 条待补录';
    id('doctor_coverage').textContent='目标 '+hs.length+' 条三级机构记录，与机构查询一致；其中 '+hs.filter(h=>filter({hospital:String(h.id)}).length>0).length+' 条已有部分医生资料，'+hs.filter(h=>!filter({hospital:String(h.id)}).length).length+' 条待补录。已收录 '+records().length+' 条医生资料 · 目录更新 '+(directory.updated_on||directory.verified_on)+'；单条核验日期见来源。';
  }
  function coverageRows(){return institutions().filter(h=>h.level==='三级').map(h=>({institution_id:String(h.id),name:h.name,category:h.category,doctor_count:filter({hospital:String(h.id)}).length}));}
  function renderCoverage(){const target=id('doctor_coverage_list');if(!target)return;target.innerHTML=coverageRows().sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')).map(h=>'<tr><td>'+escape(h.name)+'</td><td>'+escape(h.category)+'</td><td>'+(h.doctor_count?h.doctor_count+'条 · 部分资料':'待补录')+'</td><td><button class="btn sm" type="button" data-doctor-open="'+escape(h.institution_id)+'" >'+escape(entryLabel(h.institution_id))+'</button></td></tr>').join('');}
  function render(sync=true){const c=state(),rs=filter(c),totalPages=Math.max(1,Math.ceil(rs.length/PAGE_SIZE));page=Math.min(page,totalPages);id('doctor_count').textContent='找到 '+rs.length+' 条已收录医生资料';
    const selectedHospital=c.hospital?hospital(c.hospital):null;const conflict=selectedHospital&&c.district&&selectedHospital.district!==c.district;
    id('doctor_results').innerHTML=rs.length?rs.slice((page-1)*PAGE_SIZE,page*PAGE_SIZE).map(d=>card(d,false)).join(''):'<div class="doctor-empty"><h4>当前条件下暂无已收录医生</h4><p>可更换姓名、科室、医院或行政区。未收录不代表医院没有相应医生。</p><button class="btn" type="button" data-doctor-reset>清空筛选</button> <a class="btn primary" href="'+BOOKING+'" target="_blank" rel="noopener noreferrer">到北京114查询 ↗</a></div>';
    if(conflict)id('doctor_results').innerHTML='<div class="doctor-empty" role="status"><h4>医院与行政区条件冲突</h4><p>'+escape(selectedHospital.name)+'的机构地址位于'+escape(selectedHospital.district)+'，与所选'+escape(c.district)+'不一致；出诊院区另需到114核实。</p><button type="button" class="btn primary" data-doctor-conflict="district">按医院所在区查询</button> <button type="button" class="btn" data-doctor-conflict="hospital">清除医院，保留行政区</button></div>';
    if(c.hospital){const selected=hospital(c.hospital);id('doctor_results').insertAdjacentHTML('afterbegin','<p class="doctor-scope">'+escape(selected?.name)+' · 以下为医院级资料，具体出诊院区请到114核实。'+(rs.length?'名单仅包含已核实的部分医生。':'')+'</p>');}
    if(window.UX&&UX.resultsChanged)UX.resultsChanged();
    if(sync&&typeof CUR_VIEW!=='undefined'&&CUR_VIEW==='doctors')writeState(false);
    id('doctor_pager').innerHTML=totalPages>1?'<button class="btn sm" type="button" data-doctor-page="-1" '+(page===1?'disabled':'')+'>上一页</button><span>'+page+' / '+totalPages+'</span><button class="btn sm" type="button" data-doctor-page="1" '+(page===totalPages?'disabled':'')+'>下一页</button>':'';
  }
  function enter(){if(!directory){id('doctor_results').innerHTML='<p>医生目录载入失败，请刷新后重试；预约仍可前往北京114。</p>';return;}if(!initialized){populate();renderCoverage();initialized=true;for(const k of ['name','district','hospital','department'])id('doctor_'+k).value=initialState.get('doc_'+k)||'';id('doctor_aaa').checked=initialState.get('doc_grade')==='三甲';}render(false);}
  function open(h,dept,name){enter();id('doctor_name').value=name||'';id('doctor_district').value='';id('doctor_hospital').value=String(h||'');id('doctor_department').value=norm(dept);id('doctor_aaa').checked=false;page=1;switchView('doctors');render();}
  function paintHospital(r){const target=id('pane-doctors');if(!target)return;
    if(r.level!=='三级'){target.innerHTML='<div class="doctor-empty"><h4>当前医生目录面向三级医院</h4><p>该机构不在首批收录范围内。可到北京114核实相关科室与医生。</p><a class="btn primary" href="'+BOOKING+'" target="_blank" rel="noopener noreferrer">北京114预约 ↗</a></div>';return;}
    const rs=filter({hospital:String(r.id)});target.innerHTML='<div class="doctor-panel-header"><h4>已收录 '+rs.length+' 条医生资料</h4><button class="btn sm" type="button" data-doctor-open="'+escape(r.id)+'">'+escape(entryLabel(r.id))+'</button></div><p class="doctor-scope">官方公开来源的部分医生资料，不代表全院名单。资料按医院关联，具体出诊院区和时间请到北京114核实。若114无法访问，可先复制医生卡片中的预约信息，稍后到官方平台查询。</p><div class="doctor-list compact">'+(rs.length?rs.slice(0,3).map(d=>card(d,true)).join(''):'<div class="doctor-empty"><h4>该院医生资料暂未收录</h4><p>可以通过北京114继续查询医生和出诊信息。</p><a class="btn primary" href="'+BOOKING+'" target="_blank" rel="noopener noreferrer">到北京114查询 ↗</a></div>')+'</div>'+(rs.length>3?'<button class="btn" type="button" data-doctor-open="'+escape(r.id)+'">查看全部 '+rs.length+' 条已收录医生资料 →</button>':'');
  }
  function parseQuestion(q){if(!/医生|大夫|专家/.test(q)||/症状|疼|吃药|最好|推荐|诊断|怎么办|治疗方案/.test(q))return null;
    let hs=institutions().filter(r=>r.level==='三级'&&q.includes(r.name)).sort((a,b)=>b.name.length-a.name.length),h=hs[0],matched=h?.name;
    for(const item of directory?.hospitals||[]){for(const alias of item.aliases||[]){if(q.includes(alias)&&!/(延庆|医学院|卫生室|附属医院)/.test(q.split(alias).slice(1).join(alias))&&(!matched||alias.length>matched.length)){h=hospital(item.institution_id);matched=alias;}}}
    let rest=matched?q.replace(matched,''):q;rest=rest.replace(/有哪些|有哪几位|有什么|哪几位|哪些|有什么|查找|查询|帮我找|帮忙找|请问|的|有/g,'');
    for(const area of new Set(institutions().map(r=>r.district).filter(Boolean)))rest=rest.replace(area,'');
    let department='';const dm=rest.match(/([\u4e00-\u9fa5]{1,10}科)/);if(dm)department=norm(dm[1]);
    const name=records().find(d=>q.includes(d.name))?.name||'';
    const district=institutions().map(r=>r.district).find(d=>d&&q.includes(d))||'';
    // Unknown hospital names must never silently become an unrestricted query.
    const unknownHospital=!h&&/医院|三院|一院|二院/.test(q);
    return {hospital:h?String(h.id):'',department,name,district,grade:q.includes('三甲')?'三甲':'',unknownHospital};
  }
  function answer(q){const c=parseQuestion(q);if(!c)return null;if(!directory)return '<p>医生目录尚未载入，请打开“找医生”页面重试。</p>';
    if(c.unknownHospital)return '<p>暂未识别到这家三级医院，请到“找医生”选择医院核对名称。当前目录为部分资料。</p><button class="btn sm" type="button" data-doctor-open="">打开找医生</button>';
    const rs=filter(c),h=c.hospital?hospital(c.hospital):null;
    return '<p>'+escape((h?h.name+' · ':'')+(c.department?c.department+' · ':'')+(c.name?c.name+' · ':''))+'找到 '+rs.length+' 条已收录医生资料。'+(rs.length?'以下是官方资料中的部分医生，不是全院名单。':'当前目录没有匹配资料，不代表医院没有相应医生。')+'</p>'+rs.slice(0,3).map(d=>card(d,false)).join('')+'<div class="chat-actions"><button class="btn primary sm" type="button" data-doctor-query="'+escape(JSON.stringify(c))+'">查看医生查询结果（'+rs.length+' 条）</button><a class="btn sm" href="'+BOOKING+'" target="_blank" rel="noopener noreferrer">北京114预约 ↗</a></div><p class="doctor-source">按医院机构地址筛选；出诊院区、时间与号源请到114核实。</p>';
  }
  function init(){const form=id('doctor_filters');if(!form)return;form.addEventListener('submit',e=>{e.preventDefault();page=1;render();});form.addEventListener('input',()=>{page=1;render();});form.addEventListener('change',()=>{page=1;render();});form.addEventListener('reset',()=>setTimeout(()=>{page=1;render();},0));
    document.addEventListener('click',e=>{const b=e.target.closest('[data-doctor-conflict],[data-doctor-open],[data-doctor-hospital],[data-doctor-copy],[data-doctor-page],[data-doctor-reset],[data-doctor-query]');if(!b)return;
      if(b.hasAttribute('data-doctor-conflict')){if(b.dataset.doctorConflict==='district')id('doctor_district').value=hospital(state().hospital)?.district||'';else id('doctor_hospital').value='';page=1;render();}
      else if(b.hasAttribute('data-doctor-open')){closeDrawer();open(b.dataset.doctorOpen);}
      else if(b.hasAttribute('data-doctor-query')){const c=JSON.parse(b.dataset.doctorQuery);open(c.hospital,c.department,c.name);id('doctor_district').value=c.district||'';id('doctor_aaa').checked=c.grade==='三甲';render();}
      else if(b.hasAttribute('data-doctor-hospital'))openDrawer(b.dataset.doctorHospital);
      else if(b.hasAttribute('data-doctor-copy')){const d=records().find(x=>x.id===b.dataset.doctorCopy);if(d)UX.clipboard(hospital(d.institution_id).name+' · '+d.department+' · '+d.name+'\n北京114：'+BOOKING+'\n请核实出诊院区、时间及号源。','预约查询信息');}
      else if(b.hasAttribute('data-doctor-page')){page+=Number(b.dataset.doctorPage);render();id('doctor_count').scrollIntoView({block:'start'});}
      else form.reset();
    });
    if(!directory&&/^https?:$/.test(location.protocol))fetch('doctors_data.json').then(r=>{if(!r.ok)throw Error('load');return r.json();}).then(d=>{directory=d;if(typeof CUR_VIEW!=='undefined'&&CUR_VIEW==='doctors')enter();}).catch(()=>{});
  }
  function restoreState(st){enter();for(const k of ['name','district','hospital','department'])id('doctor_'+k).value=st['doc_'+k]||'';id('doctor_aaa').checked=st.doc_grade==='三甲';page=1;render();}
  root.Doctors={entryLabel,coverageRows,state,restoreState,filter,parseQuestion,answer,paintHospital,enter,open,canonical,source};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})(window);
