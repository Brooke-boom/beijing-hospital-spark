const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const snapshot=JSON.parse(fs.readFileSync('web/snapshot_data.json','utf8'));
const nodes=new Map(),node=id=>nodes.get(id)||(nodes.set(id,{innerHTML:'',value:'',textContent:'',style:{},addEventListener(){},querySelector(){return null;},querySelectorAll(){return[];}}),nodes.get(id));
const c={console,setTimeout(){},clearTimeout(){},URLSearchParams,Blob,URL,location:{protocol:'file:',hostname:'',port:'',hash:''},document:{readyState:'loading',addEventListener(){},getElementById:node,querySelectorAll(){return[];}},localStorage:{getItem(){return null;}},navigator:{},matchMedia(){return{matches:false};},snapshot};c.window=c;vm.createContext(c);
vm.runInContext(fs.readFileSync('web/app.js','utf8'),c);vm.runInContext('DATA=snapshot;FILTERED=DATA.institutions;',c);
function run(code){return vm.runInContext(code,c);}
const sum=s=>s.reduce((n,v)=>n+Number(typeof v==='object'?v.value:v),0);
for(const fn of ['anCatOwnOpt()','anLvOwnOpt()','anNetLvOpt(FILTERED)','anDistMxOpt(FILTERED)','anFeatOpt(FILTERED)','anSrcMapOpt(FILTERED)']){
 const option=run(fn);assert.ok(option);assert.equal(option.yAxis.type,'category');assert.ok(option.series.every(s=>s.type==='bar'),fn);assert.equal(option.animation,false);assert.ok(option.series.every(s=>s.data.length===option.yAxis.data.length));
}
for(const fn of ['anOwnershipOpt(FILTERED)','anCoordOpt(FILTERED)']){const option=run(fn);assert.equal(option.series[0].type,'pie');assert.equal(option.animation,false);assert.equal(option.series[0].radius.length,2);assert.equal(option.series[0].data.length,3);assert.ok(!option.xAxis&&!option.yAxis);}
for(const fn of ['anSpDistOpt(FILTERED)','anSpLvOpt(FILTERED)']){const option=run(fn);assert.equal(option.xAxis.type,'category');assert.equal(option.yAxis.type,'value');assert.equal(option.yAxis.min,0);assert.ok(!Array.isArray(option.yAxis));assert.ok(option.series.every(s=>s.type==='bar'&&!s.stack));assert.ok(option.series.every(s=>s.data.length===option.xAxis.data.length));}
assert.equal(sum(run('anOwnershipOpt(FILTERED)').series[0].data),9678);
assert.equal(sum(run('anCoordOpt(FILTERED)').series[0].data),9678);
assert.equal(sum(run('anCatOwnOpt()').series.flatMap(s=>s.data)),9678);
assert.equal(sum(run('anLvOwnOpt()').series.flatMap(s=>s.data)),snapshot.institutions.filter(r=>['三级','二级','一级','未定级'].includes(r.level)).length);
assert.equal(sum(run('anSpDistOpt(FILTERED)').series[0].data),snapshot.institutions.filter(r=>r.national_specialty||r.municipal_specialty).length);
assert.equal(sum(run('anSpLvOpt(FILTERED)').series.flatMap(s=>s.data)),run('FILTERED.reduce((n,r)=>n+specialtyMetrics(r).national.length+specialtyMetrics(r).municipal.length,0)'));
assert.equal(sum(run('anFeatOpt(FILTERED)').series[0].data),9678);
assert.equal(sum(run('anSrcMapOpt(FILTERED)').series[0].data),9678);
assert.equal(run("anCoordOpt(FILTERED).series[0].label.formatter({name:'未收录',value:3})"),'未收录\n0.03%');
assert.match(run("anCoordOpt(FILTERED).legend.formatter('未收录')"),/未收录 3 · 0.03%/);
run("FILTERED=DATA.institutions.filter(r=>r.district==='海淀区'&&r.level==='三级');AN_REGION_METRIC='l3';");
assert.equal(sum(run('anCatOwnOpt()').series.flatMap(s=>s.data)),28);assert.equal(sum(run('anDistMxOpt(FILTERED)').series[0].data),28);
run('FILTERED=[];');assert.equal(run('anCatOwnOpt()'),null);assert.equal(run('anDistMxOpt(FILTERED)'),null);assert.equal(run('anCoordOpt(FILTERED)'),null);
const escaped=run("analysisBars(['<img onerror=bad()>'],[{name:'测试',values:[1]}]).tooltip.formatter([{dataIndex:0,seriesName:'测试',value:1,marker:''}])");assert.ok(!escaped.includes('<img'));assert.ok(escaped.includes('&lt;img'));
c.fixtureId=null;run("openDrawer=id=>fixtureId=id;AN_TOPSP_ROWS=[{id:'exact-id',name:'很长机构名称'}];CH_TOPSP={off(){},on(event,handler){globalTopHandler=handler;}};initAnalyticsInteractions();globalTopHandler({dataIndex:0,name:'很长机构…'});");assert.equal(c.fixtureId,'exact-id');
console.log('PASS 环形/分组柱状/条形图的类型、单轴和总量、当前筛选口径、坐标小比例、空结果、转义、机构排名详情下钻');
