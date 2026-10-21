#!/usr/bin/env python3
import csv,json,sys,statistics
from pathlib import Path
rows=list(csv.DictReader(open(sys.argv[1],encoding='utf-8-sig')))
seen=set();done=[]
for r in rows:
 key=(r['participant'],r['task']);assert key not in seen,'duplicate participant/task';seen.add(key)
 assert r['status'] in ('pending','success','assisted','fail')
 if r['status']=='pending':continue
 assert r['participant'] and r['task'] in ('T1','T2','T3','T4','T5')
 r['seconds']=float(r['seconds']);assert 0<=r['seconds']<=180
 for k in ['errors','helps']:r[k]=int(r[k]);assert r[k]>=0
 assert r['status']!='success' or r['helps']==0,'success requires zero help'
 done.append(r)
people={r['participant'] for r in done};complete=all(sum(r['participant']==p for r in done)==5 for p in people)
out={'status':'pending' if not done else 'partial' if not complete or not 3<=len(people)<=5 else 'recorded_pending_human_review','participants':len(people),'completed_rows':len(done),'tasks':{},'limitation':'self-reported real trial records; convenience sample, no population inference'}
for task in ['T1','T2','T3','T4','T5']:
 x=[r for r in done if r['task']==task];n=len(x)
 out['tasks'][task]={'n':n,'success':sum(r['status']=='success' for r in x),'assisted':sum(r['status']=='assisted' for r in x),'fail':sum(r['status']=='fail' for r in x),'success_rate':sum(r['status']=='success' for r in x)/n if n else None,'median_seconds':statistics.median(r['seconds'] for r in x) if n else None,'errors':sum(r['errors'] for r in x),'helps':sum(r['helps'] for r in x)}
Path(sys.argv[2]).write_text(json.dumps(out,ensure_ascii=False,indent=2));print(out['status'])
