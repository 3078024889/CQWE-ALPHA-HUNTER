import json
import tempfile
import unittest
from pathlib import Path
from cqwe.alpha_lab_v10 import validate, _rows, train_logistic, probability, _selected, summarize, analyze, run_files


def candles(n=400):
    b=[]
    for i in range(n):
        op=100 + .06*i + 2*((i%17)/17)
        cl=op + (0.3 if i%5<3 else -0.2)
        hi=max(op,cl)+0.5
        lo=min(op,cl)-0.5
        turnover=1500 + 100*(i%9)
        b.append([i*300000,str(op),str(hi),str(lo),str(cl),'1',(i+1)*300000-1,
                  str(turnover),2,'1',str(turnover*.5),'0'])
    return b


class V10Tests(unittest.TestCase):
    def test_validates(self):
        self.assertEqual(len(validate(candles())),400)
    def test_gap_rejected(self):
        b=candles();b[7][0]+=300000
        with self.assertRaises(ValueError):validate(b)
    def test_bad_taker_rejected(self):
        b=candles();b[3][10]='999999'
        with self.assertRaises(ValueError):validate(b)
    def test_features_do_not_read_future(self):
        b=candles();x=_rows(b)
        before=x[70]['x']
        b[95][4]='9999';b[95][2]='10000'
        self.assertEqual(_rows(b)[70]['x'],before)
    def test_next_open_entry(self):
        b=candles();r=_rows(b,horizon=3)[0]
        self.assertEqual(r['entry_ms'],b[25][0])
        self.assertAlmostEqual(r['gross'],float(b[27][4])/float(b[25][1])-1)
    def test_purge_split(self):
        b=candles();r=analyze(b,min_trades=2)
        self.assertGreater(r['train_rows'],60)
        self.assertGreater(r['holdout_rows'],30)
        self.assertEqual(r['decision'],'RESEARCH_ONLY_NOT_ELIGIBLE_FOR_LIVE_TRADING')
    def test_training_prob_bounded(self):
        rs=_rows(candles())[:150]
        p=probability(train_logistic(rs),rs[0]);self.assertGreaterEqual(p,0);self.assertLessEqual(p,1)
    def test_no_overlap(self):
        rs=_rows(candles())[:35]
        chosen=_selected(rs,lambda r:True,12)
        self.assertTrue(all(b['i']>a['i']+12 for a,b in zip(chosen,chosen[1:])))
    def test_costs_reduce_net(self):
        rs=_rows(candles())[:40]
        chosen=_selected(rs,lambda r:True,12)
        a=summarize(chosen,2,2,min_trades=1)
        b=summarize(chosen,20,10,min_trades=1)
        self.assertGreater(a['mean_net_pct'],b['mean_net_pct'])
    def test_insufficient_not_profit(self):
        r=summarize([],min_trades=30)
        self.assertIsNone(r['mean_net_pct']);self.assertFalse(r['eligible']);self.assertIsNone(r['portfolio_profit'])
    def test_offline_multi_input(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            for x in ('BTC','ETH'):(p/(x+'.json')).write_text(json.dumps(candles()),encoding='utf-8')
            output=run_files([p/'BTC.json',p/'ETH.json'],p/'out.json',min_trades=2)
            self.assertEqual(output['dataset_count'],2)
            self.assertTrue((p/'out.json').exists())
    def test_invalid_train(self):
        with self.assertRaises(ValueError):train_logistic(_rows(candles())[:20])


if __name__=='__main__':unittest.main()
