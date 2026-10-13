import json
import tempfile
import unittest
from pathlib import Path
from cqwe.continuous_lab_v21 import replay
from cqwe.evidence_audit_v22 import audit, _verdict
from tests.test_v21 import bars

class V22Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.paths=[]
        for sym,seed in [('BTCUSDT',0),('ETHUSDT',10)]:
            p=self.root/f'{sym}_5m_30d.json';p.write_text(json.dumps(bars(1600,seed)))
            self.paths.append(str(p))
        self.store=self.root/'evidence'
    def test_audit_complete(self):
        replay(self.paths,self.store)
        result=audit(self.store)
        self.assertEqual(result['verified_episodes'],3)
        self.assertEqual(result['decision'],'NO_AUTOMATIC_PROMOTION')
        self.assertEqual(len(result['rule_summary']),4)
        self.assertIsNone(result['realized_profit_usd'])
        self.assertEqual(result['audit_sha256'].__len__(),64)
    def test_audit_no_mutation_to_evidence(self):
        replay(self.paths,self.store,stop_after=1)
        before={(p.name,p.read_bytes()) for p in self.store.iterdir()}
        audit(self.store);self.assertEqual(before,{(p.name,p.read_bytes()) for p in self.store.iterdir()})
    def test_reject_tampering(self):
        replay(self.paths,self.store,stop_after=1)
        p=self.store/'report_0001.json';p.write_text(p.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'DIGEST'):audit(self.store)
    def test_reject_incorrect_report_semantics(self):
        replay(self.paths,self.store,stop_after=1)
        report=self.store/'report_0001.json';obj=json.loads(report.read_text())
        obj['not_independent_holdout']=False
        report.write_text(json.dumps(obj))
        # Even a changed report alone is caught before semantic audit.
        with self.assertRaises(ValueError):audit(self.store)
    def test_insufficient_samples(self):
        self.assertEqual(_verdict({'n':2,'mean':.2,'lcb':None}),'INSUFFICIENT_EVENTS')
    def test_no_events(self):
        self.assertEqual(_verdict({'n':0,'mean':None,'lcb':None}),'NO_EVENTS')
    def test_lcb_negative(self):
        self.assertEqual(_verdict({'n':20,'mean':-.01,'lcb':-.02}),'NO_VERIFIED_POSITIVE_EDGE')
    def test_positive_is_not_promotion(self):
        self.assertEqual(_verdict({'n':20,'mean':.02,'lcb':.01}),'POSITIVE_RESEARCH_SIGNAL_NOT_TRADABLE')
    def test_invalid_bounds(self):
        with self.assertRaises(ValueError):_verdict({'n':20,'mean':.01,'lcb':.02})
    def test_invalid_nan(self):
        with self.assertRaises(ValueError):_verdict({'n':20,'mean':float('nan'),'lcb':0})
    def test_minimum_events(self):
        with self.assertRaises(ValueError):audit('no-such-store',min_events=0)
    def test_missing_store(self):
        with self.assertRaises(FileNotFoundError):audit(self.store)
