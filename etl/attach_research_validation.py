"""Attach matching experiment summaries without altering aggregate rows."""
from pathlib import Path
import json
r=Path(__file__).resolve().parents[1];p=r/'web/analysis_batch.json';b=json.loads(p.read_text());v=json.loads((r/'data/processed/research_analysis/verification.json').read_text());c=json.loads((r/'data/processed/research_analysis/cluster.json').read_text())
assert v['all_passed'] and v['fingerprint']==b['meta']['fingerprint']
b['validation']={'checks':len(v['checks']),'all_passed':True,'query':[ {k:e[k] for k in ['mode','warmups','samples','concurrency','median_ms','p95_ms']} for e in v['mysql_experiment']],'cluster_runs':len(c['runs']),'cluster_note':'16区、k=2至5、种子7和42；分组对随机种子敏感，仅作结构探索。'}
p.write_text(json.dumps(b,ensure_ascii=False,indent=2))
