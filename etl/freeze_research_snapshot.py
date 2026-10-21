"""Freeze current ADS export as line-delimited Spark input and its metadata."""
import json,hashlib,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1];p=r/'web/snapshot_data.json';x=json.loads(p.read_text());out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
(out/'snapshot.jsonl').write_text('\n'.join(json.dumps(row,ensure_ascii=False) for row in x['institutions']))
(out/'input_meta.json').write_text(json.dumps({'snapshot_date':x['snapshot_time'],'fingerprint':x['project_metrics']['fingerprint'],'institution_count':len(x['institutions']),'snapshot_sha256':hashlib.sha256(p.read_bytes()).hexdigest()},ensure_ascii=False,indent=2))
