"""Versioned, manually reviewed official doctor directory; no generated clinical facts."""
import datetime
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
BOOKING = 'https://www.114yygh.com/'


def validate_directory(data, institutions):
    hospitals = {str(r['id']): r for r in institutions}
    seen = set()
    for d in data['doctors']:
        assert d['id'] not in seen, 'duplicate doctor id'
        seen.add(d['id'])
        assert hospitals[d['institution_id']]['level'] == '三级', 'not tertiary hospital'
        assert all(d.get(k) for k in ['name', 'title', 'department', 'specialty', 'source_url', 'source_name', 'verified_on'])
        source = urlparse(d['source_url'])
        assert source.scheme == 'https' and source.hostname in data.get('source_hosts', {}).get(d['institution_id'], []), 'invalid official source'
        day = datetime.date.fromisoformat(d['verified_on'])
        assert day <= datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date(), 'future verification date'
    for h in data['hospitals']:
        assert hospitals[h['institution_id']]['level'] == '三级'
        assert all(hospitals[c]['level'] == '三级' for c in h.get('campus_ids', []))
    assert data['booking_url'] == BOOKING
    return data, hospitals


def load_directory():
    data = json.loads((ROOT / 'doctors_data.json').read_text(encoding='utf-8'))
    institutions = json.loads((ROOT / 'snapshot_data.json').read_text(encoding='utf-8'))['institutions']
    return validate_directory(data, institutions)


def coverage():
    data, hospitals = load_directory()
    rows = []
    for h in hospitals.values():
        if h['level'] != '三级':
            continue
        host = next((g['institution_id'] for g in data['hospitals'] if str(h['id']) in g.get('campus_ids', [])), str(h['id']))
        doctors = [d for d in data['doctors'] if d['status']=='published' and d['institution_id']==host]
        rows.append(dict(institution_id=str(h['id']), name=h['name'], district=h['district'], category=h['category'],
                         grade='三甲' if h.get('level_sub') == '甲等' else '三级（其他等次或未收录）',
                         canonical_id=host, doctor_count=len(doctors),
                         status='部分医生资料' if doctors else '待补录',
                         completeness='partial' if doctors else 'missing'))
    return rows


def department_parts(value):
    parts = [part.strip() for part in re.split('[、；;]', value)]
    return parts if len(parts)>1 and all(re.search('科|部|中心|门诊|病房|病区|研究所', part) for part in parts) else [value]


def search(params):
    data, hospitals = load_directory()
    requested = str(params.get('hospital', '') or '')
    canonical = requested
    for h in data['hospitals']:
        if requested == h['institution_id'] or requested in h.get('campus_ids', []):
            canonical = h['institution_id']
            break
    name = str(params.get('name', '') or '').strip()
    dept = str(params.get('department', '') or '').replace('心血管内科', '心内科').replace('心血管科', '心内科').replace('心脏科', '心内科')
    district = str(params.get('district', '') or '')
    selected = hospitals.get(requested)
    rows = []
    for d in data['doctors']:
        h = hospitals[d['institution_id']]
        if d.get('status') != 'published':
            continue
        if requested and d['institution_id'] != canonical:
            continue
        if params.get('grade') == '三甲' and (selected or h).get('level_sub') != '甲等':
            continue
        if name and name not in d['name']:
            continue
        if dept and not any(dept == part.strip().replace('心血管内科', '心内科').replace('心血管科', '心内科').replace('心脏科', '心内科') for part in department_parts(d['department'])):
            continue
        if district and district != (selected or h)['district']:
            continue
        rows.append(dict(d, hospital_name=h['name'], district=h['district'], category=h['category'], booking_url=BOOKING))
    # Stable ID order for API; browser displays its own locale-aware name order.
    rows.sort(key=lambda d: d['id'])
    return rows, data
