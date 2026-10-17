import unittest
from research.spot_perp_carry_screen import replay,HOUR

T=1800000000000


def bars(n=180,spot=100.,perp=100.):
    a=[{'time':T+i*HOUR,'open':spot,'high':spot,'low':spot,'close':spot} for i in range(n)]
    b=[{'time':T+i*HOUR,'open':perp,'high':perp,'low':perp,'close':perp} for i in range(n)]
    return a,b


class CarryTests(unittest.TestCase):
    def test_no_funding_flat_prices_lose_four_leg_costs(self):
        a,b=bars();r=replay(a,b,[],T,T+180*HOUR,'hold_carry',.0002)
        self.assertLess(r['net'],0);self.assertEqual(r['trades'],1)
        self.assertAlmostEqual(r['net'],r['ledger'][0]['net'])

    def test_entry_settlement_not_collected_future_payment_collected(self):
        a,b=bars();f=[{'fundingTime':T+168*HOUR,'markPrice':'100','fundingRate':'.1'},
                     {'fundingTime':T+169*HOUR,'markPrice':'100','fundingRate':'.001'}]
        r=replay(a,b,f,T,T+180*HOUR,'hold_carry',.0002)
        self.assertAlmostEqual(r['funding_cashflow'],5/(100*1.0002)*100*.001)

    def test_future_funding_cannot_trigger_entry(self):
        a,b=bars();f=[{'fundingTime':T+179*HOUR,'markPrice':'100','fundingRate':'.1'}]
        r=replay(a,b,f,T,T+180*HOUR,'lagged_funding',.0002)
        self.assertEqual(r['trades'],0);self.assertEqual(r['net'],0)

    def test_price_move_hedged_when_basis_constant(self):
        a,b=bars()
        for i in range(169,180):
            for seq in (a,b):seq[i]={**seq[i],'open':110.,'high':110.,'low':110.,'close':110.}
        r=replay(a,b,[],T,T+180*HOUR,'hold_carry',0.)
        self.assertAlmostEqual(r['ledger'][0]['basis_pnl'],0.)
        self.assertAlmostEqual(r['net'],-r['fees'])

    def test_mismatched_spot_perp_times_rejected(self):
        a,b=bars();b[10]['time']+=1
        with self.assertRaises(ValueError):replay(a,b,[],T,T+180*HOUR,'hold_carry',.0002)

    def test_collateral_failure_flagged_even_with_hedged_total_equity(self):
        a,b=bars()
        for i in range(169,180):
            for seq in (a,b):seq[i]={**seq[i],'open':250.,'high':250.,'low':250.,'close':250.}
        r=replay(a,b,[],T,T+180*HOUR,'hold_carry',0.)
        self.assertGreater(r['margin_warning_positions'],0);self.assertFalse(r['research_eligible'])


if __name__=='__main__':unittest.main()
