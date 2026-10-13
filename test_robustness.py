import unittest
from research.robustness import events, analyze

def bar(i, op=100,hi=101,lo=99,cl=100,vol=100):
    return [i*300000,str(op),str(hi),str(lo),str(cl),'1',(i+1)*300000-1,str(vol),1,'1','50','0']

class RobustnessTests(unittest.TestCase):
    def fixture(self):
        b=[bar(i) for i in range(24)]
        b.append(bar(24,100,110,100,105,500))
        b += [bar(25+i,106 if i==0 else 110,115,100,110) for i in range(12)]
        return b
    def test_next_open_and_costs(self):
        e=events(self.fixture())
        self.assertEqual(len(e),1)
        self.assertAlmostEqual(e[0]['gross_pct'],100*(110/106-1),places=4)
        self.assertAlmostEqual(e[0]['net_pct'],e[0]['gross_pct']-.14,places=4)
    def test_no_future_signal(self):
        b=[bar(i) for i in range(24)]+[bar(24,100,101,99,100,500)]+[bar(25,100,500,99,400)]
        self.assertEqual(events(b,horizon=1),[])
    def test_invalid_gap(self):
        b=[bar(i) for i in range(101)]
        b[50][0]+=300000
        with self.assertRaises(ValueError):analyze(b)
    def test_non_overlap(self):
        b=self.fixture()
        b[25][7]='1000'; b[25][4]='200';b[25][2]='210'
        self.assertEqual(len(events(b)),1)

if __name__=='__main__':unittest.main()
