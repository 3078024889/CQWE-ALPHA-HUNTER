import unittest
from cqwe.paper_perpetual import plan_linear_usdt_order


class PaperPerpetualTests(unittest.TestCase):
    def plan(self, **overrides):
        args = dict(symbol="BTCUSDT", side="LONG", entry_price=100,
                    stop_price=98, target_price=104, equity_usdt=10000,
                    leverage=10, risk_fraction=0.005, fee_bps_each_side=5,
                    slippage_bps_each_side=2, min_net_rr=1.5)
        args.update(overrides)
        return plan_linear_usdt_order(**args)

    def test_approved_plan_is_paper_only(self):
        result = self.plan()
        self.assertEqual(result["status"], "APPROVED_PAPER_ONLY")
        self.assertTrue(result["paper_only"])
        self.assertFalse(result["real_orders"])
        self.assertAlmostEqual(result["initial_margin_usdt"], result["notional_usdt"] / 10)
        self.assertGreaterEqual(result["net_rr"], 1.5)

    def test_long_and_short_direction(self):
        long = self.plan()
        short = self.plan(side="SHORT", entry_price=100, stop_price=102, target_price=96)
        self.assertEqual(long["status"], "APPROVED_PAPER_ONLY")
        self.assertEqual(short["status"], "APPROVED_PAPER_ONLY")
        self.assertLess(long["stop_fill_estimate"], long["entry_fill_estimate"])
        self.assertGreater(short["stop_fill_estimate"], short["entry_fill_estimate"])

    def test_same_risk_qty_different_leverage_changes_margin_not_pnl(self):
        one_x = self.plan(leverage=1)
        ten_x = self.plan(leverage=10)
        self.assertAlmostEqual(one_x["quantity"], ten_x["quantity"], places=7)
        self.assertAlmostEqual(one_x["modeled_target_profit_usdt"], ten_x["modeled_target_profit_usdt"], places=7)
        self.assertAlmostEqual(one_x["initial_margin_usdt"] / ten_x["initial_margin_usdt"], 10, places=6)

    def test_leverage_cap_respects_max_notional(self):
        result = self.plan(equity_usdt=10, risk_fraction=0.02)
        self.assertLessEqual(result["notional_usdt"], 100 + 1e-7)

    def test_invalid_geometry_rejected(self):
        with self.assertRaises(ValueError):
            self.plan(side="SHORT", stop_price=99, target_price=101)
        with self.assertRaises(ValueError):
            self.plan(stop_price=101)

    def test_leverage_above_ten_rejected(self):
        with self.assertRaises(ValueError):
            self.plan(leverage=10.01)

    def test_bool_and_nan_rejected(self):
        for value in (True, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.plan(entry_price=value)

    def test_bad_symbol_rejected(self):
        with self.assertRaises(ValueError):
            self.plan(symbol="btc/usdt")

    def test_stop_beyond_liquidation_rejected(self):
        result = self.plan(entry_price=100, stop_price=89, target_price=120,
                           leverage=10, min_net_rr=0.1)
        self.assertEqual(result["status"], "REJECTED_STOP_AT_OR_BEYOND_ESTIMATED_LIQUIDATION")
        self.assertFalse(result["real_orders"])

    def test_costs_can_reject_target(self):
        result = self.plan(entry_price=100, stop_price=99.8, target_price=100.1,
                           fee_bps_each_side=20, slippage_bps_each_side=10,
                           min_net_rr=0.1)
        self.assertIn(result["status"], {
            "REJECTED_TARGET_NONPOSITIVE_AFTER_COSTS", "REJECTED_NET_RR_BELOW_MINIMUM"
        })

    def test_low_net_rr_rejected(self):
        result = self.plan(entry_price=100, stop_price=99, target_price=101,
                           min_net_rr=5)
        self.assertEqual(result["status"], "REJECTED_NET_RR_BELOW_MINIMUM")

    def test_screenshot_btc_signal_rejected_after_costs(self):
        result = self.plan(side="SHORT", entry_price=81545.70, stop_price=81716.14,
                           target_price=81543.50, equity_usdt=10, leverage=10)
        self.assertEqual(result["status"], "REJECTED_TARGET_NONPOSITIVE_AFTER_COSTS")

    def test_screenshot_bnb_signal_rejected_after_costs(self):
        result = self.plan(symbol="BNBUSDT", side="SHORT", entry_price=719.56,
                           stop_price=722.384, target_price=719.32,
                           equity_usdt=10, leverage=10)
        self.assertEqual(result["status"], "REJECTED_TARGET_NONPOSITIVE_AFTER_COSTS")


if __name__ == "__main__":
    unittest.main()
