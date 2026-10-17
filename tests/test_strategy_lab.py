import unittest
from research.strategy_lab import signals,replay,grid_stress,HOUR


def bars(n=250):
    return [{'time':i*HOUR,'open':100+i,'close':100+i,'high':101+i,'low':99+i} for i in range(n)]


class StrategyLabTests(unittest.TestCase):
    def test_future_prices_do_not_change_previous_signals(self):
        a=bars();b=bars();b[240]['close']=1000000
        for kind in ('ema_20_80','donchian_55_20','mean_revert_20_z2'):
            self.assertEqual(signals(a,kind)[:241],signals(b,kind)[:241])

    def test_flat_is_exact_zero_and_never_receives_funding(self):
        r=replay(bars(),[{'fundingTime':201*HOUR,'markPrice':'301','fundingRate':'.01'}],'flat',0,250*HOUR)
        self.assertEqual(r['final'],10);self.assertEqual(r['funding_cashflow'],0);self.assertEqual(r['fees'],0)

    def test_trend_position_quantity_fees_and_equity_reconcile(self):
        r=replay(bars(),[],'ema_20_80',200*HOUR,250*HOUR)
        entry=300*1.0002;q=5/entry;exit=349*.9998
        expected=10+q*(exit-entry)-5*.0005-q*exit*.0005
        self.assertAlmostEqual(r['final'],expected)
        self.assertAlmostEqual(r['net'],sum(t['net'] for t in r['trades']))

    def test_funding_charged_only_for_open_position(self):
        fs=[{'fundingTime':199*HOUR,'markPrice':'299','fundingRate':'.1'},
            {'fundingTime':201*HOUR,'markPrice':'301','fundingRate':'.001'}]
        r=replay(bars(),fs,'ema_20_80',200*HOUR,250*HOUR)
        self.assertAlmostEqual(r['funding_cashflow'],-5/(300*1.0002)*301*.001)
        self.assertAlmostEqual(r['net'],sum(t['net'] for t in r['trades']))

    def test_cost_increase_reduces_same_trend_return(self):
        a=replay(bars(),[],'ema_20_80',200*HOUR,250*HOUR,slip=.0002)
        b=replay(bars(),[],'ema_20_80',200*HOUR,250*HOUR,slip=.0005)
        self.assertLess(b['final'],a['final'])

    def test_stress_explicitly_not_backtest_and_exposure_matches_parameters(self):
        s=grid_stress();self.assertAlmostEqual(s['total_lots'],39)
        self.assertAlmostEqual(s['USD_base_notional'],3900000)
        self.assertLess(s['scenarios'][-1]['unrealized_USD'],s['scenarios'][0]['unrealized_USD'])


if __name__=='__main__':unittest.main()
