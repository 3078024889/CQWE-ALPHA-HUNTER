from datetime import datetime,timezone
from email.utils import format_datetime
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from decimal import Decimal as D

from cqwe.global_event_context import GlobalContext,parse,classify
from cqwe.copernican_market_policy import MarketCouncil,hypotheses
from cqwe.market_evidence import MarketEvidence
from cqwe.mechanism_exit import evaluate
from cqwe.workbench import PaperDesk

T=1800000000000


def rss(title='Exchange hacked, withdrawals halted',published=T):
    date=format_datetime(datetime.fromtimestamp(published/1000,timezone.utc))
    return f'<rss><channel><item><title>{title}</title><link>https://example.com/a</link><pubDate>{date}</pubDate></item></channel></rss>'.encode()


def quote(at=T,mid=100):
    return {'bid':mid-.01,'ask':mid+.01,'observed_ms':at,'raw':{'T':at,'bids':[['99.99','10']], 'asks':[['100.01','12']]}}


def micro(at=T,direction=1):
    return {'at_ms':at,'ready':True,'features':[.05*direction,.03*direction,.8*direction,.4*direction,0.,0.,.1,.1],
            'flow':.8*direction,'depletion':.05*direction,'refill':.03*direction,'breakout':.4*direction,
            'price_move_bps':2*direction,'mark_fresh':True,'oi_fresh':True,'funding_window_veto':False,
            'liquidations_available':False}


def news(at=T):return {'at_ms':at,'fresh_sources':['FED'],'source_count':8,'entry_veto':False,'potential_acute_events':[]}
def base():return {'diagnostics':{'warmup_seconds':120,'observed_range_bps':50,'cost_buffer_bps':20},'horizon':300}
def calendar():return {'upcoming_30min':[]}


class GlobalEventTests(unittest.TestCase):
    def test_titles_are_unconfirmed_and_never_directional(self):
        row=parse(rss(),'FED',T)[0]
        self.assertIn('HACK_EXPLOIT',row['families']);self.assertFalse(row['fact_confirmed']);self.assertIsNone(row['direction'])
        self.assertEqual(classify('Community hackathon this weekend'),[])

    def test_old_future_and_duplicate_headlines_do_not_create_fake_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            n=GlobalContext(tmp)
            old=parse(rss(published=T-86400000),'FED',T)[0]
            future=parse(rss(published=T+60000),'SEC',T)[0]
            n.state['items']={r['id']:r for r in (old,future)}
            self.assertFalse(n.snapshot(T)['entry_veto'])
            rows=parse(rss(),'FED',T)+parse(rss(),'SEC',T)
            n.state['items']={r['id']:r for r in rows}
            self.assertEqual(len(n.snapshot(T)['potential_acute_events']),1)

    def test_untrusted_xml_and_oversize_rejected(self):
        for raw in (b'<!DOCTYPE x><rss/>',b'x'*400001):
            with self.assertRaises(ValueError):parse(raw,'FED',T)

    def test_first_seen_persists_across_poll_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            n=GlobalContext(tmp)
            with patch('cqwe.global_event_context.urlopen',return_value=BytesIO(rss())),patch('cqwe.global_event_context.time.time_ns',return_value=T*1000000):n.poll_one()
            seen=next(iter(n.state['items'].values()))['first_seen_ms']
            n=GlobalContext(tmp);n.state['cursor']=0
            with patch('cqwe.global_event_context.urlopen',return_value=BytesIO(rss())),patch('cqwe.global_event_context.time.time_ns',return_value=(T+1000)*1000000):n.poll_one()
            self.assertEqual(next(iter(n.state['items'].values()))['first_seen_ms'],seen)


