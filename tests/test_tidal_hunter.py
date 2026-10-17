import copy
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from cqwe.copernican_experiment_v81_v85 import digest
from cqwe.futures_orderbook import BookFault, FuturesBook
from cqwe.tidal_hunter import Journal, replay, write_new
from cqwe.tidal_research import FlowFeatures, OnlineLab, PaperAccount, vwap

RULES = {'step':'.001','min_qty':'.001','max_qty':'100','min_notional':'1'}


def snapshot():
    return {'lastUpdateId':100,
            'bids':[[str(100-i),'100'] for i in range(5)],
            'asks':[[str(101+i),'100'] for i in range(5)]}


def event(u=101, pu=100, bids=None, asks=None):
    return {'e':'depthUpdate','s':'BTCUSDT','E':1000,'U':u-1,'u':u,'pu':pu,
            'b':bids or [],'a':asks or []}


def view(now=1_000_000_000, bid='100', ask='101', qty='100'):
    bids = [[str(D(bid)-i),qty] for i in range(5)]
    asks = [[str(D(ask)+i),qty] for i in range(5)]
    return {'symbol':'BTCUSDT','update_id':101,'bid':bid,'ask':ask,
            'bid_qty':qty,'ask_qty':qty,'mid':str((D(bid)+D(ask))/2),
            'imbalance':0.,'bids':bids,'asks':asks,'received_ns':now,'synced':True,
            'spread_bps':float((D(ask)-D(bid))/((D(bid)+D(ask))/2)*10000)}


