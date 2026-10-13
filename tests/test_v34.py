import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from cqwe.public_data_v29 import PERIOD,SYMBOLS
from cqwe.forward_dendrites_v34 import (cycle,validate,replay_journal,restore,GENOTYPES,
                                         hash_record,VERSION)
from cqwe.live_paper_v33 import _starting_state,VERSION as ACCOUNT_VERSION

START=1800000000000//PERIOD*PERIOD

def bars(last):
    return {sym:[[last-(399-i)*PERIOD,100,102,99,100+(i%3)*.1,3,
                  last-(399-i)*PERIOD+PERIOD-1,300,1,1,1,'0']
                 for i in range(400)] for sym in SYMBOLS}

def fetch_at(last):
    def fetch(sym,first,end):return bars(last)[sym]
    return fetch

class ForwardTests(unittest.TestCase):
    def _do(self,root,last):
        with patch('cqwe.forward_dendrites_v34._load_checked',return_value=(None,'registrysha',
                {'tip_sha256':'tipsha','last_seen_ms':START-PERIOD},None,None)):
            return cycle('x','y',root,fetch=fetch_at(last),now_ms=last+PERIOD+10000)
    def test_end_to_end_and_repeated(self):
        with tempfile.TemporaryDirectory() as t:
            a=self._do(t,START);self.assertEqual('FRAME_RECORDED',a['status']);self.assertEqual(0,a['settled_events'])
            b=self._do(t,START);self.assertEqual('ALREADY_RECORDED',b['status'])
            c=self._do(t,START+PERIOD);self.assertEqual(6,c['settled_events'])
            self.assertEqual(1,c['observations_per_candidate'])
            records=sorted(Path(t).glob('frame_*.json'));self.assertEqual(2,len(records))
            last=json.loads(records[-1].read_text());self.assertEqual(6,len(last['candidates']))
            self.assertTrue(last['target_already_opened']);self.assertTrue(last['target_not_yet_closed'])
            self.assertTrue(all(x['model']['updates']==1 for x in last['candidates']))
            self.assertTrue(all(x['diagnosis']=='INSUFFICIENT_FORWARD_EVIDENCE' for x in last['candidates']))
    def test_missing_bar_rejected_no_retrofill(self):
        with tempfile.TemporaryDirectory() as t:
            self._do(t,START)
            with self.assertRaisesRegex(ValueError,'MISSED_BARS'):
                self._do(t,START+2*PERIOD)
    def test_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            self._do(t,START);f=next(Path(t).glob('frame_*.json'))
            obj=json.loads(f.read_text());obj['candidates'][0]['prediction']=.777
            f.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):self._do(t,START+PERIOD)
    def test_genotype_changed_with_rehashed_record_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            self._do(t,START);f=next(Path(t).glob('frame_*.json'))
            obj=json.loads(f.read_text());obj['candidates'][0]['genotype']['topology']='star'
            obj['sha256']=hash_record(obj);f.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError,'GENOTYPE_CHANGED'):self._do(t,START+PERIOD)
    def test_no_lookahead_when_future_close_appears(self):
        with tempfile.TemporaryDirectory() as t:
            with patch('cqwe.forward_dendrites_v34._load_checked',return_value=(None,'hash',
                   {'tip_sha256':'tip','last_seen_ms':START-PERIOD},None,None)):
                with self.assertRaisesRegex(ValueError,'HISTORY_GAP_OR_MISALIGNMENT|ALREADY_CLOSED'):
                    cycle('x','y',t,fetch=fetch_at(START),now_ms=START+2*PERIOD)
    def test_version_separation(self):
        self.assertNotEqual(VERSION,ACCOUNT_VERSION)
        self.assertEqual(10.,_starting_state()['cash'])
        self.assertEqual(6,len(GENOTYPES))
    def test_weight_bounds(self):
        model=restore(GENOTYPES[0],{'weights':[.5]*4,'trace':[0]*4,'memory':[0]*4,
                     'prev_error':0.,'updates':0})
        self.assertEqual([.5]*4,model.w)
        with self.assertRaisesRegex(ValueError,'UNBOUNDED_WEIGHTS'):
            restore(GENOTYPES[0],{'weights':[20.]*4,'trace':[0]*4,'memory':[0]*4,'prev_error':0.,'updates':0})

if __name__=='__main__':unittest.main()
