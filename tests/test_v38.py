import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.paper_recovery_v38 import (_safe_restart,_load_manifests,run,segment_truth,
    VERSION,_manifest_hash)


def flat():
    return {'status':'NO_TRADES','paper_open_position':None,'paper_pending_intent':None,
       'paper_buys':0,'paper_adds':0,'paper_sells':0,'paper_completed_positions':0,
       'paper_equity_usd':10.,'paper_cash_usd':10.,'recorded_paper_fees_usd':0.,
       'frame_count':1,'last_open_ms':1800000000000}

class RecoveryTests(unittest.TestCase):
    def test_flat_no_trades_allowed(self):self.assertTrue(_safe_restart(flat()))
    def test_open_position_refused(self):
        a=flat();a['paper_open_position']='BNBUSDT'
        with self.assertRaisesRegex(ValueError,'UNRESOLVED'): _safe_restart(a)
    def test_pending_refused(self):
        a=flat();a['paper_pending_intent']={'action':'BUY'}
        with self.assertRaisesRegex(ValueError,'UNRESOLVED'): _safe_restart(a)
    def test_even_flat_traded_refused(self):
        a=flat();a['paper_buys']=1
        with self.assertRaisesRegex(ValueError,'NONZERO'): _safe_restart(a)
    def test_even_flat_with_pnl_refused(self):
        a=flat();a['paper_cash_usd']=9.9
        with self.assertRaisesRegex(ValueError,'NONZERO'): _safe_restart(a)
    def test_missing_legacy_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'NO_PREVIOUS_JOURNAL'):
                run(legacy=str(Path(d)/'not_exists'),root=str(Path(d)/'segments'))
    def test_creates_manifest_but_no_backfill(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)/'segments';legacy=Path(d)/'old';legacy.mkdir()
            with patch('cqwe.paper_recovery_v38._inspect',return_value=flat()):
                result=run(legacy=str(legacy),root=str(base),cycle_fn=lambda s,r,o:
                     {'status':'FRAME_RECORDED','equity_usd':10.})
            self.assertEqual('SEGMENT_STARTED',result['status'])
            manifest=json.loads((base/'segment_000000.json').read_text())
            self.assertEqual(manifest['sha256'],_manifest_hash(manifest))
            self.assertFalse(manifest['historical_fills_replayed'])
            self.assertEqual(10.,manifest['new_experiment_start_cash_usd'])
    def test_manifest_hash_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/'segment_000000';folder.mkdir()
            rec={'version':VERSION,'index':0,'directory':'segment_000000',
                 'previous_manifest_sha256':None,'no_orders':True}
            rec['sha256']='bad'
            (root/'segment_000000.json').write_text(json.dumps(rec))
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):_load_manifests(root)
    def test_orphan_directory_is_not_silently_reused(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'segment_000000').mkdir()
            with self.assertRaisesRegex(ValueError,'UNREGISTERED'):_load_manifests(Path(d))
    def test_lock_refuses_concurrent_writers(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'.writer.lock').mkdir()
            with self.assertRaisesRegex(ValueError,'PAPER_WRITER_BUSY'):
                run(root=str(root))

if __name__=='__main__':unittest.main()
