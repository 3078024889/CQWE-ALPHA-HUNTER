import copy
import tempfile
import unittest
from pathlib import Path
from cqwe.portfolio_router import PortfolioRouter
from cqwe.market_context import build_context,ContextCache
from cqwe.workbench import PaperDesk

T=1800000000000


def decision(at,direction=1,strength=.8,action=None):
    return {'at_ms':at,'action':action or ('OPEN_LONG' if direction==1 else 'OPEN_SHORT'),
            'exploration_allowed':True,'paper_only':True,'execution_enabled':False,'nodes':[],
            'event_context_fresh':True,'mechanism_confirmations':3,'exit_basis':'FLOW_LIQUIDITY_REVERSAL',
            'market_evidence':{'at_ms':at,'ready':True},
            'mechanism_hypotheses':[{'direction':direction,'strength':strength,'confirmations':3}]}


def context(at,direction=1):return {'ready':True,'at_ms':at,'regime':{'direction':direction}}


def stable(router,symbol='SOLUSDT',direction=1,account=None,start=T):
    for dt in range(0,100000,10000):
        at=start+dt
        result=router.route({symbol:decision(at,direction)},{symbol:context(at,direction)},account or {},at)
    return result[symbol]


class RouterTests(unittest.TestCase):
    def test_short_burst_cannot_open(self):
        r=PortfolioRouter();d=r.route({'SOLUSDT':decision(T)},{'SOLUSDT':context(T)},{},T)['SOLUSDT']
        self.assertEqual(d['reason'],'ENTRY_PERSISTENCE_WAIT')

    def test_confirmed_entry_and_direction_flip_reset(self):
        r=PortfolioRouter();self.assertEqual(stable(r)['action'],'OPEN_LONG')
        at=T+100000;d=r.route({'SOLUSDT':decision(at,-1)},{'SOLUSDT':context(at,-1)},{},at)['SOLUSDT']
        self.assertEqual(d['reason'],'ENTRY_PERSISTENCE_WAIT')

    def test_gap_breaks_continuity_across_restart(self):
        r=PortfolioRouter();stable(r);r=PortfolioRouter(r.state)
        at=T+120000
        self.assertEqual(r.route({'SOLUSDT':decision(at)},{'SOLUSDT':context(at)},{},at)['SOLUSDT']['portfolio_route']['signal_duration_ms'],0)

    def test_background_must_agree(self):
        r=PortfolioRouter();stable(r);at=T+100000
        d=r.route({'SOLUSDT':decision(at)},{'SOLUSDT':context(at,-1)},{},at)['SOLUSDT']
        self.assertEqual(d['reason'],'REGIME_CONFLICT_OR_UNCLEAR')

    def test_conflicting_hypotheses_reset_direction_instead_of_picking_tiny_winner(self):
        r=PortfolioRouter();stable(r);at=T+100000;d=decision(at)
        d['mechanism_hypotheses'].append({'direction':-1,'strength':.75,'confirmations':3})
        out=r.route({'SOLUSDT':d},{'SOLUSDT':context(at)},{},at)['SOLUSDT']
        self.assertEqual(out['reason'],'HYPOTHESES_DISAGREE')
        self.assertEqual(out['portfolio_route']['signal_duration_ms'],0)

    def test_ranking_not_dictionary_order(self):
        r=PortfolioRouter()
        for dt in range(0,100000,10000):
            at=T+dt;ds={'BTCUSDT':decision(at,strength=.6),'SOLUSDT':decision(at,strength=.9)}
            out=r.route(ds,{s:context(at) for s in ds},{},at)
        self.assertEqual(out['SOLUSDT']['portfolio_route']['rank'],1)
        self.assertEqual(out['BTCUSDT']['action'],'OBSERVE')

    def test_exit_needs_time_but_not_new_entry_permission(self):
        r=PortfolioRouter();a={'positions':{'SOLUSDT':{'direction':1}}}
        for dt in range(0,70000,10000):
            at=T+dt;d=decision(at,-1,action='CLOSE')
            d['exploration_allowed']=False
            out=r.route({'SOLUSDT':d},{},a,at)['SOLUSDT']
            self.assertEqual(out['action'],'HOLD' if dt<60000 else 'CLOSE')
        self.assertTrue(out['portfolio_route']['reversal_candidate'])
        self.assertFalse(out['portfolio_route']['reverse_after_close'])

    def test_any_asset_exit_blocks_immediate_other_asset_entry(self):
        a={'trades':[{'symbol':'ETHUSDT','direction':1,'closed_ms':T+30000,'reason':'STOP_LOSS'}]}
        self.assertEqual(stable(PortfolioRouter(),account=a)['reason'],'PORTFOLIO_COOLDOWN')

    def test_independent_opposite_entry_can_be_queued_after_exit(self):
        a={'trades':[{'symbol':'SOLUSDT','direction':1,'closed_ms':T,'reason':'FLOW_LIQUIDITY_REVERSAL'}],
           'last_exploration':{'SOLUSDT':T-10000}}
        d=stable(PortfolioRouter(),direction=-1,account=a)
        self.assertEqual(d['action'],'OPEN_SHORT');self.assertTrue(d['portfolio_route']['reverse_after_close'])

    def test_same_direction_cannot_bypass_cooldown(self):
        a={'trades':[{'symbol':'SOLUSDT','direction':1,'closed_ms':T,'reason':'FLOW_LIQUIDITY_REVERSAL'}]}
        self.assertEqual(stable(PortfolioRouter(),account=a)['reason'],'SAME_SYMBOL_COOLDOWN')

    def test_stale_input_and_news_veto_do_not_open(self):
        r=PortfolioRouter();stable(r);at=T+100000;d=decision(at-20000)
        self.assertEqual(r.route({'SOLUSDT':d},{'SOLUSDT':context(at)},{},at)['SOLUSDT']['action'],'OBSERVE')
        d=decision(at);d.update(action='OBSERVE',exploration_allowed=False,reason='EVENT_RISK_VETO')
        self.assertEqual(r.route({'SOLUSDT':d},{'SOLUSDT':context(at)},{},at)['SOLUSDT']['reason'],'EVENT_RISK_VETO')

    def test_no_entry_in_same_frame_as_stop_exit(self):
        with tempfile.TemporaryDirectory() as td:
            desk=PaperDesk(Path(td)/'paper.db')
            try:
                desk.state.update(running=True,automatic=True)
                q={'SOLUSDT':{'observed_ms':T,'bid':100.,'ask':100.01},'ETHUSDT':{'observed_ms':T,'bid':100.,'ask':100.01}}
                desk.open('SOLUSDT',1,'.5',q,T,'PAPER_EXPLORATION')
                q['SOLUSDT']['bid']=99.
                d=decision(T);desk.cycle(q,{'ETHUSDT':d},T)
                self.assertFalse(desk.state['positions']);self.assertEqual(d['execution_status'],'EXIT_FRAME_REASSESS')
            finally:desk.db.close()

    def test_validated_reversal_executes_at_10x_with_new_fees(self):
        with tempfile.TemporaryDirectory() as td:
            desk=PaperDesk(Path(td)/'paper.db')
            try:
                desk.state.update(running=True,automatic=True)
                desk.state['trades']=[{'symbol':'SOLUSDT','direction':1,'closed_ms':T,'reason':'FLOW_LIQUIDITY_REVERSAL'}]
                desk.state['cooldown_until']={'SOLUSDT':T+300000};desk.state['last_exploration']={'SOLUSDT':T}
                d=stable(PortfolioRouter(),direction=-1,account=desk.state)
                q={'SOLUSDT':{'observed_ms':T+90000,'bid':100.,'ask':100.01}}
                desk.cycle(q,{'SOLUSDT':d},T+90000)
                p=desk.state['positions']['SOLUSDT'];self.assertEqual(p['direction'],-1)
                self.assertEqual(p['leverage'],10);self.assertGreater(float(desk.state['fees']),0)
            finally:desk.db.close()


