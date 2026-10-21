"""Reproducible topic aggregates from a frozen application snapshot (ADS export).
Does not rerun upstream ODS/DWD. Writes new research ADS tables only.
"""
import json,sys,os,time,hashlib
from pyspark.sql import SparkSession,functions as F
from common import write_mysql

def main():
 src,meta_path,out=sys.argv[1:4];meta=json.load(open(meta_path));start=time.time()
 spark=SparkSession.builder.appName('BeijingResearchTopics').config('spark.sql.shuffle.partitions','4').getOrCreate();spark.sparkContext.setLogLevel('WARN')
 d=spark.read.json(src).cache();assert d.count()==meta['institution_count']
 nets=['pediatric','stroke','neonatal','maternal'];pred=[F.col('net_pediatric').isin('核心','成员'),F.col('net_stroke')=='1',F.col('net_neonatal')=='市级',F.col('net_maternal')=='市级']
 d=d.withColumn('recorded_depts',F.expr("filter(split(coalesce(recorded_depts,''), ';'), x -> trim(x) <> '')"))
 d=d.withColumn('network',pred[0]|pred[1]|pred[2]|pred[3])
 district=d.groupBy('district').agg(F.count('*').alias('total'),F.sum((F.col('level')=='三级').cast('int')).alias('tertiary'),F.sum((F.size('recorded_depts')>0).cast('int')).alias('recorded'),F.sum(F.col('network').cast('int')).alias('network'))
 grade=d.groupBy('district','level').count()
 dept=d.select('id','district',F.explode(F.array_distinct('recorded_depts')).alias('department')).groupBy('district','department').agg(F.countDistinct('id').alias('count'))
 network=None
 for name,p in zip(nets,pred):
  a=d.filter(p).groupBy('district').agg(F.countDistinct('id').alias('count')).withColumn('network',F.lit(name));network=a if network is None else network.unionByName(a)
 overlap=[]
 for i,p in enumerate(pred):
  for j,q in enumerate(pred):overlap.append({'left':nets[i],'right':nets[j],'count':d.filter(p&q).count()})
 quality=d.groupBy('coord_precision').count()
 tables={'district':district,'grade':grade,'department':dept,'network':network,'quality':quality}
 result={'meta':{**meta,'engine':'Spark '+spark.version,'master':spark.sparkContext.master,'input_layer':'frozen ADS application snapshot','upstream_rerun':False},'overlap':overlap,'tables':{}}
 for name,df in tables.items():
  rows=[r.asDict() for r in df.collect()];result['tables'][name]=sorted(rows,key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False));df.write.mode('overwrite').parquet('hdfs://namenode:8020/hospital/ads/research_topics/'+name);write_mysql(df,'ads_research_'+name)
 result['meta']['elapsed_seconds']=round(time.time()-start,2)
 result['meta']['checks']={'district_sum':sum(r['total'] for r in result['tables']['district']),'grade_sum':sum(r['count'] for r in result['tables']['grade']),'coordinate_sum':sum(r['count'] for r in result['tables']['quality'])}
 assert all(v==meta['institution_count'] for v in result['meta']['checks'].values())
 json.dump(result,open(out,'w'),ensure_ascii=False,indent=2);spark.stop()
if __name__=='__main__':main()
