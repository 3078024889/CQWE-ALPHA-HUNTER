import unittest
from cqwe.strategy_lab_v09 import analyze,_unoverlap,_metrics,_strategies

def bar(i,close=100,high=101,low=99,volume=100,buy=40):
    return [i*300000,'100',str(high),str(low),str(close),'1',(i+1)*300000-1,str(volume),1,'1',str(buy),'0']

class V09Tests(unittest.TestCase):
    def fixture(self):
        c=[bar(i) for i in range(450)]
        # Spike every 25 bars, non-overlapping, with valid OHLC
        for i in range(40,430,25):c[i]=bar(i,close=105,high=106,volume=500,buy=400)
        return c
    def test_empty_oi_is_not_imputed(self):
        a=analyze(self.fixture());self.assertEqual(a['oi_covered_rows'],0)
        self.assertFalse(a['oi_comparison_eligible'])
    def test_cost_sensitivity(self):
        x=analyze(self.fixture())['splits']['train_70pct']['volume_breakout']
        a=x['fee_2_slip_2_bps_each_side']['mean_net_pct']
        b=x['fee_20_slip_10_bps_each_side']['mean_net_pct']
        self.assertIsNotNone(a);self.assertLess(b,a)
    def test_no_lookahead_signal(self):
        cs=[bar(i) for i in range(420)]
        cs[46]=bar(46,close=100,high=101,volume=500)
        cs[47]=bar(47,close=500,high=501,volume=100)
        a=analyze(cs)
        self.assertEqual(a['splits']['train_70pct']['volume_breakout']['fee_5_slip_2_bps_each_side']['n'],0)
    def test_nonoverlap(self):
        a=[{'signal_ms':5,'future_exit_ms':10},{'signal_ms':6,'future_exit_ms':13},{'signal_ms':11,'future_exit_ms':20}]
        self.assertEqual(len(_unoverlap(a)),2)
    def test_reject_gap(self):
        cs=self.fixture();cs[50][0]+=300000
        with self.assertRaises(ValueError):analyze(cs)
    def test_bad_threshold(self):
        with self.assertRaises(ValueError):analyze(self.fixture(),min_events=1)
    def test_oi_not_disguised_as_inflow(self):
        a=analyze(self.fixture())
        self.assertEqual(a['splits']['holdout_30pct']['oi_rising']['fee_5_slip_2_bps_each_side']['n'],0)

if __name__=='__main__':unittest.main()
