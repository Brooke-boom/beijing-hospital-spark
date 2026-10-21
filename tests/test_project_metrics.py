import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'etl/export_project_metrics.py'
spec = importlib.util.spec_from_file_location('project_metrics', MODULE)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class ProjectMetricsTests(unittest.TestCase):
    def fixture(self, root, mismatch=False):
        for folder in ['web', 'docs', 'data/processed']:
            (root / folder).mkdir(parents=True)
        data = {'snapshot_time': '2026-10-18', 'meta': {'depts': [{'dept_name':'骨科'}]},
                'institutions': [{'id':'1','name':'测试','depts':'骨科','recorded_depts':'骨科',
                 'level':'三级','grade_scope':'applicable','lng':116.4,'lat':39.9,'coord_precision':'high'}]}
        (root/'web/snapshot_data.json').write_text(json.dumps(data))
        with (root/'data/processed/hospital_depts.csv').open('w', newline='') as f:
            w=csv.DictWriter(f,fieldnames=['hospital_id','dept_name','source']);w.writeheader()
            w.writerow({'hospital_id':'1','dept_name':'骨科','source':'name' if mismatch else 'online'})

    def test_matching_provenance_and_stable_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            first=metrics.export(root);second=metrics.export(root)
            self.assertEqual(first['fingerprint'],second['fingerprint'])
            self.assertEqual(second['snapshot_date'],'2026-10-18')
            self.assertEqual(second['evidence_status'],'csv_verified_against_snapshot')
            row=json.loads((root/'web/snapshot_data.json').read_text())['institutions'][0]
            self.assertEqual(row['dept_evidence'],{'骨科':['online']})

    def test_mismatched_local_csv_never_attaches_false_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root,True)
            result=metrics.export(root)
            self.assertEqual(result['evidence_status'],'unavailable')
            row=json.loads((root/'web/snapshot_data.json').read_text())['institutions'][0]
            self.assertEqual(row['dept_evidence'],{})
            self.assertNotIn('local_relation_rows',{m['key'] for m in result['metrics']})

    def test_duplicate_institution_ids_block_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            path=root/'web/snapshot_data.json';data=json.loads(path.read_text())
            data['institutions'] *= 2;path.write_text(json.dumps(data))
            with self.assertRaises(ValueError): metrics.export(root)
