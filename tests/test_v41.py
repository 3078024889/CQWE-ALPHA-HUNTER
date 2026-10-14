import json,tempfile,unittest
from pathlib import Path
from cqwe.microstructure_v40 import VERSION, store_record
from cqwe.public_data_v29 import _digest
from cqwe.micro_forward_v41 import evaluate, rule, run_once

BASE=2_000_000_000_000

def obs(t,mid=100.,im=.4,micro=.3):
    return {'symbol':'BNBUSDT','bid':mid-.02,'ask':mid+.02,'mid':mid,
        'spread_bps':4.,'top_imbalance':im,'depth5_imbalance':im,
        'microprice':mid+micro/10000*mid,'microprice_displacement_bps':micro,
        'aggressor_buy_notional':100.,'aggressor_sell_notional':20.,
        'aggressor_imbalance':.6,'trade_count':3,'latest_trade_ms':t,
        'book_update_id':1,'regime':'NO_CONFIRMED_PRESSURE','snapshot_start_ms':t-400,
        'recorded_at_ms':t,'prediction_horizon_end_ms':t+300000,
        'trade_window_completeness':'UNKNOWN_REST_LIMITED','queue_fill_known':False,
        'market_maker_identity_known':False,'not_a_trading_signal':True}

class MicroForwardV41(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=self.temp.name
    def put(self,t,mid=100,im=.4,micro=.3):store_record(obs(t,mid,im,micro),self.root)
    def test_60s_and_300s_future_after_maturity(self):
        self.put(BASE,100);self.put(BASE+60_000,100.05);self.put(BASE+300_000,100.20)
        r=evaluate(self.root,now_ms=BASE+1_000_000)
        self.assertEqual(r['symbol_results']['BNBUSDT']['horizons']['60s']['matched_pairs'],1)
        self.assertEqual(r['symbol_results']['BNBUSDT']['horizons']['300s']['matched_pairs'],1)
        self.assertEqual(r['symbol_results']['BNBUSDT']['horizons']['300s']['directional_signals'],1)
    def test_no_early_future_leak(self):
        self.put(BASE,100);self.put(BASE+59_000,100.1)
        r=evaluate(self.root,now_ms=BASE+100_000)
        self.assertEqual(r['symbol_results']['BNBUSDT']['horizons']['60s']['matched_pairs'],0)
    def test_gap_rejected_for_matching(self):
        self.put(BASE,100);self.put(BASE+120_000,101)
        r=evaluate(self.root,now_ms=BASE+900_000)
        self.assertEqual(r['symbol_results']['BNBUSDT']['horizons']['60s']['matched_pairs'],0)
    def test_does_not_set_profit_true(self):
        self.put(BASE);self.put(BASE+60_000,102)
        r=evaluate(self.root,now_ms=BASE+1_000_000)
        self.assertFalse(r['profitable_edge_proven']);self.assertTrue(r['no_orders'])
    def test_nonindependent_events_admitted(self):
        self.put(BASE);self.put(BASE+60_000,101);self.put(BASE+120_000,102)
        r=evaluate(self.root,now_ms=BASE+1_000_000)
        self.assertEqual(r['symbol_results']['BNBUSDT']['horizons']['60s']['matched_pairs'],2)
        self.assertIn('overlapping',r['limitations'][-1])
    def test_untampered_hash_required(self):
        self.put(BASE)
        f=next(Path(self.root).glob('*.json'));v=json.loads(f.read_text());v['observed_market']['ask']=99
        f.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'MICRO_RECORD_HASH_MISMATCH'):evaluate(self.root,now_ms=BASE+900000)
    def test_rule_fixed(self):
        self.assertEqual(rule(obs(BASE)),1)
        self.assertEqual(rule(obs(BASE,im=-.3,micro=-.4)),-1)
        self.assertEqual(rule(obs(BASE,im=.02)),0)
    def test_no_retroactive_settlement_before_maturity(self):
        self.put(BASE);self.put(BASE+60_000,101)
        r=evaluate(self.root,now_ms=BASE+30_000)
        self.assertEqual(r['matched_event_count'],0)
    def test_duplicate_timestamp_denied_even_different_file(self):
        self.put(BASE)
        f=next(Path(self.root).glob('*.json'))
        (Path(self.root)/'observation_BNBUSDT_DUPLICATE.json').write_bytes(f.read_bytes())
        with self.assertRaisesRegex(ValueError,'DUPLICATE_MARKET_TIMESTAMP'):evaluate(self.root,now_ms=BASE+900000)
    def test_spread_as_quote_crossing_proxy_only(self):
        self.put(BASE,100);self.put(BASE+60_000,100)
        r=evaluate(self.root,now_ms=BASE+900000)
        value=r['symbol_results']['BNBUSDT']['horizons']['60s']['mean_quote_cross_proxy_bps']
        self.assertLess(value,0)
        self.assertFalse(r['profitable_edge_proven'])

if __name__=='__main__':unittest.main()
