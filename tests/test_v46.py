import tempfile,unittest
from pathlib import Path
from cqwe.readiness_gate_v46 import assess, FOUR, CAPITAL, MAX_ORDER_FRACTION

class V46Adversarial(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
  self.root=Path(self.t.name)/'raw';self.out=Path(self.t.name)/'research'
 def result(self):return assess(self.root,self.out)
 def test_01_no_samples_no_winner(self):self.assertEqual(self.result()['rankable_markets'],[])
 def test_02_no_live_promotion(self):self.assertFalse(self.result()['promotion_allowed'])
 def test_03_no_real_profit_claim(self):self.assertEqual(self.result()['real_profit_usd'],0)
 def test_04_all_four_markets(self):self.assertEqual(set(self.result()['markets']),set(FOUR))
 def test_05_no_maker_fill_claim(self):self.assertEqual(self.result()['real_order_count'],0)
 def test_06_budget_cap(self):self.assertTrue(all(v['max_hypothetical_ticket_usd']==CAPITAL*MAX_ORDER_FRACTION for v in self.result()['markets'].values()))
 def test_07_no_unverified_filter(self):self.assertTrue(all(not v['gates']['exchange_filters_verified'] for v in self.result()['markets'].values()))
 def test_08_no_order_queue_claim(self):self.assertIn('queue position',self.result()['limitations'])
 def test_09_repeat_same_hash(self):self.assertEqual(self.result()['sha256'],self.result()['sha256'])
 def test_10_archive_is_append_only(self):
  r=self.result();f=self.out/('readiness_'+r['sha256']+'.json');self.assertTrue(f.exists());self.result();self.assertEqual(len(list(self.out.glob('readiness_*.json'))),1)
 def test_11_empty_train_gate(self):self.assertTrue(all(not v['gates']['enough_training_events'] for v in self.result()['markets'].values()))
 def test_12_empty_holdout_gate(self):self.assertTrue(all(not v['gates']['enough_independent_holdout_events'] for v in self.result()['markets'].values()))
 def test_13_no_data_deletion(self):
  marker=self.root/'unrelated.bin';marker.parent.mkdir(parents=True,exist_ok=True);marker.write_bytes(b'irreplaceable');self.result();self.assertEqual(marker.read_bytes(),b'irreplaceable')
 def test_14_rejected_missing_sessions(self):self.assertEqual(len(self.result()['alerts']),4)
 def test_15_not_profitability_test(self):self.assertEqual(self.result()['trade_readiness'],'BLOCKED_NO_INDEPENDENT_EXECUTABLE_OOS')

if __name__=='__main__':unittest.main()