class MarketPolicyTests(unittest.TestCase):
    def test_multiple_independent_observations_required(self):
        m=MarketCouncil()
        first=m.decide('BTCUSDT',quote(),base(),micro(),news(),calendar(),T)
        self.assertFalse(first['exploration_allowed'])
        second=m.decide('BTCUSDT',quote(T+5000),base(),micro(T+5000),news(T+5000),calendar(),T+5000)
        self.assertTrue(second['exploration_allowed']);self.assertEqual(second['action'],'OPEN_LONG')
        self.assertTrue(all(not n['eligible'] for n in second['nodes']))
        self.assertFalse(second['maker_intent_known'])

    def test_single_book_imbalance_without_flow_never_confirms_intent(self):
        e=micro();e['flow']=0
        self.assertEqual(hypotheses(e),[])

    def test_news_and_calendar_veto_entries_but_not_fabricate_direction(self):
        for context,cal in (({**news(),'entry_veto':True},calendar()),(news(),{'upcoming_30min':[{'scheduled_ms':T+10000}]})):
            m=MarketCouncil()
            for at in (T,T+5000):d=m.decide('BTCUSDT',quote(at),base(),micro(at),context,cal,at)
            self.assertEqual(d['reason'],'EVENT_RISK_VETO');self.assertEqual(d['action'],'OBSERVE')

    def test_unknown_flow_and_funding_window_veto(self):
        for bad in ({**micro(),'ready':False},{**micro(),'funding_window_veto':True}):
            m=MarketCouncil()
            for at in (T,T+5000):d=m.decide('BTCUSDT',quote(at),base(),bad,news(),calendar(),at)
            self.assertFalse(d['exploration_allowed'])

    def test_opposing_flow_closes_position_without_candle_input(self):
        m=MarketCouncil();position={'direction':1,'entry':'100','opened_ms':T-1000}
        for at in (T,T+5000):d=m.decide('BTCUSDT',quote(at),base(),micro(at,-1),news(),calendar(),at,position)
        self.assertEqual(d['action'],'CLOSE')
        self.assertEqual(evaluate(position,D('100.01'),D('100.02'),T+5000,d),'FLOW_LIQUIDITY_REVERSAL')

    def test_news_alone_and_unconfirmed_single_flow_do_not_close(self):
        m=MarketCouncil();position={'direction':1,'entry':'100','opened_ms':T-1000}
        d=m.decide('BTCUSDT',quote(),base(),micro(T,-1),{**news(),'entry_veto':True},calendar(),T,position)
        self.assertEqual(d['action'],'HOLD');self.assertIsNone(evaluate(position,D('100'),D('100.01'),T,d))

    def test_delayed_outcomes_train_variants_and_restart_has_no_duplication(self):
        m=MarketCouncil();m.decide('BTCUSDT',quote(),base(),micro(),news(),calendar(),T)
        m=MarketCouncil(m.state)
        m.decide('BTCUSDT',quote(T+300000,101),base(),micro(T+300000),news(T+300000),calendar(),T+300000)
        b=m.state['banks']['BTCUSDT'];self.assertEqual(b['scores']['market_event']['n'],1)
        self.assertEqual(b['models']['market_event']['updates'],1);self.assertEqual(b['models']['frozen']['updates'],0)
        m=MarketCouncil(m.state);m.decide('BTCUSDT',quote(T+300001,101),base(),micro(T+300001),news(T+300001),calendar(),T+300001)
        self.assertEqual(m.state['banks']['BTCUSDT']['scores']['market_event']['n'],1)

    def test_profit_protection_and_stale_close_are_independent(self):
        p={'direction':1,'entry':'100'}
        self.assertIsNone(evaluate(p,D('101'),D('101.01'),T))
        self.assertEqual(evaluate(p,D('100.7'),D('100.71'),T+1000),'TRAILING_PROFIT_EXIT')


class MarketEvidenceTests(unittest.TestCase):
    def test_trade_direction_and_coverage_recorded_without_maker_identity(self):
        m=MarketEvidence()
        for i in range(3):
            at=T+i*5000
            batch={'rows':[{'a':i,'T':at,'p':'100','q':'2','m':False}],
                'trade_sha256':'a'*64,'complete':True,'received_ms':at,'exchange_ms':at,'aux':{
                  'premiumIndex':{'received_ms':at,'sha256':'b'*64,'raw':{'markPrice':'100','indexPrice':'100','lastFundingRate':'0.0001','nextFundingTime':T+86400000}},
                  'openInterest':{'received_ms':at,'sha256':'c'*64,'raw':{'openInterest':'100'}}},'stream':{}}
            d=m.frame('BTCUSDT',quote(at),batch,at)
        self.assertTrue(d['ready']);self.assertGreater(d['flow'],0);self.assertFalse(d['maker_identity_known'])
        batch['complete']=False
        self.assertFalse(m.frame('BTCUSDT',quote(at),batch,at)['ready'])


class IntegratedExecutionTests(unittest.TestCase):
    def test_mechanism_entry_and_exit_go_through_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            desk=PaperDesk(Path(tmp)/'paper.db');m=MarketCouncil()
            try:
                desk.action({'action':'start','mode':'automatic','request_id':'mechanism-start'},{},T)
                for at in (T,T+5000):
                    d=m.decide('BTCUSDT',quote(at),base(),micro(at),news(at),calendar(),at)
                    desk.cycle({'BTCUSDT':quote(at)},{'BTCUSDT':d},at)
                self.assertEqual(desk.state['positions']['BTCUSDT']['strategy_id'],'COPERNICAN_MARKET_EVENT_V1')
                self.assertFalse(desk.state['positions']['BTCUSDT']['entry_evidence']['model_scores'][0]['eligible'])
                for at in (T+10000,T+15000):
                    d=m.decide('BTCUSDT',quote(at),base(),micro(at,-1),news(at),calendar(),at,desk.state['positions']['BTCUSDT'])
                    desk.cycle({'BTCUSDT':quote(at)},{'BTCUSDT':d},at)
                self.assertFalse(desk.state['positions'])
                self.assertEqual(desk.state['trades'][0]['reason'],'FLOW_LIQUIDITY_REVERSAL')
            finally:desk.db.close()

    def test_two_opposite_candles_cannot_exit_live_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            desk=PaperDesk(Path(tmp)/'paper.db')
            try:
                desk.action({'action':'start','mode':'manual','request_id':'manual-start'},{},T)
                desk.action({'action':'open','symbol':'BTCUSDT','direction':1,'amount':'2','request_id':'manual-long'},
                            {'BTCUSDT':quote()},T)
                candles={'BTCUSDT':[{'time':T,'end':T+59999,'open':'100.2','close':'100.15'},
                                   {'time':T+60000,'end':T+119999,'open':'100.15','close':'100.1'}]}
                desk.cycle({'BTCUSDT':quote(T+120001,100.1)},{},T+120001,candles)
                self.assertIn('BTCUSDT',desk.state['positions'])
            finally:desk.db.close()
