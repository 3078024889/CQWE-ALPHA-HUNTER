import tempfile, unittest
from pathlib import Path
from cqwe.microstructure_v40 import analyze,store_record,audit,_verify,collect_once
class V40Microstructure(unittest.TestCase):
 def setUp(self):
  self.depth={'lastUpdateId':22,'bids':[['99','4'],['98','3']],'asks':[['101','1'],['102','2']]}
  self.trades=[{'p':'100','q':'1','m':False,'T':1000},{'p':'100','q':'1','m':True,'T':1100}]
 def calc(self):return analyze(self.depth,self.trades,symbol='BNBUSDT',started_ms=1100,ended_ms=1200)
 def test_balanced_aggressor(self):
  v=self.calc();self.assertAlmostEqual(v['aggressor_imbalance'],0);self.assertGreater(v['microprice'],v['mid']);self.assertTrue(v['not_a_trading_signal'])
 def test_zero_trades(self):
  x=analyze(self.depth,[],symbol='BNBUSDT',started_ms=1100,ended_ms=1200);self.assertIsNone(x['aggressor_imbalance'])
 def test_spread_not_fill(self):
  v=self.calc();self.assertFalse(v['queue_fill_known']);self.assertFalse(v['market_maker_identity_known'])
 def test_crossover_rejected(self):
  x=dict(self.depth,asks=[['99','1']]);self.assertRaisesRegex(ValueError,'CROSSED_BOOK',analyze,x,[],symbol='BNBUSDT',started_ms=1100,ended_ms=1200)
 def test_reorder_rejected(self):
  x=dict(self.depth,bids=[['98','2'],['99','2']]);self.assertRaisesRegex(ValueError,'BOOK_NOT_SORTED',analyze,x,[],symbol='BNBUSDT',started_ms=1100,ended_ms=1200)
 def test_out_of_window_rejected(self):
  x=[{'p':'100','q':'1','m':False,'T':-300001}];self.assertRaisesRegex(ValueError,'TRADE_TIMESTAMP_OUT_OF_WINDOW',analyze,self.depth,x,symbol='BNBUSDT',started_ms=1100,ended_ms=1200)
 def test_stale_rejected(self):self.assertRaisesRegex(ValueError,'SNAPSHOT_TOO_SLOW',analyze,self.depth,[],symbol='BNBUSDT',started_ms=1100,ended_ms=40000)
 def test_observation_hashed_and_append_only(self):
  with tempfile.TemporaryDirectory() as d:
   path,status=store_record(self.calc(),d);self.assertEqual(status,'OBSERVATION_RECORDED')
   self.assertEqual(store_record(self.calc(),d)[1],'ALREADY_RECORDED')
   self.assertEqual(audit(d)['total_observations'],1)
   p=Path(path);p.write_text(p.read_text().replace('BNBUSDT','BTCUSDT'))
   self.assertRaisesRegex(ValueError,'MICRO_RECORD_HASH_MISMATCH',audit,d)
 def test_public_fetch_is_injected(self):
  def fetch(endpoint,params):return self.depth if endpoint=='depth' else self.trades
  self.assertEqual(collect_once(fetch=fetch,clock=lambda:1200)['symbol'],'BNBUSDT')
 def test_no_tradable_claim(self):
  self.assertFalse(audit('/nonexistent/path')['profitable_edge_proven'])
if __name__=='__main__':unittest.main()
