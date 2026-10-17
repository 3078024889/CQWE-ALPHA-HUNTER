import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cqwe.unified_dendritic_paper import UnifiedCouncil,IDS,POLICY
from cqwe.workbench import PaperDesk

T=1800000000000


def quotes(at,price=100.):return {s:{'observed_ms':at,'bid':price,'ask':price+.01} for s in ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT')}


def targets():
    t={k:{} for k in IDS}
    t['vol_rsi:ETHUSDT']={'ETHUSDT':1.};t['ts_momentum:ETHUSDT']={'ETHUSDT':1.}
    return t


def decide(council,at,ts=None,positions=None,news_veto=False):
    q=quotes(at);e={s:{'ready':True,'at_ms':at,'mark_fresh':True,'oi_fresh':True,'flow':.5,'depletion':.1} for s in q}
    return council.decide(targets() if ts is None else ts,at//3600000,q,e,{'fresh_sources':['FED'],'at_ms':at,'entry_veto':news_veto},{},at,positions or {})


def ready(c):
    for dt in range(0,100000,10000):p=decide(c,T+dt)
    return p


class CouncilTests(unittest.TestCase):
    def test_all_12_experts_in_16_inputs_and_family_caps(self):
        p=ready(UnifiedCouncil())
        self.assertEqual(len(p['experts']),12);self.assertEqual(len(p['neural']['ETHUSDT']['features']),16)
        self.assertEqual(len(p['neural']['ETHUSDT']['branches']),4)
        self.assertEqual(p['weights']['ETHUSDT'],.125);self.assertEqual(p['action'],'OPEN_BASKET')
        self.assertFalse(p['research_qualification_granted'])

    def test_correlated_single_family_is_not_two_families(self):
        c=UnifiedCouncil();t={k:{} for k in IDS}
        for s in ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT'):t['vol_rsi:'+s]={s:1.}
        p=decide(c,T,t);self.assertEqual(p['reason'],'FAMILY_QUORUM_MISSING')

    def test_opposite_experts_cancel_without_renormalizing_risk(self):
        t=targets();t['ts_momentum:ETHUSDT']={'ETHUSDT':-1.}
        p=decide(UnifiedCouncil(),T,t);self.assertFalse(p['weights']);self.assertEqual(p['action'],'OBSERVE')

    def test_news_blocks_entry_but_does_not_force_exit(self):
        c=UnifiedCouncil();ready(c);p=decide(c,T+100000,news_veto=True)
        self.assertEqual(p['reason'],'ENSEMBLE_EVENT_VETO')
        p=decide(c,T+110000,positions={'ETHUSDT':{'direction':1}},news_veto=True)
        self.assertEqual(p['action'],'HOLD_BASKET')

    def test_delayed_learning_and_no_five_minute_expiry(self):
        c=UnifiedCouncil();decide(c,T)
        self.assertEqual(c.state['banks']['ETHUSDT']['model']['updates'],0)
        at=T+300000;q=quotes(at,101);e={s:{'ready':True,'at_ms':at,'mark_fresh':True,'oi_fresh':True} for s in q}
        p=c.decide(targets(),at//3600000,q,e,{'fresh_sources':['FED'],'at_ms':at},{},at,{'ETHUSDT':{'direction':1}})
        self.assertEqual(p['neural']['ETHUSDT']['updates'],1);self.assertEqual(p['action'],'HOLD_BASKET')

    def test_gap_resets_activation(self):
        c=UnifiedCouncil();ready(c);self.assertEqual(decide(c,T+120000)['reason'],'ENSEMBLE_PERSISTENCE_WAIT')


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.desk=PaperDesk(Path(self.tmp.name)/'paper.db')
        self.desk.action({'action':'start','mode':'automatic','policy':POLICY,'request_id':'unified-start-unique'},quotes(T),T)
    def tearDown(self):self.desk.db.close();self.tmp.cleanup()
    def plan(self,at):
        return {'policy':POLICY,'at_ms':at,'action':'OPEN_BASKET','paper_only':True,'real_orders_enabled':False,'active_families':2,
                'weights':{'ETHUSDT':.3,'BTCUSDT':-.3},'families':{},'experts':{},'neural':{}}
    def cycle(self,at,plan=None,q=None):self.desk.cycle(q or quotes(at),{},at,ensemble=plan or self.plan(at))

    def test_atomic_basket_uses_same_account_10x_and_not_12_separate_budgets(self):
        self.cycle(T)
        ps=self.desk.state['positions'];self.assertEqual(len(ps),2)
        self.assertAlmostEqual(sum(float(p['margin']) for p in ps.values()),.3)
        self.assertTrue(all(p['leverage']==10 for p in ps.values()))
        self.assertTrue(all(p['source']=='PAPER_DENDRITIC_ENSEMBLE' for p in ps.values()))

    def test_second_leg_failure_rolls_back_first_and_fees(self):
        original=self.desk.open
        def fail(s,*args,**kwargs):
            if s=='BTCUSDT':raise ValueError('simulated second leg reject')
            return original(s,*args,**kwargs)
        with patch.object(self.desk,'open',side_effect=fail):self.cycle(T)
        self.assertFalse(self.desk.state['positions']);self.assertEqual(self.desk.state['cash'],'10');self.assertEqual(self.desk.state['fees'],'0')

    def test_stop_on_one_leg_closes_entire_group_and_no_reentry_same_frame(self):
        self.cycle(T);self.cycle(T+1000,q=quotes(T+1000,99))
        self.assertFalse(self.desk.state['positions']);self.assertEqual(len(self.desk.state['trades']),2)
        self.assertEqual(len(self.desk.state['ensemble_groups']),1)
        self.cycle(T+2000);self.assertFalse(self.desk.state['positions'])

    def test_manual_single_leg_close_closes_group_and_net_reconciles(self):
        self.cycle(T)
        self.desk.action({'action':'close','symbol':'ETHUSDT','request_id':'manual-close-group'},quotes(T+1000),T+1000)
        self.assertFalse(self.desk.state['positions'])
        self.assertAlmostEqual(float(self.desk.state['cash'])-10,sum(float(t['net_pnl']) for t in self.desk.state['trades']))

    def test_paused_mode_keeps_group_risk_alive(self):
        self.cycle(T);self.desk.action({'action':'pause','request_id':'pause-group-risk'},quotes(T+1000),T+1000)
        self.cycle(T+2000,q=quotes(T+2000,99));self.assertFalse(self.desk.state['positions'])

    def test_disable_failed_family_preserves_positions_and_auto_mode(self):
        self.cycle(T);before=copy.deepcopy(self.desk.state['positions'])
        self.desk.action({'action':'disable_family','family':'vol_rsi','request_id':'disable-failed-family'},quotes(T),T)
        self.assertEqual(self.desk.state['positions'],before);self.assertTrue(self.desk.state['automatic'])
        self.assertEqual(self.desk.state['disabled_strategy_families'],['vol_rsi'])


if __name__=='__main__':unittest.main()
