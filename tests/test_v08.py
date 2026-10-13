import unittest
from unittest.mock import Mock
from cqwe.oi_lab import fetch_oi,paired_study

def bar(i,close=100,hi=101,lo=99,turnover=100):
    return [i*300000,'100',str(hi),str(lo),str(close),'1',(i+1)*300000-1,str(turnover),1,'1',str(turnover*.4),'0']

class V08Tests(unittest.TestCase):
    def test_empty_oi_does_not_claim_edge(self):
        bars=[bar(i) for i in range(150)]
        out=paired_study(bars)
        self.assertFalse(out['eligible_for_oi_comparison'])
        self.assertEqual(out['conclusion'],'INSUFFICIENT_OI_SAMPLES')
    def test_paging_with_duplicate_boundary(self):
        def item(t):return {'timestamp':t,'sumOpenInterestValue':'100'}
        pages=[[item(0),item(300000)],[item(600000)]]
        f=Mock(side_effect=pages)
        out=fetch_oi('BTCUSDT',0,600000,page_limit=2,pause=0,get=f)
        self.assertEqual(len(out),3)
        self.assertEqual(f.call_count,2)
    def test_missing_oi_remains_missing(self):
        f=Mock(return_value=[])
        self.assertEqual(fetch_oi('BTCUSDT',0,600000,pause=0,get=f),[])
    def test_invalid_symbol(self):
        with self.assertRaises(ValueError):fetch_oi('BTC;USDT',0,600000)
    def test_reject_negative_cost(self):
        with self.assertRaises(ValueError):paired_study([bar(i) for i in range(150)],fee_bps=-1)
    def test_reject_invalid_oi(self):
        f=Mock(return_value=[{'timestamp':0,'sumOpenInterestValue':'nan'}])
        with self.assertRaises(ValueError):fetch_oi('BTCUSDT',0,300000,pause=0,get=f)

if __name__=='__main__':unittest.main()
