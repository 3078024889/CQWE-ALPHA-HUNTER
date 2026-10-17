import copy
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from cqwe.copernican_experiment_v81_v85 import digest
from cqwe.four_market_core import Engine, Model, Portfolio, SYMBOLS, BASIS, config, eligible
from cqwe.four_market_runner import Processor, envelope, replay_round
from cqwe.prediction_catalog import binance_read
from cqwe.tidal_hunter import Journal, write_new

RULE = {'step':'.001','min_qty':'.001','max_qty':'100','min_notional':'1'}
RULES = {s:RULE.copy() for s in SYMBOLS}


def view(s='BTCUSDT', price=100, ms=1000):
    return {'symbol':s,'synced':True,'bid':str(price), 'ask':str(price+.02),
            'mid':str(price+.01),'bid_qty':'100','ask_qty':'100','imbalance':0.,
            'spread_bps':2.,'bids':[[str(price-i*.01),'100'] for i in range(5)],
            'asks':[[str(price+.02+i*.01),'100'] for i in range(5)],'received_ns':ms*1_000_000}


def quote(**kw):
    q = {'venue':'fixture','market_id':'one','symbol':'BTCUSDT','at_ms':1000,'collateral':'USDT',
         'start_ms':0,'end_ms':300000,'reference_ms':1000,'book_ms':1000,
         'reference_basis':'EXPLICIT_TEST_ORACLE','reference_matches_rules':True,
         'reference_price':'100','anchor_price':'99','tie_rule':'UP',
         'rules_sha256':'a'*64,'source_sha256':'b'*64,'features':[.1]*8,
         'market_probability_up':.5,'fee_rate':'.04','fee_formula':'RATE_P_ONE_MINUS_P',
         'up_ask':'.5','down_ask':'.51','up_ask_size':'100','down_ask_size':'100','min_shares':'1'}
    q.update(kw)
    return q


