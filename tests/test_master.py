import unittest
from unittest.mock import patch
from cqwe.core import valid_candles,valid_symbol,request
from cqwe.research import evaluate,walkforward
from cqwe.paper import Ledger
from cqwe.history import fetch


def bar(i,op=100,hi=101,lo=99,cl=100,v=100,taker=40):
    return [i*300000,str(op),str(hi),str(lo),str(cl),'1',(i+1)*300000-1,str(v),4,'1',str(taker),'0']

class MasterTests(unittest.TestCase):
    def test_closed_valid(self):
        self.assertEqual(len(valid_candles([bar(0),bar(1)],now_ms=900000)),2)
    def test_gap(self):
        with self.assertRaises(ValueError):valid_candles([bar(0),bar(2)])
    def test_incomplete(self):
        with self.assertRaises(ValueError):valid_candles([bar(0)],now_ms=200000)
    def test_bad_ohlc(self):
        with self.assertRaises(ValueError):valid_candles([bar(0,hi=99)])
    def test_invalid_symbol(self):
        with self.assertRaises(ValueError):valid_symbol('BTCUSDT;DELETE')
    def test_no_trade_endpoints(self):
        with self.assertRaises(ValueError):request('/fapi/v1/order')
    def test_non_overlapping_events(self):
        cs=[bar(i) for i in range(24)]+[bar(24,hi=110,cl=105,v=600)]
        cs += [bar(25+i,op=106,hi=115,lo=99,cl=110,v=100) for i in range(12)]
        ev=evaluate(cs)
        self.assertEqual(len(ev),1)
        self.assertGreater(ev[0]['gross_pct'],0)
    def test_no_future_signal(self):
        cs=[bar(i) for i in range(24)]+[bar(24,cl=100,v=900),bar(25,hi=900,cl=800)]
        self.assertEqual(evaluate(cs,horizon=1),[])
    def test_paper_allocation(self):
        a=Ledger(); self.assertTrue(a.buy(100));self.assertLessEqual(a.initial-a.cash,2.000001)
        self.assertFalse(a.buy(100));a.sell(101);self.assertEqual(a.qty,0)
    def test_paper_guard(self):
        a=Ledger()
        with self.assertRaises(ValueError):a.buy(100,allocation=-1)
    def test_paper_stop(self):
        a=Ledger(max_allocation=1)
        a.buy(100);a.sell(90);self.assertTrue(a.stopped);self.assertFalse(a.buy(100))
    def test_history_paging(self):
        pages=[[bar(i) for i in range(1,1001)], [bar(i) for i in range(1001,2001)], [bar(i) for i in range(2001,2017)]]
        calls=[]
        def fake(endpoint,params):
            calls.append(params)
            return pages[len(calls)-1]
        with patch('cqwe.history.request',side_effect=fake),patch('cqwe.history.time.sleep'):
            cs=fetch('BTCUSDT',days=7,now_ms=2017*300000)
        self.assertEqual(len(cs),2016)
        self.assertEqual(len(calls),3)
    def test_walkforward(self):
        cs=[bar(i) for i in range(150)]
        out=walkforward(cs)
        self.assertEqual(out['test']['count'],0)

if __name__=='__main__':unittest.main()
