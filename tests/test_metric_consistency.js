// Cross-page contracts use real UI functions plus an independent ledger reference.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/app.js','utf8'),snapshot=JSON.parse(fs.readFileSync('web/snapshot_data.json','utf8'));
const definitions=JSON.parse(fs.readFileSync('web/metric_definitions.json','utf8')).metrics;
assert.deepEqual(snapshot.project_metrics.definitions,definitions);
const labels=new Map();const c={DATA:snapshot,setText:(id,v)=>labels.set(id,v),num:v=>String(v),$:()=>null,dqv:()=>({sourceFiles:70})};vm.createContext(c);
vm.runInContext(source.split('// DIRECTION_ANALYSIS_PURE_START')[1].split('// DIRECTION_ANALYSIS_PURE_END')[0],c);
vm.runInContext(source.slice(source.indexOf('function renderOverviewKPI()'),source.indexOf('// ---------- 数据整合中心')),c);
c.renderOverviewKPI();const ledger=Object.fromEntries(snapshot.project_metrics.metrics.map(m=>[m.key,m.value]));
const grouped=c.directionRows(snapshot.institutions,[]);
for(const [id,key,field] of [['v_total','institutions','total'],['v_hospitals','hospitals','hospital'],['v_community','community','community']]){assert.equal(Number(labels.get(id)),ledger[key]);assert.equal(grouped.reduce((s,r)=>s+r[field],0),ledger[key]);}
assert.equal(ledger.community,1455);assert.equal(ledger.hospitals,681);assert.equal(ledger.tertiary,180);
for(const [field,key] of [['l3','tertiary'],['mapped','dept_covered'],['recorded','dept_recorded']])assert.equal(grouped.reduce((s,r)=>s+r[field],0),ledger[key]);
for(const key of Object.keys(definitions))assert.equal(c.metricCount(snapshot.institutions,key),ledger[key]);
// Name and class conflict: names never override standardized categories.
const contradictory=[{id:'x',name:'社区卫生服务中心',category:'诊所'},{id:'y',name:'甲机构',category:'社区卫生服务站'},{id:'z',category:'其他机构'}];
assert.equal(c.metricCount(contradictory,'community'),1);assert.equal(c.directionRows(contradictory,[]).reduce((s,r)=>s+r.community,0),1);
assert.equal(c.metricCount([],'community'),0);assert.equal(c.metricCount([{lng:0,lat:0},{lng:1}], 'coordinates'),1);
for(const district of ['昌平区','朝阳区','海淀区']){const rows=snapshot.institutions.filter(r=>r.district===district);const groups=c.directionRows(rows,[]);for(const [key,field] of [['community','community'],['hospitals','hospital'],['tertiary','l3'],['dept_recorded','recorded']])assert.equal(c.metricCount(rows,key),groups.reduce((s,r)=>s+r[field],0));}
const batch=JSON.parse(fs.readFileSync('web/analysis_batch.json','utf8'));for(const [field,key] of [['total','institutions'],['tertiary','tertiary'],['recorded','dept_recorded']])assert.equal(batch.tables.district.reduce((s,r)=>s+r[field],0),ledger[key]);for(const row of batch.tables.quality)assert.equal(row.count,ledger['coord_'+row.coord_precision]);
console.log('PASS 指标台账、总览、专题、Spark批次、筛选子集、名称类别冲突及空集口径一致');