def bars():
    start=T//900000*900000-100*900000;result=[]
    for i in range(100):
        c=100+i*.2;t=start+i*900000
        result.append([t,str(c-.1),str(c+.1),str(c-.2),str(c),'100',t+899999,'0',0,'0','0','0'])
    return result


class ContextTests(unittest.TestCase):
    def test_closed_multiscale_background_and_no_true_amount_claim(self):
        c=build_context(bars(),T)
        self.assertTrue(c['ready']);self.assertEqual(c['regime']['direction'],1)
        surface=c['liquidation_scenarios'];self.assertEqual(surface['execution_weight'],0)
        self.assertFalse(surface['private_stops_known']);self.assertTrue(surface['zones'])
        self.assertTrue(all(0<z['relative_intensity']<=1 for z in surface['zones']))

    def test_future_candle_not_used_and_gap_rejected(self):
        raw=bars();c=build_context(raw,T)
        raw.append([T,'99999','99999','99999','99999','99999',T+899999])
        self.assertEqual(c['regime'],build_context(raw,T)['regime'])
        self.assertFalse(build_context(raw[:40]+raw[41:],T)['ready'])

    def test_failed_refresh_not_reusing_good_context(self):
        calls=[]
        def fetch(*args):
            calls.append(1)
            if len(calls)>1:raise TimeoutError('offline')
            return bars()
        cache=ContextCache(fetch);self.assertTrue(cache.get('SOLUSDT',T)['ready'])
        self.assertFalse(cache.get('SOLUSDT',T+300000)['ready'])
        self.assertFalse(cache.get('SOLUSDT',T+310000)['ready']);self.assertEqual(len(calls),2)

    def test_unselected_symbol_makes_no_network_request(self):
        def fetch(*args):raise AssertionError('unexpected request')
        self.assertFalse(ContextCache(fetch).get('BNBUSDT',T,refresh=False)['ready'])


if __name__=='__main__':unittest.main()
