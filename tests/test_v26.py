import unittest,tempfile,json,copy
from pathlib import Path
from cqwe.dendritic_diagnostics_v26 import evaluate,run

def sample():
 return {'decision':'NO_LIVE_PROMOTION','research_only':True,'reports':{
  'shadow':{'account_ledger_verified':True,'initial_usd':10.,'ending_equity_usd':9.7,'virtual_net_usd':-.3,
            'explicit_fill_fees_usd':.035,'entries':2,'max_drawdown_pct':-4.,'paired_trades':[
             {'symbol':'BTCUSDT','buy_time_ms':1,'gross_price_move_usd':-.21,'explicit_fees_usd':.02,'net_usd':-.23},
             {'symbol':'ETHUSDT','buy_time_ms':2,'gross_price_move_usd':-.04,'explicit_fees_usd':.01,'net_usd':-.05}]},
  'shadow_stress':{'account_ledger_verified':True,'explicit_fill_fees_usd':.07}}}
class DiagnosticTests(unittest.TestCase):
 def test_diagnosis(self):
  x=evaluate(sample());self.assertEqual(x['closed_trade_net_usd'],-.28);self.assertIn('PRICE_DIRECTION',[v['finding'] for v in x['proposals']]);self.assertFalse(x['profit_claim'])
 def test_no_fabricated_venue(self):self.assertEqual(evaluate(sample())['venue_status'],'UNKNOWN')
 def test_minimum_trade_rejected(self):
  v={'min_notional_usd':10,'min_qty':.0001,'qty_step':.00001,'price_tick':.01}
  self.assertIn('ORDER_FEASIBILITY_REJECTED',[a['finding'] for a in evaluate(sample(),v)['proposals']])
 def test_valid_venue_not_assumed_tradable(self):
  v={'min_notional_usd':5,'min_qty':.001,'qty_step':.00001,'price_tick':.01}
  self.assertFalse(evaluate(sample(),v)['profit_claim'])
 def test_unknown_partial_venue(self):self.assertIn('ORDER_FEASIBILITY_UNKNOWN',[a['finding'] for a in evaluate(sample(),{'min_qty':1})['proposals']])
 def test_no_mutation(self):
  s=sample();before=copy.deepcopy(s);evaluate(s);self.assertEqual(s,before)
 def test_reject_tampered_account(self):
  s=sample();s['reports']['shadow']['virtual_net_usd']=1
  with self.assertRaisesRegex(ValueError,'NET_RECONCILIATION'):evaluate(s)
 def test_reject_trade_attribution(self):
  s=sample();s['reports']['shadow']['paired_trades'][0]['net_usd']=0
  with self.assertRaisesRegex(ValueError,'TRADE_ATTRIBUTION'):evaluate(s)
 def test_reject_bad_stress(self):
  s=sample();s['reports']['shadow_stress']['explicit_fill_fees_usd']=.01
  with self.assertRaisesRegex(ValueError,'INVALID_COST_STRESS'):evaluate(s)
 def test_reject_invalid_venue(self):
  with self.assertRaisesRegex(ValueError,'INVALID_VENUE_FILTER'):evaluate(sample(),{'min_notional_usd':5,'min_qty':-1,'qty_step':1,'price_tick':1})
 def test_serialization_and_hash(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'s.json';p.write_text(json.dumps(sample()));out=Path(d)/'r.json';x=run(p,out);self.assertEqual(x,json.loads(out.read_text()));self.assertIn('audit_sha256',x)
 def test_repeat_determinism(self):
  a=evaluate(sample());self.assertEqual(a,evaluate(sample()))
if __name__=='__main__':unittest.main()
