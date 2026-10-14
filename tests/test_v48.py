import unittest
from cqwe.microstructure_v40 import analyze, collect_once

class V48TimestampProvenance(unittest.TestCase):
    def setUp(self):
        self.book = {'bids': [['99','2']], 'asks': [['101','2']], 'lastUpdateId': 1}
        self.recent={'T':600000,'p':'100','q':'1','m':False}
        self.stale={'T':1,'p':'100','q':'1','m':True}
    def run_capture(self, prints):
        def fetch(name, params): return self.book if name=='depth' else prints
        return collect_once(fetch=fetch,clock=lambda:600000)
    def test_stale_quarantined_and_counter_visible(self):
        r=self.run_capture([self.stale,self.recent]);self.assertEqual(r['trade_count'],1)
        self.assertEqual(r['excluded_stale_trades'],1)
        self.assertEqual(r['trade_payload_count'],2)
        self.assertEqual(r['aggressor_imbalance'],1.0)
        self.assertEqual(r['trade_window_completeness'],'STALE_RECORDS_EXCLUDED_REST_LIMITED')
    def test_all_stale_no_fake_pressure(self):
        r=self.run_capture([self.stale]);self.assertEqual(r['trade_count'],0)
        self.assertIsNone(r['aggressor_imbalance'])
        self.assertEqual(r['excluded_stale_trades'],1)
    def test_future_trade_rejected(self):
        with self.assertRaisesRegex(ValueError,'TRADE_TIMESTAMP_OUT_OF_WINDOW'):
            self.run_capture([dict(self.recent,T=602000)])
    def test_bad_stale_row_rejected(self):
        with self.assertRaisesRegex(ValueError,'INVALID_NUMERIC_VALUE'):
            self.run_capture([dict(self.stale,p='nan')])
    def test_bad_recent_row_rejected(self):
        with self.assertRaisesRegex(ValueError,'TRADE_SIDE_MISSING'):
            self.run_capture([dict(self.recent,m='yes')])
    def test_analyze_remains_strict_for_outside_window(self):
        with self.assertRaisesRegex(ValueError,'TRADE_TIMESTAMP_OUT_OF_WINDOW'):
            analyze(self.book,[self.stale],symbol='BNBUSDT',started_ms=600000,ended_ms=600000)
    def test_empty_public_result_not_fabricated(self):
        r=self.run_capture([]);self.assertEqual(r['trade_payload_count'],0)
        self.assertEqual(r['excluded_stale_trades'],0)
        self.assertIsNone(r['aggressor_imbalance'])
    def test_count_cannot_be_negative(self):
        with self.assertRaisesRegex(ValueError,'INVALID_STALE_TRADE_COUNT'):
            analyze(self.book,[],symbol='BNBUSDT',started_ms=600000,ended_ms=600000,excluded_stale_trades=-1)

if __name__=='__main__':unittest.main()
