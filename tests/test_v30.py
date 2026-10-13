import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.auto_research_v30 import run_cycle, _verify_finished
from cqwe.public_data_v29 import _digest, PERIOD, SYMBOLS

START=1791870300000
CHECK={'last_seen_ms':START-PERIOD,'tip_sha256':'e'*64}

def candle(t):
    return [t,100.,102.,99.,101.,3.,t+PERIOD-1,301.,10,1.,100.,'0']

def make_collector(root, count):
    root=Path(root);root.mkdir(exist_ok=True,parents=True)
    import hashlib
    hashes={}
    for sym in SYMBOLS:
        p=root/(sym+'_5m.json')
        p.write_text(json.dumps([candle(START+i*PERIOD) for i in range(count)]),encoding='utf-8')
        hashes[sym]=hashlib.sha256(p.read_bytes()).hexdigest()
    m={'bars_per_symbol':count,'forward_ready':count>=240,'checkpoint_tip_sha256':CHECK['tip_sha256'],'source_sha256':hashes}
    m['manifest_sha256']=_digest(m)
    (root/'manifest_v29.json').write_text(json.dumps(m))
    return m

class AutomatedTests(unittest.TestCase):
    def run_with(self, d, count, evaluator=None):
        data=Path(d)/'data'; e=Path(d)/'evidence'
        def collector(*a):return make_collector(data,count)
        with patch('cqwe.auto_research_v30.verify_saved',return_value=CHECK):
            return run_cycle('unused',str(data),'unused',str(e),collector=collector,evaluator=evaluator or self.fake_eval)
    @staticmethod
    def fake_eval(reg,store,inputs,output):
        records=[json.loads(Path(x).read_text()) for x in inputs]
        assert all(len(r)==240 for r in records)
        report={'decision':'EXPLORATORY_ONLY_NO_PROMOTION','no_orders':True,'future_first_ms':START,
                'future_last_ms':START+239*PERIOD,'variants':[{'ledger_balanced':True}]}
        report['audit_sha256']=_digest(report)
        Path(output).write_text(json.dumps(report))
        return report
    def test_wait_without_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.run_with(d,37);self.assertEqual(r['status'],'WAIT_FOR_CLOSED_BARS')
            self.assertFalse((Path(d)/'evidence'/'receipt_v30.json').exists())
    def test_freeze_first240_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.run_with(d,251);self.assertEqual(r['status'],'FORWARD_VERIFIED')
            with patch('cqwe.auto_research_v30.verify_saved',return_value=CHECK):
                rr=run_cycle('unused',str(Path(d)/'data'),'unused',str(Path(d)/'evidence'),collector=lambda *_:make_collector(Path(d)/'data',260))
            self.assertEqual(rr['status'],'ALREADY_VERIFIED')
            self.assertEqual(rr['latest_collected_bars'],260)
    def test_report_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_with(d,240)
            (Path(d)/'evidence'/'forward_v28.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'IMMUTABLE_ARTIFACT_CHANGED'):self.run_with(d,260)
    def test_snapshot_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_with(d,240)
            (Path(d)/'evidence'/'snapshot'/'BTCUSDT_5m.json').write_text('[]')
            with self.assertRaisesRegex(ValueError,'IMMUTABLE_ARTIFACT_CHANGED'):self.run_with(d,260)
    def test_experiment_rejection_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            def bad(*args):raise ValueError('NO_ELIGIBLE_SIGNAL')
            with self.assertRaisesRegex(ValueError,'NO_ELIGIBLE_SIGNAL'):self.run_with(d,240,bad)
            self.assertFalse((Path(d)/'evidence'/'receipt_v30.json').exists())
            with self.assertRaisesRegex(RuntimeError,'INCOMPLETE_EVIDENCE_DIR'):self.run_with(d,240)
    def test_unbalanced_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            def bad(r,s,i,o):
                x=self.fake_eval(r,s,i,o);x['variants'][0]['ledger_balanced']=False;return x
            with self.assertRaisesRegex(ValueError,'UNBALANCED_LEDGER'):self.run_with(d,240,bad)
    def test_lock_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'evidence'/'.cycle_lock';p.mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError,'CYCLE_ALREADY_RUNNING'):self.run_with(d,240)
    def test_checkpoint_changed(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_with(d,240)
            with patch('cqwe.auto_research_v30.verify_saved',return_value={'last_seen_ms':CHECK['last_seen_ms'],'tip_sha256':'a'*64}):
                with self.assertRaisesRegex(ValueError,'CHECKPOINT_CHANGED'):
                    run_cycle('unused',str(Path(d)/'data'),'unused',str(Path(d)/'evidence'))

if __name__=='__main__':unittest.main()
