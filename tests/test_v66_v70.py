import unittest,sys,io,json,tempfile
from pathlib import Path
from decimal import Decimal
from cqwe import tidal_hunter_v66_v70 as m

def bars(n=150):
    raw=[]
    for i in range(n):
        x=100+i*.1;raw.append([i*3600000,str(x),str(x+2),str(x-2),str(x+0.3),'20',i*3600000+3599999,'0',1,'0','0','0'])
    return raw
class TenReverseAudits(unittest.TestCase):
    def test_01_noncontinuous_rejected(self):
        a=bars();a[20][0]+=1
        with self.assertRaises(ValueError):m.parse_klines(a,'1h')
    def test_02_high_low_invalid(self):
        a=bars();a[5][2]='1'
        with self.assertRaises(ValueError):m.parse_klines(a,'1h')
    def test_03_nan_rejected(self):
        a=bars();a[5][4]='NaN'
        with self.assertRaises(ValueError):m.parse_klines(a,'1h')
    def test_04_invalid_symbol_rejected(self):
        with self.assertRaises(ValueError):m.fetch_public('../secret','1h')
    def test_05_future_feature_not_read(self):
        a=m.parse_klines(bars(),'1h');before=m.features_at(a,30);a[30]['close']='99999';self.assertEqual(before,m.features_at(a,30))
    def test_06_repeatable(self):
        a=m.parse_klines(bars(),'1h');self.assertEqual(m.evaluate(a),m.evaluate(a))
    def test_07_immutable(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'a.json';m.save_immutable(f,{'x':1})
            with self.assertRaises(FileExistsError):m.save_immutable(f,{'x':2})
    def test_08_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'a.json';a={'source':'BINANCE_USDM_PUBLIC_KLINES','interval':'1h','bars':m.parse_klines(bars(),'1h'),'sha256':'f'*64};f.write_text(json.dumps(a))
            with self.assertRaises(ValueError):m.load_verified(f)
    def test_09_no_live_orders(self):
        a=m.evaluate(m.parse_klines(bars(),'1h'));self.assertFalse(a['live_trading']);self.assertEqual(a['real_orders'],0);self.assertIsNone(a['realized_cash_profit_usd'])
    def test_10_bad_cost(self):
        with self.assertRaises(ValueError):m.evaluate(m.parse_klines(bars(),'1h'),fee_bps=-1)
if __name__=='__main__':unittest.main()
