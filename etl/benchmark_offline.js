/* Read-only, reproducible engine timing; no network or AI requests. */
const fs = require('node:fs');
const os = require('node:os');
const crypto = require('node:crypto');
const { performance } = require('node:perf_hooks');
const { NLQ } = require('../web/app.nlq.js');
const audit = require('../web/app.query.js');
const snapshot = JSON.parse(fs.readFileSync(require.resolve('../web/snapshot_data.json'), 'utf8'));
NLQ.init(require('../web/nlq_lexicon.json').lex);
const base = { lng: 116.397428, lat: 39.90923 };
const samples = Number(process.env.BENCH_SAMPLES || 30);
if (!Number.isInteger(samples) || samples < 10 || samples > 1000) throw Error('BENCH_SAMPLES must be 10..1000');
const scenarios = [
  { name: '三甲医院：解析、筛选、解释', run: () => NLQ.runFilter(snapshot.institutions, NLQ.parse('三甲医院').conditions, 1, 20, base).total },
  { name: '天安门5公里内三甲医院：解析、筛选、解释', run: () => NLQ.runFilter(snapshot.institutions, NLQ.parse('天安门5公里内的三甲医院').conditions, 1, 20, base).total },
  { name: '骨科来源记录：列表筛选与逐条件解释', run: () => {
    const c = { dept: '骨科', dept_evidence: 'recorded' };
    const n = snapshot.institutions.filter(r => audit.matches(r, c, base, NLQ)).length;
    audit.explain(snapshot.institutions, c, base, NLQ, n); return n;
  } },
];
const results = scenarios.map(s => {
  for (let i = 0; i < 3; i++) s.run();
  const times = [], counts = new Set();
  for (let i = 0; i < samples; i++) { const start = performance.now(); counts.add(s.run()); times.push(performance.now() - start); }
  if (counts.size !== 1) throw Error('同批次重复查询结果不稳定');
  times.sort((a, b) => a - b);
  const r = n => Math.round(n * 100) / 100;
  return { name: s.name, samples, warmups: 3, concurrency: 1, total: [...counts][0],
    mean_ms: r(times.reduce((a,b)=>a+b,0)/samples), p95_ms: r(times[Math.ceil(samples*.95)-1]),
    min_ms: r(times[0]), max_ms: r(times[times.length-1]) };
});
console.log(JSON.stringify({ kind: 'offline_engine', runtime: process.version, platform: process.platform,
  arch: process.arch, cpu: os.cpus()[0]?.model, snapshot_date: snapshot.snapshot_time,
  fingerprint: snapshot.project_metrics?.fingerprint,
  engine_sha256: crypto.createHash('sha256').update(fs.readFileSync(require.resolve('../web/app.query.js'))).digest('hex'),
  limitation: 'Node.js 单进程引擎耗时，不含浏览器绘制、HTTP、MySQL、Spark；不代表在线接口性能。', results }, null, 2));
