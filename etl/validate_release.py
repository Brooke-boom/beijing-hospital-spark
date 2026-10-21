"""Archive one release's exact source hashes, checks and read-only benchmarks.

Run after building. Optional --base-url benchmarks existing Flask/MySQL service.
No container starts, database writes or model calls. Missing service is SKIPPED.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def http_benchmark(base, samples, concurrency):
    endpoints = ['/api/health', '/api/institutions?level=三甲',
                 '/api/institutions?level=三甲&radius=5',
                 '/api/institutions?dept_evidence=recorded']
    results = []
    for path in endpoints:
        def request(_=None):
            start = time.perf_counter()
            with urlopen(base.rstrip('/') + quote(path, safe='/?=&'), timeout=15) as r:
                payload = json.load(r)
            if 'error' in payload or not any(k in payload for k in ('total', 'institutions')):
                raise ValueError('接口未返回有效查询结果')
            return (time.perf_counter() - start) * 1000, payload.get('total', payload.get('institutions'))
        for _ in range(3): request()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            values = list(pool.map(request, range(samples)))
        times = sorted(v[0] for v in values)
        counts = {v[1] for v in values}
        if len(counts) != 1: raise ValueError('重复请求数量不稳定')
        results.append(dict(path=path, samples=samples, concurrency=concurrency,
                            total=values[0][1], mean_ms=round(statistics.mean(times), 2),
                            p95_ms=round(times[math.ceil(.95 * samples)-1], 2)))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url')
    parser.add_argument('--samples', type=int, default=30)
    parser.add_argument('--concurrency', type=int, default=4)
    args = parser.parse_args()
    if not 10 <= args.samples <= 1000 or not 1 <= args.concurrency <= 16:
        parser.error('samples=10..1000; concurrency=1..16')
    node = os.environ.get('NODE_BIN') or shutil.which('node')
    if not node: raise SystemExit('缺少 Node，请设置 NODE_BIN 或 PATH')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT / 'data/validation' / stamp
    out.mkdir(parents=True)
    snapshot = json.loads((ROOT / 'web/snapshot_data.json').read_text())
    sources = ['web/app.js', 'web/app.query.js', 'web/app.nlq.js', 'web/nlq.py',
               'web/app.py', 'web/dashboard.html', 'web/build_spa.sh', 'web/dashboard_offline.html',
               'web/templates/index.html', 'etl/export_project_metrics.py', 'etl/validate_release.py',
               'etl/benchmark_offline.js', 'tests/test_lookup_audit.js', 'tests/test_project_metrics.py', 'tests/test_dashboard_rendering.js', 'tests/test_product_workflows.js', 'web/app.ux.js', 'web/ux.css', 'web/app.chat.js', 'tests/test_direction_analysis.js', 'tests/test_analysis_charts.js', 'tests/test_chat_workflows.js', 'web/app.evidence.js', 'tests/test_release_validation.py']
    manifest = dict(created_at_utc=stamp, python=sys.version, platform=platform.platform(),
                    snapshot_date=snapshot['snapshot_time'], fingerprint=snapshot.get('project_metrics', {}).get('fingerprint'),
                    source_sha256={s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in sources}, checks=[])
    checks = [('python_regression', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v']),
              ('lookup_regression', [node, 'tests/test_lookup_audit.js']),
              ('dashboard_text_rendering', [node, 'tests/test_dashboard_rendering.js']),
              ('product_workflows', [node, 'tests/test_product_workflows.js']),
              ('direction_analysis', [node, 'tests/test_direction_analysis.js']),
              ('analysis_charts', [node, 'tests/test_analysis_charts.js']),
              ('chat_workflows', [node, 'tests/test_chat_workflows.js']),
              ('artifact_consistency', [sys.executable, 'etl/verify_artifacts.py']),
              ('offline_consistency', [sys.executable, 'etl/verify_offline_nlq.py']),
              ('offline_benchmark', [node, 'etl/benchmark_offline.js'])]
    env = dict(os.environ, BENCH_SAMPLES=str(args.samples))
    env['PATH'] = str(Path(node).parent) + os.pathsep + env.get('PATH', '')
    for name, command in checks:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        (out / (name + '.log')).write_text(result.stdout + result.stderr)
        entry = dict(name=name, status='passed' if result.returncode == 0 else 'failed', exit_code=result.returncode)
        if name == 'offline_benchmark' and result.returncode == 0:
            entry['measurements'] = json.loads(result.stdout)
        manifest['checks'].append(entry)
        print(name, entry['status'], flush=True)
    if args.base_url:
        try:
            results = http_benchmark(args.base_url, args.samples, args.concurrency)
            manifest['checks'].append(dict(name='http_benchmark', status='passed', base_url=args.base_url, results=results))
        except Exception as exc:
            manifest['checks'].append(dict(name='http_benchmark', status='failed', detail=str(exc)))
    else:
        manifest['checks'].append(dict(name='http_benchmark', status='skipped', detail='未指定运行中的服务；没有测量 MySQL / Flask 性能'))
    manifest['limitations'] = ['未重跑 HDFS / Spark；未调用 AI；Node 引擎耗时不等于端到端耗时。',
                               'HTTP 服务与文件使用同批数据需额外核对；记录不自动证明部署版本一致。',
                               '自动化前端流程使用 DOM 模型；真实浏览器记录另见 docs/浏览器验收记录.md。实体移动设备与辅助技术未验收。']
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    latest = ROOT / 'docs/当前版本验证结果.md'
    lines = ['# 当前版本验证结果', '', f'归档：`{out.relative_to(ROOT)}`',
             f'快照：{manifest["snapshot_date"]}。数据指纹：`{manifest["fingerprint"]}`。', '',
             '| 检查 | 状态 |', '|---|---|']
    lines += [f'| {c["name"]} | {c["status"]} |' for c in manifest['checks']]
    for c in manifest['checks']:
        if 'measurements' in c:
            lines += ['', '## 离线引擎性能', '', '仅含解析、筛选与解释，不含浏览器绘制或在线接口。', '',
                      '| 场景 | 次数 | 并发 | 命中 | 均值 ms | P95 ms |', '|---|---:|---:|---:|---:|---:|']
            lines += [f'| {r["name"]} | {r["samples"]} | {r["concurrency"]} | {r["total"]} | {r["mean_ms"]} | {r["p95_ms"]} |' for r in c['measurements']['results']]
    lines += ['', *manifest['limitations']]
    latest.write_text('\n'.join(lines)+'\n')
    print('记录已归档：', out)
    return int(any(c['status'] == 'failed' for c in manifest['checks']))


if __name__ == '__main__':
    sys.exit(main())
