#!/usr/bin/env python3
"""Fetch public official profile fields into pending_review JSONL; never publish automatically."""
import json,re,time,datetime
from pathlib import Path
from urllib.parse import urljoin
import requests
from lxml import html
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/processed/doctor_coverage/pkuh6_candidates.jsonl'
seed='https://www.pkuh6.cn/Html/Doctors/Main/Index_260.html'
s=requests.Session()
def get(url):
 r=s.get(url,timeout=12)
 if r.status_code!=200:raise ValueError('HTTP '+str(r.status_code))
 p=html.fromstring(r.content)
 if '北京大学第六医院' not in ''.join(p.xpath('//title/text()')):raise ValueError('unexpected title / verification')
 return p
p=get(seed)
links=sorted({urljoin(seed,a) for a in p.xpath('//a[contains(@href,"/Doctors/Main/Index_")]/@href')})
seen=set()
if OUT.exists():
 for line in OUT.read_text().splitlines():seen.add(json.loads(line)['source_url'])
print('公开官网个人介绍链接',len(links),flush=True)
errors=[]
for i,u in enumerate(links):
 if u in seen:continue
 try:
  p=get(u)
  def label(name):
   nodes=p.xpath('//*[self::dd or self::dt][strong[contains(text(),"'+name+'")]]')
   if not nodes:return ''
   return ''.join(nodes[0].itertext()).strip().split('：',1)[-1].strip()
  name=label('姓名');title=label('职称');specialty=label('专业特长')
  if not re.fullmatch(r'[\u4e00-\u9fff·]{2,6}',name) or re.search('门诊|普通|病房|科室',name):raise ValueError('not individual doctor')
  pagetitle=''.join(p.xpath('//title/text()'))
  if name not in pagetitle:raise ValueError('name mismatch')
  dept='门诊医生（官网栏目）' # Profile explicitly uses this official category; no invented specialty department.
  row=dict(institution_id='1500',name=name,title=title or '职称未收录',department=dept,specialty=specialty,source_url=u,source_name='北京大学第六医院官网',verified_on='2026-10-19',status='pending_review')
  with OUT.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
  print(i+1,name,title,flush=True)
 except Exception as e:
  errors.append(dict(url=u,error=str(e)));print('SKIP',i+1,str(e),flush=True)
  if '418' in str(e) or 'verification' in str(e):break
 time.sleep(.5)
(OUT.parent/'pkuh6_fetch_errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2))
print('DONE',flush=True)
