import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cqwe.copernican_experiment_v81_v85 import digest
from cqwe.learning_cycle import checked, read_history, run, source_hashes, summarize


def checkpoint(n=0):
    c = {'settled':n,'models':{},'stats':{'dendritic':{'n':n,'mean':-1.,'m2':0.}}}
    c['sha256'] = digest(c)
    return c


def fake_capture(symbol,seconds,root,seed):
    c = checkpoint((seed['settled'] if seed else 0)+2)
    return Path(root)/str(c['settled']),{'checkpoint':c,'sha256':digest(c)}


def fake_audit(folder,report,seed,registered,last_end,sources):
    return {str(i):True for i in range(10)},max(registered,last_end)+100,2


class LearningCycleChecks(unittest.TestCase):
    def test_01_five_rounds_inherit_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            a = run(d,rounds=5,capture_fn=fake_capture,audit_fn=fake_audit)
            self.assertEqual(a['new_matured_forecasts'],10)
            b = run(d,rounds=1,capture_fn=fake_capture,audit_fn=fake_audit)
            self.assertEqual(b['recorded_rounds'],6)
            r = json.loads((Path(d)/'round_000006.json').read_text())
            self.assertEqual(r['checkpoint']['settled'],12)

    def test_02_no_seed_reset_after_registration(self):
        with tempfile.TemporaryDirectory() as d:
            run(d,rounds=1,capture_fn=fake_capture,audit_fn=fake_audit)
            with self.assertRaises(ValueError):
                run(d,rounds=1,seed_checkpoint=checkpoint(),capture_fn=fake_capture,audit_fn=fake_audit)

    def test_03_changed_round_is_not_silent_memory(self):
        with tempfile.TemporaryDirectory() as d:
            run(d,rounds=1,capture_fn=fake_capture,audit_fn=fake_audit)
            p = Path(d)/'round_000001.json'
            r = json.loads(p.read_text())
            r['checkpoint']['settled'] = 999
            p.write_text(json.dumps(r))
            with self.assertRaises(ValueError):
                run(d,rounds=1,capture_fn=fake_capture,audit_fn=fake_audit)

    def test_04_failed_audit_rolls_back_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            seed = checkpoint(10)
            def fail(*args):
                checks,end,n = fake_audit(*args)
                checks['0'] = False
                return checks,end,n
            r = run(d,rounds=5,seed_checkpoint=seed,capture_fn=fake_capture,audit_fn=fail)
            self.assertEqual(r['recorded_rounds'],1)
            self.assertEqual(r['accepted_rounds'],0)
            record = json.loads((Path(d)/'round_000001.json').read_text())
            self.assertEqual(record['checkpoint'],seed)

    def test_05_replay_exception_preserves_error_and_stops(self):
        with tempfile.TemporaryDirectory() as d:
            def fail(*args):
                raise ValueError('CORRUPTED_RAW_DATA')
            r = run(d,rounds=2,capture_fn=fake_capture,audit_fn=fail)
            self.assertEqual(r['accepted_rounds'],0)
            row = json.loads((Path(d)/'round_000001.json').read_text())
            self.assertIn('CORRUPTED_RAW_DATA',row['error'])

    def test_06_resource_and_concurrency_limits(self):
        with tempfile.TemporaryDirectory() as d:
            for rounds in (0,31,True):
                with self.assertRaises(ValueError):
                    run(d,rounds=rounds)
            (Path(d)/'supervisor.lock').write_text('another writer')
            with self.assertRaises(FileExistsError):
                run(d,capture_fn=fake_capture,audit_fn=fake_audit)

    def test_07_source_change_requires_new_experiment(self):
        with tempfile.TemporaryDirectory() as d:
            run(d,rounds=1,capture_fn=fake_capture,audit_fn=fake_audit)
            with patch('cqwe.learning_cycle.source_hashes',return_value={'changed':'code'}):
                with self.assertRaisesRegex(ValueError,'CONTEXT_CHANGED'):
                    run(d,rounds=1,capture_fn=fake_capture,audit_fn=fake_audit)

    def test_08_transport_failure_releases_lock_retains_prior_round(self):
        with tempfile.TemporaryDirectory() as d:
            run(d,rounds=1,capture_fn=fake_capture,audit_fn=fake_audit)
            def broken(*args):
                raise RuntimeError('NETWORK_DOWN')
            with self.assertRaises(RuntimeError):
                run(d,rounds=1,capture_fn=broken,audit_fn=fake_audit)
            self.assertFalse((Path(d)/'supervisor.lock').exists())
            b = run(d,rounds=1,capture_fn=fake_capture,audit_fn=fake_audit)
            self.assertEqual(b['recorded_rounds'],2)

    def test_09_sample_count_does_not_establish_profitability(self):
        with tempfile.TemporaryDirectory() as d:
            r = run(d,rounds=5,capture_fn=fake_capture,audit_fn=fake_audit)
            self.assertIn('at_least_300_new_matured_forecasts',r['missing_research_evidence'])
            self.assertIn('positive_cost_adjusted_candidate_evidence',r['missing_research_evidence'])
            self.assertFalse(r['profitability_proven'])

    def test_10_session_and_round_context_cannot_be_reordered(self):
        with tempfile.TemporaryDirectory() as d:
            run(d,rounds=2,capture_fn=fake_capture,audit_fn=fake_audit)
            p = Path(d)/'round_000002.json'
            row = json.loads(p.read_text())
            row['previous'] = '0'*64
            row['sha256'] = digest({k:v for k,v in row.items() if k!='sha256'})
            p.write_text(json.dumps(row))
            anchor = json.loads((Path(d)/'anchor.json').read_text())
            with self.assertRaises(ValueError):
                read_history(Path(d),anchor)


if __name__=='__main__':
    unittest.main()
