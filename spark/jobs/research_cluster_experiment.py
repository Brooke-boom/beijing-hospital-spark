"""Frozen-snapshot exploratory clustering; structure labels only; no quality ranking."""
import sys,json
from pyspark.sql import SparkSession,functions as F
from pyspark.ml.feature import VectorAssembler,StandardScaler
from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import ClusteringEvaluator
s=SparkSession.builder.appName('ResearchClusterStability').config('spark.sql.shuffle.partitions','2').getOrCreate();s.sparkContext.setLogLevel('WARN')
d=s.read.json(sys.argv[1]);f=d.groupBy('district').agg(F.count('*').alias('total'),F.sum((F.col('level')=='三级').cast('int')).alias('tertiary'),F.sum((F.col('level')=='二级').cast('int')).alias('secondary'),F.sum((F.col('category')=='医院').cast('int')).alias('hospital'),F.sum((F.length('recorded_depts')>0).cast('int')).alias('recorded'),F.sum((F.col('national_specialty_count')+F.col('municipal_specialty_count')).cast('double')).alias('specialty')).fillna(0)
cols=['total','tertiary','secondary','hospital','recorded','specialty'];v=VectorAssembler(inputCols=cols,outputCol='raw').transform(f);data=StandardScaler(inputCol='raw',outputCol='features',withMean=True,withStd=True).fit(v).transform(v).cache();runs=[]
for k in [2,3,4,5]:
 for seed in [7,42]:
  pred=KMeans(k=k,seed=seed,maxIter=50).fit(data).transform(data);score=ClusteringEvaluator().evaluate(pred);runs.append({'k':k,'seed':seed,'silhouette':score,'assignments':{r['district']:r['prediction'] for r in pred.select('district','prediction').collect()}})
json.dump({'engine':'Spark '+s.version,'master':s.sparkContext.master,'features':cols,'standardization':'mean and std','rows':f.count(),'features_by_district':[r.asDict() for r in f.collect()],'runs':runs,'limits':'16 districts, correlated count features; no population or service denominators; labels are structural, not healthcare quality or sufficiency.'},open(sys.argv[2],'w'),ensure_ascii=False,indent=2);s.stop()
