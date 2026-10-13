import unittest
from cqwe.alpha import decisions
from cqwe.portfolio import simulate,Parameters
from cqwe.validation import compare

def bar(i,cl=100,op=100,hi=101,lo=99,vol=100):
    return [i*300000,str(op),str(hi),str(lo),str(cl),'1',(i+1)*300000-1,str(vol),1,'1',str(vol*.4),'0']

class V06Tests(unittest.TestCase):
    def test_no_future_signal(self):
        cs=[bar(i) for i in range(30)]
        cs[25]=bar(25,cl=101,hi=102,vol=400)
        cs[26]=bar(26,cl=900,hi=1000)
        self.assertEqual(decisions(cs,'breakout'),{})
    def test_entry_on_next_open(self):
        cs=[bar(i,op=100,cl=100) for i in range(30)]
        cs[25]=bar(25,op=120,cl=120,hi=121)
        outcome=simulate(cs,{24:'long'},Parameters(hold_bars=2))
        self.assertEqual(outcome['trades'][0]['entry_index'],25)
        self.assertAlmostEqual(outcome['trades'][0]['entry_fill'],120.024)
    def test_fee_slippage_reduce_cash(self):
        cs=[bar(i) for i in range(35)]
        result=simulate(cs,{24:'long'},Parameters(allocation=1,hold_bars=2))
        self.assertLess(result['final_equity'],10)
    def test_overlapping_ignored(self):
        cs=[bar(i) for i in range(45)]
        result=simulate(cs,{24:'long',25:'long',26:'long'},Parameters(hold_bars=4))
        self.assertEqual(len(result['trades']),1)
    def test_bad_inputs(self):
        with self.assertRaises(ValueError):Parameters(starting_cash=-10)
        with self.assertRaises(ValueError):Parameters(allocation=2)
    def test_split(self):
        cs=[bar(i) for i in range(320)]
        result=compare(cs)
        self.assertEqual(result['sample_sizes']['earlier'],224)
        self.assertEqual(result['outcomes']['later_30pct']['breakout']['net_profit'],0)
    def test_drawdown_stop(self):
        cs=[bar(i) for i in range(40)]
        for i in range(26,40):cs[i]=bar(i,op=50,cl=50,hi=51,lo=49)
        out=simulate(cs,{24:'long',32:'long'},Parameters(allocation=1,hold_bars=3))
        self.assertTrue(out['stopped'])
        self.assertEqual(len(out['trades']),1)
if __name__=='__main__':unittest.main()
