import unittest
from cqwe_radar import analyze, candidates, select_contracts


class RadarTests(unittest.TestCase):
    def test_allow_only_active_usdt_perps(self):
        data = {'symbols': [
            {'symbol':'ABCUSDT','status':'TRADING','contractType':'PERPETUAL','quoteAsset':'USDT'},
            {'symbol':'XYZUSDT','status':'BREAK','contractType':'PERPETUAL','quoteAsset':'USDT'},
            {'symbol':'ABCUSDC','status':'TRADING','contractType':'PERPETUAL','quoteAsset':'USDC'}]}
        self.assertEqual(select_contracts(data), {'ABCUSDT'})

    def test_anomaly_uses_closed_candles_only(self):
        candles = [[i*300000, '100', '101', '99', '100', '1', (i+1)*300000-1, '100', 1, '1', '50', '0'] for i in range(28)]
        candles[-1][4] = '9999'  # incomplete candle must not be used
        score = analyze({'symbol':'ABCUSDT','priceChangePercent':'0','quoteVolume':'10000000'}, candles)
        self.assertAlmostEqual(score['momentum_30m_pct'], 0)
        self.assertFalse(score['breakout_above_prior_2h'])

    def test_volume_filter(self):
        ts=[{'symbol':'ABCUSDT','quoteVolume':'100','lastPrice':'1'}]
        self.assertEqual(candidates(ts, {'ABCUSDT'}, 1000, 20), [])


if __name__ == '__main__':
    unittest.main()
