import copy
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from cqwe.event_learning import EventJournal, EventLearner
from cqwe.polymarket_research import (ask_cost, binary_market, collect, fee_rate,
                                      final_binary_outcome, parse_book)

CID = '0x'+'a'*64
SOURCE = 'b'*64


def market():
    return {'active':True,'closed':False,'enableOrderBook':True,'negRisk':False,
            'conditionId':CID,'outcomes':'["Yes","No"]','clobTokenIds':'["1","2"]',
            'feeType':'research','question':'Synthetic unit-test event',
            'description':'Synthetic test fixture only','endDate':'2030-01-01T00:00:00Z',
            'feesEnabled':True,'feeSchedule':{'rate':.04,'exponent':1,'takerOnly':True}}


def book(token='1'):
    return {'asset_id':token,'market':CID,'bids':[{'price':'.4','size':'10'}],
            'asks':[{'price':'.6','size':'10'}],'timestamp':'1','min_order_size':'5'}


def forecast(learner, event_id='event', category='category', at_ms=100):
    return learner.forecast(event_id=event_id,category=category,market_probability=.7,
                features=[1.,.4,.2,.1],source_sha256=SOURCE,at_ms=at_ms)


class EventLearningChecks(unittest.TestCase):
    def test_01_untrained_forecast_is_reference_not_invented_edge(self):
        l = EventLearner()
        f = forecast(l)
        self.assertAlmostEqual(f['predicted_probability'],.7)
        self.assertEqual(l.summary()['resolved_events'],0)
        self.assertIsNone(l.summary()['mean_scores']['brier'])

    def test_02_only_future_binary_outcomes_train(self):
        l = EventLearner()
        forecast(l)
        for label in (.99,True,2,-1):
            with self.assertRaises(ValueError):
                l.resolve(event_id='event',outcome=label,source_sha256=SOURCE,at_ms=200)
        with self.assertRaises(ValueError):
            l.resolve(event_id='event',outcome=1,source_sha256=SOURCE,at_ms=100)
        self.assertEqual(l.model('category')['updates'],0)

    def test_03_matured_learning_and_proper_scores(self):
        l = EventLearner()
        forecast(l)
        r = l.resolve(event_id='event',outcome=1,source_sha256=SOURCE,at_ms=200)
        self.assertAlmostEqual(r['score']['brier'],.09)
        self.assertEqual(l.model('category')['updates'],1)
        self.assertNotEqual(l.model('category')['weights'],[0.]*4)
        self.assertEqual(l.model('unrelated')['weights'],[0.]*4)

    def test_04_duplicate_forecast_and_resolution_rejected(self):
        l = EventLearner()
        forecast(l)
        with self.assertRaises(ValueError):
            forecast(l)
        l.resolve(event_id='event',outcome=0,source_sha256=SOURCE,at_ms=200)
        with self.assertRaises(ValueError):
            l.resolve(event_id='event',outcome=0,source_sha256=SOURCE,at_ms=300)

    def test_05_durable_replay_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            j = EventJournal(Path(tmp)/'events.jsonl')
            j.append('FORECAST',event_id='a',category='x',market_probability=.4,
                     features=[1.,-.2,0.,.1],source_sha256=SOURCE,at_ms=100)
            j.append('RESOLVED',event_id='a',outcome=1,source_sha256=SOURCE,at_ms=200)
            learner,tip,n = j.load()
            self.assertEqual(n,2)
            self.assertEqual(learner.summary()['resolved_events'],1)
            data = j.path.read_text()
            j.path.write_text(data.replace('"outcome":1','"outcome":0'))
            with self.assertRaises(ValueError):
                j.load()

    def test_06_binary_identity_and_neg_risk_separation(self):
        m = market()
        self.assertEqual(binary_market(m)['yes'],'1')
        m['outcomes'] = '["No","Yes"]'
        self.assertEqual(binary_market(m)['yes'],'2')
        m['negRisk'] = True
        with self.assertRaises(ValueError):
            binary_market(m)
        with self.assertRaises(ValueError):
            parse_book(book(),token='99',condition=CID)

    def test_07_prices_are_not_final_outcomes(self):
        raw = {'condition_id':CID,'closed':False,'outcomePrices':['1','0'],
               'tokens':[{'outcome':'Yes','winner':True},{'outcome':'No','winner':False}]}
        self.assertIsNone(final_binary_outcome(raw,CID))
        raw['closed'] = True
        self.assertEqual(final_binary_outcome(raw,CID),1)
        raw['tokens'][1]['winner'] = True
        self.assertIsNone(final_binary_outcome(raw,CID))

    def test_08_fee_depth_and_complete_set_economics(self):
        b = parse_book(book(),token='1',condition=CID)
        gross,fee = ask_cost(b,D(5),fee_rate(market()))
        self.assertEqual(gross,D('3'))
        self.assertEqual(fee,D('.04800'))
        self.assertLess(D(5)-2*(gross+fee),0)
        with self.assertRaises(ValueError):
            ask_cost(b,D(100),D('.04'))
        with self.assertRaises(ValueError):
            fee_rate({'feesEnabled':True})

    def test_09_pending_collection_does_not_fabricate_learning(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fetch(kind, token=None):
                return {'markets':[market()]} if kind=='discovery' else book(token)
            _,r = collect(tmp,limit=1,fetch=fetch)
            self.assertEqual(r['event_learning']['forecasts'],1)
            self.assertEqual(r['event_learning']['resolved_events'],0)
            self.assertIsNone(r['realized_account_profit'])
            _,again = collect(tmp,limit=1,fetch=fetch)
            self.assertEqual(again['event_learning']['forecasts'],1)

    def test_10_invalid_probabilities_features_and_source(self):
        for p in (float('nan'),0,1,True):
            with self.assertRaises(ValueError):
                EventLearner().forecast(event_id='e',category='x',market_probability=p,
                    features=[0.]*4,source_sha256=SOURCE,at_ms=100)
        with self.assertRaises(ValueError):
            EventLearner().forecast(event_id='e',category='x',market_probability=.5,
                features=[True,0.,0.,0.],source_sha256=SOURCE,at_ms=100)


if __name__=='__main__':
    unittest.main()
