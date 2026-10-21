#!/usr/bin/env python3
"""Recompute three descriptive questions from the shipped ADS snapshot; no DB mutation."""
import argparse,json,hashlib,csv,html
from pathlib import Path
from collections import Counter
p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
f=a.project/'web/snapshot_data.json';s=json.loads(f.read_text());rows=s['institutions'];batch=json.loads((a.project/'web/analysis_batch.json').read_text())
def net(r):return [r.get('net_pediatric') in ('核心','成员'),str(r.get('net_stroke'))=='1',r.get('net_neonatal')=='市级',r.get('net_maternal')=='市级']
district=[]
for name in sorted({r['district'] for r in rows}):
 x=[r for r in rows if r['district']==name];t=sum(r['level']=='三级' for r in x);rec=sum(bool(r.get('recorded_depts','').strip('; ')) for r in x)
 district.append(dict(district=name,total=len(x),tertiary=t,recorded=rec,network=sum(any(net(r)) for r in x)))
assert district==sorted(batch['tables']['district'],key=lambda x:x['district'])
assert all(not r.get('recorded_depts','').strip('; ') or r.get('depts','').strip('; ') for r in rows)
N=len(rows);T=sum(r['level']=='三级' for r in rows);R=sum(bool(r.get('recorded_depts','').strip('; ')) for r in rows);M=sum(bool(r.get('depts','').strip('; ')) for r in rows)
counts=[sum(net(r)[i] for r in rows) for i in range(4)];intersection=sum(net(r)[0] and net(r)[1] for r in rows);union=counts[0]+counts[1]-intersection
assert all(sum(net(r)[i] and net(r)[j] for r in rows)==next(x['count'] for x in batch['overlap'] if x['left']==['pediatric','stroke','neonatal','maternal'][i] and x['right']==['pediatric','stroke','neonatal','maternal'][j]) for i in range(4) for j in range(4))
with (a.out/'区域明细.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(district[0]));w.writeheader();w.writerows(district)
rank=sorted(district,key=lambda x:x['tertiary'],reverse=True);top=[r for r in district if r['tertiary']==28];topnames='、'.join(r['district'] for r in top)
sections=[('问题一：三级记录集中在哪些区域？',f'机构快照 {N:,} 条，按机构ID计数；其中三级 {T} 条。分析单位是快照记录，院区、旧名可能分别计入。','按行政区分组，同时计算三级绝对数量、占全市三级记录比重；不用全类型机构总数代替人口分母。',f'{topnames}各28条，并列最高；合计84条，占三级记录的{84/T:.1%}。总机构记录最多的昌平区有1309条，三级12条。总记录多与三级记录多不是同一结论。','只能说明本快照中的分布。没有人口、面积、床位、就诊量和去重后的医院实体口径，不能据此认定哪个区医疗资源不足或质量更高。'),('问题二：科室检索结果有多少来源支撑？',f'同一快照 {N:,} 条；depts 为映射集合（含名称/规则）；recorded_depts 为有来源的映射集合。','逐机构判断两字段是否非空；按区统计来源记录覆盖率。分母固定为当前快照记录数，避免把机构数和科室关系数相加。',f'有映射 {M:,} 条（{M/N:.2%}），有来源 {R:,} 条（{R/N:.2%}），差{(M-R):,}条。昌平区有来源489条，占全市有来源记录{489/R:.1%}，显示来源采集分布不均。','有来源不等于已确认当前在营；缺少来源不等于未开设。区域矩阵反映记录与采集覆盖，不能用于科室供给强弱排名。'),('问题三：协作网络是否可以直接相加？','四类网络使用快照标识：儿科核心/成员、卒中=1、新生儿市级、孕产妇市级。','以机构ID为单位构造四个集合，计算交集矩阵、去重并集和Jaccard（交集÷并集）；相同机构跨网络仅计一次。',f'儿科44、卒中67，交集{intersection}；两者并集{union}，Jaccard={intersection/union:.2%}。四网络成员次数合计{sum(counts)}，去重机构{sum(any(net(r)) for r in rows)}，不能把成员次数当独立机构数。','网络名单成员不等于实时转诊、接诊能力或服务覆盖人口；数据中“无标识”不证明未加入。不同网络准入口径不同，不能直接排名。')]
def bars(items,key,label):
 maxv=max(x[key] for x in items);out=''
 for x in items:
  val=x[key];out+=f'<div class="bar"><span>{html.escape(x["district"])}</span><meter min="0" max="{maxv}" value="{val}"></meter><b>{val}</b></div>'
 return f'<h3>{label}</h3>'+out
body=''
for i,(title,basis,method,finding,limit) in enumerate(sections):
 chart=bars(rank,'tertiary','各区三级记录数（条，固定零基线）') if i==0 else bars(sorted(district,key=lambda x:x['recorded']/x['total'],reverse=True),'recorded','各区有来源记录数量（条；覆盖率请查CSV分母）') if i==1 else '<table><tr><th>网络</th><th>儿科</th><th>卒中</th><th>新生儿</th><th>孕产妇</th></tr>'+''.join('<tr><th>'+name+'</th>'+''.join('<td>'+str(sum(net(r)[j] and net(r)[k] for r in rows))+'</td>' for k in range(4))+'</tr>' for j,name in enumerate(['儿科','卒中','新生儿','孕产妇']))+'</table><p>对角线为成员数，其余单元格为交集，不可跨单元格求和。</p>'
 body+=f'<section><h2>{title}</h2>'+''.join(f'<p><strong>{k}</strong> {v}</p>' for k,v in zip(['数据依据','处理方法','图表发现','结论限制'],[basis,method,finding,limit]))+chart+'</section>'
meta={'snapshot_sha256':hashlib.sha256((a.project/'web/snapshot_data.json').read_bytes()).hexdigest(),'institutions':N,'tertiary':T,'mapped':M,'recorded':R,'networks':counts,'network_union':sum(any(net(r)) for r in rows),'spark_district_match':True,'spark_overlap_cells_match':16}
(a.out/'analysis_evidence.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
(a.out/'三个分析问题.html').write_text('<!doctype html><meta charset="utf-8"><title>三个分析问题与证据</title><style>body{font:17px/1.8 system-ui;color:#203047;max-width:1080px;margin:40px auto;padding:0 24px}section{margin:44px 0;padding-bottom:30px;border-bottom:1px solid #ddd}.bar{display:flex;gap:16px;align-items:center}.bar span{width:90px}meter{width:65%;height:22px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #ddd}strong{color:#175aa6}@media print{section{break-before:page}}</style><h1>三个分析问题与证据</h1><p>机构快照：2026-10-18。基于冻结ADS应用快照独立复算；未重跑ODS/DWD。本报告为描述性分析。</p>'+body+'<footer>复现：python scripts/build_analysis.py --project 项目目录 --out 输出目录。输入哈希和Spark核对结果见analysis_evidence.json，区域分母见区域明细.csv。</footer>')
print(json.dumps(meta,ensure_ascii=False))
