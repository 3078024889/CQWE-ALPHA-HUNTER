import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.public_data_v29 import PERIOD,SYMBOLS
from cqwe.rolling_signal_v31 import market_snapshot,run,_verify,_read

START=1800000000000//PERIOD*PERIOD

def bars_for(sym,start,end):
    arr=[]
    for t in range(start,end+1,PERIOD):
        p=100+(t-start)/PERIOD*.001
        arr.append([t,str(p),str(p+1),str(p-1),str(p+.1),'3',t+PERIOD-1,'300','2','1','100','0'])
    return arr

class V31Tests(unittest.TestCase):
    def test_snapshot_400(self):
        last=START+399*PERIOD
        t,data=market_snapshot(fetch=bars_for,now_ms=last+PERIOD+20)
        self.assertEqual(last,t)
        self.assertEqual(400,len(data['BTCUSDT']))
    def test_fail_short(self):
        with self.assertRaisesRegex(ValueError,'HISTORY_NOT_COMPLETE'):
            market_snapshot(fetch=lambda *args:[],now_ms=START+500*PERIOD)
    def test_fail_gap(self):
        def gap(*args):return bars_for(*args)[:-1]+bars_for(*args)[-1:]
        with self.assertRaisesRegex(ValueError,'BAD_CLOCK'):
            market_snapshot(fetch=bars_for,now_ms='x')
    def test_record_and_settle(self):
        start=START+399*PERIOD
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            data={s:[] for s in SYMBOLS}
            for s in SYMBOLS:
                data[s]=[[start-399*PERIOD+i*PERIOD,100,101,99,100,2,0,200,2,1,1,'0'] for i in range(400)]
            def snap(t,*,fetch,now_ms):return t,data
            fake_weights={}
            with patch('cqwe.rolling_signal_v31._load_checked',return_value=({},'regsha',{'last_seen_ms':start-500*PERIOD,'tip_sha256':'tip'},fake_weights,{})),patch('cqwe.rolling_signal_v31.market_snapshot',side_effect=[(start,data),(start,data),(start+PERIOD,{s:data[s][1:]+[[start+PERIOD,101,102,100,101,2,0,202,2,1,1,'0']] for s in SYMBOLS})]):
                a=run('unused','unused',root,now_ms=start+PERIOD+30)
                self.assertEqual('SIGNAL_RECORDED',a['status'])
                b=run('unused','unused',root,now_ms=start+PERIOD+30)
                self.assertEqual('ALREADY_RECORDED',b['status'])
                c=run('unused','unused',root,now_ms=start+PERIOD+30)
                self.assertEqual(1,c['new_outcomes'])
            record=_read(root/f'signal_{start}.json');_verify(record)
            self.assertEqual('HOLD_CASH',record['decision']['intent'])
            outcome=_read(root/f'outcome_{start}.json');_verify(outcome)
            self.assertIsNone(outcome['candidate_close_to_close_return'])
    def test_threshold(self):
        with self.assertRaisesRegex(ValueError,'UNREGISTERED_THRESHOLD'):
            run('x','y','z',threshold=.35)
if __name__=='__main__':unittest.main()
