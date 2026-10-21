"""One read-only validation entry; each test file runs in an isolated process.
Does not start containers, rerun ETL, dial, book, or call a model.
"""
import argparse,hashlib,json,os,platform,shutil,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--node',default=shutil.which('node'));p.add_argument('--base-url');p.add_argument('--output',default='docs/发布验证/current');args=p.parse_args()
 output=ROOT/args.output;output.mkdir(parents=True,exist_ok=True)
 logs=output/'logs';logs.mkdir(exist_ok=True)
 env=os.environ.copy();env['PYTHONPATH']=str(ROOT)+os.pathsep+env.get('PYTHONPATH','')
 if args.node:env['PATH']=str(Path(args.node).parent)+os.pathsep+env.get('PATH','')
 entries=[]
 for path in sorted((ROOT/'tests').glob('test_*')):
  if path.suffix not in ('.js','.py'):continue
  name=path.name;cmd=[args.node,str(path)] if path.suffix=='.js' and args.node else [sys.executable,str(path)]
  if path.suffix=='.js' and not args.node:
   entries.append(dict(name=name,status='failed',reason='Node.js不可用'));continue
  t=time.perf_counter()
  try:
   r=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
   log=r.stdout+'\n'+r.stderr;status='passed' if r.returncode==0 else 'failed';code=r.returncode
  except (subprocess.TimeoutExpired,OSError) as e:
   log=str(e);status='failed';code=None
  (logs/(name+'.log')).write_text(log,encoding='utf-8')
  entry=dict(name=name,status=status,exit_code=code,seconds=round(time.perf_counter()-t,3),log='logs/'+name+'.log');entries.append(entry)
  print(status.upper(),name,flush=True)
 if args.base_url:
  for endpoint in ['/','/api/health','/api/doctors/coverage']:
   try:
    with urlopen(args.base_url.rstrip('/')+endpoint,timeout=15) as response:
     raw=response.read();assert response.status==200
     if endpoint=='/api/doctors/coverage':
      d=json.loads(raw);assert d['target_records']==180 and d['records_with_doctors']+d['missing_records']==180
     if endpoint=='/api/health':assert json.loads(raw).get('institutions')==9678
    entries.append(dict(name='HTTP '+endpoint,status='passed'))
   except Exception as e:entries.append(dict(name='HTTP '+endpoint,status='failed',reason=str(e)))
 else:entries.append(dict(name='真实HTTP接口',status='skipped',reason='未提供--base-url；Flask测试客户端不等同运行中HTTP服务'))
 for name,reason in [('浏览器视觉与真人试用','本命令不执行；需另附本批次观察及原始记录'),('隔离部署与上游ETL重建','本命令不执行；历史记录不作为本次重测')]:entries.append(dict(name=name,status='skipped',reason=reason))
 def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
 manifest={str(x.relative_to(ROOT)):digest(x) for folder in ['web','etl','tests','scripts'] for x in (ROOT/folder).rglob('*') if x.is_file() and (x.suffix in ['.js','.py','.css','.html','.json','.sh']) and not any(k in x.parts for k in ['node_modules','__pycache__','_legacy','vue'])}
 ledger=json.loads((ROOT/'web/project_metrics.json').read_text());counts={k:sum(x['status']==k for x in entries) for k in ['passed','failed','skipped']}
 result=dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),scope='all JS/Python test entry files + optional read-only live HTTP; no production deployment',snapshot_date=ledger['snapshot_date'],fingerprint=ledger['fingerprint'],python=platform.python_version(),node=args.node,summary=counts,entries=entries,sha256=manifest)
 (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# 当前版本完整验证报告','',f"生成时间：{result['generated_at_utc']}",f"快照：{result['snapshot_date']}；指纹：`{result['fingerprint']}`",'',f"通过 {counts['passed']}；失败 {counts['failed']}；未执行 {counts['skipped']}。测试入口通过不等于浏览器/真人/生产部署通过。",'', '|检查|状态|证据|','|---|---|---|']
 for x in entries:lines.append('|'+x['name']+'|'+{'passed':'通过','failed':'失败','skipped':'未执行'}[x['status']]+'|'+('['+x['log']+']('+x['log']+')' if x.get('log') else x.get('reason','运行中HTTP 200与响应断言'))+'|')
 lines+=['','命令：`python scripts/validate_current.py --node /path/to/node --base-url http://127.0.0.1:5001`。运行环境与源码/构建文件SHA256见results.json。每个入口的断言数量不同，不能将文件数称为用例数。']
 (output/'验证报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps(counts,ensure_ascii=False));return 1 if counts['failed'] else 0
if __name__=='__main__':raise SystemExit(main())
