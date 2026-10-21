// Aggregation and navigation tests, using actual functions; no browser layout assertions.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/app.js','utf8'),ctx=vm.createContext({METRIC_DEFINITIONS:JSON.parse(fs.readFileSync('web/metric_definitions.json','utf8')).metrics});
vm.runInContext(source.split('// DIRECTION_ANALYSIS_PURE_START')[1].split('// DIRECTION_ANALYSIS_PURE_END')[0],ctx);
const rows=[{district:'甲区',category:'社区卫生服务中心',depts:'全科;骨科',recorded_depts:'骨科',net_pediatric:'成员',net_stroke:'1'},
 {district:'甲区',category:'综合医院',level:'三级',depts:['骨科'],recorded_depts:[]},
 {district:'乙区',category:'诊所',net_pediatric:'未标注',net_neonatal:'市级'}, {category:'专科医院'}];
const groups=ctx.directionRows(rows,['甲区','乙区','丙区']);
const a=groups.find(x=>x.name==='甲区'),b=groups.find(x=>x.name==='乙区'),c=groups.find(x=>x.name==='丙区');
assert.equal(a.total,2);assert.equal(a.community,1);assert.equal(a.hospital,1);assert.equal(a.l3,1);assert.equal(a.recorded,1);assert.equal(a.mapped,2);
assert.equal(a.network,1,'overlapping network memberships count once');assert.equal(a.pediatric,1);assert.equal(a.stroke,1);
assert.equal(b.pediatric,0);assert.equal(b.network,1);assert.equal(c.total,0);assert.equal(groups.reduce((n,g)=>n+g.total,0),4);
for(const kind of ['region','primary','evidence','network']){
 const t=ctx.directionTable(kind,groups);assert.equal(t.rows.length,4);assert.ok(t.rows.every(r=>r.length===t.headers.length));
 const zero=ctx.directionTable(kind,ctx.directionRows([],['甲区']));assert.ok(!JSON.stringify(zero).match(/NaN|Infinity/));assert.equal(zero.rows[0].at(-1),'—');
}
assert.equal(ctx.directionTable('evidence',groups).rows.find(r=>r[0]==='甲区').at(-1),'50.0%');
assert.equal(ctx.directionTable('region',groups).rows.find(r=>r[0]==='甲区')[2],'50.0%');
const snapshot=JSON.parse(fs.readFileSync('web/snapshot_data.json','utf8')),real=snapshot.institutions;
const actual=ctx.directionRows(real,[]);assert.equal(actual.reduce((n,g)=>n+g.total,0),real.length);
assert.equal(actual.reduce((n,g)=>n+g.recorded,0),real.filter(r=>Array.isArray(r.recorded_depts)?r.recorded_depts.length:String(r.recorded_depts||'').split(';').some(x=>x.trim())).length);
const filtered=real.filter(r=>r.district==='海淀区'&&r.level==='三级');assert.equal(ctx.directionRows(filtered,[]).reduce((n,g)=>n+g.total,0),filtered.length);
const labels=[],classes=new Set(),nav={attrs:{'aria-current':'page'},classList:{contains:()=>true},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]}};
function node(){return{attrs:{},classList:{add(){},remove(){},toggle(){}},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},querySelector(){return{style:{}}},focus(){this.focused=true}}}
const nodes={fab_nlq:node(),'view-filter':node(),nav_chat:node()};
const navctx=vm.createContext({document:{getElementById:id=>nodes[id],body:{classList:{toggle(k,v){v?classes.add(k):classes.delete(k)}}},querySelectorAll:()=>[nav],querySelector:()=>true},$:id=>nodes[id],setTimeout(){},resizeAll(){},window:{UX:{viewChanged(v){labels.push(v)}}},UX:{viewChanged(v){labels.push(v)}},console});
vm.runInContext("let CUR_VIEW='analytics',DOCK_PREV_VIEW='institutions';"+source.slice(source.indexOf('function smartDockSet(on)'),source.indexOf('function initSmartDock()')),navctx);
vm.runInContext('smartDockSet(true)',navctx);assert.ok(classes.has('ux-chat-page'));assert.equal(nav.attrs['aria-current'],undefined);assert.equal(nodes.nav_chat.attrs['aria-current'],'page');assert.equal(labels.at(-1),'filter');
vm.runInContext('smartDockSet(false)',navctx);assert.ok(!classes.has('ux-chat-page'));assert.equal(labels.at(-1),'analytics');assert.equal(nav.attrs['aria-current'],'page');assert.equal(nodes.nav_chat.attrs['aria-current'],undefined);assert.ok(nodes.nav_chat.focused);
vm.runInContext("CUR_VIEW='quality';smartDockSet(false)",navctx);assert.equal(vm.runInContext('CUR_VIEW',navctx),'quality');
// Integrated charts follow the single topic navigation; no disclosure is required.
const definitions=JSON.parse(fs.readFileSync('web/metric_definitions.json','utf8')).metrics;
const panels=['structure','specialty','spatial','network'].map(kind=>({dataset:{detailPanel:kind},hidden:false}));
const wrappers=new Map();const ui=new Map();let chartInitializations=0;const instances=new Map();
const get=id=>{if(!ui.has(id))ui.set(id,{id,textContent:'',innerHTML:'',style:{},events:{},setAttribute(){},addEventListener(k,fn){(this.events[k]??=[]).push(fn);},closest(selector){if(selector==='.apanel'){if(!wrappers.has(id))wrappers.set(id,{hidden:false});return wrappers.get(id);}const group=id==='ch_distlv'||id==='ch_distmx'?'spatial':['ch_own','ch_lvown','ch_catown'].includes(id)?'structure':['ch_netlv','ch_srcmap','ch_coord'].includes(id)?'network':'specialty';if(selector==='[data-detail-panel][hidden]')return panels.find(p=>p.dataset.detailPanel===group&&p.hidden)||null;if(selector==='.apanel[hidden]')return wrappers.get(id)?.hidden?wrappers.get(id):null;return null;}});return ui.get(id);};
const lazy=vm.createContext({$:get,setText:(id,v)=>get(id).textContent=v,document:{querySelectorAll:s=>s==='[data-detail-panel]'?panels:[],querySelector:()=>null},echarts:{getInstanceByDom:n=>instances.get(n.id),init(n){chartInitializations++;const x={};instances.set(n.id,x);return x;}},initAnalyticsInteractions(){},updateDirectionChart(){},anExportCSV(){},anCopySummary(){},DATA:{institutions:rows,project_metrics:{definitions}},FILTERED:rows,esc:s=>String(s)});
vm.runInContext('let CH_OWN,CH_FEAT,CH_LVOWN,CH_TOPSP,CH_DEPTOP,CH_DISTLV,CH_COORD,CH_CATOWN,CH_SPDIST,CH_SPLV,CH_DISTMX,CH_NETLV,CH_SRCMAP;'+source.split('// DIRECTION_ANALYSIS_PURE_START')[1].split('// DIRECTION_ANALYSIS_PURE_END')[0]+source.slice(source.indexOf("let AN_DIRECTION="),source.indexOf('// 科室覆盖统一口径')),lazy);
vm.runInContext('initAnalyticsCharts();initAnalyticsCharts();renderDirectionAnalysis();',lazy);
assert.equal(chartInitializations,1,'region initializes its visible matrix without disclosure');assert.equal(get('an_direction_export').events.click.length,1);
for(const [topic,group] of [['primary','structure'],['evidence','specialty'],['network','network'],['quality','network']]){vm.runInContext("AN_DIRECTION='"+topic+"';initAnalyticsCharts();",lazy);assert.deepEqual(panels.filter(p=>!p.hidden).map(p=>p.dataset.detailPanel),[group]);}
assert.equal(wrappers.get('ch_netlv').hidden,true);assert.equal(wrappers.get('ch_srcmap').hidden,false);assert.equal(wrappers.get('ch_coord').hidden,false);
vm.runInContext("AN_DIRECTION='network';initAnalyticsCharts();",lazy);assert.equal(wrappers.get('ch_netlv').hidden,false);assert.equal(wrappers.get('ch_srcmap').hidden,true);assert.equal(get('an_direction_export').events.click.length,1);
assert.equal(chartInitializations,12,'all current charts initialized once; duplicate region ranking stays hidden');
console.log('PASS 专题聚合、指标、空集、导航返回、整合图表直接初始化、专题可见性和事件只绑定一次');
