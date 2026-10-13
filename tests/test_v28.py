import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.forward_experiment_v28 import _simulate,evaluate

class V28Tests(unittest.TestCase):
 def candle(self,i,price=100.):return [i*300000,price,price*1.01,price*.99,price,100,0,1000]
 def bars(self,n=250,price=100.):return [self.candle(i,price) for i in range(n)]
 def stub(self):
  return ({'version':'CQWE_V27_MUTATION_REGISTRY'},'a'*64,{'last_seen_ms':-300000,'tip_sha256':'b'*64},{'BTCUSDT|range_low|breakout':.15},{'BTCUSDT':'x'*64})
 def mocked(self,bars=None):
  if bars is None:bars=self.bars()
  return patch('cqwe.forward_experiment_v28._load_checked',return_value=self.stub()),patch('cqwe.forward_experiment_v28.read_markets',return_value=([x[0] for x in bars],{'BTCUSDT':bars},{'BTCUSDT':'y'*64}))
 def test_flat_ledger(self):
  b=self.bars();x=_simulate([r[0] for r in b],{'BTCUSDT':b},{'BTCUSDT|range_low|breakout':.15},.1,5,2,0,5)
  self.assertTrue(x['ledger_balanced']);self.assertEqual(x['entries'],0);self.assertEqual(x['virtual_equity_usd'],10.)
 def test_both_variants_cash(self):
  a,b=self.mocked()
  with a,b:
   x=evaluate('r','s',['future']);self.assertEqual([v['threshold'] for v in x['variants']],[.1,.2]);self.assertFalse(x['auto_promotion'])
 def test_reused_history(self):
  b=self.bars();b[0][0]=-300000;a,c=self.mocked(b)
  with a,c,self.assertRaisesRegex(ValueError,'OVERLAPPING'):evaluate('r','s',['future'])
 def test_gap(self):
  b=self.bars();[row.__setitem__(0,row[0]+300000) for row in b];a,c=self.mocked(b)
  with a,c,self.assertRaisesRegex(ValueError,'GAP'):evaluate('r','s',['future'])
 def test_sources_repeated(self):
  a,b=self.mocked()
  with a,b,patch('cqwe.forward_experiment_v28.read_markets',return_value=([x[0] for x in self.bars()],{'BTCUSDT':self.bars()},{'BTCUSDT':'x'*64})):
   with self.assertRaisesRegex(ValueError,'SAME_SOURCE'):evaluate('r','s',['future'])
 def test_market_change(self):
  a,b=self.mocked()
  with a,b,patch('cqwe.forward_experiment_v28.read_markets',return_value=([x[0] for x in self.bars()],{'ETHUSDT':self.bars()},{'ETHUSDT':'y'*64})):
   with self.assertRaisesRegex(ValueError,'MARKET_SET'):evaluate('r','s',['future'])
 def test_bad_cost(self):
  with self.assertRaisesRegex(ValueError,'BAD_COST'):evaluate('r','s',['future'],extra_cost_bps=-1)
 def test_short(self):
  a,b=self.mocked(self.bars(239))
  with a,b,self.assertRaisesRegex(ValueError,'INSUFFICIENT'):evaluate('r','s',['future'])
 def test_empty_weights(self):
  st=list(self.stub());st[3]={};a,b=self.mocked()
  with a,b,patch('cqwe.forward_experiment_v28._load_checked',return_value=tuple(st)):
   with self.assertRaisesRegex(ValueError,'EMPTY'):evaluate('r','s',['future'])
 def test_output_audit(self):
  a,b=self.mocked()
  with tempfile.TemporaryDirectory() as t,a,b:
   out=Path(t)/'a.json';r=evaluate('r','s',['future'],out)
   self.assertEqual(r,json.loads(out.read_text()));self.assertIn('audit_sha256',r)
if __name__=='__main__':unittest.main()
