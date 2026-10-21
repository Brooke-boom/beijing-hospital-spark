#!/usr/bin/env bash
# Frozen ADS snapshot analysis. Does not rerun upstream ODS/DWD.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-/Users/brooke/.workbuddy/binaries/python/envs/default/bin/python}"
OUT=data/processed/research_analysis
mkdir -p "$OUT"
"$PY" etl/freeze_research_snapshot.py "$OUT/input"
docker cp "$OUT/input/snapshot.jsonl" spark-master:/tmp/research_snapshot.jsonl
docker cp "$OUT/input/input_meta.json" spark-master:/tmp/research_meta.json
docker cp spark/jobs/dim_research_topics.py spark-master:/tmp/dim_research_topics.py
docker cp spark/jobs/research_cluster_experiment.py spark-master:/tmp/research_cluster_experiment.py
docker exec -e PYTHONPATH=/opt/workspace/jobs/jobs spark-master /opt/spark/bin/spark-submit --master 'local[2]' --conf spark.jars.ivy=/opt/workspace/jobs/.ivy2 --packages com.mysql:mysql-connector-j:8.4.0 /tmp/dim_research_topics.py file:///tmp/research_snapshot.jsonl /tmp/research_meta.json /tmp/analysis_batch.json > "$OUT/spark.log" 2>&1
docker cp spark-master:/tmp/analysis_batch.json web/analysis_batch.json
docker exec spark-master /opt/spark/bin/spark-submit --master 'local[2]' /tmp/research_cluster_experiment.py file:///tmp/research_snapshot.jsonl /tmp/research_cluster.json > "$OUT/cluster.log" 2>&1
docker cp spark-master:/tmp/research_cluster.json "$OUT/cluster.json"
"$PY" etl/verify_research_batch.py
"$PY" etl/attach_research_validation.py
PYTHON_BIN="$PY" bash web/build_spa.sh --no-db
node tests/test_research_topics.js
