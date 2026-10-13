import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.public_data_v29 import PERIOD,SYMBOLS
from cqwe.live_paper_v32 import cycle,_check_existing,_intent,_starting_state,_fill,_verify_frame,MIN_NOTIONAL

START=1800000000000//PERIOD*PERIOD

def markets(last,price=100):
    return {sym:[[last-(399-i)*PERIOD,price,price+1,price-1,price,10,
                   last-(399-i)*PERIOD+PERIOD-1,1000,1,1,1,'0'] for i in range(400)] for sym in SYMBOLS}

class V32Tests(unittest.TestCase):
    def _walk(self,root,decisions):
        start=START+399*PERIOD
        weights={'BNBUSDT|trend_low|reversal':0.5}
        chk={'last_seen_ms':start-500*PERIOD,'tip_sha256':'tip'}
        with patch('cqwe.live_paper_v32._load_checked',return_value=({},'reg',chk,weights,{})),\
             patch('cqwe.live_paper_v32.market_snapshot',side_effect=[(start+i*PERIOD,markets(start+i*PERIOD,price=100+i)) for i in range(len(decisions))]),\
             patch('cqwe.live_paper_v32._score',side_effect=decisions):
            return [cycle('store','registry',root,now_ms=start+(i+1)*PERIOD+1000) for i in range(len(decisions))]
    def test_no_order_on_first_bar_and_delayed_fill(self):
        with tempfile.TemporaryDirectory() as d:
            buy={'intent':'PAPER_BUY_CANDIDATE_NOT_ORDER','symbol':'BNBUSDT','expert':'reversal','regime':'trend_low','weight':.5}
            hold={'intent':'HOLD_CASH','symbol':None,'expert':None,'weight':None}
            res=self._walk(d,[buy,buy,buy,hold,hold,hold])
            self.assertEqual(10.,res[0]['cash_usd'])
            self.assertEqual(10.,res[1]['cash_usd'])
            self.assertTrue(any(t['action']=='BUY' for t in res[2]['events']))
            self.assertTrue(res[2]['cash_usd']<10)
            self.assertTrue(any(t['action']=='SELL' for t in res[5]['events']))
            self.assertEqual(None,res[5]['position'])
            self.assertTrue(all(x['no_orders'] for x in res))
    def test_idempotent_without_rewriting(self):
        with tempfile.TemporaryDirectory() as d:
            self._walk(d,[{'intent':'HOLD_CASH','symbol':None,'expert':None,'weight':None}])
            p=next(Path(d).glob('frame_*.json'));raw=p.read_bytes()
            last=json.loads(raw)['last_open_ms']
            with patch('cqwe.live_paper_v32._load_checked',return_value=({},'reg',{'last_seen_ms':last-100*PERIOD,'tip_sha256':'tip'}, {},{})),patch('cqwe.live_paper_v32.market_snapshot',return_value=(last,markets(last))):
                x=cycle('x','y',d,now_ms=last+PERIOD+1000)
            self.assertEqual('ALREADY_RECORDED',x['status']);self.assertEqual(raw,p.read_bytes())
    def test_tamper_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self._walk(d,[{'intent':'HOLD_CASH','symbol':None,'expert':None,'weight':None}])
            p=next(Path(d).glob('frame_*.json'));obj=json.loads(p.read_text());obj['state']['cash']=99;p.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError,'FRAME_HASH_MISMATCH'):_check_existing(Path(d),10**20,obj['context_sha256'])
    def test_no_impossible_partial(self):
        s=_starting_state();s.update(symbol='BTCUSDT',qty=.06,avg_entry=100,entry_bar=START,peak_price=102,stop_price=98, cash=3.999)
        market=markets(START+PERIOD,102)
        candidate={'intent':'PAPER_BUY_CANDIDATE_NOT_ORDER','symbol':'BTCUSDT','expert':'reversal'}
        p=_intent(s,candidate,START+PERIOD,market)
        self.assertFalse(p and p['action']=='SELL_PART')
    def test_future_intent_is_not_instant_fill(self):
        s=_starting_state();buy={'intent':'PAPER_BUY_CANDIDATE_NOT_ORDER','symbol':'BTCUSDT','expert':'reversal'}
        p=_intent(s,buy,START,markets(START))
        self.assertEqual(START+2*PERIOD,p['execution_open_ms'])
        self.assertEqual(10,s['cash'])
    def test_reject_small_add_and_fees(self):
        s=_starting_state();p={'action':'BUY','symbol':'BTCUSDT','budget_usd':4.99}
        ev=[];_fill(s,p,markets(START)['BTCUSDT'][-1],ev)
        self.assertEqual(10,s['cash']);self.assertEqual('REJECT_MIN_NOTIONAL',ev[0]['action'])
    def test_reject_invalid_frame(self):
        with self.assertRaisesRegex(ValueError,'FRAME_HASH_MISMATCH'):_verify_frame({'record_sha256':'nonsense'})
    def test_no_next_bar_artificial_profit(self):
        # No returns are declared from the choice itself: fill is delayed and observed.
        with tempfile.TemporaryDirectory() as d:
            buy={'intent':'PAPER_BUY_CANDIDATE_NOT_ORDER','symbol':'BNBUSDT','expert':'reversal'}
            r=self._walk(d,[buy]);self.assertEqual(10,r[0]['equity_usd']);self.assertEqual([],r[0]['events'])
if __name__=='__main__':unittest.main()
