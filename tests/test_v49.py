import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.forward_supervisor_v49 import collect,store_report
class V49SupervisorTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
  self.root=Path(self.t.name)/'sessions';self.reports=Path(self.t.name)/'reports'
 def test_success_four_independently(self):
  def capture(symbol,seconds,root):return {'file':str(root/(symbol+'.jsonl'))}
  with patch('cqwe.forward_supervisor_v49.audit_file',return_value={'precommits':2,'settled':1}):
   out=collect(self.root,self.reports,seconds=180,capture=capture,free_bytes=4*1024**3)
  self.assertEqual(len(out['markets']),4);self.assertEqual(out['failures'],{})
  self.assertTrue(Path(out['report_file']).is_file())
 def test_one_broken_symbol_cannot_pass(self):
  calls=[]
  def capture(symbol,seconds,root):
   calls.append(symbol)
   if symbol=='ETHUSDT':raise RuntimeError('SEQUENCE_GAP_RESYNC_REQUIRED')
   return {'file':str(root/(symbol+'.jsonl'))}
  with patch('cqwe.forward_supervisor_v49.audit_file',return_value={'precommits':2,'settled':1}):
   out=collect(self.root,self.reports,capture=capture,free_bytes=4*1024**3)
  self.assertEqual(out['status'],'PARTIAL_FAILURE');self.assertEqual(len(out['failures']['ETHUSDT']),2)
  self.assertEqual(calls.count('ETHUSDT'),2)
 def test_zero_settled_does_not_count(self):
  with patch('cqwe.forward_supervisor_v49.audit_file',return_value={'precommits':1,'settled':0}):
   out=collect(self.root,self.reports,capture=lambda symbol,seconds,root:{'file':'fake'},free_bytes=4*1024**3)
  self.assertEqual(len(out['markets']),0)
 def test_disk_budget_fail_closed(self):
  with self.assertRaisesRegex(RuntimeError,'DISK_FREE'):
   collect(self.root,self.reports,free_bytes=0)
 def test_duration_fails(self):
  with self.assertRaises(ValueError):collect(self.root,self.reports,seconds=60,free_bytes=4*1024**3)
 def test_report_cannot_overwrite(self):
  p=self.reports/'sample.json';store_report(p,{'x':1})
  with self.assertRaises(FileExistsError):store_report(p,{'x':2})
 def test_no_spurious_profit(self):
  with patch('cqwe.forward_supervisor_v49.audit_file',return_value={'precommits':2,'settled':1}):
   out=collect(self.root,self.reports,capture=lambda symbol,seconds,root:{'file':'sample'},free_bytes=4*1024**3)
  self.assertEqual(out['real_orders'],0);self.assertEqual(out['real_profit_usd'],0)
if __name__=='__main__':unittest.main()
