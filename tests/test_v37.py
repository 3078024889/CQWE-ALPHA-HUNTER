import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.operational_truth_v37 import _read_account, evaluate, atomic_write
from cqwe.live_paper_v33 import _starting_state, _hashrec, VERSION
from cqwe.public_data_v29 import PERIOD
from tests.test_v35 import START

class V37Tests(unittest.TestCase):
    def test_empty_paper_directory(self):
        with tempfile.TemporaryDirectory() as d:
            r=_read_account(d,now_ms=START)
            self.assertEqual('NO_ACCOUNT_FRAMES',r['status'])
            self.assertFalse(r['account_profit_proven'])
    def _write(self,root,state=None,events=None,previous=None,offset=0):
        state=state or _starting_state();t=START+offset*PERIOD
        r={'version':VERSION,'no_real_orders':True,'context_sha256':'context',
           'last_open_ms':t,'previous_sha256':previous,
           'market_close_for_position': 0.0 if not state['symbol'] else state['equity']/state['qty']-state['cash']/state['qty'],
           'state':state,'events':events or [],'pending':None}
        r['record_sha256']=_hashrec(r)
        (Path(root)/f'frame_{t}.json').write_text(json.dumps(r),encoding='utf-8')
        return r
    def test_cash_only_is_not_profit(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d)
            r=_read_account(d,now_ms=START+PERIOD+1)
            self.assertEqual('NO_TRADES',r['status'])
            self.assertEqual(10.,r['paper_equity_usd'])
            self.assertEqual(0.,r['real_profit_usd'])
    def test_invented_profit_without_fill_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            state=_starting_state();state['cash']=10.25;state['equity']=10.25
            self._write(d,state=state)
            with self.assertRaisesRegex(ValueError,'ACCOUNT_EVENT_CASH_OR_INVENTORY_MISMATCH'):
                _read_account(d,now_ms=START+PERIOD+1)
    def test_full_roundtrip_is_paper_only(self):
        with tempfile.TemporaryDirectory() as d:
            fee=0.003
            buy={'action':'BUY','symbol':'BNBUSDT','time_ms':START,'qty':0.06,'price':100.0,'gross_usd':6.0,'fee_usd':fee,'hypothetical':True}
            state=_starting_state()
            state.update(cash=3.997,symbol='BNBUSDT',qty=0.06,avg_entry=100.0,entry_bar=START,fees=fee,equity=9.997)
            first=self._write(d,state=state,events=[buy])
            sellfee=0.00315
            sell={'action':'SELL','symbol':'BNBUSDT','time_ms':START+PERIOD,'qty':0.06,'price':105.0,'gross_usd':6.3,'fee_usd':sellfee,'hypothetical':True}
            state=_starting_state()
            state.update(cash=10.29385,equity=10.29385,fees=fee+sellfee,closed_positions=1,realized=0.29685)
            self._write(d,state=state,events=[sell],previous=first['record_sha256'],offset=1)
            r=_read_account(d,now_ms=START+2*PERIOD)
            self.assertEqual('PAPER_POSITIVE_NOT_REAL_PROFIT',r['status'])
            self.assertFalse(r['account_profit_proven'])
    def test_tampered_cash_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            r=self._write(d)
            r['state']['cash']=100
            (Path(d)/f'frame_{START}.json').write_text(json.dumps(r),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'FRAME_HASH_MISMATCH'):
                _read_account(d,now_ms=START+PERIOD)
    def test_gap_in_paper_chain_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            first=self._write(d)
            self._write(d,previous=first['record_sha256'],offset=2)
            with self.assertRaisesRegex(ValueError,'GAP_IN_JOURNAL'):_read_account(d,now_ms=START+3*PERIOD)
    def test_output_stays_safe_when_no_account(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('cqwe.operational_truth_v37.context_hash',return_value='dummy'),\
                 patch('cqwe.operational_truth_v37.longitudinal',return_value={
                     'freshness':'STALE_OR_TASK_DELAY','observed_gaps':1,'epoch_count':2,
                     'candidate_comparison':[{'settled_steps':12,'status':'INSUFFICIENT_SEQUENTIAL_OBSERVATIONS'}]*6,
                     'last_open_ms':START,'sha256':'abc'}):
                result=evaluate(store='none',registry='none',lineages='none',account=d,now_ms=START+10*PERIOD)
            self.assertIn('NO_ACCOUNT_EVIDENCE',result['alerts'])
            self.assertFalse(result['real_receipts_verified'])
            p=Path(d)/'truth.json';atomic_write(p,result)
            self.assertEqual(result,json.loads(p.read_text(encoding='utf-8')))
    def test_corrupt_fee_ledger_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            s=_starting_state();s['fees']=0.2
            self._write(d,state=s)
            with self.assertRaisesRegex(ValueError,'ACCOUNT_FEE_LEDGER_MISMATCH'):_read_account(d,now_ms=START+PERIOD)

if __name__=='__main__':unittest.main()
