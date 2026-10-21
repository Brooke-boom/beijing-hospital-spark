/* Headless DOM stubs test text rendering only; this is NOT a browser/visual test. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const snapshot = JSON.parse(fs.readFileSync('web/snapshot_data.json', 'utf8'));
const nodes = new Map();
const element = id => nodes.get(id) || (nodes.set(id, { innerHTML:'', value:'', textContent:'', addEventListener(){},
  querySelector(){return null}, querySelectorAll(){return []} }), nodes.get(id));
const context = { console, setTimeout, clearTimeout, URLSearchParams, Blob, URL,
  location:{protocol:'file:',hostname:'',port:'',hash:''},
  localStorage:{getItem(){return null},setItem(){}},
  document:{readyState:'loading',addEventListener(){},getElementById:element,querySelectorAll(){return []}},
  snapshotFixture:snapshot, navigator:{}, history:{replaceState(){}} };
context.window=context;
vm.createContext(context);
for (const file of ['web/app.query.js','web/app.nlq.js','web/app.js']) vm.runInContext(fs.readFileSync(file,'utf8'),context,{filename:file});
vm.runInContext('DATA = snapshotFixture; NLQ.init(' + fs.readFileSync('web/nlq_lexicon.json','utf8') + '.lex); renderMetricLedger();',context);
assert.match(element('metric_ledger').innerHTML,/当前批次指标/);
assert.ok(element('metric_ledger').innerHTML.includes(snapshot.project_metrics.fingerprint));
const mixed = {depts:'骨科;儿科',recorded_depts:'骨科',dept_evidence:{骨科:['online'],儿科:['name','rule']}};
context.mixed=mixed;
const html=vm.runInContext('deptsLocalHTML(mixed)',context);
assert.match(html,/有来源记录/);assert.match(html,/推断映射/);assert.match(html,/机构名称推断/);
assert.match(html,/检查项目映射到科室，不证明/);
context.hostile={depts:'<img src=x onerror=bad()>',recorded_depts:'',dept_evidence:{}};
assert.ok(!vm.runInContext('deptsLocalHTML(hostile)',context).includes('<img'));
vm.runInContext("FILTERED=[]; renderQueryExplanation({district:'海淀区',level:'三级',kw:'不存在的测试机构'},BASE_POINTS.tiananmen)",context);
assert.match(element('query_explain').innerHTML,/单独命中/);
assert.match(element('query_explain').innerHTML,/data-relax="f_kw"/);
assert.match(element('query_explain').innerHTML,/可尝试取消/);
assert.match(vm.runInContext("coordPrecisionText('rough')",context),/不参与半径筛选/);
console.log('PASS 指标渲染、混合来源标签、转义、零结果放宽动作、坐标精度说明（DOM 桩，不含视觉检查）');

// Compile every inline script in the delivered offline bundle, including the snapshot.
const bundle = fs.readFileSync('web/dashboard_offline.html','utf8');
let scripts=0;
for (const match of bundle.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
  if (match[1].trim()) { new vm.Script(match[1]); scripts++; }
}
assert.ok(scripts >= 7);
assert.match(bundle,/QueryAudit/);
assert.match(bundle,/当前批次指标与计算口径/);
for (const label of ['查询与筛选','资源分析','数据治理','系统信息']) assert.ok(bundle.includes(label));
console.log('PASS 离线产物 '+scripts+' 段内联脚本可编译，包含解释引擎、指标与导航分组');
