from decimal import Decimal as D
import unittest
from cqwe.trend_exit import evaluate,validate_bars


def pos(direction=1):
    return {'direction':direction,'entry':'100','opened_ms':0,'expires_ms':300000}


def bar(t,o,c):
    return {'time':t,'end':t+59999,'open':str(o),'close':str(c)}


class TrendExitTests(unittest.TestCase):
    def test_five_and_fifteen_minutes_do_not_expire_trend_position(self):
        p=pos()
        for at in (300000,900000,3600000):self.assertIsNone(evaluate(p,D('100.2'),D('100.21'),at))

    def test_profit_above_old_take_profit_does_not_force_exit(self):
        self.assertIsNone(evaluate(pos(),D('101'),D('101.01'),300000))

    def test_trailing_long_short_and_hard_stop(self):
        long=pos();self.assertIsNone(evaluate(long,D('101'),D('101.01'),1000))
        self.assertEqual(evaluate(long,D('100.7'),D('100.71'),2000),'TRAILING_PROFIT_EXIT')
        short=pos(-1);self.assertIsNone(evaluate(short,D('98.99'),D('99'),1000))
        self.assertEqual(evaluate(short,D('99.29'),D('99.3'),2000),'TRAILING_PROFIT_EXIT')
        self.assertEqual(evaluate(pos(),D('99'),D('99.01'),1000),'STOP_LOSS')

    def test_two_closed_opposite_candles_confirm_reversal(self):
        bars=[bar(60000,100.2,100.15),bar(120000,100.15,100.1)]
        self.assertEqual(evaluate(pos(),D('100.1'),D('100.11'),180001,bars),'CANDLE_REVERSAL')
        bars=[bar(60000,99.8,99.85),bar(120000,99.85,99.9)]
        self.assertEqual(evaluate(pos(-1),D('99.89'),D('99.9'),180001,bars),'CANDLE_REVERSAL')

    def test_one_opposite_candle_noise_or_missing_bar_does_not_confirm(self):
        for bars in ([bar(60000,100.2,100.15)],
                     [bar(60000,100.2,100.19),bar(120000,100.19,100.18)],
                     [bar(0,100.2,100.15),bar(120000,100.15,100.1)]):
            self.assertIsNone(evaluate(pos(),D('100.1'),D('100.11'),180001,bars))

    def test_future_pre_entry_and_stale_candles_cannot_exit(self):
        p=pos();p['opened_ms']=180000
        bars=[bar(60000,100.2,100.15),bar(120000,100.15,100.1)]
        self.assertIsNone(evaluate(p,D('100.1'),D('100.11'),180001,bars))
        self.assertIsNone(evaluate(pos(),D('100.1'),D('100.11'),150000,bars))
        self.assertIsNone(evaluate(pos(),D('100.1'),D('100.11'),400000,bars))

    def test_forming_candles_are_filtered_and_bad_ohlc_rejected(self):
        raw=[[t,'100','101','99','100.5','1',t+59999,'1',1,'1','1','0'] for t in (0,60000)]
        self.assertEqual(len(validate_bars(raw,90000)),1)
        raw[0][2]='99'
        with self.assertRaises(ValueError):validate_bars(raw,90000)
