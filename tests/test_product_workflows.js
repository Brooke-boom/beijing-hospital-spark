// Tests run in a deterministic DOM model, not a real browser or layout engine.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const pure=require('../web/app.ux.js');let passed=0;
function check(label,fn){fn();passed++;console.log('PASS '+label);}
check('CSV escapes commas, quotes and newlines',()=>assert.equal(pure.csvCell('a,"b"\nc'),'"a,""b""\nc"'));
check('CSV prevents spreadsheet formula execution',()=>{for(const x of ['=1','+SUM(A1)','-1+2','@x','  =1'])assert.ok(pure.csvCell(x).startsWith('"\''));});
check('Export records snapshot and evidence semantics',()=>{const csv=pure.buildCSV([{name:'医院',recorded_depts:'骨科',coord_precision:'rough'}],'2026-10-18');assert.ok(csv.startsWith('\uFEFF'));for(const x of ['有来源记录的科室','粗精度','2026-10-18'])assert.ok(csv.includes(x));});
check('Malformed saved search storage is rejected and bounded',()=>{assert.deepEqual(pure.normalizeSaved({}),[]);assert.deepEqual(pure.normalizeSaved([null,{title:3},{id:'x',title:'x'}]),[]);assert.equal(pure.normalizeSaved(Array.from({length:12},(_,i)=>({id:''+i,title:'x'.repeat(50),state:{}}))).length,8);});
const ids=new Set([...fs.readFileSync('web/dashboard.html','utf8').matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]));
let document,mobile=false;const elements=new Map(),storage=new Map();
class Classes{constructor(){this.set=new Set();}add(...a){a.forEach(x=>this.set.add(x));}remove(...a){a.forEach(x=>this.set.delete(x));}contains(x){return this.set.has(x);}toggle(x,on){on=on===undefined?!this.contains(x):on;on?this.add(x):this.remove(x);return on;}}
class Element{
 constructor(id){Object.assign(this,{id,tagName:'DIV',value:'',textContent:'',innerHTML:'',hidden:false,inert:false,attrs:{},dataset:{},style:{},classList:new Classes(),events:{},isConnected:true,children:[]});}
 set innerHTML(value){this._html=String(value);for(const match of this._html.matchAll(/\bid="([^"]+)"/g)){if(!elements.has(match[1]))elements.set(match[1],new Element(match[1]));}}
 get innerHTML(){return this._html||'';}
 setAttribute(k,v){this.attrs[k]=String(v);}getAttribute(k){return this.attrs[k]??null;}removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,fn){(this.events[k]??=[]).push(fn);}focus(){document.activeElement=this;}select(){this.selected=true;}click(){(this.events.click||[]).forEach(fn=>fn({target:this,preventDefault(){}}));}
 querySelector(){return this.children[0]||null;}querySelectorAll(){return this.children;}closest(){return null;}contains(x){return x===this||this.children.includes(x);}getClientRects(){return[{}];}scrollIntoView(){}
}
for(const id of ids)elements.set(id,new Element(id));
check('Required workflow controls exist in the template',()=>{for(const match of fs.readFileSync('web/app.ux.js','utf8').matchAll(/byId\('([^']+)'\)/g)){if(match[1]!=='ux_undo')assert.ok(ids.has(match[1]),'missing '+match[1]);}});
const navs=[...fs.readFileSync('web/dashboard.html','utf8').matchAll(/<button class="navtab([^"]*)"[^>]*data-view="([^"]+)"/g)].map(match=>{const element=new Element('nav-'+match[2]);element.setAttribute('data-view',match[2]);element.dataset.view=match[2];if(match[1].includes('active'))element.classList.add('active');return element;});
const rootEvents=new Map();
const node=id=>elements.get(id)||null;node('f_sort').value='score';node('pg_size').value='20';
document={readyState:'loading',activeElement:new Element('trigger'),body:new Element('body'),documentElement:new Element('html'),getElementById:node,querySelector(selector){if(selector==='.dw-tabs')return elements.get('tablist')||elements.set('tablist',new Element('tablist')).get('tablist');const view=selector.match(/data-view="([^"]+)"/);return view?navs.find(n=>n.getAttribute('data-view')===view[1])||null:null;},querySelectorAll(sel){if(sel==='.navtab[data-view]')return navs;if(sel==='.view')return [...elements.values()].filter(e=>e.id.startsWith('view-'));return sel.includes('.maincol >')?[node('sidebar'),node('ux_page_title')]:[];},addEventListener(){},createElement(tag){const e=new Element('created');e.tagName=tag.toUpperCase();return e;}};
const c={document,console,URL,URLSearchParams,Blob,setTimeout(){return 1;},clearTimeout(){},location:{protocol:'file:',hostname:'',port:'',hash:''},localStorage:{getItem(k){return storage.get(k)||null;},setItem(k,v){storage.set(k,v);},removeItem(k){storage.delete(k);}},navigator:{},isSecureContext:false,matchMedia(){return{matches:mobile};},addEventListener(name,fn){(rootEvents.get(name)||rootEvents.set(name,[]).get(name)).push(fn);},scrollTo(){},snapshot:JSON.parse(fs.readFileSync('web/snapshot_data.json','utf8'))};
c.navPushes=0;c.history={replaceState(a,b,h){c.location.hash=h;},pushState(a,b,h){c.location.hash=h;c.navPushes++;}};c.window=c;vm.createContext(c);
for(const f of ['web/app.query.js','web/app.nlq.js','web/app.js','web/app.ux.js'])vm.runInContext(fs.readFileSync(f,'utf8'),c,{filename:f});
vm.runInContext('DATA=snapshot;NLQ.init('+fs.readFileSync('web/nlq_lexicon.json','utf8')+'.lex);',c);
check('Application initializes all query workflows without a browser or chart service',()=>{
 vm.runInContext('init();',c);
 assert.equal(node('loading').classList.contains('hide'),true,'initialization failed: '+node('loading').innerHTML);
 assert.ok(node('ux_save_toggle').events.click?.length,'workflow initialization did not finish');
 assert.equal(vm.runInContext('FILTERED.length',c),c.snapshot.institutions.length);
});
vm.runInContext(`originalSwitchView=switchView;initCharts=()=>{};renderKPI=()=>{};renderList=()=>{UX.resultsChanged();};updateCharts=()=>{};updateAnalyticsCharts=()=>{};renderQueryExplanation=()=>{};renderFilterChips=()=>{};syncPresetUI=()=>{};syncKwClear=()=>{};syncDirUI=()=>{};switchView=v=>{CUR_VIEW=v;};smartDockSet=()=>{};toast=()=>{};`,c);
check('Page initialization does not request location',()=>{const body=fs.readFileSync('web/app.js','utf8').split('function init() {')[1].split('// 后端探活')[0];assert.ok(!/^[ \t]*autoLocate\(\);/m.test(body));});
check('Scoped tertiary query explains 8 versus the city-wide 180 and preserves level when leaving scope',()=>{
 vm.runInContext("clearConditionsSilent();setLookupScope({district:['海淀区'],dept:'骨科'});applyFilter();",c);
 node('f_level').value='三级';vm.runInContext('applyFilter();scopeN=LOOKUP_SCOPE.rows.length;scopedN=FILTERED.length;cityN=fullQueryCount();',c);
 assert.equal(c.scopeN,16);assert.equal(c.scopedN,8);assert.equal(c.cityN,180);
 assert.match(node('ux_results_summary').textContent,/智能范围 16/);
 assert.match(node('ux_scope_text').textContent,/不是全市结果/);
 vm.runInContext('clearLookupScope();afterScopeN=FILTERED.length;',c);
 assert.equal(c.afterScopeN,180);assert.equal(node('f_level').value,'三级');assert.equal(node('ux_scope').hidden,true);
});
check('Saved filters restore the same institution IDs',()=>{node('f_district').value='海淀区';node('f_level').value='三级';vm.runInContext('applyFilter();state=UX.capture();before=FILTERED.map(x=>x.id);',c);node('f_district').value='朝阳区';vm.runInContext('UX.restore(state);after=FILTERED.map(x=>x.id);',c);assert.deepEqual(c.before,c.after);assert.ok(c.after.length);});
check('Smart multi-district scope preserves all results',()=>{vm.runInContext(`clearConditionsSilent();conditions={district:['海淀区','朝阳区'],grades:['三级甲等']};reference=NLQ.runFilter(DATA.institutions,conditions,1,1e9,curBase());setLookupScope(conditions);applyFilter();scopeIds=FILTERED.map(x=>String(x.id)).sort();referenceIds=reference.all.map(x=>String(x.id)).sort();`,c);assert.deepEqual(Array.from(c.scopeIds),Array.from(c.referenceIds));});
check('Saved scope preserves multi-district semantics',()=>{vm.runInContext('scopeState=UX.capture();clearConditionsSilent();UX.restore(scopeState);after=FILTERED.map(x=>String(x.id)).sort();',c);assert.deepEqual(Array.from(c.after),Array.from(c.referenceIds));});
check('Saved radius scope retains its original reference after changing the distance base',()=>{
 vm.runInContext('oldScope=UX.capture();clearConditionsSilent();setLookupScope({radius:5});applyFilter();radiusIds=FILTERED.map(x=>String(x.id)).sort();BASE_NOW={name:"另一参考点",lng:117,lat:40};radiusState=UX.capture();UX.restore(radiusState);restoredRadiusIds=FILTERED.map(x=>String(x.id)).sort();',c);
 assert.deepEqual(Array.from(c.radiusIds),Array.from(c.restoredRadiusIds));
 vm.runInContext('UX.restore(oldScope);',c);
});
check('Additional filters stay within smart scope',()=>{node('f_district').value='海淀区';vm.runInContext('applyFilter();subset=FILTERED.map(x=>String(x.id));',c);assert.ok(c.subset.length);assert.ok(c.subset.every(id=>c.referenceIds.includes(id)));});
check('Analysis facets honor evidence, radius and smart-result scope',()=>{
 node('f_dept').value='骨科';node('f_evidence').value='recorded';node('f_radius').value='5';
 vm.runInContext('applyFilter();facetIds=anSubset("cat").map(x=>String(x.id)).sort();expectedFacet=(LOOKUP_SCOPE?LOOKUP_SCOPE.rows:DATA.institutions).filter(x=>QueryAudit.matches(x,readLookupConditions(),curBase(),NLQ)).map(x=>String(x.id)).sort();',c);
 assert.deepEqual(Array.from(c.facetIds),Array.from(c.expectedFacet));
 node('f_dept').value='';node('f_evidence').value='';node('f_radius').value='';
});
check('Zero results produce an empty map, never a full-data map',()=>{node('f_kw').value='不存在的测试机构XYZ';vm.runInContext('applyFilter();mapRows=mapDistrictRows();',c);assert.equal(vm.runInContext('FILTERED.length',c),0);assert.ok(c.mapRows.every(r=>r.inst_count===0));});
check('Invalid radius is distinct from a valid empty result',()=>{node('f_radius').value='201';vm.runInContext('applyFilter();',c);assert.match(vm.runInContext('LOOKUP_ERROR',c),/200/);assert.equal(node('ux_form_error').hidden,false);});
check('Nested dialogs restore focus and keep background isolated',()=>{const trigger=new Element('trigger'),close=node('dw_close'),copy=node('ux_copy_text');node('drawer').children=[close];node('copywrap').children=[copy];document.activeElement=trigger;c.UX.openLayer('drawer','dw_close');assert.equal(document.activeElement,close);assert.equal(node('ux_page_title').inert,true);c.UX.openLayer('copywrap','ux_copy_text');assert.equal(node('drawer').inert,true);c.UX.closeLayer('copywrap');assert.equal(document.activeElement,close);c.UX.closeLayer('drawer');assert.equal(document.activeElement,trigger);assert.equal(document.body.classList.contains('ux-modal-open'),false);});
check('Dialog close preserves hidden mobile navigation',()=>{mobile=true;c.UX.openLayer('drawer','dw_close');c.UX.closeLayer('drawer');assert.equal(node('sidebar').inert,true);mobile=false;});
check('Clipboard fallback provides selected readable text',()=>{node('copywrap').children=[node('ux_copy_text')];c.UX.clipboard('公开机构条件','筛选条件');assert.equal(node('ux_copy_text').value,'公开机构条件');assert.equal(node('ux_copy_text').selected,true);assert.equal(c.UX.topLayer(),'copywrap');c.UX.closeLayer('copywrap');});
check('Navigation updates the selected page, heading and browser history',()=>{
 vm.runInContext('switchView=originalSwitchView;LOOKUP_SCOPE=null;',c);const before=c.navPushes;
 vm.runInContext('switchView("overview")',c);
 assert.equal(vm.runInContext('CUR_VIEW',c),'overview');assert.equal(node('ux_page_title').textContent,'数据总览');
 assert.equal(navs.find(n=>n.dataset.view==='overview').getAttribute('aria-current'),'page');assert.equal(c.navPushes,before+1);
});
check('Browser history restores filters without adding another history entry',()=>{
 const before=c.navPushes;c.location.hash='#v=institutions&district='+encodeURIComponent('朝阳区');
 for(const fn of rootEvents.get('popstate')||[])fn();
 assert.equal(node('f_district').value,'朝阳区');assert.equal(vm.runInContext('CUR_VIEW',c),'institutions');assert.equal(c.navPushes,before);
 assert.equal(node('ux_page_title').textContent,'机构查询');
});
console.log(JSON.stringify({status:'passed',tests:passed,limitation:'DOM model, not browser/layout/assistive-technology verification.'}));
