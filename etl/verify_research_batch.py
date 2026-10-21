"""Read-only source/snapshot/Spark/MySQL consistency and index experiment."""
import json,csv,hashlib,time,statistics,platform,sys
from pathlib import Path
import pymysql
ROOT=Path(__file__).resolve().parents[1];batch=json.loads((ROOT/'web/analysis_batch.json').read_text());snap=json.loads((ROOT/'web/snapshot_data.json').read_text());rows=snap['institutions']
sys.path.insert(0,str(ROOT/'web'));from app import DB_CONFIG
c=pymysql.connect(**DB_CONFIG);cur=c.cursor()
checks=[]
def check(name,ok,detail):checks.append({'name':name,'passed':bool(ok),'detail':detail})
cur.execute('SELECT id,name,district,level_norm,coord_precision FROM ads_inst_search');db=cur.fetchall();a={str(r['id']):r for r in rows};b={str(r['id']):r for r in db}
check('snapshot_vs_mysql_ids',set(a)==set(b),{'snapshot':len(a),'mysql':len(b)})
check('snapshot_vs_mysql_fields',all(str(a[k].get('name') or '')==str(b[k].get('name') or '') and str(a[k].get('district') or '')==str(b[k].get('district') or '') and str(a[k].get('level') or '')==str(b[k].get('level_norm') or '') and str(a[k].get('coord_precision') or '')==str(b[k].get('coord_precision') or '') for k in set(a)&set(b)), 'name/district/level/coord_precision per ID')
for key,expected in batch['tables'].items():
 cur.execute('SELECT * FROM ads_research_'+key);actual=cur.fetchall();norm=lambda rs:sorted(json.dumps(r,sort_keys=True,ensure_ascii=False,default=str) for r in rs);check('spark_vs_mysql_'+key,norm(actual)==norm(expected),{'rows':len(actual)})
for g in batch['tables']['district']:
 sub=[r for r in rows if r['district']==g['district']];check('page_aggregation_'+g['district'],len(sub)==g['total'] and sum(r['level']=='三级' for r in sub)==g['tertiary'] and sum(bool(r['recorded_depts']) for r in sub)==g['recorded'],{'total':len(sub)})
source=ROOT/'data/processed/hospital_master.csv'
if source.exists():
 with source.open(encoding='utf-8-sig') as f:src=list(csv.DictReader(f))
 check('source_master_vs_snapshot_count',len(src)==len(rows),{'source_file':source.name,'source':len(src),'snapshot':len(rows),'note':'count check only; snapshot contains enrichment'})
cur.execute('SHOW INDEX FROM ads_inst_search');indices=sorted({r['Key_name'] for r in cur.fetchall() if r['Key_name']!='PRIMARY'})
ignore=' IGNORE INDEX ('+','.join('`'+x.replace('`','``')+'`' for x in indices)+')' if indices else ''
base="SELECT SQL_NO_CACHE id,name FROM ads_inst_search{} WHERE district=%s AND level_norm=%s ORDER BY name LIMIT 20";params=('海淀区','三级');experiments=[]
for label,hint in [('existing_indexes',''),('ignore_secondary_indexes',ignore)]:
 sql=base.format(hint);cur.execute('EXPLAIN '+sql,params);plan=cur.fetchall();times=[];ids=[]
 for i in range(35):
  t=time.perf_counter();cur.execute(sql,params);result=cur.fetchall();dt=(time.perf_counter()-t)*1000
  if i>=5:times.append(dt)
  ids=[r['id'] for r in result]
 experiments.append({'mode':label,'warmups':5,'samples':30,'concurrency':1,'mean_ms':round(statistics.mean(times),3),'median_ms':round(statistics.median(times),3),'p95_ms':round(sorted(times)[28],3),'raw_ms':times,'ids':ids,'explain':plan})
check('index_experiment_same_results',experiments[0]['ids']==experiments[1]['ids'],{'rows':len(ids)})
report={'snapshot_date':snap['snapshot_time'],'fingerprint':batch['meta']['fingerprint'],'spark':batch['meta'],'checks':checks,'all_passed':all(x['passed'] for x in checks),'mysql_experiment':experiments,'environment':{'python':platform.python_version(),'platform':platform.platform()},'limits':['This is a frozen ADS snapshot topic rerun, not upstream ODS/DWD replay.','MySQL experiment compares existing indexes with IGNORE INDEX on one read-only query; it is not a before/after production benchmark.','Timing excludes browser rendering, concurrency and model latency.']}
out=ROOT/'data/processed/research_analysis';out.mkdir(exist_ok=True);(out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str));print(json.dumps({'all_passed':report['all_passed'],'checks':len(checks),'query_timings':[{k:v for k,v in x.items() if k in ['mode','mean_ms','median_ms','p95_ms']} for x in experiments]},ensure_ascii=False));c.close()
if not report['all_passed']:raise SystemExit(1)
