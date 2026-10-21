#!/usr/bin/env python3
"""Validate a reviewed JSONL doctor batch; dry-run by default, atomic write with --apply."""
import argparse
import copy
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'web'))
from doctors import validate_directory


def merge_batch(current, institutions, rows):
    result = copy.deepcopy(current)
    by_key = {(d['institution_id'], d['name'], d['department']): d for d in result['doctors']}
    used = {d['id'] for d in result['doctors']}
    for number, row in enumerate(rows, 1):
        item = dict(row)
        if item.pop('reviewed', None) is not True:
            raise ValueError(f'第 {number} 行尚未逐条核实，缺少 reviewed=true')
        item['institution_id'] = str(item.get('institution_id', ''))
        key = tuple(item.get(k, '') for k in ['institution_id', 'name', 'department'])
        if key in by_key:
            raise ValueError(f'第 {number} 行已有同院同科同名记录，需人工决定更新方式')
        item.setdefault('id', 'doc-' + hashlib.sha256('|'.join(key).encode()).hexdigest()[:16])
        if item['id'] in used:
            raise ValueError(f'第 {number} 行ID重复')
        if item.get('status') != 'published':
            raise ValueError(f'第 {number} 行必须明确指定 published')
        result['doctors'].append(item)
        by_key[key] = item
        used.add(item['id'])
    validate_directory(result, institutions)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'web/doctors_data.json'
    old_bytes = path.read_bytes()
    current = json.loads(old_bytes)
    institutions = json.loads((ROOT / 'web/snapshot_data.json').read_text())['institutions']
    rows = [json.loads(line) for line in args.batch.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not rows:
        raise SystemExit('批次为空，未修改目录')
    result = merge_batch(current, institutions, rows)
    if args.apply:
        # Atomic replacement after validation and a concurrent-edit check. Keep an exact backup.
        if path.read_bytes() != old_bytes:
            raise SystemExit('目录有并发变更，停止写入')
        backup = ROOT / 'data/processed/doctor_backups' / (hashlib.sha256(old_bytes).hexdigest() + '.json')
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes(old_bytes)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    print(('已导入' if args.apply else '预检通过，未写入') + f' {len(rows)} 条；请重新构建并生成覆盖报告。')


if __name__ == '__main__':
    main()
