import unittest
from research.event_study import build_events, summarize


def bar(i, open_, high, low, close, turnover=100):
    return [i * 300000, str(open_), str(high), str(low), str(close),
            '1', (i + 1) * 300000 - 1, str(turnover), 1, '1', '50', '0']


class EventStudyTests(unittest.TestCase):
    def test_next_open_entry_fee_and_adverse_excursion(self):
        candles = [bar(i, 100, 101, 99, 100) for i in range(24)]
        candles += [bar(24, 100, 110, 100, 105, 500)]
        candles += [bar(25, 106, 115, 103, 112)]
        candles += [bar(26, 112, 114, 100, 101)]
        events = build_events(candles, horizon=2, fee_bps=5)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['entry'], 106)
        self.assertAlmostEqual(events[0]['net_return_pct_before_slippage_funding'],
                               round(100 * (101 / 106 - 1) - 0.1, 4))
        self.assertAlmostEqual(events[0]['max_adverse_excursion_pct'],
                               round(100 * (100 / 106 - 1), 4))

    def test_signal_does_not_see_future_high(self):
        candles = [bar(i, 100, 101, 99, 100) for i in range(24)]
        candles += [bar(24, 100, 105, 99, 100, 900)]
        candles += [bar(25, 100, 500, 99, 499)]
        self.assertEqual(build_events(candles, horizon=1), [])

    def test_empty_summary(self):
        self.assertEqual(summarize([])['events'], 0)

    def test_invalid_parameters(self):
        with self.assertRaises(ValueError):
            build_events([], horizon=0)


if __name__ == '__main__':
    unittest.main()
