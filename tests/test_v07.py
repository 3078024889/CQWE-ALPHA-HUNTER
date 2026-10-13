import unittest
from cqwe.microstructure import rows,describe,validate_klines

def bar(i, op=100, hi=101, lo=99, cl=100, turnover=100, bought=40):
    return [i*300000,str(op),str(hi),str(lo),str(cl),'1',(i+1)*300000-1,str(turnover),1,'1',str(bought),'0']

class MicrostructureTests(unittest.TestCase):
    def test_missing_kline_rejected(self):
        b=[bar(i) for i in range(51)];b.pop(25)
        with self.assertRaises(ValueError): validate_klines(b)
    def test_next_open_label(self):
        b=[bar(i) for i in range(51)]
        b[25]=bar(25,op=100,hi=108,cl=105,turnover=500,bought=300)
        b[26]=bar(26,op=106,hi=120,lo=102,cl=112)
        r=rows(b,lookback=24,horizon=1)[1]
        self.assertEqual(r['entry_ms'],26*300000)
        self.assertAlmostEqual(r['return_next_open_to_horizon_close_pct'],100*(112/106-1))
    def test_signal_cannot_see_future_high(self):
        b=[bar(i) for i in range(51)];b[25]=bar(25,cl=100,turnover=900,bought=600)
        b[26]=bar(26,op=100,hi=500,cl=400)
        r=rows(b,lookback=24,horizon=1)[1]
        self.assertFalse(r['breakout'])
    def test_future_oi_cannot_be_used(self):
        b=[bar(i) for i in range(51)]
        # OI timestamps occur after signal close -> must be absent
        oi=[{'timestamp':30*300000,'oi_value':100},{'timestamp':31*300000,'oi_value':1000}]
        r=rows(b,oi,lookback=24,horizon=1)[1]
        self.assertIsNone(r['oi_change_pct'])
    def test_oi_change_strictly_historical(self):
        b=[bar(i) for i in range(51)]
        oi=[{'timestamp':24*300000,'oi_value':100},{'timestamp':25*300000,'oi_value':120}]
        r=rows(b,oi,lookback=24,horizon=1)[1]
        self.assertAlmostEqual(r['oi_change_pct'],20)
    def test_duplicate_oi_rejected(self):
        b=[bar(i) for i in range(51)]
        oi=[{'timestamp':1,'oi_value':100},{'timestamp':1,'oi_value':120}]
        with self.assertRaises(ValueError): rows(b,oi)
    def test_negative_taker_rejected(self):
        b=[bar(i) for i in range(51)];b[3][10]='101'
        with self.assertRaises(ValueError): rows(b)
    def test_no_signals_zero(self):
        b=[bar(i) for i in range(51)]
        self.assertEqual(describe(rows(b))['matched_signals'],0)

if __name__=='__main__':unittest.main()
