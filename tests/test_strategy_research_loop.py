import copy
from pathlib import Path
import tempfile
import unittest
from cqwe.strategy_candidates import single_targets,pair_targets,basket_targets
from cqwe.strategy_research_loop import ShadowBench,ResearchLoop,admission,HOUR,targets_from_closed_history
from research.expanded_strategy_screen import replay
from research.strategy_lab import replay as baseline_replay,signals

T=1800000000000


def bars(n=760):
    return [{'time':T+i*HOUR,'open':100+i*.1,'high':100.2+i*.1,'low':99.8+i*.1,'close':100+i*.1} for i in range(n)]


def quotes(at):return {s:{'bid':100.,'ask':100.02,'observed_ms':at} for s in ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT')}


class CandidateTests(unittest.TestCase):
    def test_causal_variants_do_not_use_current_or_future_candles(self):
        a=bars();b=copy.deepcopy(a);b[740]['close']=1000000
        for k in ('vol_rsi','ts_momentum'):
            self.assertEqual(single_targets(a,k,'ETHUSDT')[:741],single_targets(b,k,'ETHUSDT')[:741])
        self.assertEqual(pair_targets(a,a,'ETHUSDT')[:741],pair_targets(b,a,'ETHUSDT')[:741])

    def test_pair_gap_rejected(self):
        a=bars();b=copy.deepcopy(a);b[100]['time']+=1
        with self.assertRaises(ValueError):pair_targets(a,b,'ETHUSDT')

    def test_same_asset_pair_flat_without_invented_stationarity(self):
        a=bars();self.assertTrue(all(not t for t in pair_targets(a,a,'ETHUSDT')))

    def test_multileg_engine_reconciles_single_leg_baseline(self):
        b=bars();data={s:b for s in quotes(T)};funding={s:[] for s in data}
        target=[{'BTCUSDT':float(d)} if d else {} for d in signals(b,'ema_20_80')]
        a=replay(data,funding,target,T,T+len(b)*HOUR)
        c=baseline_replay(b,[],'ema_20_80',T,T+len(b)*HOUR)
        self.assertAlmostEqual(a['net'],c['net']);self.assertAlmostEqual(a['fees'],c['fees'])

    def test_pair_costs_both_legs_even_when_price_unchanged(self):
        b=[{'time':T+i*HOUR,'open':100.,'high':100.,'low':100.,'close':100.} for i in range(3)]
        d={s:b for s in quotes(T)};targets=[{'ETHUSDT':.5,'BTCUSDT':-.5}]*3
        r=replay(d,{s:[] for s in d},targets,T,T+3*HOUR)
        self.assertLess(r['net'],0);self.assertAlmostEqual(r['net'],r['ledger'][0]['net']);self.assertGreater(r['fees'],0)


class ForwardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'shadow.db';self.bench=ShadowBench(self.path)
    def tearDown(self):self.bench.db.close();self.tmp.cleanup()

    def test_forecast_precedes_label_and_duplicate_tick_does_not_duplicate(self):
        self.bench.tick(quotes(T),T,{'test':{'BTCUSDT':1.}})
        self.assertEqual(self.bench.snapshot()['counts'],{'PENDING':1})
        self.bench.tick(quotes(T),T,{'test':{'BTCUSDT':1.}})
        self.bench.tick(quotes(T+HOUR),T+HOUR)
        s=self.bench.snapshot();self.assertEqual(s['counts'],{'SCORED':1});self.assertEqual(s['nodes'][0]['n'],1)
        self.assertLess(s['nodes'][0]['mean_proxy_bps'],0);self.assertFalse(s['nodes'][0]['funding_reconciled'])
        self.bench.tick(quotes(T+HOUR),T+HOUR);self.assertEqual(self.bench.snapshot()['nodes'][0]['n'],1)

    def test_stale_leg_not_scored_and_late_quote_marked_missed(self):
        self.bench.tick(quotes(T),T,{'pair':{'ETHUSDT':.5,'BTCUSDT':-.5}})
        self.bench.tick(quotes(T),T+HOUR);self.assertEqual(self.bench.snapshot()['counts'],{'PENDING':1})
        self.bench.tick(quotes(T+HOUR+31000),T+HOUR+31000)
        self.assertEqual(self.bench.snapshot()['counts'],{'MISSED':1});self.assertFalse(self.bench.snapshot()['nodes'])

    def test_restart_retains_forecast_and_preserves_no_future_label(self):
        self.bench.tick(quotes(T),T,{'test':{'BTCUSDT':1.}});self.bench.db.close();self.bench=ShadowBench(self.path)
        self.assertEqual(self.bench.snapshot()['counts'],{'PENDING':1})

    def test_source_change_fails_closed(self):
        with self.bench.db:self.bench.db.execute("UPDATE meta SET value='modified' WHERE key='source'")
        with self.assertRaises(ValueError):ShadowBench(self.path)

    def test_cached_histories_generate_real_forward_requests_and_admission_stays_separate(self):
        rows=[[b['time'],str(b['open']),str(b['high']),str(b['low']),str(b['close']),'1',b['time']+HOUR-1] for b in bars()]
        at=rows[-1][6]+1;histories={s:rows for s in quotes(at)}
        proposed=targets_from_closed_history(histories,at)
        self.assertEqual(len(proposed),12)
        self.assertTrue(proposed['ts_momentum:BTCUSDT'])
        def fetch(*args):return rows
        loop=ResearchLoop(Path(self.tmp.name)/'integrated.db',fetch,[{'id':'ts_momentum:BTCUSDT','historical_gate_pass':False}])
        try:
            for _ in range(4):loop.refresh_one(at)
            snap=loop.tick(quotes(at),at)
            self.assertGreater(snap['counts'].get('PENDING',0),0)
            self.assertFalse(snap['admission'][0]['research_gate_pass'])
            self.assertIn('HISTORY_NOT_PASSED',snap['admission'][0]['reasons'])
        finally:loop.close()

    def test_bad_weights_rollback_new_forecast(self):
        with self.assertRaises(ValueError):self.bench.tick(quotes(T),T,{'test':{'BTCUSDT':2.}})
        self.assertFalse(self.bench.snapshot()['counts'])

    def test_profit_proxy_never_promotes_without_real_execution_quality(self):
        a=admission({'historical_gate_pass':True},{'n':1000,'span_days':60,'net_lower_confidence_bps':25},{})
        self.assertFalse(a['research_gate_pass']);self.assertEqual(a['execution_weight'],0)
        q={k:True for k in ('funding_reconciled','order_filters_validated','execution_model_validated','selection_bias_checked')}
        b=admission({'historical_gate_pass':True},{'n':1000,'span_days':60,'net_lower_confidence_bps':float('nan')},q)
        self.assertFalse(b['research_gate_pass'])


if __name__=='__main__':unittest.main()