class FourMarketTests(unittest.TestCase):
    def engine(self, emit=None):
        return Engine(config(),RULES,emit)

    def test_causal_300_and_900_second_labels_separate_symbols(self):
        e = self.engine()
        for ms in range(1000,903000,1000):
            for s in SYMBOLS:
                e.frame(s,ms,view(s,100+ms/100000,ms),[.1,.2,.3,.1])
        self.assertEqual(e.matured,16)
        for s in SYMBOLS:
            self.assertEqual(e.models[s+':300']['branch2'].updates,3)
            self.assertEqual(e.models[s+':900']['branch2'].updates,1)
            self.assertEqual(e.models[s+':300']['frozen'].updates,0)
        self.assertEqual(e.portfolio.cash,10)

    def test_gap_drops_labels_and_does_not_train(self):
        e = self.engine()
        e.frame('BTCUSDT',1000,view(),[0.]*4)
        e.frame('BTCUSDT',301000,view(price=101,ms=301000),[0.]*4)
        self.assertEqual(e.matured,0)
        self.assertEqual(e.dropped,2)
        self.assertEqual(e.faults['BTCUSDT'],1)

    def test_stale_one_symbol_detected_when_another_is_fresh(self):
        e = self.engine()
        for s in SYMBOLS:
            e.frame(s,1000,view(s),[0.]*4)
        e.frame('ETHUSDT',2000,view('ETHUSDT',ms=2000),[0.]*4)
        e.tick(2600)
        self.assertNotIn('BTCUSDT',e.latest)
        self.assertIn('ETHUSDT',e.latest)

    def test_resume_roundtrip_has_identical_future_updates(self):
        a = self.engine()
        for ms in range(1000,151000,1000):
            a.frame('SOLUSDT',ms,view('SOLUSDT',100+ms/100000,ms),[.1]*4)
        b = Engine(a.cfg,RULES,previous=json.loads(json.dumps(a.state())))
        for ms in range(151000,302000,1000):
            v = view('SOLUSDT',100+ms/100000,ms)
            a.frame('SOLUSDT',ms,v,[.1]*4)
            b.frame('SOLUSDT',ms,v,[.1]*4)
        self.assertEqual(a.state(),b.state())

    def test_tamper_and_context_change_rejected(self):
        e = self.engine()
        st = e.state()
        st['matured'] = 99
        with self.assertRaisesRegex(ValueError,'HASH'):
            Engine(e.cfg,RULES,previous=st)
        with self.assertRaisesRegex(ValueError,'CONTEXT'):
            Engine(config((300,)),RULES,previous=e.state())

    def test_model_bounds_and_invalid_input(self):
        m = Model('branch4')
        x = [1.,-1.]*4
        for _ in range(1000):
            p,c = m.predict(x)
            self.assertTrue(0 < p < 1)
            m.learn(x,1,p,c)
        m.validate()
        with self.assertRaises(ValueError):
            m.predict([float('nan')]*8)

    def test_one_cash_pool_limits_four_entries(self):
        events=[]
        emit=lambda k,p:events.append((k,p))
        p = Portfolio(config())
        for s in SYMBOLS:
            p.request(s,view(s),1000,1,300,'source',RULE,emit)
        self.assertLessEqual(p.reserved(),5)
        self.assertLessEqual(len(p.futures),2)
        for s in SYMBOLS:
            p.frame(s,view(s,ms=1300),1300,emit,RULE)
        self.assertLessEqual(p.reserved(),5)
        self.assertGreater(p.cash,0)
        self.assertTrue(any(k=='FUTURES_OPEN' for k,_ in events))

    def test_entry_latency_then_exit_fees_and_cash(self):
        p = Portfolio(config())
        events=[]
        emit=lambda k,r:events.append((k,r))
        p.request('BTCUSDT',view(),1000,1,300,'id',RULE,emit)
        p.frame('BTCUSDT',view(ms=1100),1100,emit,RULE)
        self.assertTrue(p.futures['BTCUSDT']['pending'])
        p.frame('BTCUSDT',view(ms=1300),1300,emit,RULE)
        entry = copy.deepcopy(p.futures['BTCUSDT'])
        cash_before = p.cash
        p.frame('BTCUSDT',view(price=101,ms=2000),2000,emit,RULE)
        close = [r for k,r in events if k=='FUTURES_CLOSE'][0]
        self.assertEqual(p.cash,cash_before+D(close['gross'])-D(close['fee']))
        self.assertLess(D(entry['entry']),D(close['price']))
        self.assertEqual(p.closed,1)

    def test_real_minimum_notional_not_bypassed(self):
        p = Portfolio(config())
        rules = {**RULE,'min_notional':'50'}
        p.request('BTCUSDT',view(),1000,1,300,'id',rules,lambda *_:None)
        self.assertFalse(p.futures)

    def test_fault_retains_position_then_exits_on_fresh_book(self):
        p = Portfolio(config())
        emit=lambda *_:None
        p.request('BTCUSDT',view(),1000,1,300,'id',RULE,emit)
        p.frame('BTCUSDT',view(ms=1300),1300,emit,RULE)
        p.fault('BTCUSDT')
        self.assertTrue(p.futures['BTCUSDT']['force_exit'])
        self.assertEqual(p.room('SOLUSDT'),0)
        p.frame('BTCUSDT',view(ms=2000),2000,emit,RULE)
        self.assertFalse(p.futures)

    def test_event_forecast_then_final_label_only(self):
        e = self.engine()
        e.frame('BTCUSDT',1000,view(),[0.]*4)
        e.event_quote(quote())
        self.assertEqual(sum(m.updates for m in e.event_models.values()),0)
        r = {'venue':'fixture','market_id':'one','final':True,'rules_sha256':'a'*64,
             'at_ms':300000,'source_sha256':'c'*64,'payouts':['1','0']}
        with self.assertRaises(ValueError):
            e.event_resolve({**r,'at_ms':2000})
        e.event_resolve(r)
        self.assertEqual(sum(m.updates for m in e.event_models.values()),1)
        with self.assertRaises(ValueError):
            e.event_resolve(r)

    def test_proxy_cannot_be_external_reference(self):
        e = self.engine()
        e.frame('BTCUSDT',1000,view(),[0.]*4)
        with self.assertRaisesRegex(ValueError,'EXTERNAL_REFERENCE'):
            e.event_quote(quote(reference_basis=BASIS))
        self.assertFalse(e.events)

    def test_refund_pays_but_never_becomes_binary_label(self):
        e = self.engine()
        e.frame('BTCUSDT',1000,view(),[0.]*4)
        e.event_quote(quote())
        e.portfolio.cash -= D('1')
        e.portfolio.binary['fixture:one'] = {'symbol':'BTCUSDT','side':'UP','shares':'2','cost':'1','rules_sha256':'a'*64}
        e.event_resolve({'venue':'fixture','market_id':'one','final':True,'rules_sha256':'a'*64,
                         'at_ms':300000,'source_sha256':'c'*64,'payouts':['.5','.5']})
        self.assertEqual(e.portfolio.cash,10)
        self.assertEqual(sum(m.updates for m in e.event_models.values()),0)

    def test_unknown_fee_or_stale_reference_fails_without_event(self):
        for changes in ({'fee_formula':'UNKNOWN'},{'book_ms':-10000},{'reference_ms':2000},{'features':[float('inf')]*8}):
            e = self.engine()
            e.frame('BTCUSDT',1000,view(),[0.]*4)
            with self.assertRaises(ValueError):
                e.event_quote(quote(**changes))
            self.assertFalse(e.events)
            self.assertFalse(e.event_models)

    def test_no_candidate_promotion_on_tiny_or_negative_samples(self):
        e = self.engine()
        for _ in range(5):
            e.end_round()
        self.assertFalse(e.promotions)
        self.assertFalse(any(eligible(s) for scores in e.scores.values() for s in scores.values()))

    def test_signed_reader_allowlist_blocks_mutating_endpoints(self):
        for path in ('order','transfer','market/list?evil=1','https://example.com'):
            with self.assertRaisesRegex(ValueError,'NOT_ALLOWED'):
                binance_read(path)
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(ValueError,'CREDENTIALS_NOT_CONFIGURED'):
                binance_read('market/list')

    def test_horizons_reject_five_seconds_and_duplicates(self):
        for value in ((5,), (300,300), (), (True,), (300.,)):
            with self.assertRaises(ValueError):
                config(value)

    def test_collateral_is_not_silently_treated_as_usdt(self):
        e=self.engine()
        e.frame('BTCUSDT',1000,view(),[0.]*4)
        with self.assertRaisesRegex(ValueError,'COLLATERAL'):
            e.event_quote(quote(collateral='USDC'))
        self.assertFalse(e.events)

    def test_quiet_symbol_zero_flow_does_not_drop_maturity(self):
        e=self.engine()
        p=Processor(e)
        snap={'lastUpdateId':100,'bids':[[str(100-i),'100'] for i in range(5)],
              'asks':[[str(101+i),'100'] for i in range(5)]}
        p.process('SNAPSHOT',{'symbol':'BNBUSDT','snapshot':snap})
        p.process('FLOW',{'symbol':'BNBUSDT','event':{'e':'aggTrade','s':'BNBUSDT','a':1,'m':False,'p':'100','q':'1'},'received_ns':1000000000})
        previous=100
        for ms in range(1000,302000,1000):
            p.process('FLOW',{'symbol':'BTCUSDT','event':{'e':'aggTrade','s':'BTCUSDT','a':ms,'m':False,'p':'100','q':'1'},'received_ns':ms*1000000})
            ident=previous+1
            p.process('DEPTH',{'symbol':'BNBUSDT','event':{'e':'depthUpdate','s':'BNBUSDT','E':ms,
                      'U':previous,'u':ident,'pu':previous,'b':[['100',str(100+ms//1000)]],'a':[['101','0'],['101.02','100']] if ms==301000 else []},
                      'at_ms':ms,'now_ns':ms*1000000,'received_ns':ms*1000000})
            p.process('TICK',{'at_ms':ms})
            previous=ident
        self.assertEqual(e.faults['BNBUSDT'],0)
        self.assertEqual(e.models['BNBUSDT:300']['branch2'].updates,1)

    def test_raw_journal_replay_and_tamper_detection(self):
        e = self.engine()
        p = Processor(e)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_new(folder/'initial.json',envelope(e,p,None,None))
            with (folder/'journal.jsonl').open('x',encoding='utf-8') as f:
                j = Journal(f)
                e.emit = lambda k,v:j.emit('DERIVED_'+k,v)
                def consume(k,v):
                    j.emit('INPUT_'+k,v)
                    p.process(k,v)
                snap = {'lastUpdateId':100,'bids':[[str(100-i),'100'] for i in range(5)],
                        'asks':[[str(101+i),'100'] for i in range(5)]}
                for symbol in SYMBOLS:
                    consume('SNAPSHOT',{'symbol':symbol,'snapshot':snap})
                    consume('FLOW',{'symbol':symbol,'event':{'e':'aggTrade','s':symbol,'a':1,'m':False,'p':'100','q':'1'},'received_ns':1000000000})
                    consume('DEPTH',{'symbol':symbol,'event':{'e':'depthUpdate','s':symbol,'E':1000,'U':100,'u':101,'pu':99,'b':[],'a':[]},
                                     'at_ms':1000,'now_ns':1000000000,'received_ns':1000000000})
                consume('ROUND_END',{})
                final = envelope(e,p,None,j.previous)
            write_new(folder/'state.json',final)
            audit = replay_round(folder)
            self.assertEqual(sum(v is True for v in audit.values()),10)
            text = (folder/'journal.jsonl').read_text()
            (folder/'journal.jsonl').write_text(text.replace('"E":1000','"E":2000'))
            with self.assertRaises(ValueError):
                replay_round(folder)


if __name__ == '__main__':
    unittest.main()
