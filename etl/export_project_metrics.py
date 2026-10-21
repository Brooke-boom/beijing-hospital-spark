"""Generate the current metric ledger and per-department provenance from one snapshot.

CSV provenance is attached only after EVERY institution's department sets match.
Snapshot date is never replaced by the build date. No database writes or network calls.
"""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDED = {'specialty', 'online', 'key_depts'}


def split(value):
    return set(filter(None, str(value or '').split(';')))


def metric_matches(row, definition):
    r=definition['rule'];op=r['op'];value=row.get(r.get('field'))
    nonempty=lambda v: bool(v.strip()) if isinstance(v,str) else bool(v)
    if op=='all':return True
    if op=='eq':return value==r['value']
    if op=='in':return value in r['value']
    if op=='nonempty':return nonempty(value)
    if op=='all_present':return all(row.get(k) is not None for k in r['fields'])
    if op=='any_nonempty':return any(nonempty(row.get(k)) for k in r['fields'])
    raise ValueError('未知指标操作:'+op)


def export(root=ROOT):
    path = root / 'web/snapshot_data.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    rows = data['institutions']
    if len({str(r['id']) for r in rows}) != len(rows):
        raise ValueError('快照机构 ID 重复，停止生成指标')
    relation_path = root / 'data/processed/hospital_depts.csv'
    relations = []
    if relation_path.exists():
        with relation_path.open(encoding='utf-8-sig', newline='') as f:
            relations = list(csv.DictReader(f))
    evidence = defaultdict(lambda: defaultdict(set))
    for r in relations:
        evidence[str(r['hospital_id'])][r['dept_name']].add(r['source'])
    matched = bool(relations) and all(
        set(evidence[str(r['id'])]) == split(r.get('depts')) and
        {d for d, src in evidence[str(r['id'])].items() if src & RECORDED}
        == split(r.get('recorded_depts')) for r in rows)
    # A live DB export contains provenance. Keep it; never overwrite with a local CSV.
    live = all(r.get('dept_evidence_origin') == 'database' for r in rows)
    for r in rows:
        if live:
            continue
        r['dept_evidence'] = ({d: sorted(src) for d, src in evidence[str(r['id'])].items()}
                              if matched else {})
        r['dept_evidence_origin'] = 'csv_verified_against_snapshot' if matched else 'unavailable'
    payload = {'snapshot_time': data.get('snapshot_time'), 'institutions': rows, 'meta': data['meta']}
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                           separators=(',', ':')).encode()).hexdigest()
    generated = datetime.now(timezone.utc).isoformat()
    metrics = []

    def add(key, label, value, basis, definition, source='web/snapshot_data.json'):
        metrics.append(dict(key=key, label=label, value=value, denominator=basis,
                            percentage=round(value / basis * 100, 2) if basis else None,
                            definition=definition, source=source))

    n = len(rows)
    definitions=json.loads((ROOT/'web/metric_definitions.json').read_text(encoding='utf-8'))['metrics']
    add('institutions', '机构总数', n, n, '当前应用快照内唯一机构 ID 数')
    add('specialty_named_institutions', '重点专科名单名称覆盖机构记录', sum(bool(r.get('national_specialty') or r.get('municipal_specialty')) for r in rows), n, '当前快照国家级或市级名单名称字段非空；不使用历史key_specialty_count字段')
    add('specialty_legacy_institutions', '历史专科汇总字段非零机构记录', sum(float(r.get('key_specialty_count') or 0) > 0 for r in rows), n, '历史汇总字段口径，独立保留，不与名单名称覆盖数混用')
    add('coordinates', '有坐标机构', sum(r.get('lng') is not None and r.get('lat') is not None for r in rows), n, '经纬度均非空；覆盖不等于高精度')
    for precision, label in [('high', '高精度坐标'), ('rough', '粗精度坐标'), ('missing', '缺失坐标')]:
        add('coord_' + precision, label, sum(r.get('coord_precision') == precision for r in rows), n, 'coord_precision = ' + precision)
    applicable = sum(r.get('grade_scope') == 'applicable' for r in rows)
    # Some source versions use different grade_scope codes; the service level explicitly separates N/A.
    applicable = sum(r.get('level') != '不适用医院分级' for r in rows) if not applicable else applicable
    add('grade_applicable', '等级适用机构', applicable, n, '按当前快照等级适用范围统计')
    add('grade_known', '适用范围内等级非空', sum(r.get('level') in ('一级', '二级', '三级') for r in rows), applicable, '一级 / 二级 / 三级；分母为等级适用机构')
    add('dept_dictionary', '筛选科室词表条目', len(data['meta']['depts']), None, '当前筛选下拉词表条目数，不是任一医院科室总数')
    add('dept_covered', '有科室映射机构', sum(bool(r.get('depts')) for r in rows), n, '至少一条科室映射，含名称与规则推断')
    add('dept_recorded', '有科室来源记录机构', sum(bool(r.get('recorded_depts')) for r in rows), n, '至少一条 specialty / online / key_depts 映射，不代表当前在营确认')
    add('dept_pairs', '机构与科室唯一组合', sum(len(split(r.get('depts'))) for r in rows), None, '每个机构内科室去重后的组合数，不等于来源记录行数')
    if live or matched:
        counts = Counter(s for r in rows for sources in r['dept_evidence'].values() for s in sources)
        add('dept_source_records', '科室来源去重记录数', sum(counts.values()), None, '按机构 ID / 科室 / 来源三元组去重')
        for source, count in sorted(counts.items()):
            add('dept_source_' + source, '科室来源 · ' + source, count, sum(counts.values()), '按机构 ID / 科室 / 来源三元组去重')
    if matched:
        add('local_relation_rows', '本地科室 CSV 行数', len(relations), None, '本地文件行数，已逐机构核对科室集合；与去重组合口径分别记录', 'data/processed/hospital_depts.csv')
    # Registry is authoritative for all shared UI / ledger metrics.
    for key, definition in definitions.items():
        entry=next((m for m in metrics if m['key']==key),None)
        value=sum(metric_matches(r,definition) for r in rows)
        if entry:
            entry.update(value=value,denominator=n,percentage=round(value/n*100,2) if n else None,
                         definition=definition['definition'],label=definition['label'])
        else:add(key,definition['label'],value,n,definition['definition'])
    ledger = dict(schema_version=1, snapshot_date=data.get('snapshot_time'),
                  generated_at_utc=generated, fingerprint=fingerprint,
                  evidence_status='database' if live else ('csv_verified_against_snapshot' if matched else 'unavailable'),
                  definitions=definitions, metrics=metrics)
    data['project_metrics'] = ledger
    data['total'] = n
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (root / 'web/project_metrics.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 当前项目指标', '', f'数据快照日期：{ledger["snapshot_date"]}。生成时间（UTC）：{generated}。',
             f'数据指纹 SHA256：`{fingerprint}`。', '',
             '本表由 `etl/export_project_metrics.py` 自动生成。论文和答辩引用当前统计时应注明本批次；历史测试记录不自动改写为本次实测。', '',
             '| 指标 | 数值 | 分母 | 占比 | 定义 | 来源 |', '|---|---:|---:|---:|---|---|']
    for m in metrics:
        pct = str(m['percentage']) + '%' if m['percentage'] is not None else '—'
        lines.append(f'| {m["label"]} | {m["value"]} | {m["denominator"] or "—"} | {pct} | {m["definition"].replace("|", "/")} | `{m["source"]}` |')
    lines += ['', '科室来源记录不是机构实时在营确认；粗精度坐标不参与半径筛选；检查项目映射到科室不证明机构具备该检查设备或服务。',
              '原始文件数与合并前记录数属于历史采集口径，本次仅重算现有快照可验证的指标。']
    (root / 'docs/当前项目指标.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    with (root / 'data/processed/project_metrics.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(metrics[0]))
        writer.writeheader(); writer.writerows(metrics)
    print('指标表已更新：%s 家，证据 %s，指纹 %s' % (n, ledger['evidence_status'], fingerprint[:12]))
    return ledger


if __name__ == '__main__':
    export()
