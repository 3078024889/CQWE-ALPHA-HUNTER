import copy
import json
from pathlib import Path
import tempfile
import unittest

from cqwe.historical_curriculum import STEP,initial,closed_bars,learn_page,catch_up
from cqwe.macro_events import features,responses
from cqwe.local_autopilot import atomic,exclusive,accepted,prepare
from cqwe.four_market_runner import checked
from cqwe.four_market_core import Engine
from tests.test_four_market import RULES,view


def raw(t,close='100'):
    return [t,close,close,close,close,'5',t+STEP-1,'0',1,'0','0','0']


class HistoryTests(unittest.TestCase):
    def test_unclosed_bar_excluded(self):
        self.assertEqual(closed_bars([raw(0)],STEP-1),[])
        self.assertEqual(len(closed_bars([raw(0)],STEP)),1)

    def test_gaps_and_invalid_numbers_rejected(self):
        for rows in ([raw(0),raw(2*STEP)],[raw(0,'NaN')]):
            with self.assertRaises(ValueError):closed_bars(rows,3*STEP)

    def test_delayed_learning_and_frozen_node(self):
        st=initial(86400000,1)
        bars=closed_bars([raw(i*STEP,str(100+i)) for i in range(10)],10*STEP)
        learn_page(st,'BTCUSDT',bars)
        d=st['symbols']['BTCUSDT']
        self.assertEqual(d['labels']['300'],6)
        self.assertEqual(d['labels']['900'],2)
        self.assertEqual(d['models']['300']['frozen']['updates'],0)
        self.assertEqual(d['models']['300']['branch2']['updates'],6)

    def test_duplicate_page_does_not_double_learn(self):
        st=initial(86400000,1)
        bars=closed_bars([raw(i*STEP,str(100+i)) for i in range(10)],10*STEP)
        learn_page(st,'BTCUSDT',bars);before=copy.deepcopy(st)
        learn_page(st,'BTCUSDT',bars)
        self.assertEqual(st,before)

    def test_resume_matches_uninterrupted(self):
        a=initial(86400000,1);b=copy.deepcopy(a)
        bars=closed_bars([raw(i*STEP,str(100+i)) for i in range(20)],20*STEP)
        learn_page(a,'BTCUSDT',bars)
        learn_page(b,'BTCUSDT',bars[:9]);b=json.loads(json.dumps(b))
        learn_page(b,'BTCUSDT',bars[9:]);a=json.loads(json.dumps(a))
        self.assertEqual(a,b)

    def test_request_budget_and_original_state_unchanged(self):
        st=initial(86400000,1);before=copy.deepcopy(st);saved=[];requests=[]
        def fetch(endpoint,params):
            requests.append(params);return [raw(params['startTime'])]
        out=catch_up(st,86400000,saved.append,pages=4,fetch=fetch)
        self.assertEqual(st,before);self.assertEqual(len(requests),4)
        self.assertEqual(out['pages'],4)
        self.assertEqual({r['symbol'] for r in requests},set(RULES))

    def test_missing_period_drops_pending_instead_of_fabricating(self):
        st=initial(86400000,1)
        learn_page(st,'BTCUSDT',closed_bars([raw(i*STEP,str(100+i)) for i in range(4)],5*STEP))
        learn_page(st,'BTCUSDT',closed_bars([raw(10*STEP)],11*STEP))
        self.assertEqual(st['symbols']['BTCUSDT']['dropped'],2)
        self.assertEqual(st['symbols']['BTCUSDT']['labels']['300'],0)


class EventTests(unittest.TestCase):
    def event(self):
        source='a'*64
        return {'event_id':'CPI_TEST','family':'US_CPI','scheduled_ms':600000,
                'consensus':{'value':.3,'series':'core_mom','unit':'percent',
                    'available_ms':500000,'first_seen_ms':500000,'source_sha256':source},
                'actual':{'value':.4,'series':'core_mom','unit':'percent','first_release':True,
                    'available_ms':600000,'first_seen_ms':600100,'source_sha256':source}}

    def test_actual_unavailable_before_release_or_first_seen(self):
        e=self.event()
        self.assertIsNone(features(e,599999)['actual'])
        self.assertIsNone(features(e,600050)['actual'])
        self.assertAlmostEqual(features(e,600100)['surprise'],.1)

    def test_later_consensus_and_revisions_not_substituted(self):
        e=self.event();e['consensus']['first_seen_ms']=600100
        self.assertIsNone(features(e,700000)['consensus'])
        e['actual']['first_release']=False
        self.assertIsNone(features(e,700000)['actual'])

    def test_unit_or_series_mismatch_has_no_surprise(self):
        e=self.event();e['actual']['series']='headline_yoy'
        self.assertIsNone(features(e,700000)['surprise'])

    def test_event_cluster_and_missing_candle(self):
        e=self.event();bars=[{'time':600000+i*60000,'open':100.,'close':101.} for i in range(5)]
        r=responses(e,'BTCUSDT',bars)
        self.assertEqual(r['cluster_id'],e['event_id'])
        self.assertEqual(r['responses'][0]['label'],1)
        self.assertEqual(r['responses'][1]['status'],'MISSING_CANDLES')
        self.assertIsNone(r['pre_release_features']['actual'])
        self.assertFalse(r['execution_costs_included'])

    def test_related_political_and_hack_events_share_explicit_cluster(self):
        e=self.event();e['family']='POLITICAL_STATEMENT';e['cluster_id']='COMMON_EVENT'
        self.assertEqual(responses(e,'ETHUSDT',[])['cluster_id'],'COMMON_EVENT')
        e['family']='HACK_EXPLOIT'
        self.assertEqual(responses(e,'SOLUSDT',[])['cluster_id'],'COMMON_EVENT')

    def test_unregistered_family_is_not_silently_trained(self):
        e=self.event();e['family']='UNVERIFIED_MAGIC_PROFIT'
        with self.assertRaises(ValueError):features(e,700000)


class ServiceTests(unittest.TestCase):
    def test_atomic_integrity_and_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json';atomic(p,{'a':1})
            obj=checked(json.loads(p.read_text()));self.assertEqual(obj['a'],1)
            obj['a']=2
            with self.assertRaises(ValueError):checked(obj)

    def test_second_process_lock_fails(self):
        with tempfile.TemporaryDirectory() as td:
            with exclusive(Path(td)):
                with self.assertRaises(OSError):
                    with exclusive(Path(td)):pass

    def test_fresh_session_has_no_fabricated_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);folder=prepare(root)
            self.assertTrue(folder.is_dir());self.assertIsNone(accepted(root))

    def test_engine_council_is_replayed_in_state(self):
        e=Engine(rules=RULES);e.frame('BTCUSDT',1000,view(),[0.]*4)
        self.assertEqual(e.council['BTCUSDT']['action'],'OBSERVE')
        self.assertEqual(len(e.council['BTCUSDT']['nodes']),9)
        st=e.state();other=Engine(e.cfg,RULES,previous=st)
        self.assertEqual(other.state(),st)


if __name__=='__main__':unittest.main()