class TenTidalResearchChecks(unittest.TestCase):
    def test_01_futures_snapshot_overlap_and_pu(self):
        b = FuturesBook('BTCUSDT')
        b.snapshot(snapshot())
        self.assertTrue(b.apply(event(), 100))
        self.assertTrue(b.apply(event(103,101), 200))
        with self.assertRaisesRegex(BookFault,'PU_GAP'):
            b.apply(event(104,102),300)
        with self.assertRaises(BookFault):
            b.view(300)
        recovered = snapshot()
        recovered['lastUpdateId'] = 200
        b.snapshot(recovered)
        self.assertTrue(b.apply(event(201,200),400))
        self.assertEqual(b.view(400)['update_id'],201)

    def test_02_stale_events_and_unknown_deletes(self):
        b = FuturesBook('BTCUSDT')
        b.snapshot(snapshot())
        self.assertFalse(b.apply(event(99,98),10))
        with self.assertRaises(BookFault):
            b.view(10)
        b.apply(event(101,100,bids=[['20','0']]),20)
        self.assertFalse(b.apply(event(101,100),21))
        self.assertEqual(b.update_id,101)
        self.assertEqual(b.view(21)['bid'],'100')

    def test_03_invalid_or_crossed_book_fails_closed(self):
        for bad in ([['102','1']],[['100','NaN']],[['100','-1']],[['100','1'],['100','2']]):
            with self.subTest(bad=bad):
                b = FuturesBook('BTCUSDT')
                b.snapshot(snapshot())
                with self.assertRaises(BookFault):
                    b.apply(event(bids=bad),10)
                self.assertFalse(b.valid)
        b = FuturesBook('BTCUSDT')
        b.snapshot(snapshot())
        b.apply(event(),10)
        with self.assertRaisesRegex(BookFault,'STALE'):
            b.view(2_000_000_000)

    def test_04_trade_direction_ofi_and_future_exclusion(self):
        f = FlowFeatures()
        e = {'e':'aggTrade','s':'BTCUSDT','a':1,'p':'100','q':'2','m':True}
        f.trade(e,100,'BTCUSDT')
        x,fresh = f.sample(view(100),100)
        self.assertTrue(fresh)
        self.assertEqual(x[2],-1.)
        # Duplicate aggregate trades must not be counted twice.
        f.trade(e,101,'BTCUSDT')
        self.assertEqual(len(f.trades),1)
        v = view(200)
        v['bid_qty'] = '200'
        x,_ = f.sample(v,200)
        self.assertGreater(x[1],0)
        f.trade({**e,'a':2,'m':False,'q':'999'},10000,'BTCUSDT')
        x,_ = f.sample(v,300)
        self.assertEqual(x[2],-1.)

    def test_05_depth_vwap_and_no_optimistic_fill(self):
        v = view(qty='1')
        self.assertEqual(vwap(v,'buy',D('.15')),D('101.3333333333333333333333333'))
        self.assertIsNone(vwap(v,'buy',D('1')))
        with self.assertRaises(ValueError):
            vwap(v,'buy',D(0))

    def test_06_virtual_entry_exit_latency_and_cash_replay(self):
        p = PaperAccount(RULES)
        t = 1_000_000_000
        p.request('entry',1,t,'TEST')
        p.advance(view(t),t)
        self.assertIsNone(p.position)
        p.advance(view(t+250_000_000),t+250_000_000)
        self.assertIsNotNone(p.position)
        self.assertLess(p.cash,D(10))
        self.assertLessEqual(p.position['entry']*p.position['quantity'],D(5))
        t += 1_000_000_000
        p.request('exit',1,t,'TEST_CLOSE')
        p.advance(view(t+250_000_000,bid='104',ask='105'),t+250_000_000)
        self.assertIsNone(p.position)
        self.assertGreater(p.cash,D(10))
        self.assertTrue(p.summary()['ledger_balanced'])

    def test_07_filter_risk_expiry_and_pause(self):
        p = PaperAccount({**RULES,'min_notional':'100'})
        p.request('entry',1,0,'TEST')
        p.advance(view(250_000_000),250_000_000)
        self.assertIsNone(p.position)
        self.assertEqual(p.ledger[-1]['event'],'VIRTUAL_REJECT_FILTER')
        p = PaperAccount(RULES)
        p.request('entry',-1,0,'TEST')
        p.advance(view(250_000_000),250_000_000)
        self.assertEqual(p.position['direction'],-1)
        p.pause('GAP')
        self.assertIsNotNone(p.position)
        p.advance(view(1_000_000_000,bid='103',ask='104'),1_000_000_000)
        p.manage(view(1_000_000_000,bid='103',ask='104'),1_000_000_000,0)
        self.assertEqual(p.pending['reason'],'STOP')
        p.advance(view(1_250_000_000,bid='103',ask='104'),1_250_000_000)
        self.assertLess(p.cash,D(10))
        self.assertTrue(p.summary()['ledger_balanced'])

    def test_08_label_maturity_gap_and_memory_growth(self):
        emitted = []
        lab = OnlineLab(RULES, lambda k,p:emitted.append((k,p)))
        lab.book(view(1_000_000_000),1_000_000_000)
        lab.book(view(5_000_000_000),5_000_000_000)
        self.assertEqual(lab.models['dendritic'].updates,0)
        lab.book(view(6_000_000_000,bid='101',ask='102'),6_000_000_000)
        self.assertEqual(lab.models['dendritic'].updates,1)
        checkpoint = lab.checkpoint()
        restored = OnlineLab(RULES,lambda k,p:None,previous=checkpoint)
        self.assertEqual(restored.models['dendritic'].state(),lab.models['dendritic'].state())
        lab.fault('TEST_GAP')
        lab.book(view(20_000_000_000),20_000_000_000)
        self.assertEqual(lab.models['dendritic'].updates,1)
        self.assertEqual(restored.paper.cash,D(10))

    def test_09_bad_checkpoint_and_unproven_edge(self):
        lab = OnlineLab(RULES,lambda k,p:None)
        c = lab.checkpoint()
        c['models']['dendritic']['weights'][0] = 100
        with self.assertRaises(ValueError):
            OnlineLab(RULES,lambda k,p:None,previous=c)
        c['sha256'] = digest({k:v for k,v in c.items() if k != 'sha256'})
        with self.assertRaises(ValueError):
            OnlineLab(RULES,lambda k,p:None,previous=c)
        self.assertEqual(lab._gate({'dendritic':1,'linear':1},True,[1,1,1,1]),0)
        for s in lab.stats.values():
            s.update({'n':40,'mean':-2.,'m2':1.})
        self.assertEqual(lab._gate({'dendritic':1,'linear':1},True,[1,1,1,1]),0)

    def test_10_raw_capture_model_ledger_replay_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with (folder/'capture.jsonl').open('x',encoding='utf-8') as file:
                journal = Journal(file)
                lab = OnlineLab(RULES,journal.emit)
                journal.emit('START',{'symbol':'BTCUSDT','rules':RULES,'previous':None,
                                      'initial_checkpoint':lab.checkpoint()})
                b = FuturesBook('BTCUSDT')
                for i in range(15):
                    now = (i+1)*1_000_000_000
                    e = event(101+i,100+i)
                    if i == 7:
                        e['pu'] -= 1
                    journal.emit('RAW_DEPTH',{'event':e,'received_ns':now})
                    if i in (0,8):
                        snap = snapshot()
                        snap['lastUpdateId'] = 100+i
                        journal.emit('SNAPSHOT',snap)
                        b.snapshot(snap)
                    if i == 7:
                        with self.assertRaises(BookFault):
                            b.apply(e,now)
                        journal.emit('FAULT',{'reason':'DEPTH_PU_GAP'})
                        lab.fault('DEPTH_PU_GAP')
                        continue
                    b.apply(e,now)
                    trade = {'e':'aggTrade','s':'BTCUSDT','a':i,'p':'100','q':'1','m':bool(i%2)}
                    journal.emit('RAW_FLOW',{'event':trade,'received_ns':now})
                    lab.flow.trade(trade,now,'BTCUSDT')
                    v = b.view(now)
                    journal.emit('FRAME',{'now_ns':now,'view':v})
                    lab.book(v,now)
                journal.emit('STOP',{'status':'COMPLETE'})
                r = {'capture_tip_sha256':journal.previous,'checkpoint':lab.checkpoint(),
                     'virtual_account':lab.paper.summary(),'virtual_ledger':lab.paper.ledger}
                r['sha256'] = digest(r)
                write_new(folder/'report.json',r)
            self.assertTrue(replay(folder)['causal_model_replay_equal'])
            with (folder/'capture.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps({'sequence':999})+'\n')
            with self.assertRaises(ValueError):
                replay(folder)


if __name__ == '__main__':
    unittest.main()
