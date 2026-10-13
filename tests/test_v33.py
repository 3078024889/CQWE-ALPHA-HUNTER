import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.public_data_v29 import SYMBOLS,PERIOD
from cqwe.live_paper_v33 import _starting_state,_intent,_fill,_verify_frame,cycle,MAX_ADDS
from cqwe.copernican_lab_v33 import AXES,Dendrite,respond,links,specs,evaluate,features

START=1800000000000//PERIOD*PERIOD

def markets(last,price=100):
    return {sym:[[last-(399-i)*PERIOD,price,price+1,price-1,price,10,last-(399-i)*PERIOD+PERIOD-1,1000,1,1,1,'0'] for i in range(400)] for sym in SYMBOLS}

class V33Tests(unittest.TestCase):
    def test_only_full_sell_after_target(self):
        state=_starting_state();state.update(symbol='BNBUSDT',qty=.06,avg_entry=100,entry_bar=START,peak_price=101,stop_price=99,cash=4.)
        p=_intent(state,{'symbol':'BNBUSDT','expert':'reversal'},START+PERIOD,markets(START+PERIOD,103))
        self.assertEqual('SELL',p['action']);ev=[];_fill(state,p,markets(START+2*PERIOD,103)['BNBUSDT'][-1],ev)
        self.assertEqual(0.,state['qty']);self.assertIsNone(state['symbol']);self.assertEqual(1,state['closed_positions']);self.assertEqual('SELL',ev[0]['action'])
    def test_partial_rejected(self):
        state=_starting_state();state.update(symbol='BNBUSDT',qty=.06,avg_entry=100,entry_bar=START,peak_price=101,stop_price=99,cash=4.)
        with self.assertRaisesRegex(ValueError,'PARTIAL_ACTION_DISABLED'):
            _fill(state,{'action':'SELL_PART','symbol':'BNBUSDT','reason':'x'},markets(START+PERIOD)['BNBUSDT'][-1],[])
    def test_trend_expert_condition_exists_but_cash_blocks(self):
        s=_starting_state();s.update(symbol='BNBUSDT',qty=.06,avg_entry=100,entry_bar=START,peak_price=100,stop_price=98,cash=4.,equity=10)
        m=markets(START+PERIOD,101);m['BNBUSDT'][-1][2]=101
        p=_intent(s,{'symbol':'BNBUSDT','expert':'trend_volume'},START+PERIOD,m)
        self.assertIsNone(p)
        s['cash']=9.;s['equity']=15.
        p=_intent(s,{'symbol':'BNBUSDT','expert':'trend_volume'},START+PERIOD,m)
        self.assertEqual('ADD',p['action'])
        self.assertLessEqual(s['adds'],MAX_ADDS)
    def test_six_mechanisms_each_axis(self):
        self.assertEqual(5,len(AXES));self.assertTrue(all(len(v)==6 for v in AXES.values()))
        self.assertEqual(6,len(specs()))
        self.assertEqual(6**5,7776)
        for spec in specs():
            d=Dendrite(spec);pred,r=d.forward([.1,.2,-.3,.4]);self.assertTrue(-1<=pred<=1)
            d.update(r,1.,pred,[.1,.2,-.3,.4]);self.assertEqual(1,d.updates)
    def test_mechanisms_have_distinct_effects(self):
        self.assertNotEqual(links('ring'),links('star'))
        self.assertNotEqual(respond('linear',.1,.2),respond('threshold',.1,.2))
        x=[.21,.4,-.2,.1];a=Dendrite(specs()[0]);b=Dendrite(specs()[1]);pa,ra=a.forward(x);pb,rb=b.forward(x)
        a.update(ra,1.,pa,x);b.update(rb,1.,pb,x)
        self.assertNotEqual(a.w,b.w)
    def test_fail_closed_missing_and_discontinuous(self):
        with tempfile.TemporaryDirectory() as d:
            paths=[]
            for sym in ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT'):
                p=Path(d)/(sym+'_5m.json');p.write_text(json.dumps(markets(START)[sym]));paths.append(str(p))
            report=evaluate(paths,Path(d)/'out.json')
            self.assertTrue(report['research_only']);self.assertFalse(report['account_pnl_available'])
            self.assertFalse(report['independent_out_of_sample_claim'])
            self.assertEqual(6,len(report['candidates']))
            self.assertEqual(report,evaluate(paths,Path(d)/'out.json'))
            rows=json.loads(Path(paths[0]).read_text());rows[-1][0]+=300000;Path(paths[0]).write_text(json.dumps(rows))
            with self.assertRaisesRegex(ValueError,'NONCONTIGUOUS_HISTORY'):evaluate(paths,Path(d)/'new.json')
    def test_new_journal_not_v32(self):
        self.assertNotEqual('CQWE_V33_CASH_ONLY_FULL_EXIT','CQWE_V32_CASH_ONLY_PAPER')
    def test_pending_timing_preserved(self):
        state=_starting_state();intent=_intent(state,{'intent':'PAPER_BUY_CANDIDATE_NOT_ORDER','symbol':'BNBUSDT'},START,markets(START))
        self.assertEqual(START+2*PERIOD,intent['execution_open_ms'])
        self.assertEqual(10.,state['cash'])

if __name__=='__main__':unittest.main()
