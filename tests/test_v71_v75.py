import unittest, json, tempfile
from pathlib import Path
from cqwe.tidal_hunter_v71_v75 import execution_gate,audit_walkforward,record_lineage,classify_regimes,money
from cqwe.tidal_hunter_v66_v70 import parse_klines,sha

class ReverseAuditsV75(unittest.TestCase):
 def test_01_leverage_rejected(self):
  with self.assertRaises(ValueError):execution_gate(price='1',quantity='1',step='1',min_notional='1',leverage=2)
 def test_02_over_budget(self):
  self.assertEqual(execution_gate(price='11',quantity='1',step='1',min_notional='1')['reason'],'INSUFFICIENT_CASH')
 def test_03_min_notional(self):
  self.assertEqual(execution_gate(price='1',quantity='1',step='1',min_notional='5')['reason'],'MIN_NOTIONAL')
 def test_04_quantity_step(self):
  self.assertEqual(execution_gate(price='1',quantity='1.1',step='1',min_notional='1')['reason'],'LOT_STEP')
 def test_05_fee_consumes_cash(self):
  self.assertFalse(execution_gate(price='10',quantity='1',step='1',min_notional='1')['eligible'])
 def test_06_money_float_nan(self):
  for v in [1.0,'NaN','Infinity','-1']:
   with self.assertRaises(ValueError):money(v)
 def test_07_fake_promotion_rejected(self):
  x={'schema':'CQWE_V66_V70_WALK_FORWARD','selection_uses_test_data':False,'real_orders':0,'live_trading':True,'folds':[{},{}]}
  with self.assertRaises(ValueError):audit_walkforward(x)
 def test_08_overlap_rejected(self):
  f=lambda start,end:{'test_start_time':start,'test_end_time':end,'trades':20,'simulated_net_bps':10.}
  x={'schema':'CQWE_V66_V70_WALK_FORWARD','selection_uses_test_data':False,'real_orders':0,'live_trading':False,'folds':[f(1,5),f(5,10)]}
  with self.assertRaises(ValueError):audit_walkforward(x)
 def test_09_research_is_not_promotion(self):
  f=lambda start,end:{'test_start_time':start,'test_end_time':end,'trades':15,'simulated_net_bps':10.}
  x={'schema':'CQWE_V66_V70_WALK_FORWARD','selection_uses_test_data':False,'real_orders':0,'live_trading':False,'folds':[f(1,2),f(3,4),f(5,6)]}
  self.assertFalse(audit_walkforward(x)['promotion_eligible'])
 def test_10_lineage_immutable_semantics(self):
  x=record_lineage({'ok':True},parent_digest='a'*64)
  self.assertIsNone(x['cash_income_usd']);self.assertFalse(x['live_order_enabled']);self.assertEqual(x['record_sha256'],sha({k:v for k,v in x.items() if k!='record_sha256'}))
 def test_11_regime_no_future(self):
  bars=[{'time':i,'close':str(100+i)} for i in range(120)]
  a=classify_regimes(bars)
  bars[119]['close']='99999'
  b=classify_regimes(bars)
  self.assertEqual(a,b)
 def test_12_cash_cap(self):
  with self.assertRaises(ValueError):execution_gate(cash_usd='100',price='1',quantity='1',step='1',min_notional='1')
if __name__=='__main__':unittest.main()
