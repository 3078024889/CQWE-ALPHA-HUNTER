import unittest
from cqwe.walkforward_v11 import analyze,diagnostics,folds


def bar(i, price=100, turnover=100, taker=40):
    return [i*300000,str(price),'101','99',str(price),'1',(i+1)*300000-1,
            str(turnover),2,'1',str(taker),'0']


class V11Tests(unittest.TestCase):
    def test_fold_chronology(self):
        f=folds(1000)
        self.assertGreaterEqual(len(f),3)
        self.assertTrue(all(a<b<=c<d for a,b,c,d in f))

    def test_small_dataset_invalid(self):
        with self.assertRaises(ValueError): folds(100)

    def test_probability_diagnostics(self):
        d=diagnostics([.1,.3,.6],[0,1,1])
        self.assertEqual(d['above_60'],1)
        self.assertEqual(d['above_50'],1)
        self.assertAlmostEqual(d['brier_score'],(.01+.49+.16)/3)

    def test_empty_diagnostics(self):
        self.assertEqual(diagnostics([],[])['observations'],0)

    def test_reject_bad_probabilities(self):
        with self.assertRaises(ValueError):diagnostics([1.2],[1])

    def test_no_events_are_not_eligible(self):
        candles=[bar(i) for i in range(600)]
        result=analyze(candles)
        self.assertFalse(result['aggregate']['breakout']['eligible_for_further_research'])
        self.assertEqual(result['aggregate']['breakout']['total_events'],0)

    def test_costs_monotonic(self):
        candles=[bar(i,turnover=500 if i%31==0 else 100) for i in range(600)]
        result=analyze(candles)
        for fold in result['folds']:
            low=fold['cost_scenarios']['fee_2_slip_2_bps_each_side']['always_long']['mean_net_event_pct']
            high=fold['cost_scenarios']['fee_20_slip_10_bps_each_side']['always_long']['mean_net_event_pct']
            if low is not None:self.assertGreaterEqual(low,high)

    def test_gap_rejected(self):
        candles=[bar(i) for i in range(600)]
        candles[50][0]+=300000
        with self.assertRaises(ValueError):analyze(candles)

    def test_invalid_cost_rejected(self):
        with self.assertRaises(ValueError):analyze([bar(i) for i in range(600)],fee_bps=-1)


if __name__=='__main__':unittest.main()
