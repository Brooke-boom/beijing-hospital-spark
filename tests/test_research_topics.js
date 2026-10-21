const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const code=fs.readFileSync(process.env.ANALYSIS_SOURCE||'web/app.js','utf8'),data=JSON.parse(fs.readFileSync('web/snapshot_data.json')),batch=JSON.parse(fs.readFileSync('web/analysis_batch.json'));
const nodes=new Map(),charts=[];const c={window:{__RESEARCH__:batch,matchMedia:()=>({matches:false})},DATA:data,FILTERED:data.institutions,CUR_VIEW:'analytics',AN_DIRECTION_CHART:null,emptyOpt:()=>({series:[]}),AN_DIRECTION:'region',ACC:'#2468c8',INK:'#111',SUB:'#555',CHART_AXIS:'#555',EDGE:'#ddd',TIP:{},LEGEND:{},num:x=>String(x),esc:x=>String(x),$:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id)},echarts:{init:()=>{const x={setOption(o){this.option=o},resize(){},handlers:{},off(e){delete this.handlers[e]},on(e,fn){this.handlers[e]=fn}};charts.push(x);return x}}};
vm.createContext(c);vm.runInContext(code.slice(code.indexOf('function analysisBars('),code.indexOf('function anOwnershipOpt(')),c);vm.runInContext(code.split('// DIRECTION_ANALYSIS_PURE_START')[1].split('// DIRECTION_ANALYSIS_PURE_END')[0],c);vm.runInContext(code.slice(code.indexOf('let AN_SECONDARY_CHART='),code.indexOf('function setAnalysisDetail')),c);
const run=kind=>{c.AN_DIRECTION=kind;vm.runInContext('updateDirectionChart(directionRows(FILTERED,[]))',c);return charts.map(x=>x.option)};
for(const kind of ['region','primary','evidence','network','quality']){const opts=run(kind);assert.equal(opts.length,2);assert.ok(opts.every(x=>x.series?.length));assert.ok(nodes.get('an_question').textContent);assert.ok(!JSON.stringify(opts).match(/NaN|Infinity/));}
let o=run('region');assert.equal(o[1].series[0].data.reduce((n,x)=>n+x[2],0),9678);
nodes.get('an_region_focus').value='tertiary';o=run('region');assert.equal(o[0].series[0].data.reduce((n,x)=>n+x,0),180);assert.deepEqual(Array.from(o[0].series[0].data.slice(0,3)),[28,28,28]);assert.match(nodes.get('an_direction_chart_title').textContent,/三级/);nodes.get('an_region_focus').value='total';
o=run('primary');for(let i=0;i<16;i++)assert.ok(Math.abs(o[0].series.reduce((n,s)=>n+s.data[i],0)-100)<.04);
o=run('network');const cells=o[1].series[0].data;assert.equal(cells.find(x=>x[0]===0&&x[1]===1)[2],cells.find(x=>x[0]===1&&x[1]===0)[2]);
const full=JSON.stringify(run('evidence')[1].series[0].data);c.window.__RESEARCH__=null;assert.equal(JSON.stringify(run('evidence')[1].series[0].data),full,'Spark and browser cells must match');c.window.__RESEARCH__=batch;
c.FILTERED=data.institutions.filter(r=>r.district==='海淀区'&&r.level==='三级');run('region');assert.match(nodes.get('an_batch_status').textContent,/按当前筛选范围统计/);assert.equal(charts[1].option.series[0].data.reduce((n,x)=>n+x[2],0),c.FILTERED.length);
c.FILTERED=[];for(const k of ['region','primary','evidence','network','quality'])run(k);
console.log('PASS 五专题、矩阵总量、百分比堆叠、网络对称性、Spark与浏览器逐格一致、子集与空集');

