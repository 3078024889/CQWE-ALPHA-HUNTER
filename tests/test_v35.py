import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.public_data_v29 import PERIOD,SYMBOLS
from cqwe.evolution_supervisor_v35 import run,report,context_hash,review_candidate,audit

START=1800000000000//PERIOD*PERIOD

def fake_fetch(last):
    def get(sym,first,end):
        return [[last-(399-i)*PERIOD,100,102,99,100+(i%3)*.1,3,
                 last-(399-i)*PERIOD+PERIOD-1,300,1,1,1,'0'] for i in range(400)]
    return get

class RecoveryTests(unittest.TestCase):
    def invoke(self,root,at,**kwargs):
        with patch('cqwe.evolution_supervisor_v35._load_checked',return_value=(None,'reg',{'tip_sha256':'tip','last_seen_ms':START-PERIOD},None,None)),\
             patch('cqwe.forward_dendrites_v34._load_checked',return_value=(None,'reg',{'tip_sha256':'tip','last_seen_ms':START-PERIOD},None,None)):
            return run('s','r',root,fetch=fake_fetch(at),now_ms=at+PERIOD+10000,**kwargs)
    def test_continuity_and_one_gap_recovery(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(0,self.invoke(t,START)['epoch'])
            self.assertEqual('ALREADY_RECORDED',self.invoke(t,START)['status'])
            self.assertEqual(0,self.invoke(t,START+PERIOD)['epoch'])
            recovered=self.invoke(t,START+4*PERIOD)
            self.assertEqual(1,recovered['epoch'])
            self.assertEqual(2,recovered['recovered_gap_bars'])
            self.assertEqual(0,json.loads(next((Path(t)/'epoch_000000000001').glob('frame_*.json')).read_text())['candidates'][0]['observations'])
            self.assertEqual(2,len(list(Path(t).glob('epoch_*'))))
    def test_journal_tamper_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            self.invoke(t,START)
            file=next(Path(t).glob('epoch_*/frame_*.json'))
            obj=json.loads(file.read_text());obj['observed_close']=987
            file.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):
                self.invoke(t,START+PERIOD)
    def test_manifest_tamper_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            self.invoke(t,START)
            path=next(Path(t).glob('epoch_*/lineage.json'))
            value=json.loads(path.read_text());value['gap_bars_from_prior']=999
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'MANIFEST_TAMPERED'):
                self.invoke(t,START+PERIOD)
    def test_lock_prevents_parallel_cycle(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t,'.run.lock').write_text('another pid')
            with self.assertRaisesRegex(RuntimeError,'LOCK_EXISTS'):
                self.invoke(t,START)
            self.assertTrue(Path(t,'.run.lock').exists())
    def test_observation_floor_no_promotion(self):
        c={'observations':3,'squared_error_sum':.1,'zero_baseline_squared_error_sum':3}
        self.assertEqual('INSUFFICIENT_SEQUENTIAL_OBSERVATIONS',review_candidate(c)['status'])
        c={'observations':120,'squared_error_sum':2.,'zero_baseline_squared_error_sum':120}
        self.assertFalse(review_candidate(c)['eligible_for_auto_promotion'])
        self.assertIn('HOLDOUT',review_candidate(c)['status'])
    def test_report_sha_and_no_auto_orders(self):
        with tempfile.TemporaryDirectory() as t:
            dest=Path(t)/'audit.json'
            self.invoke(Path(t)/'evidence',START,report_path=dest)
            data=json.loads(dest.read_text())
            self.assertTrue(data['no_promotion']);self.assertTrue(data['no_orders'])
            self.assertEqual(6,len(data['candidates']))
    def test_no_hindsight_close(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'HISTORY_GAP_OR_MISALIGNMENT|ALREADY_CLOSED'):
                with patch('cqwe.evolution_supervisor_v35._load_checked',return_value=(None,'reg',{'tip_sha256':'tip','last_seen_ms':START-PERIOD},None,None)),\
                     patch('cqwe.forward_dendrites_v34._load_checked',return_value=(None,'reg',{'tip_sha256':'tip','last_seen_ms':START-PERIOD},None,None)):
                    run('s','r',t,fetch=fake_fetch(START),now_ms=START+2*PERIOD)

if __name__=='__main__':unittest.main()
