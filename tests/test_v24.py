import copy,math,unittest
from cqwe.frozen_portfolio_v24 import paper
from tests.test_v20 import candles

class FrozenPortfolioTests(unittest.TestCase):
    def data(self,n=850):return {'BTCUSDT':candles(n=n),'ETHUSDT':candles(n=n,seed=1)}
    def test_determinism(self):self.assertEqual(paper(self.data()),paper(self.data()))
    def test_gate_unchanged_cash_when_not_promoted(self):
        x=paper(self.data())
        if not x['evidence_gate_pass']:
            self.assertEqual(x['entries'],0);self.assertEqual(x['virtual_net_usd'],0)
    def test_all_modes_balance(self):
        for mode in ('gate','shadow'):
            x=paper(self.data(),mode=mode,min_notional=1)
            self.assertTrue(x['ledger_balanced']);self.assertGreaterEqual(x['cash_usd'],-1e-8)
            self.assertIsNone(x['realized_profit_usd'])
    def test_shadow_not_independent(self):self.assertFalse(paper(self.data(),mode='shadow')['independent_holdout_claim'])
    def test_sealed_future_does_not_change_selection(self):
        x=self.data();a=paper(x);y=copy.deepcopy(x)
        for bars in y.values():
            for v in bars[700:]:v[4]=str(float(v[4])*1.0001)
        b=paper(y)
        self.assertEqual(a['research_selection'],b['research_selection'])
    def test_fee_stress_nonpositive_for_fixed_trades(self):
        x=self.data();a=paper(x,mode='shadow',min_notional=1,extra_cost_bps=0)
        b=paper(x,mode='shadow',min_notional=1,extra_cost_bps=20)
        # Costs must never improve a fixed trade path; differing later allocations can change eligibility.
        self.assertLessEqual(b['final_virtual_equity_usd'],a['final_virtual_equity_usd']+0.001)
    def test_bad_values(self):
        for k,v in [('cash0',0),('allocation',1.2),('min_notional',0),('fee_bps',-1),('slip_bps',float('nan'))]:
            with self.subTest(k=k),self.assertRaises(ValueError):paper(self.data(),**{k:v})
    def test_bad_rule(self):
        with self.assertRaises(ValueError):paper(self.data(),mode='shadow',rule=(1,2))
    def test_no_final_forced_exit(self):
        x=paper(self.data(),mode='shadow',min_notional=1)
        self.assertFalse(any(t['side']=='SELL_END_ASSUMPTION' for t in x['trades']))
    def test_account_shared_not_per_asset(self):self.assertEqual(paper(self.data())['initial_virtual_usd'],10)