c.FILTERED=data.institutions;c.AN_DIRECTION="region";c.document={querySelectorAll:()=>[]};c.$("an_direction_panel").setAttribute=()=>{};c.$("an_region_focus").value="tertiary";vm.runInContext(code.slice(code.indexOf("function renderDirectionAnalysis()"),code.indexOf("function initAnalysisToolbar()")),c);c.renderDirectionAnalysis();assert.match(nodes.get("an_direction_insight").textContent,/当前三级记录 180/);assert.doesNotMatch(nodes.get("an_direction_insight").textContent,/昌平区、朝阳区、房山区/);console.log("PASS 指标切换后最终摘要保持三级口径");

c.FILTERED=data.institutions;c.$('an_region_measure').value='share';o=run('region');assert.ok(Math.abs(o[0].series[0].data.reduce((n,x)=>n+x,0)-100)<.1);let ex=vm.runInContext('AN_MAIN_EXPORT',c);assert.ok(ex.slice(1).every(r=>r[2]===180));
c.$('an_region_measure').value='local';run('region');ex=vm.runInContext('AN_MAIN_EXPORT',c);for(const r of ex.slice(1)){const den=data.institutions.filter(x=>x.district===r[0]).length;assert.equal(r[2],den);assert.equal(r[3],+(r[1]/den*100).toFixed(2));}
c.$('an_region_focus').value='total';run('region');assert.equal(c.$('an_region_measure').value,'count');
o=run('evidence');assert.equal(o[0].series[0].type,'bar');ex=vm.runInContext('AN_MAIN_EXPORT',c);assert.equal(ex.slice(1).reduce((n,r)=>n+r[1],0),772);assert.equal(ex.slice(1).reduce((n,r)=>n+r[2],0),9678);assert.match(c.$('an_scope_summary').innerHTML,/5973/);
o=run('network');assert.deepEqual(Array.from(o[0].series[0].data),[44,67,7,18]);assert.match(c.$('an_scope_summary').innerHTML,/89/);assert.match(c.$('an_direction_insight').textContent,/92/);
o=run('quality');assert.ok(Math.abs(o[1].series.reduce((n,s)=>n+s.data[0],0)-100)<.03);
console.log('PASS 数量和两种比例分母、主图导出、来源覆盖分母、网络去重、坐标百分比构成');

let lastDrill,evidenceValue;c.anDrill=q=>lastDrill=q;c.anSetSel=(k,v)=>evidenceValue=v;c.$('an_region_focus').value='tertiary';c.$('an_region_measure').value='count';o=run('region');charts[0].handlers.click({dataIndex:0});assert.equal(lastDrill.level,'三级');assert.equal(lastDrill.district,o[0].yAxis.data[0]);
o=run('evidence');const hit=o[1].series[0].data.find(x=>x[2]>0);charts[1].handlers.click({data:hit});assert.equal(evidenceValue,'recorded');assert.ok(lastDrill.dept);const frozen=lastDrill;charts[1].handlers.click({data:[0,0,0]});assert.equal(lastDrill,frozen);
run('network');assert.ok(!charts[0].handlers.click);assert.match(JSON.stringify(vm.runInContext('AN_TOPIC_EXPORT',c)),/合并去重/);
console.log('PASS 三级排序下钻、科室来源矩阵下钻、零值不下钻、网络无错误区域跳转及去重导出');

c.FILTERED=data.institutions.filter(r=>!r.recorded_depts);o=run('evidence');assert.ok(o[0].series[0].data.every(x=>x===0));assert.equal(o[1].series.length,0);console.log('PASS 无来源子集展示零覆盖并明确明细为空');

let copied;c.FILTERED=data.institutions;run('evidence');c.UX={clipboard:t=>copied=t};c.track=()=>{};c.location={hash:'#v=analytics'};const copyStart=code.indexOf('function anCopySummary() {');vm.runInContext(code.slice(copyStart,code.indexOf('\n// ============================================================================',copyStart)),c);c.anCopySummary();assert.match(copied,/489/);assert.match(copied,/来源支持的科室记录覆盖率/);assert.match(copied,/解读边界/);assert.match(copied,/9678/);console.log('PASS 复制文本使用当前专题指标、范围、发现与限制');
