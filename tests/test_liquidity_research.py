import copy
import json
import unittest
from unittest.mock import patch

from cqwe.four_market_core import Engine,config
from cqwe.four_market_runner import Processor
from cqwe.liquidity_research import LiquidityTape,LiquidityStudy,Branch16,open_interest
from tests.test_four_market import RULES,view

S='BTCUSDT'


def mark(ms=1000, **kwargs):
    return {'e':'markPriceUpdate','s':S,'E':ms,'p':'100.1','i':'100','r':'-.0001','T':30000000,**kwargs}


def oi(ms=1000,value='100'):
    return {'symbol':S,'time':ms,'openInterest':value}


def liq(side='SELL',last='1',cumulative='10',avg='100'):
    return {'e':'forceOrder','E':1000,'o':{'s':S,'S':side,'l':last,'z':cumulative,
            'ap':avg,'q':'1000','p':'101','T':1000,'X':'FILLED'}}


class LiquidityTests(unittest.TestCase):
    def tape(self):
        t=LiquidityTape()
        t.context('MARK',S,mark(),1000000000)
        t.context('OI',S,oi(),1000000000)
        return t

    def test_sampled_liquidation_direction_last_fill_and_dedup(self):
        t=self.tape()
        t.context('LIQUIDATION',S,liq(),1000000000)
        t.context('LIQUIDATION',S,liq(),1000000001)
        d=t.data[S]
        self.assertEqual(d['counters']['liquidations'],1)
        self.assertEqual(d['liquidations'][0][1],-100.)
        t.context('LIQUIDATION',S,liq('BUY',last='2'),1000000002)
        self.assertEqual(d['liquidations'][-1][1],200.)
        x,q=t.sample(S,view(),1100000000,1100)
        self.assertAlmostEqual(x[4],1/3)
        self.assertTrue(q['sampled_liquidations_only'])

    def test_unfilled_liquidation_is_not_original_quantity(self):
        t=self.tape()
        t.context('LIQUIDATION',S,liq(last='0',cumulative='0',avg='0'),1000000000)
        self.assertEqual(t.data[S]['liquidations'][0][1],0)

    def test_invalid_liquidation_does_not_change_state(self):
        t=self.tape();before=t.state()
        with self.assertRaises(ValueError):
            t.context('LIQUIDATION',S,liq(last='11',cumulative='10'),1000000000)
        self.assertEqual(t.state(),before)

    def test_missing_context_is_unknown_not_observed_zero(self):
        t=LiquidityTape()
        x,q=t.sample(S,view(),1000000000,1000)
        self.assertEqual(x[4:6],[0.,0.])
        self.assertFalse(q['context_ready'])
        self.assertFalse(q['stop_orders_visible'])
        self.assertFalse(q['cancellation_vs_execution_identified'])

    def test_mark_and_oi_freshness_and_future_rejection(self):
        t=self.tape()
        self.assertTrue(t.sample(S,view(),1000000000,1000)[1]['context_ready'])
        self.assertFalse(t.sample(S,view(),5000000000,5000)[1]['context_ready'])
        t.context('MARK',S,mark(ms=9999999),5000000000)
        self.assertFalse(t.sample(S,view(),5000000000,5000)[1]['mark_fresh'])

    def test_mark_received_after_depth_before_decision_is_available(self):
        e=Engine(config(),RULES)
        e.liquidity.context('MARK',S,mark(),1100000000)
        e.liquidity.context('OI',S,oi(),1100000000)
        v=view();v['decision_ns']=1200000000
        e.frame(S,1200,v,[0.]*4)
        self.assertEqual(len(e.liquidity_study.pending),2)

    def test_oi_change_uses_only_previous_observation(self):
        t=self.tape()
        before=t.sample(S,view(),1000000000,1000)[0][7]
        t.context('OI',S,oi(2000,'110'),2000000000)
        after=t.sample(S,view(ms=2000),2000000000,2000)[0][7]
        self.assertEqual(before,0)
        self.assertGreater(after,0)

    def test_out_of_window_level_not_inferred_cancelled(self):
        t=self.tape();v=view();t.sample(S,v,1000000000,1000)
        shifted=view(price=101,ms=1100)
        shifted['asks']=copy.deepcopy(v['asks'])
        # Shift bids upward by one price level without reducing overlapping sizes.
        shifted['bids']=[['100.01','100']]+v['bids'][:-1]
        x,q=t.sample(S,shifted,1100000000,1100)
        self.assertEqual(x[0],0.)
        self.assertGreater(x[1],0.)
        self.assertFalse(q['cancellation_vs_execution_identified'])

    def test_removed_best_level_inside_known_range_is_depletion(self):
        t=self.tape();v=view();t.sample(S,v,1000000000,1000)
        changed=copy.deepcopy(v);changed['asks']=v['asks'][1:]+[['101','100']]
        x,_=t.sample(S,changed,1100000000,1100)
        self.assertGreater(x[0],0.)

    def test_price_formatting_does_not_create_liquidity(self):
        t=self.tape();v=view();t.sample(S,v,1000000000,1000)
        formatted=copy.deepcopy(v)
        formatted['bids']=[[p+'0' if '.' in p else p+'.0',q] for p,q in v['bids']]
        x,_=t.sample(S,formatted,1100000000,1100)
        self.assertEqual(x[:2],[0.,0.])

    def test_range_uses_past_only_and_not_hidden_stops(self):
        t=self.tape()
        for i in range(10):t.sample(S,view(),1000000000+i*10000000,1000)
        x,_=t.sample(S,view(price=101),1200000000,1200)
        self.assertGreater(x[3],0.)
        self.assertLess(t.data[S]['last_signals']['observed_prior_high'],101)
        self.assertFalse(t.data[S]['last_signals']['inferred_stop_locations'])

    def test_ablation_only_removes_liquidation_features(self):
        study=LiquidityStudy([300]);events=[]
        micro=[.1,.2,.3,.4,.5,.6,.7,.8]
        study.frame(S,1000,view(),[.1]*8,micro,{'context_ready':True},lambda k,p:events.append((k,p)),14)
        f=study.pending[S+':300']
        self.assertEqual(f['features']['control'],[.1]*8+[0.]*8)
        full=f['features']['liquidity'].copy();full[12]=full[13]=0.
        self.assertEqual(full,f['features']['no_liquidation'])
        self.assertEqual(sum(m.updates for m in study.models[S+':300'].values()),0)

    def test_shadow_matures_once_and_scores_before_learning(self):
        study=LiquidityStudy([300]);events=[]
        emit=lambda k,p:events.append((k,copy.deepcopy(p)))
        study.frame(S,1000,view(),[.1]*8,[.2]*8,{'context_ready':True},emit,14)
        study.frame(S,301000,view(price=101,ms=301000),[.1]*8,[.2]*8,{'context_ready':True},emit,14)
        s=study.stats[S+':300']
        self.assertEqual(s['n'],1)
        self.assertEqual(study.models[S+':300']['liquidity'].updates,1)
        self.assertEqual(study.models[S+':300']['frozen'].updates,0)
        self.assertEqual(len([r for k,r in events if k=='LIQUIDITY_MATURED']),1)
        self.assertFalse(study.summary()['execution_enabled'])

    def test_missing_context_drops_shadow_without_training(self):
        study=LiquidityStudy([300]);emit=lambda *_:None
        study.frame(S,1000,view(),[0.]*8,[0.]*8,{'context_ready':True},emit,14)
        study.frame(S,301000,view(price=101),[0.]*8,[0.]*8,{'context_ready':False},emit,14)
        self.assertEqual(study.stats[S+':300']['n'],0)
        self.assertEqual(study.dropped,1)

    def test_shadow_checkpoint_roundtrip(self):
        e=Engine(config(),RULES)
        e.liquidity.context('MARK',S,mark(),1000000000)
        e.liquidity.context('OI',S,oi(),1000000000)
        e.frame(S,1000,view(),[.1]*4)
        st=json.loads(json.dumps(e.state()))
        restored=Engine(config(),RULES,previous=st)
        self.assertEqual(restored.state(),e.state())

    def test_negative_funding_and_cross_window_entry_guard(self):
        t=self.tape()
        self.assertEqual(t.data[S]['mark']['funding_rate'],'-0.0001')
        self.assertIsNone(t.entry_guard(S,1000,300,1000000000))
        self.assertEqual(t.entry_guard(S,29900000,300,1000000000),'UNRECONCILED_FUNDING_WINDOW')
        self.assertEqual(t.entry_guard(S,1000,300,9000000000),'MARK_AND_FUNDING_CONTEXT_UNAVAILABLE')

    def test_invalid_auxiliary_event_does_not_corrupt_main_engine(self):
        e=Engine(config(),RULES);p=Processor(e)
        p.process('MARK',{'symbol':S,'event':mark(p='NaN'),'received_ns':1000000000})
        self.assertIsNone(e.liquidity.data[S]['mark'])
        self.assertEqual(e.faults[S],0)

    def test_open_interest_cannot_select_private_endpoint(self):
        with patch('cqwe.liquidity_research.urlopen') as request:
            with self.assertRaises(ValueError):open_interest('../account')
            request.assert_not_called()

    def test_duplicate_aggregate_trades_do_not_inflate_pressure(self):
        t=self.tape()
        event={'s':S,'a':1,'p':'100','q':'2','m':False}
        t.trade(S,event,1000000000);t.trade(S,event,1100000000)
        self.assertEqual(len(t.data[S]['trades']),1)
        t.invalidate(S)
        t.trade(S,event,1200000000)
        self.assertEqual(len(t.data[S]['trades']),0)

    def test_negative_open_interest_timestamp_rejected(self):
        t=self.tape()
        with self.assertRaises(ValueError):t.context('OI',S,oi(-1),1000000000)


if __name__=='__main__':unittest.main()
