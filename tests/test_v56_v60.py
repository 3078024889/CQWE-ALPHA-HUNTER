import unittest,tempfile
from pathlib import Path
from cqwe.cash_truth_v56 import ledger
from cqwe.commerce_funnel_v57 import funnel
from cqwe.execution_reality_v58 import execute
from cqwe.failure_memory_v59 import analyze_trials
from cqwe.storage_integrity_v60 import archive
H='a'*64
class TenAdversarialAudits(unittest.TestCase):
 def test_01_fake_income_rejected(self):
  with self.assertRaisesRegex(ValueError,'UNVERIFIED'):ledger([dict(id='a',timestamp='2026-10-14T00:00:00+00:00',type='receipt',amount='1000',evidence_sha256=H,verified=False)])
 def test_02_cash_negative_rejected(self):
  with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):ledger([dict(id='a',timestamp='2026-10-14T00:00:00+00:00',type='expense',amount='11',evidence_sha256=H,verified=True)])
 def test_03_duplicate_cash_rejected(self):
  x=dict(id='a',timestamp='2026-10-14T00:00:00+00:00',type='receipt',amount='1',evidence_sha256=H,verified=True)
  with self.assertRaisesRegex(ValueError,'DUPLICATE'):ledger([x,x])
 def test_04_float_money_rejected(self):
  with self.assertRaisesRegex(ValueError,'NON_DECIMAL'):ledger([dict(id='a',timestamp='2026-10-14T00:00:00+00:00',type='receipt',amount=0.1,evidence_sha256=H,verified=True)])
 def test_05_untraceable_sale_rejected(self):
  with self.assertRaisesRegex(ValueError,'UNTRACEABLE'):funnel([], [dict(id='1',lead_id='missing',price_usd='9',payment_event_id='p')])
 def test_06_payment_not_counted_as_cash(self):
  self.assertEqual(funnel([],[])['cash_confirmation'],'REQUIRES_SEPARATE_VERIFIED_LEDGER')
 def test_07_leverage_excluded(self):
  self.assertEqual(execute('10',side='buy',quantity='20',price='1',fee_bps='5',slip_bps='10')['status'],'REJECTED_INSUFFICIENT_CASH')
 def test_08_negative_cost_rejected(self):
  with self.assertRaisesRegex(ValueError,'INVALID_UNLEVERAGED'):execute('10',side='buy',quantity='1',price='1',fee_bps='-1',slip_bps='0')
 def test_09_failed_candidate_never_promoted(self):
  v=analyze_trials([dict(id='t1',candidate='c',window='future',score=-1,baseline_score=0,evidence_sha256=H)])
  self.assertFalse(v['promotion_allowed']); self.assertEqual(len(v['failed_trials']),1)
 def test_10_immutable_archive_and_budget(self):
  with tempfile.TemporaryDirectory() as p:
   archive(p,'a',{'x':1})
   with self.assertRaises(FileExistsError):archive(p,'a',{'x':2})
   with self.assertRaisesRegex(ValueError,'BUDGET'):archive(p,'b',{'x':'too big'},max_bytes=3)
if __name__=='__main__': unittest.main()
