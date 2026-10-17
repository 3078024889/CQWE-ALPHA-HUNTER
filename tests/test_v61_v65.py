import unittest
from cqwe.binance_futures_v61_v65 import Rules,Sandbox,reject_unsafe_environment

EX={'symbols':[{'symbol':'BTCUSDT','status':'TRADING','filters':[
 {'filterType':'LOT_SIZE','minQty':'0.001','maxQty':'100','stepSize':'0.001'},
 {'filterType':'PRICE_FILTER','tickSize':'0.1'},
 {'filterType':'MIN_NOTIONAL','notional':'5'}]}]}
class TenReverseAudits(unittest.TestCase):
 def setUp(self):self.rules=Rules.parse(EX,'BTCUSDT')
 def test_01_missing_filters(self):
  with self.assertRaises(ValueError):Rules.parse({'symbols':[{'symbol':'BTCUSDT','status':'TRADING','filters':[]}]},'BTCUSDT')
 def test_02_below_min_notional(self):
  with self.assertRaises(ValueError):self.rules.check('0.001','1000')
 def test_03_lot_step(self):
  with self.assertRaises(ValueError):self.rules.check('0.0015','10000')
 def test_04_tick(self):
  with self.assertRaises(ValueError):self.rules.check('0.001','10000.03')
 def test_05_no_leverage(self):
  with self.assertRaises(ValueError):Sandbox().open(self.rules,'LONG','0.001','10000',leverage=2)
 def test_06_10usd_risk_cap(self):
  with self.assertRaises(ValueError):Sandbox().open(self.rules,'LONG','0.001','10000')
 def test_07_fees_and_slippage_lose_money(self):
  s=Sandbox(max_fraction='1');s.open(self.rules,'LONG','0.001','9000');r=s.close('9000');self.assertLess(float(r['roundtrip_net_pnl']),0)
 def test_08_short_funding_sign(self):
  a=Sandbox(max_fraction='1',fee_bps='0',slip_bps='0');a.open(self.rules,'SHORT','0.001','10000');r=a.close('10000',funding_bps='10');self.assertGreater(float(r['roundtrip_net_pnl']),0)
 def test_09_no_fake_cash(self):
  s=Sandbox(max_fraction='1');s.open(self.rules,'LONG','0.001','9000');s.close('9000');self.assertIsNone(s.report()['real_cash_pnl_usd'])
 def test_10_block_live_config(self):
  for cfg in ({'mode':'LIVE'},{'mode':'OFFLINE','api_key':'X'},{'mode':'OFFLINE','auto_promotion':True}):
   with self.assertRaises(ValueError):reject_unsafe_environment(cfg)
if __name__=='__main__':unittest.main()
