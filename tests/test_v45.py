import json,tempfile,unittest,os,time
from pathlib import Path
from cqwe.storage_governor_v45 import plan,apply
from cqwe.evolution_cycle_v45 import extract_events,score,digest
from cqwe.market_replay_v43 import hash_record
from cqwe.market_maker_competition_v45 import evaluate as mm_evaluate

class TestV45TenAdversarial(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def make_capture(self,invalid=False):
  f=self.root/'capture.jsonl';prev='0'*64
  kinds=[('START',{'synced':True}),('BOOK',{'bid':'100','ask':'101','bid_qty':'5','ask_qty':'5','synced':True}),
    ('BOOK',{'bid':'100','ask':'101','bid_qty':'6','ask_qty':'4','synced':True}),
    ('BOOK',{'bid':'101','ask':'102','bid_qty':'6','ask_qty':'4','synced':True}),
    ('BOOK',{'bid':'103','ask':'104','bid_qty':'6','ask_qty':'4','synced':True}),('STOP',{'synced':True})]
  with f.open('w') as stream:
   for i,(kind,payload) in enumerate(kinds,1):
    ns=(i-1)*61_000_000_000
    rec={'schema':'CQWE_V43_CAPTURE','sequence':i,'prev_sha256':prev,'session_id':'fixed','received_ns':ns,'kind':kind,'payload':payload}
    rec['sha256']=hash_record(rec)
    if invalid and i==4:rec['sha256']='0'*64
    prev=rec['sha256'];stream.write(json.dumps(rec)+'\n')
  return f
 def test_01_corrupt_hash_rejected(self):
  with self.assertRaises(ValueError):extract_events(self.make_capture(True))
 def test_02_only_prior_book_features(self):
  e=extract_events(self.make_capture());self.assertTrue(e);self.assertEqual(e[0]['decision_ns'],122_000_000_000)
 def test_03_future_outcome_after_decision(self):
  for e in extract_events(self.make_capture()):self.assertGreaterEqual(e['outcome_ns']-e['decision_ns'],60_000_000_000)
 def test_04_nonoverlap_events(self):
  e=extract_events(self.make_capture());self.assertEqual(len(e),1)
 def test_05_all_six_genotypes(self):
  s=score(extract_events(self.make_capture()));self.assertEqual(len(s),6)
 def test_06_no_auto_promotion(self):
  self.assertTrue(all(s['promotion']=='INELIGIBLE_REPLAY_NOT_LIVE_OOS' for s in score(extract_events(self.make_capture()))))
 def test_07_dry_run_no_deletion(self):
  p=self.root/'pycache'/'x.pyc';p.parent.mkdir();p.write_bytes(b'abc');os.utime(p,(time.time()-9*86400,)*2)
  report=plan(self.root);self.assertEqual(len(report['files']),1);self.assertTrue(p.exists())
 def test_08_old_cache_only(self):
  cache=self.root/'pycache';cache.mkdir();a=cache/'a.pyc';b=cache/'b.pyc';a.write_bytes(b'a');b.write_bytes(b'b')
  os.utime(a,(time.time()-9*86400,)*2)
  self.assertEqual([Path(x['path']).name for x in plan(self.root)['files']],['a.pyc'])
 def test_09_protected_evidence(self):
  p=self.root/'l2_v44'/'BTCUSDT'/'x.jsonl';p.parent.mkdir(parents=True);p.write_bytes(b'important');self.assertFalse(plan(self.root)['files']);self.assertTrue(p.exists())
 def test_10_no_changed_cache_purge(self):
  p=self.root/'pycache'/'x.pyc';p.parent.mkdir();p.write_bytes(b'abc');os.utime(p,(time.time()-9*86400,)*2)
  saved=plan(self.root);p.write_bytes(b'changed')
  with self.assertRaises(ValueError):apply(self.root,saved)
  self.assertTrue(p.exists())

 def test_11_no_maker_fill_claim(self):
  r=mm_evaluate(extract_events(self.make_capture()))
  self.assertEqual(r['actual_fills'],0)
  self.assertFalse(r['promotion_allowed'])
  self.assertEqual(r['benchmarks']['inventory_skew_proxy']['hypothetical_fill_count'],0)
 def test_12_all_baselines_on_same_events(self):
  events=extract_events(self.make_capture());r=mm_evaluate(events)
  self.assertEqual(r['event_count'],len(events));self.assertEqual(len(r['benchmarks']),5)
 def test_13_future_leak_overlap_refused(self):
  events=extract_events(self.make_capture())
  with self.assertRaises(ValueError):mm_evaluate(events+events)
 def test_14_nan_cost_proxy_refused(self):
  event=extract_events(self.make_capture())[0];event['long_cross_proxy_bps']=float('nan')
  with self.assertRaises(ValueError):mm_evaluate([event])
 def test_15_zero_events_not_profit(self):
  r=mm_evaluate([])
  self.assertEqual(r['event_count'],0);self.assertFalse(r['benchmarks']['always_cross_buy']['profit_proven'])

if __name__=='__main__':unittest.main()
