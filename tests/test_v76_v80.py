import unittest,tempfile,json
from pathlib import Path
from cqwe.tidal_hunter_v66_v70 import sha
from cqwe.tidal_hunter_v76_v80 import plan_round,verify_chain,memory_summary,validate_archive,run

def source(end=501,market='BTCUSDT'):
    bars=[{'time':i*3600000,'open':str(100+i*.02),'high':str(101+i*.02),'low':str(99+i*.02),'close':str(100+i*.02),'volume':'10'} for i in range(end)]
    return {'source':'BINANCE_USDM_PUBLIC_KLINES','symbol':market,'interval':'1h','bars':bars,'sha256':sha(bars),'live_orders':False}
class TenReverseAuditsV80(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def archive(self,s):
    p=self.p/'in.json';p.write_text(json.dumps(s));return p
 def test_01_unverified_hash_rejected(self):
    s=source();s['sha256']='0'*64
    with self.assertRaises(ValueError):validate_archive(self.archive(s))
 def test_02_forged_live_flag_rejected(self):
    s=source();s['live_orders']=True
    with self.assertRaises(ValueError):validate_archive(self.archive(s))
 def test_03_simulated_never_cash(self):
    r=plan_round(source(),[]);self.assertIsNone(r['realized_cash_profit_usd']);self.assertEqual(r['real_orders'],0)
 def test_04_prevent_early_auto_promotion(self):
    r=plan_round(source(),[]);self.assertFalse(r['promotion_eligible']);self.assertFalse(r['research']['research_review_candidate'])
 def test_05_fail_forged_memhash(self):
    r=plan_round(source(),[]);d=self.p/'m';d.mkdir();(d/'round_000001.json').write_text(json.dumps({**r,'research':{'worst_fold_bps':9999}}))
    with self.assertRaises(ValueError):verify_chain(d)
 def test_06_reject_stale_candle(self):
    old=plan_round(source(),[])
    with self.assertRaises(ValueError):plan_round(source(),[old])
 def test_07_reject_wrong_market(self):
    old=plan_round(source(),[])
    with self.assertRaises(ValueError):plan_round(source(502,'ETHUSDT'),[old])
 def test_08_reject_negative_fees(self):
    with self.assertRaises(ValueError):plan_round(source(),[],fee_bps=-1)
 def test_09_reject_nan_slippage(self):
    with self.assertRaises(ValueError):plan_round(source(),[],slip_bps=float('nan'))
 def test_10_immutable_round_and_chain(self):
    s=source();f=self.archive(s);d=self.p/'memory';p,r=run(f,d);self.assertEqual(len(verify_chain(d)),1)
    with self.assertRaises(ValueError):run(f,d)
    s2=source(502);f.write_text(json.dumps(s2));q,r2=run(f,d);self.assertEqual(r2['previous_record_sha256'],r['record_sha256']);self.assertEqual(len(verify_chain(d)),2)
 def test_11_detect_missing_chain_member(self):
    f=self.archive(source());d=self.p/'mem';a,_=run(f,d);f.write_text(json.dumps(source(502)));run(f,d);a.unlink()
    with self.assertRaises(ValueError):verify_chain(d)
 def test_12_memory_past_only(self):
    self.assertEqual(memory_summary([])['prior_rounds'],0)
    with self.assertRaises(ValueError):memory_summary([],0)
if __name__=='__main__':unittest.main()
