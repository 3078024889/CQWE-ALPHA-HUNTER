import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cqwe.event_forward_loop import ForwardLoop,causal_features
from cqwe.four_market_core import SYMBOLS
from research.supplement_event_sources import ism_rows

T=1800000000000


def event(t=T,name='US_CPI'):
    return {'event_id':name+str(t),'event_type':name,'scheduled_ms':t,
            'source_url':'https://www.bls.gov/','time_granularity':'MINUTE'}


def quotes(t,price=100.):
    return {s:{'observed_ms':t,'bid':price-.01,'ask':price+.01} for s in SYMBOLS}


def histories(t=T):
    return {s:[{'time':i,'open':'100','close':'100.1'} for i in range(t-3600000,t,60000)] for s in SYMBOLS}


class EventForwardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'forward.db'
        self.loop=ForwardLoop(self.path)

    def tearDown(self):
        self.loop.close();self.tmp.cleanup()

    def tick(self,t=T,ev=None,q=None):
        return self.loop.tick(t,[event()] if ev is None else ev,quotes(t) if q is None else q,histories())

    def test_forecast_precedes_learning_and_matures_once(self):
        s=self.tick();self.assertEqual(s['counts'],{'PENDING':12})
        self.assertEqual(self.loop.model('BTCUSDT:300').updates,0)
        s=self.tick(T+300000,q=quotes(T+300000,101.))
        self.assertEqual(s['counts'],{'MATURED':4,'PENDING':8})
        self.assertEqual(self.loop.model('BTCUSDT:300').updates,1)
        self.tick(T+300001)
        self.assertEqual(self.loop.model('BTCUSDT:300').updates,1)
        self.assertEqual(self.loop.verify()['outcomes'],4)
        self.assertFalse(s['execution_enabled'])

    def test_restarts_do_not_duplicate_forecasts_or_learning(self):
        self.tick();self.loop.close();self.loop=ForwardLoop(self.path)
        self.tick();self.assertEqual(self.loop.verify()['forecasts'],12)
        self.tick(T+300000,q=quotes(T+300000,101.));self.loop.close();self.loop=ForwardLoop(self.path)
        self.tick(T+300001);self.assertEqual(self.loop.model('BTCUSDT:300').updates,1)

    def test_recovery_after_missed_maturity_drops_instead_of_backfills(self):
        self.tick();s=self.tick(T+340000)
        self.assertEqual(s['counts']['DROPPED'],4)
        self.assertEqual(self.loop.model('BTCUSDT:300').updates,0)

    def test_stale_or_pre_maturity_quotes_do_not_label(self):
        self.tick();s=self.tick(T+300000,q=quotes(T+299999))
        self.assertEqual(s['counts'],{'PENDING':12})
        s=self.tick(T+300001,q=quotes(T+290000))
        self.assertEqual(s['counts'],{'PENDING':12})

    def test_simultaneous_headlines_share_one_outcome(self):
        self.tick(ev=[event(),event(name='US_RETAIL')])
        self.assertEqual(self.loop.verify()['forecasts'],12)

    def test_overlap_and_retrospective_events_do_not_add_predictions(self):
        self.tick();self.tick(T+30000,ev=[event(T+30000)])
        self.assertEqual(self.loop.verify()['forecasts'],12)
        self.tick(T+120000,ev=[event()]);self.assertEqual(self.loop.verify()['forecasts'],12)

    def test_future_schedule_and_date_only_are_not_minute_predictions(self):
        e=event();e['time_granularity']='DATE_ONLY'
        self.tick(ev=[event(T+1),e]);self.assertEqual(self.loop.verify()['forecasts'],0)

    def test_future_candle_and_missing_history_cannot_influence_features(self):
        rows=histories()['BTCUSDT'];x=causal_features(['US_CPI'],T,rows)
        future={'time':T,'open':'1','close':'1000000'}
        self.assertEqual(x,causal_features(['US_CPI'],T,rows+[future]))
        with self.assertRaises(ValueError):causal_features(['US_CPI'],T,rows[1:])

    def test_transaction_rolls_back_learning_and_outcome_together(self):
        self.tick()
        with patch.object(self.loop,'log',side_effect=RuntimeError('simulated disk failure')):
            with self.assertRaises(RuntimeError):self.tick(T+300000)
        self.assertEqual(self.loop.model('BTCUSDT:300').updates,0)
        self.assertEqual(self.loop.status(T)['counts'],{'PENDING':12})
        self.tick(T+300000);self.assertEqual(self.loop.verify()['outcomes'],4)

    def test_table_and_journal_tampering_are_detected(self):
        self.tick()
        with self.loop.db:self.loop.db.execute('UPDATE predictions SET p=.9')
        with self.assertRaisesRegex(ValueError,'TABLE_TAMPERED'):self.loop.verify()

    def test_saved_model_tampering_is_detected(self):
        self.tick();self.tick(T+300000,q=quotes(T+300000,101.))
        state=self.loop.model('BTCUSDT:300').state();state['weights'][0]=.999
        with self.loop.db:self.loop.db.execute('UPDATE models SET state=? WHERE k=?',(json.dumps(state),'BTCUSDT:300'))
        with self.assertRaisesRegex(ValueError,'MODEL_STATE_REPLAY'):self.loop.verify()

    def test_bad_quote_clock_and_values_rejected(self):
        for q in ({'bid':0,'ask':1,'observed_ms':T},{'bid':2,'ask':1,'observed_ms':T},
                  {'bid':1,'ask':float('nan'),'observed_ms':T},{'bid':1,'ask':2,'observed_ms':T+1}):
            self.assertIsNone(self.loop.quote(q,T))
        self.tick()
        with self.assertRaisesRegex(ValueError,'CLOCK_REVERSED'):self.tick(T-1)

    def test_fee_spread_proxy_and_ties(self):
        self.tick();self.tick(T+300000,q=quotes(T+300000,100.))
        rows=self.loop.db.execute("SELECT result FROM predictions WHERE status='MATURED'").fetchall()
        self.assertTrue(all(json.loads(r['result'])['y'] is None for r in rows))
        self.assertEqual(self.loop.model('BTCUSDT:300').updates,0)

    def test_ism_only_explicit_dates_and_separate_series(self):
        text='<table><tr><td>April 2026</td><td>1</td><td>6</td></tr><tr><td>Forecast</td><td>June 17</td><td>June 17</td></tr></table>'
        self.assertEqual(list(ism_rows(text)),[('US_ISM_MANUFACTURING','2026-04-01'),('US_ISM_SERVICES','2026-04-06')])


if __name__=='__main__':unittest.main()
