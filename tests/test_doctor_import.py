import copy
import importlib.util
import json
from pathlib import Path
r=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('import_doctor_records',r/'etl/import_doctor_records.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
d=json.loads((r/'web/doctors_data.json').read_text());hs=json.loads((r/'web/snapshot_data.json').read_text())['institutions']
x=dict(d['doctors'][0],name='导入校验测试',id='test-import-only',reviewed=True)
merged=mod.merge_batch(d,hs,[x]);assert len(merged['doctors'])==len(d['doctors'])+1
for changes in [dict(reviewed=False),dict(institution_id='not-found'),dict(verified_on='2999-01-01'),dict(source_url='https://unverified.invalid/doctor/1')]:
 bad=dict(x,**changes)
 try:mod.merge_batch(d,hs,[bad])
 except (ValueError,KeyError,AssertionError):pass
 else:raise AssertionError(changes)
try:mod.merge_batch(d,hs,[dict(d['doctors'][0],reviewed=True)])
except ValueError:pass
else:raise AssertionError('duplicate accepted')
assert len(d['doctors'])==len(json.loads((r/'web/doctors_data.json').read_text())['doctors'])
print('PASS 批量导入：核实标记、机构关联、来源域名、未来日期、重复与原数据保护')
