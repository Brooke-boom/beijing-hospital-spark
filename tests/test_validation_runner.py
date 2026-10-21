"""Release runner must report failures and omissions instead of hiding them."""
import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('validation_runner',Path(__file__).resolve().parents[1]/'scripts/validate_current.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
class RunnerTests(unittest.TestCase):
 def run_case(self,code=0,missing_node=False):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for d in ['web','etl','tests','scripts']:(root/d).mkdir()
   (root/'web/project_metrics.json').write_text(json.dumps({'snapshot_date':'fixture','fingerprint':'fixture-hash'}))
   (root/'tests/test_probe.py').write_text('raise SystemExit('+str(code)+')')
   if missing_node:(root/'tests/test_probe.js').write_text('// fixture')
   argv=['validate_current.py','--node',str(root/'no-such-node') if missing_node else sys.executable]
   with patch.object(runner,'ROOT',root),patch.object(sys,'argv',argv):status=runner.main()
   result=json.loads((root/'docs/发布验证/current/results.json').read_text())
   self.assertEqual(result['snapshot_date'],'fixture')
   self.assertIn('web/project_metrics.json',result['sha256'])
   return status,result
 def test_success_does_not_claim_manual_or_http_validation(self):
  status,r=self.run_case();self.assertEqual(status,0);self.assertEqual(r['summary'],{'passed':1,'failed':0,'skipped':3})
 def test_failure_returns_nonzero_and_remains_in_report(self):
  status,r=self.run_case(3);self.assertEqual(status,1);self.assertEqual(r['summary']['failed'],1);self.assertEqual(r['entries'][0]['exit_code'],3)
 def test_unavailable_requested_runtime_is_failure_not_crash(self):
  status,r=self.run_case(missing_node=True);self.assertEqual(status,1);self.assertTrue(any(x['name']=='test_probe.js' and x['status']=='failed' for x in r['entries']))
if __name__=='__main__':unittest.main()
