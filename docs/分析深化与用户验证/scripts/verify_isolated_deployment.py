#!/usr/bin/env python3
"""Fresh MySQL volume + copied web source. Existing services are read only.
Requires Docker, cached mysql:8.0 and this Python's Flask/PyMySQL.
Source DB credentials: SOURCE_DB_PASSWORD env; never written to report.
"""
import argparse,subprocess,tempfile,os,time,json,sys,shutil,socket,hashlib,urllib.request,urllib.parse,secrets,importlib.metadata
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--source-container',default='hospital-mysql');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
pw=os.environ['SOURCE_DB_PASSWORD'];newpw=secrets.token_hex(18);token=secrets.token_hex(5);name='thesis-verify-'+token;volume=name+'-db';proc=None;report={'scope':'fresh MySQL volume + copied web source; no upstream ETL rebuild','isolated_python':sys.prefix!=sys.base_prefix,'python_prefix':sys.prefix,'checks':[],'python':sys.version,'packages':{n:importlib.metadata.version(n) for n in ['flask','pymysql','requests']}}
def run(args,**kw):return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)
def check(label,ok,detail):
 report['checks'].append({'name':label,'passed':bool(ok),'detail':detail});assert ok,label
with tempfile.TemporaryDirectory(prefix='thesis-deploy-') as temp:
 root=Path(temp);web=root/'web';shutil.copytree(a.project/'web',web,ignore=shutil.ignore_patterns('__pycache__*','*.log','_legacy'))
 # Doctor source files are relative to project/data; only copy the public doctor dataset.
 data=a.project/'data';(root/'data').mkdir()
 if (data/'doctors').exists():shutil.copytree(data/'doctors',root/'data/doctors')
 try:
  dump=run(['docker','exec','-e','MYSQL_PWD='+pw,a.source_container,'mysqldump','-uroot','--single-transaction','--skip-lock-tables','--no-tablespaces','hospital']).stdout
  check('database_export',len(dump)>1000,{'bytes':len(dump),'sha256':hashlib.sha256(dump).hexdigest()})
  run(['docker','volume','create',volume]);run(['docker','run','-d','--name',name,'-e','MYSQL_ROOT_PASSWORD='+newpw,'-e','MYSQL_DATABASE=hospital','-p','127.0.0.1::3306','-v',volume+':/var/lib/mysql','mysql:8.0'])
  for _ in range(90):
   try:
    run(['docker','exec','-e','MYSQL_PWD='+newpw,name,'mysql','-uroot','-e','SELECT 1']);break
   except subprocess.CalledProcessError:time.sleep(1)
  else:raise RuntimeError('fresh mysql startup timeout')
  run(['docker','exec','-i','-e','MYSQL_PWD='+newpw,name,'mysql','-uroot','hospital'],input=dump)
  port=int(run(['docker','port',name,'3306/tcp']).stdout.decode().strip().rsplit(':',1)[1]);sock=socket.socket();sock.bind(('127.0.0.1',0));httpport=sock.getsockname()[1];sock.close()
  env={**os.environ,'DB_HOST':'127.0.0.1','DB_PORT':str(port),'DB_USER':'root','DB_PASS':newpw,'PYTHONPATH':str(web),'AI_API_KEY':''}
  command=[sys.executable,'-c',f'import app; app.app.run(host="127.0.0.1",port={httpport},debug=False)']
  log=(root/'server.log').open('w');proc=subprocess.Popen(command,cwd=web,env=env,stdout=log,stderr=log)
  def get(path):
   with urllib.request.urlopen(f'http://127.0.0.1:{httpport}'+path,timeout=15) as r:return json.load(r)
  for _ in range(40):
   try:health=get('/api/health');break
   except Exception:time.sleep(.5)
  else:raise RuntimeError('fresh web startup failed')
  snapshot=json.loads((web/'snapshot_data.json').read_text());rows=snapshot['institutions']
  check('fresh_database_health',health.get('institutions')==len(rows),health)
  result=get('/api/institutions?'+urllib.parse.urlencode({'level':'三级','page_size':100}));check('tertiary_filter',result['total']==sum(x['level']=='三级' for x in rows),{'total':result['total']})
  result=get('/api/institutions?'+urllib.parse.urlencode({'district':'海淀区','level':'三级'}));check('district_grade_filter',result['total']==sum(x['district']=='海淀区' and x['level']=='三级' for x in rows),{'total':result['total']})
  doctors=get('/api/doctors');check('doctor_api',doctors.get('ok') and doctors.get('total',0)>0,{'total':doctors.get('total')})
  with urllib.request.urlopen(f'http://127.0.0.1:{httpport}/',timeout=15) as r:page=r.read().decode()
  check('homepage', '基于Spark' in page.replace(' ',''),{'bytes':len(page.encode())})
  proc.terminate();proc.wait(10);proc=None
  run(['docker','restart',name])
  for _ in range(40):
   try:run(['docker','exec','-e','MYSQL_PWD='+newpw,name,'mysql','-uroot','-e','SELECT 1']);break
   except subprocess.CalledProcessError:time.sleep(1)
  proc=subprocess.Popen(command,cwd=web,env=env,stdout=log,stderr=log)
  for _ in range(40):
   try:health=get('/api/health');break
   except Exception:time.sleep(.5)
  check('restart_persistence',health.get('institutions')==len(rows),health)
 except Exception as e:
  report['error']=str(e);raise
 finally:
  if proc:proc.terminate();proc.wait(10)
  subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  subprocess.run(['docker','volume','rm',volume],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  report['cleanup']='only uniquely named verification container and volume removed'
  (a.out/'deployment_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
