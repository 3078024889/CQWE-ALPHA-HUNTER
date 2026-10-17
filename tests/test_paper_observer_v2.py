import math
from pathlib import Path
import tempfile
import unittest
from cqwe.liquidity_research import Branch16
from cqwe.paper_observer_v2 import ActiveBranch,PaperObserver,LEGACY_SOURCE
from cqwe.workbench import PaperDesk
from cqwe.event_council_bridge import combine


def quote(at,mid=100):
    return {'observed_ms':at,'bid':mid-.0001,'ask':mid+.0001,
            'raw':{'bids':[[str(mid-.0001),'12']], 'asks':[[str(mid+.0001),'10']]}}


class ObserverV2Tests(unittest.TestCase):
    def trend(self,sign=1):
        learner=PaperObserver()
        for i in range(13):decision=learner.frame('BTCUSDT',quote(i*5000,100+sign*i*.03),i*5000)
        return learner,decision

    def test_active_compartment_is_not_diluted_by_three_missing_branches(self):
        x=[.4,.8,.1,.7]+[0.]*12
        old=Branch16().predict(x)[0];new=ActiveBranch().predict(x)[0]
        self.assertAlmostEqual(math.log(new/(1-new)),4*math.log(old/(1-old)))
        self.assertNotAlmostEqual(new,old)

    def test_gradient_matches_active_probability_loss(self):
        model=ActiveBranch();x=[.4,.8,.1,.7]+[0.]*12;p,cache=model.predict(x)
        old=model.weights[1];eps=1e-6
        model.weights[1]=old+eps;up=-math.log(model.predict(x)[0])
        model.weights[1]=old-eps;down=-math.log(model.predict(x)[0])
        model.weights[1]=old;model.learn(x,1,p,cache)
        self.assertAlmostEqual(model.weights[1]-old,-.03*(up-down)/(2*eps),places=8)

    def test_flat_market_abstains_and_has_no_policy_count(self):
        learner=PaperObserver()
        for i in range(61):d=learner.frame('BTCUSDT',quote(i*5000),i*5000)
        self.assertEqual(d['action'],'OBSERVE');self.assertFalse(d['exploration_allowed'])
        self.assertEqual(d['diagnostics']['classes']['FLAT'],1)
        self.assertEqual(d['diagnostics']['directional_policy_samples'],0)

    def test_low_probability_count_does_not_block_explicit_exploration(self):
        for sign,action in ((1,'OPEN_LONG'),(-1,'OPEN_SHORT')):
            learner,d=self.trend(sign)
            self.assertEqual(d['action'],action);self.assertTrue(d['exploration_allowed'])
            self.assertFalse(d['nodes'][0]['eligible']);self.assertEqual(d['diagnostics']['directional_policy_samples'],0)
            self.assertFalse(d['profitability_proven'])

    def test_missing_history_stale_quote_and_cadence_block_entry(self):
        learner,d=self.trend();learner.state['banks']['BTCUSDT']['last_exploration_ms']=60000
        d=learner.frame('BTCUSDT',quote(65000,100.4),65000)
        self.assertEqual(d['reason'],'EXPLORATION_CADENCE')
        self.assertIsNone(learner.frame('BTCUSDT',quote(65000),90000))
        d=learner.frame('BTCUSDT',quote(100000,100.5),100000)
        self.assertEqual(d['reason'],'EXPLORATION_WARMUP')

    def test_migration_keeps_weights_but_resets_incomparable_validation(self):
        m=Branch16();m.updates=7
        legacy={'source':LEGACY_SOURCE,'banks':{'BTCUSDT':{'model':m.state(),'n':7}},'dropped':0,'last':{}}
        new=PaperObserver.migrate_legacy(legacy)
        self.assertEqual(new.state['banks']['BTCUSDT']['model']['updates'],7)
        self.assertEqual(new.state['banks']['BTCUSDT']['n'],0)
        self.assertEqual(new.state['migration']['previous_labels']['BTCUSDT'],7)

    def test_restarts_preserve_forecast_and_do_not_learn_twice(self):
        learner,d=self.trend();learner=PaperObserver(learner.state)
        d=learner.frame('BTCUSDT',quote(300000,101),300000)
        self.assertEqual(d['diagnostics']['labels'],1)
        learner=PaperObserver(learner.state);learner.frame('BTCUSDT',quote(305000,101),305000)
        self.assertEqual(learner.state['banks']['BTCUSDT']['n'],1)

    def test_entry_and_forecast_horizon_do_not_force_close(self):
        learner,d=self.trend();at=60000;q={'BTCUSDT':quote(at,100.36)}
        with tempfile.TemporaryDirectory() as tmp:
            desk=PaperDesk(Path(tmp)/'paper.db')
            try:
                desk.action({'action':'start','mode':'automatic','request_id':'start-exploration'},q,at)
                event={'at_ms':at,'execution_enabled':False,'upcoming_30min':[],'scores':{}}
                decision=combine(d,event,at);desk.cycle(q,{'BTCUSDT':decision},at)
                p=desk.state['positions']['BTCUSDT']
                self.assertEqual(p['source'],'PAPER_EXPLORATION');self.assertEqual(float(p['margin']),.5)
                self.assertEqual(float(p['notional']),5);self.assertIsNone(p['expires_ms'])
                q={'BTCUSDT':quote(360000,100.36)};desk.cycle(q,{},360000)
                self.assertIn('BTCUSDT',desk.state['positions'])
                desk.action({'action':'close','symbol':'BTCUSDT','request_id':'manual-close-after-horizon'},q,360000)
                desk.cycle({'BTCUSDT':quote(360001,100.36)},{'BTCUSDT':{**decision,'at_ms':360001}},360001)
                self.assertFalse(desk.state['positions'])
            finally:desk.db.close()

    def test_event_veto_cannot_be_bypassed_by_exploration_flag(self):
        learner,d=self.trend();at=60000
        event={'at_ms':at,'execution_enabled':False,'upcoming_30min':[{'scheduled_ms':65000}],'scores':{}}
        decision=combine(d,event,at);self.assertEqual(decision['action'],'WAIT')
        with tempfile.TemporaryDirectory() as tmp:
            desk=PaperDesk(Path(tmp)/'paper.db')
            try:
                desk.action({'action':'start','mode':'automatic','request_id':'start-event-veto'},{},at)
                desk.cycle({'BTCUSDT':quote(at,100.36)},{'BTCUSDT':decision},at)
                self.assertFalse(desk.state['positions'])
            finally:desk.db.close()
