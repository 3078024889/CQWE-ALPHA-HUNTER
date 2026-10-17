import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from cqwe import copernican_paper_v32 as paper


def utc(ms):
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def report(*, stamp=1_800_000_000_000, generated=None, side='LONG', selected=True, price=100.0, funding_history=None, stop=None, target=None):
    generated = generated or utc(stamp + 300_000)
    d = {
        'symbol': 'BTCUSDT', 'action': side if selected else 'HOLD', 'portfolio_selected': selected,
        'event_veto': False, 'entry_reference': price, 'stop_invalidation': stop if stop is not None else (99.0 if side == 'LONG' else 101.0),
        'dynamic_exit_reference': target if target is not None else (102.0 if side == 'LONG' else 98.0),
        'funding_history': funding_history or [],
    }
    ds = [d]
    for symbol in ('ETHUSDT', 'SOLUSDT', 'BNBUSDT'):
        ds.append({'symbol': symbol, 'action': 'HOLD', 'portfolio_selected': False, 'event_veto': False,
                   'entry_reference': price, 'stop_invalidation': None, 'dynamic_exit_reference': None, 'funding_history': []})
    return {'generated_utc': generated, 'decisions': ds, 'real_orders': 0, 'mode': 'PUBLIC_DATA_PAPER_ONLY'}


