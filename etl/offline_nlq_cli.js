// ============================================================================
//  离线自然语言筛选引擎的 Node 入口（仅供校验脚本调用，不参与页面加载）
// ----------------------------------------------------------------------------
//  用法：
//    node etl/offline_nlq_cli.js <<'JSON'
//    {"queries": ["朝阳区三级医院"], "dept_names": ["骨科"], "cases": [...]}
//    JSON
//  输入 JSON 支持两种模式：
//    · queries  —— 只跑解析，返回每条的 conditions / intent / applied
//    · cases    —— 编译条件后跑筛选与统计，返回条数与首位机构
//  输出：{"ok": true, "results": [...]}
//
//  目的：让 etl/verify_offline_nlq.py 能把「Python 侧」与「浏览器侧」的同一批
//  输入逐字段比对。没有这个入口，前端引擎就只能靠肉眼看，等于没有回归保护。
// ============================================================================
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const { NLQ } = require(path.join(ROOT, 'web', 'app.nlq.js'));

const lexPayload = JSON.parse(fs.readFileSync(path.join(ROOT, 'web', 'nlq_lexicon.json'), 'utf8'));
NLQ.init(lexPayload.lex);

const snap = JSON.parse(fs.readFileSync(path.join(ROOT, 'web', 'snapshot_data.json'), 'utf8'));
const INSTS = snap.institutions;

let raw = '';
process.stdin.on('data', (c) => { raw += c; });
process.stdin.on('end', () => {
  let req;
  try {
    req = JSON.parse(raw || '{}');
  } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, error: 'bad input: ' + e.message }));
    return;
  }
  const deptNames = req.dept_names || null;
  const out = [];

  (req.queries || []).forEach((q) => {
    const r = NLQ.parse(q, deptNames);
    out.push({
      query: q,
      intent: r.intent,
      dimension: r.dimension || null,
      chart: r.chart || null,
      conditions: r.conditions,
      applied: r.applied.map((c) => c.label + '=' + c.text),
      unmatched: r.unmatched,
      message: r.message || '',
      notice: r.notice || null,
    });
  });

  (req.cases || []).forEach((c) => {
    const r = NLQ.runFilter(INSTS, c.conditions || {}, 1, c.page_size || 20);
    const first = r.items[0] || null;
    const rec = {
      name: c.name,
      total: r.total,
      returned: r.items.length,
      sort: r.sort,
      first_id: first ? String(first.id) : null,
      first_name: first ? first.name : null,
      stats: r.stats || null,
      unsupported: r.unsupported || null,
    };
    if (c.with_stats) {
      const dim = c.dimension || 'district';
      const st = NLQ.runStats(INSTS, c.conditions || {}, dim);
      rec.stats_rows = st.rows.map((x) => [x.name, x.cnt]);
      rec.stats_total = st.rows.reduce((a, b) => a + b.cnt, 0);
      rec.stats_summary = st.summary;
    }
    out.push(rec);
  });

  process.stdout.write(JSON.stringify({ ok: true, results: out }));
});
