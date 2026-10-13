import json
import unittest
from research.fetch_klines import fetch, STEP

class FakeResponse:
    def __init__(self, rows): self.rows=rows
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,*args): return json.dumps(self.rows).encode()

class FetchTests(unittest.TestCase):
    def test_symbol_and_window_validation(self):
        with self.assertRaises(ValueError): fetch('BAD', days=1)
        with self.assertRaises(ValueError): fetch('BTCUSDT',days=100)
    def test_excludes_open_bar_and_deduplicates(self):
        now=10*STEP+1200
        def opener(req,timeout=0):
            return FakeResponse([[i*STEP,'100','101','99','100','1',(i+1)*STEP-1,'100','1','1','50','0'] for i in range(10)])
        rows=fetch('BTCUSDT',1,now_ms=now,opener=opener,pause=0)
        self.assertEqual(len(rows),10)
        self.assertEqual(int(rows[-1][0]),9*STEP)
    def test_detects_gap(self):
        now=10*STEP+1200
        def opener(req,timeout=0):
            return FakeResponse([[i*STEP,'100','101','99','100','1',(i+1)*STEP-1,'100','1','1','50','0'] for i in [0,1,3,4,5,6,7,8,9]])
        with self.assertRaisesRegex(RuntimeError,'KLINE_GAP_DETECTED'):
            fetch('BTCUSDT',1,now_ms=now,opener=opener,pause=0)

if __name__=='__main__':unittest.main()
