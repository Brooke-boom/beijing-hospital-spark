const assert = require('node:assert/strict');
const { NLQ } = require('../web/app.nlq.js');
const audit = require('../web/app.query.js');
NLQ.init(require('../web/nlq_lexicon.json').lex);
const base = { lng: 116.397428, lat: 39.90923 };
const rows = [
  { id: '1', name: '来源骨科', district: '东城区', level: '三级', level_sub: '甲等', depts: '骨科;儿科', recorded_depts: '骨科', coord_precision: 'high', ...base, net_stroke: '1' },
  { id: '2', name: '推断骨科', district: '东城区', level: '三级', level_sub: '乙等', depts: '骨科;儿科', recorded_depts: '儿科', coord_precision: 'rough', ...base },
  { id: '3', name: '无来源骨科', district: '海淀区', level: '二级', level_sub: '甲', depts: '骨科', recorded_depts: '', coord_precision: 'high', ...base },
];
let tests = 0;
function check(name, fn) { fn(); tests++; console.log('PASS ' + name); }
const ids = c => rows.filter(r => audit.matches(r, c, base, NLQ)).map(r => r.id);
check('科室证据属于所选科室，而非机构任意科室', () => assert.deepEqual(ids({ dept: '骨科', dept_evidence: 'recorded' }), ['1']));
check('不指定科室时证据条件仍生效', () => assert.deepEqual(ids({ dept_evidence: 'recorded' }), ['1', '2']));
check('等级与等次联合匹配', () => assert.deepEqual(ids({ level: '三级', level_sub: '甲等' }), ['1']));
check('等次简称与全称兼容', () => assert.deepEqual(ids({ level_sub: '甲等' }), ['1', '3']));
check('半径排除粗精度', () => assert.deepEqual(ids({ radius: 5 }), ['1', '3']));
check('无效半径不静默退化为全量结果', () => [0, -1, 201, 'nan', Infinity].forEach(radius => assert.throws(() => ids({ radius }))));
check('旧快照证据缺失明确报错', () => assert.throws(() => audit.matches({ depts: '骨科' }, { dept_evidence: 'recorded' }, base, NLQ)));
check('协作网络数字与字符串兼容', () => assert.equal(audit.matches({ ...rows[0], net_stroke: 1 }, { network: 'stroke' }, base, NLQ), true));
check('零结果解释给出真实可恢复集合', () => {
  const c = { district: '海淀区', level: '三级' };
  const ex = audit.explain(rows, c, base, NLQ, ids(c).length);
  assert.equal(ex.total, 0); assert.equal(ex.suggestions.length, 2);
  assert.equal(ex.items.find(x => x.key === 'district').keep_n, 2);
  assert.equal(ex.items.find(x => x.key === 'level').keep_n, 1);
});
check('取消证据条件不改变其余条件', () => {
  const c = { dept: '骨科', dept_evidence: 'recorded', district: '东城区' };
  const ex = audit.explain(rows, c, base, NLQ, ids(c).length);
  const ev = ex.items.find(x => x.key === 'dept_evidence');
  assert.equal(ev.alone_n, 2); assert.equal(ev.keep_n, 2); assert.equal(ev.drop_n, 1);
  assert.equal(c.dept_evidence, 'recorded');
});
console.log(JSON.stringify({ tests, status: 'passed' }));