class PaperMarginV2Tests(unittest.TestCase):
    def test_open_uses_10x_margin_notional_and_explicit_costs(self):
        state = paper._new_state()
        result = paper.step(state, report())
        pos = state['positions']['BTCUSDT']
        self.assertEqual(result['real_orders'], 0)
        self.assertAlmostEqual(pos['notional'], 1.0, places=7)
        self.assertAlmostEqual(pos['margin'], 0.1, places=7)
        self.assertEqual(pos['leverage'], 10)
        self.assertAlmostEqual(state['cash'], 10 - 0.1 - 0.0005 - 0.0002, places=8)
        self.assertAlmostEqual(result['equity'], 10 - 0.0007, places=8)

    def test_mark_to_market_and_pnl_sign_for_long_and_short(self):
        long_state = paper._new_state()
        paper.step(long_state, report(side='LONG', price=100, stop=99, target=102))
        self.assertAlmostEqual(paper.mark_to_market(long_state, {'BTCUSDT': 101}), 10 - 0.0007 + 0.01, places=7)
        short_state = paper._new_state()
        paper.step(short_state, report(side='SHORT', price=100, stop=101, target=98))
        self.assertAlmostEqual(paper.mark_to_market(short_state, {'BTCUSDT': 99}), 10 - 0.0007 + 0.01, places=7)

    def test_exit_costs_and_entry_costs_are_counted_once(self):
        state = paper._new_state()
        paper.step(state, report(price=100, stop=99, target=102))
        result = paper.step(state, report(stamp=1_800_000_300_000, price=102, stop=99, target=102))
        trade = state['trades'][-1]
        expected = 0.02 - 0.0005 - 0.0002 - 1.02 * 0.0005 - 1.02 * 0.0002
        self.assertEqual(trade['reason'], 'DYNAMIC_EXIT')
        self.assertAlmostEqual(trade['net_pnl'], expected, places=8)
        self.assertAlmostEqual(state['cash'], 10 + expected, places=7)
        self.assertEqual(result['closed'], ['BTCUSDT'])

    def test_legacy_migration_preserves_equity_and_marks_assumption(self):
        legacy = {
            'version': 'V32_PAPER', 'cash': 8.0987,
            'positions': {
                'BTCUSDT': {'side':'SHORT','entry':81545.7,'notional':0.9995,'stop_invalidation':81670,'dynamic_exit_reference':80816,'opened_at':'2026-10-17T01:00:00Z'},
                'BNBUSDT': {'side':'SHORT','entry':719.56,'notional':0.9003,'stop_invalidation':720.1,'dynamic_exit_reference':719.09,'opened_at':'2026-10-17T01:00:00Z'},
            }, 'trades': [], 'equity_history': []
        }
        marks = {'BTCUSDT':81502.1,'BNBUSDT':719.83}
        before = legacy['cash'] + sum(p['notional'] + paper._pnl(p, marks[s]) for s,p in legacy['positions'].items())
        migrated, changed = paper.migrate_state(legacy)
        self.assertTrue(changed)
        after = paper.mark_to_market(migrated, marks)
        self.assertAlmostEqual(after, before, places=8)
        self.assertAlmostEqual(migrated['cash'], 8.0987 + (0.9995 - 0.09995) + (0.9003 - 0.09003), places=8)
        self.assertAlmostEqual(migrated['positions']['BTCUSDT']['margin'], 0.09995, places=8)
        self.assertEqual(migrated['positions']['BTCUSDT']['leverage_source'], 'MIGRATION_ASSUMPTION_10X_NOT_HISTORICAL_FACT')
        self.assertEqual(migrated['migrations'][-1]['real_orders'], 0)

    def test_load_persists_migration_atomically(self):
        legacy = {'version':'V32_PAPER','cash':9.0,'positions':{'BTCUSDT':{'side':'LONG','entry':100,'notional':1,'stop_invalidation':99,'dynamic_exit_reference':102}},'trades':[],'equity_history':[]}
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json'; path.write_text(json.dumps(legacy),encoding='utf-8')
            loaded=paper.load(path)
            saved=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(loaded['version'],paper.SCHEMA)
            self.assertEqual(saved['version'],paper.SCHEMA)
            self.assertAlmostEqual(saved['cash'],9.9,places=8)

    def test_missing_partial_margin_fields_refuse_to_guess(self):
        legacy={'cash':9.0,'positions':{'BTCUSDT':{'side':'LONG','entry':100,'notional':1,'margin':0.1}},'trades':[],'equity_history':[]}
        with self.assertRaisesRegex(ValueError,'PARTIAL_MARGIN_SCHEMA_REFUSE_GUESS'):
            paper.migrate_state(legacy)

    def test_legacy_version_with_margin_fields_refuses_ambiguous_cash_model(self):
        legacy={'version':'V32_PAPER','cash':9.9,'positions':{'BTCUSDT':{'side':'LONG','entry':100,'notional':1,'margin':0.1,'leverage':10}},'trades':[],'equity_history':[]}
        with self.assertRaisesRegex(ValueError,'LEGACY_VERSION_WITH_MARGIN_FIELDS_REFUSE_AMBIGUOUS_MIGRATION'):
            paper.migrate_state(legacy)

    def test_liquidation_estimate_is_side_aware_and_assumption_labeled(self):
        long={'side':'LONG','entry':100,'notional':1,'margin':0.1,'leverage':10,'maintenance_margin_rate':0.005}
        short={**long,'side':'SHORT'}
        self.assertAlmostEqual(paper.liquidation_price_estimate(long),90.5)
        self.assertAlmostEqual(paper.liquidation_price_estimate(short),109.5)
        self.assertIsNone(paper.liquidation_price_estimate({'side':'LONG','entry':100,'leverage':10}))

    def test_funding_settlement_is_applied_once_and_recorded(self):
        t=1_800_000_000_000
        state=paper._new_state()
        paper.step(state, report(stamp=t, generated=utc(t+300_000), price=100, funding_history=[{'ts':t-1000,'rate':0.0001}]))
        pos=state['positions']['BTCUSDT']
        event={'ts':t+600_000,'rate':0.001}
        second=report(stamp=t+300_000, generated=utc(t+600_000), price=100, funding_history=[{'ts':t-1000,'rate':0.0001},event])
        paper.step(state, second)
        cash_after=state['cash']
        self.assertAlmostEqual(pos['funding_paid_usdt'],0.001,places=8)
        paper.step(state, second)
        self.assertAlmostEqual(state['cash'],cash_after,places=10)

    def test_short_receives_positive_funding(self):
        t=1_800_000_000_000
        state=paper._new_state()
        paper.step(state, report(stamp=t, generated=utc(t+300_000), side='SHORT', price=100, funding_history=[{'ts':t-1000,'rate':0.0001}]))
        second=report(stamp=t+300_000, generated=utc(t+600_000), side='SHORT', price=100, funding_history=[{'ts':t-1000,'rate':0.0001},{'ts':t+600_000,'rate':0.001}])
        paper.step(state,second)
        self.assertAlmostEqual(state['positions']['BTCUSDT']['funding_paid_usdt'],-0.001,places=8)

    def test_migrated_position_without_funding_history_sets_gap_warning(self):
        legacy={'version':'V32_PAPER','cash':9.0,'positions':{'BTCUSDT':{'side':'LONG','entry':100,'notional':1,'stop_invalidation':99,'dynamic_exit_reference':102,'opened_at':'2026-10-17T01:00:00Z'}},'trades':[],'equity_history':[]}
        state, changed=paper.migrate_state(legacy)
        self.assertTrue(changed)
        paper.step(state, report(stamp=1_800_000_000_000, generated=utc(1_800_000_300_000), selected=False, price=100, funding_history=[]))
        self.assertTrue(state['positions']['BTCUSDT']['funding_history_gap_possible'])
        self.assertTrue(paper.account_snapshot(state, {'BTCUSDT':100})['funding_history_gap_possible'])

    def test_simulated_liquidation_closes_without_real_orders(self):
        state=paper._new_state()
        paper.step(state, report(side='LONG',price=100,stop=99,target=102))
        result=paper.step(state, report(stamp=1_800_000_300_000,price=90,stop=99,target=102))
        self.assertEqual(result['closed'],['BTCUSDT'])
        self.assertEqual(state['trades'][-1]['reason'],'SIMULATED_LIQUIDATION_ESTIMATE')
        self.assertEqual(state['real_orders'],0)

    def test_stop_risk_gate_blocks_oversized_entry(self):
        state=paper._new_state()
        paper.step(state, report(side='LONG',price=100,stop=70,target=110))
        self.assertEqual(state['positions'],{})

    def test_invalid_side_is_rejected_instead_of_treated_as_short(self):
        with self.assertRaisesRegex(ValueError, "INVALID_POSITION_SIDE"):
            paper._pnl({"side": "SIDEWAYS", "entry": 100, "notional": 10}, 99)

    def test_trailing_stop_tightens_from_favorable_extreme_and_closes(self):
        state = paper._new_state()
        first = report(price=100, stop=95, target=150)
        first["decisions"][0]["trailing_stop_distance_fraction"] = 0.02
        paper.step(state, first)
        second = report(stamp=1_800_000_300_000, price=110, stop=95, target=150)
        second["decisions"][0]["trailing_stop_distance_fraction"] = 0.02
        paper.step(state, second)
        self.assertAlmostEqual(state["positions"]["BTCUSDT"]["trailing_stop"], 107.8, places=7)
        third = report(stamp=1_800_000_600_000, price=107.7, stop=95, target=150)
        third["decisions"][0]["trailing_stop_distance_fraction"] = 0.02
        result = paper.step(state, third)
        self.assertEqual(result["closed"], ["BTCUSDT"])
        self.assertEqual(state["trades"][-1]["reason"], "TRAILING_STOP")
        self.assertEqual(state["real_orders"], 0)

    def test_short_trailing_stop_tracks_favorable_low_and_closes(self):
        state = paper._new_state()
        first = report(side='SHORT', price=100, stop=105, target=80)
        first['decisions'][0]['trailing_stop_distance_fraction'] = 0.02
        paper.step(state, first)
        second = report(stamp=1_800_000_300_000, side='SHORT', price=90, stop=105, target=80)
        second['decisions'][0]['trailing_stop_distance_fraction'] = 0.02
        paper.step(state, second)
        self.assertAlmostEqual(state['positions']['BTCUSDT']['trailing_stop'], 91.8, places=7)
        third = report(stamp=1_800_000_600_000, side='SHORT', price=92, stop=105, target=80)
        third['decisions'][0]['trailing_stop_distance_fraction'] = 0.02
        result = paper.step(state, third)
        self.assertEqual(result['closed'], ['BTCUSDT'])
        self.assertEqual(state['trades'][-1]['reason'], 'TRAILING_STOP')

    def test_adverse_move_without_favorable_excursion_does_not_activate_distance_trailing(self):
        state = paper._new_state()
        first = report(price=100, stop=95, target=150)
        first['decisions'][0]['trailing_stop_distance_fraction'] = 0.02
        paper.step(state, first)
        second = report(stamp=1_800_000_300_000, price=97, stop=95, target=150)
        second['decisions'][0]['trailing_stop_distance_fraction'] = 0.02
        result = paper.step(state, second)
        self.assertEqual(result['closed'], [])
        self.assertIsNone(state['positions']['BTCUSDT']['trailing_stop'])

    def test_trailing_stop_is_monotonic_across_repeated_long_and_short_marks(self):
        for side, prices, stop, target, expected_direction in (
            ('LONG', [101,102,103,104,105,106], 95, 150, 'up'),
            ('SHORT', [99,98,97,96,95,94], 105, 50, 'down'),
        ):
            state = paper._new_state()
            first = report(side=side, price=100, stop=stop, target=target)
            first['decisions'][0]['trailing_stop_distance_fraction'] = 0.02
            paper.step(state, first)
            observed = []
            stamp = 1_800_000_000_000
            for i, price in enumerate(prices, start=1):
                cycle = report(stamp=stamp+i*300_000, side=side, price=price, stop=stop, target=target)
                cycle['decisions'][0]['trailing_stop_distance_fraction'] = 0.02
                paper.step(state, cycle)
                observed.append(state['positions']['BTCUSDT']['trailing_stop'])
            self.assertTrue(all(x is not None for x in observed))
            pairs = zip(observed, observed[1:])
            if expected_direction == 'up':
                self.assertTrue(all(b >= a for a,b in pairs))
            else:
                self.assertTrue(all(b <= a for a,b in pairs))

    def test_trailing_stop_never_loosens_when_distance_widens(self):
        state = paper._new_state()
        first = report(price=100, stop=95, target=150)
        first["decisions"][0]["trailing_stop_distance_fraction"] = 0.02
        paper.step(state, first)
        second = report(stamp=1_800_000_300_000, price=110, stop=95, target=150)
        second["decisions"][0]["trailing_stop_distance_fraction"] = 0.02
        paper.step(state, second)
        third = report(stamp=1_800_000_600_000, price=109, stop=95, target=150)
        third["decisions"][0]["trailing_stop_distance_fraction"] = 0.05
        paper.step(state, third)
        self.assertAlmostEqual(state["positions"]["BTCUSDT"]["trailing_stop"], 107.8, places=7)

    def test_multiple_same_direction_assets_can_open_but_opposite_basket_is_blocked(self):
        state = paper._new_state()
        r = report(price=100, stop=99, target=110)
        eth = dict(r["decisions"][1])
        eth.update({"action": "LONG", "portfolio_selected": True, "entry_reference": 200,
                    "stop_invalidation": 198, "dynamic_exit_reference": 210})
        r["decisions"][1] = eth
        paper.step(state, r, max_positions=2)
        self.assertEqual(set(state["positions"]), {"BTCUSDT", "ETHUSDT"})
        self.assertAlmostEqual(sum(p["margin"] for p in state["positions"].values()), 0.199986, places=4)

        opposite = report(stamp=1_800_000_300_000, side="LONG", selected=False, price=100, stop=99, target=110)
        opposite["decisions"][1].update({"action": "HOLD", "portfolio_selected": False, "entry_reference": 200,
                                        "stop_invalidation": 198, "dynamic_exit_reference": 210})
        opposite["decisions"][2].update({"action": "SHORT", "portfolio_selected": True, "entry_reference": 300,
                                        "stop_invalidation": 303, "dynamic_exit_reference": 294})
        paper.step(state, opposite, max_positions=3)
        self.assertEqual({p["side"] for p in state["positions"].values()}, {"LONG"})
        self.assertTrue(any(e["event"] == "ENTRY_REJECTED" for e in state["strategy_events"]))

    def test_explicit_roll_closes_and_reopens_with_bounded_roll_count(self):
        state = paper._new_state()
        first = report(price=100, stop=99, target=110)
        first["decisions"][0]["roll_policy"] = {"enabled": True, "max_rolls": 1}
        paper.step(state, first)
        roll = report(stamp=1_800_000_300_000, price=101, stop=100, target=110)
        roll["decisions"][0].update({"roll_action": "ROLL", "roll_policy": {"enabled": True, "max_rolls": 1}})
        result = paper.step(state, roll)
        self.assertEqual(result["closed"], ["BTCUSDT"])
        self.assertEqual(state["trades"][-1]["reason"], "STRATEGY_ROLL")
        self.assertIn("BTCUSDT", state["positions"])
        self.assertEqual(state["positions"]["BTCUSDT"]["roll_count"], 1)
        self.assertEqual(state["positions"]["BTCUSDT"]["roll_policy"]["max_rolls"], 1)
        self.assertEqual(state["real_orders"], 0)

    def test_roll_without_explicit_policy_is_rejected(self):
        state = paper._new_state()
        paper.step(state, report(price=100, stop=99, target=110))
        roll = report(stamp=1_800_000_300_000, price=100.5, stop=99, target=110)
        roll["decisions"][0]["roll_action"] = "ROLL"
        result = paper.step(state, roll)
        self.assertEqual(result["closed"], [])
        self.assertIn("BTCUSDT", state["positions"])
        self.assertTrue(any(e["event"] == "ROLL_REJECTED" for e in state["strategy_events"]))

    def test_stop_or_target_exit_cannot_reopen_same_symbol_in_same_cycle(self):
        state = paper._new_state()
        paper.step(state, report(price=100, stop=99, target=102))
        result = paper.step(state, report(stamp=1_800_000_300_000, price=102, stop=99, target=102))
        self.assertEqual(result["closed"], ["BTCUSDT"])
        self.assertEqual(state["positions"], {})
        self.assertTrue(any(e["event"] == "REENTRY_BLOCKED_AFTER_EXIT" for e in state["strategy_events"]))

    def test_step_fails_closed_on_inconsistent_existing_margin_or_quantity(self):
        state = paper._new_state()
        paper.step(state, report(price=100, stop=99, target=110))
        state['positions']['BTCUSDT']['quantity'] = 0.5
        with self.assertRaisesRegex(ValueError, 'INCONSISTENT_POSITION_QUANTITY'):
            paper.step(state, report(stamp=1_800_000_300_000, price=100, stop=99, target=110))

    def test_nonfinite_strategy_event_values_are_json_safe(self):
        state = paper._new_state()
        paper._record_strategy_event(state, utc(1_800_000_000_000), 'INPUT_REJECTED', 'BTCUSDT', value=float('nan'))
        json.dumps(state, allow_nan=False)
        self.assertEqual(state['strategy_events'][-1]['value'], 'nan')

    def test_roll_policy_maximum_is_enforced(self):
        state = paper._new_state()
        first = report(price=100, stop=99, target=120)
        first['decisions'][0]['roll_policy'] = {'enabled': True, 'max_rolls': 1}
        paper.step(state, first)
        roll1 = report(stamp=1_800_000_300_000, price=101, stop=99, target=120)
        roll1['decisions'][0].update({'roll_action':'ROLL','roll_policy':{'enabled':True,'max_rolls':1}})
        paper.step(state, roll1)
        self.assertEqual(state['positions']['BTCUSDT']['roll_count'], 1)
        roll2 = report(stamp=1_800_000_600_000, price=101.5, stop=99, target=120)
        roll2['decisions'][0]['roll_action'] = 'ROLL'
        result = paper.step(state, roll2)
        self.assertEqual(result['closed'], [])
        self.assertIn('BTCUSDT', state['positions'])
        self.assertTrue(any(e['event']=='ROLL_REJECTED' for e in state['strategy_events']))

    def test_snapshot_reconciles_equity_cash_margin_and_unrealized_pnl(self):
        state=paper._new_state()
        paper.step(state, report(price=100,stop=99,target=102))
        snap=paper.account_snapshot(state,{'BTCUSDT':101})
        self.assertEqual(snap['accounting_status'],'VERIFIED_MARGIN_LEDGER_V2')
        self.assertAlmostEqual(snap['current_equity_usdt'],snap['available_cash_usdt']+snap['used_margin_usdt']+snap['unrealized_pnl_gross_usdt'],places=8)
        self.assertAlmostEqual(snap['used_margin_usdt'],0.1,places=7)
        self.assertEqual(snap['real_orders'],0)

if __name__ == '__main__':
    unittest.main(verbosity=2)
