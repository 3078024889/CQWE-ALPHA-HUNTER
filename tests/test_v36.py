import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.public_data_v29 import PERIOD
from cqwe.evidence_health_v36 import longitudinal,write_report
from cqwe.evolution_supervisor_v35 import run,context_hash
from tests.test_v35 import START,fake_fetch

class V36Tests(unittest.TestCase):
    def cycle(self,root,at):
        with patch('cqwe.evolution_supervisor_v35._load_checked',return_value=(None,'reg',{'tip_sha256':'tip','last_seen_ms':START-PERIOD},None,None)),\
             patch('cqwe.forward_dendrites_v34._load_checked',return_value=(None,'reg',{'tip_sha256':'tip','last_seen_ms':START-PERIOD},None,None)):
            return run('store','registry',root,fetch=fake_fetch(at),now_ms=at+PERIOD+10000)
    def ctx(self):
        with patch('cqwe.evolution_supervisor_v35._load_checked',return_value=(None,'reg',{'tip_sha256':'tip','last_seen_ms':START-PERIOD},None,None)):
            return context_hash('store','registry')
    def test_empty(self):
        with tempfile.TemporaryDirectory() as d:
            result=longitudinal(d,self.ctx(),now_ms=START)
            self.assertEqual('NO_LINEAGE',result['freshness'])
            self.assertEqual(0,result['epoch_count'])
            self.assertFalse(result['candidate_comparison'][0]['eligible_for_auto_promotion'])
    def test_continuity_and_gap_reports_no_fake_improvement(self):
        with tempfile.TemporaryDirectory() as d:
            self.cycle(d,START);self.cycle(d,START+PERIOD)
            self.cycle(d,START+4*PERIOD);self.cycle(d,START+5*PERIOD)
            result=longitudinal(d,self.ctx(),now_ms=START+6*PERIOD+1000)
            self.assertEqual(2,result['epoch_count'])
            self.assertEqual(2,result['observed_gaps'])
            self.assertEqual(2,result['candidate_comparison'][0]['settled_steps'])
            self.assertEqual('FRESH',result['freshness'])
            self.assertEqual('ARCHIVE_ONLY_NO_WEIGHT_INHERITANCE',result['cross_epoch_state_policy'])
            self.assertTrue(all(not x['eligible_for_auto_promotion'] for x in result['candidate_comparison']))
            path=Path(d)/'audit.json';write_report(path,result)
            self.assertTrue(path.exists())
    def test_stale_data_flag(self):
        with tempfile.TemporaryDirectory() as d:
            self.cycle(d,START)
            result=longitudinal(d,self.ctx(),now_ms=START+10*PERIOD)
            self.assertEqual('STALE_OR_TASK_DELAY',result['freshness'])
    def test_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            self.cycle(d,START);self.cycle(d,START+PERIOD)
            path=next(Path(d).glob('epoch_*/frame_*.json'))
            path.write_text('{"broken":true}',encoding='utf-8')
            with self.assertRaises(ValueError):longitudinal(d,self.ctx(),now_ms=START+2*PERIOD)

if __name__=='__main__':unittest.main()
