import json
import tempfile
import unittest
from pathlib import Path

from cqwe.copernican_experiment_v81_v85 import digest
from cqwe.four_market_core import Engine, config
from cqwe.four_market_runner import Processor, envelope, sources
from cqwe.four_market_supervisor import supervise
from cqwe.tidal_hunter import write_new


class SupervisorChecks(unittest.TestCase):
    def test_retry_inherits_only_last_accepted_cash_and_round(self):
        calls=[]
        def fake_run(root, **kwargs):
            calls.append(kwargs['rounds'])
            pointer = root/'LATEST.json'
            if pointer.exists():
                prior=json.loads(pointer.read_text())
                st=json.loads((root/prior['round_name']/'state.json').read_text())
                e=Engine(st['engine']['cfg'],{},previous=st['engine'])
                self.assertEqual(e.rounds,1)
                self.assertEqual(str(e.portfolio.cash),'9.7')
            else:
                e=Engine(config(),{})
            e.portfolio.cash=type(e.portfolio.cash)('9.7')
            e.end_round()
            p=Processor(e)
            folder=root/f'round_{e.rounds:06d}'
            folder.mkdir()
            st=envelope(e,p,None,None)
            write_new(folder/'state.json',st)
            ptr={'round_name':folder.name,'state_sha256':st['sha256']}
            ptr['sha256']=digest(ptr)
            write_new(pointer,ptr) if not pointer.exists() else pointer.write_text(json.dumps(ptr))
            if len(calls)==1:
                (root/'failed_round_evidence.txt').write_text('kept')
                raise ConnectionError('injected transport failure after accepted round')
        def replay(folder):
            self.assertTrue((folder/'state.json').exists())
            return {str(i):True for i in range(10)}
        with tempfile.TemporaryDirectory() as temp:
            result=supervise(temp,rounds=2,seconds=15,attempts=3,catalog=False,run_fn=fake_run,replay_fn=replay)
            self.assertEqual(result['status'],'TARGET_COMPLETED')
            self.assertEqual(calls,[2,1])
            self.assertTrue((Path(temp)/'attempt_0001/failed_round_evidence.txt').exists())
            self.assertFalse((Path(temp)/'supervisor.lock').exists())

    def test_repeated_failure_stops_at_budget_preserving_records(self):
        def fail(*args,**kwargs):
            raise ConnectionError('injected')
        with tempfile.TemporaryDirectory() as temp:
            result=supervise(temp,seconds=15,attempts=3,catalog=False,run_fn=fail)
            self.assertEqual(result['status'],'REPAIR_BUDGET_EXHAUSTED')
            self.assertEqual(len(result['attempts_this_call']),3)
            self.assertEqual(len(list(Path(temp).glob('attempt_*/supervisor_result.json'))),3)

    def test_context_change_rejected_and_lock_released(self):
        def fail(*args,**kwargs):
            raise ConnectionError('injected')
        with tempfile.TemporaryDirectory() as temp:
            supervise(temp,seconds=15,attempts=1,catalog=False,run_fn=fail)
            with self.assertRaisesRegex(ValueError,'CONTEXT_CHANGED'):
                supervise(temp,seconds=16,attempts=1,catalog=False,run_fn=fail)
            self.assertFalse((Path(temp)/'supervisor.lock').exists())

    def test_existing_writer_lock_is_never_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            lock=Path(temp)/'supervisor.lock'
            lock.write_text('another-process')
            with self.assertRaises(FileExistsError):
                supervise(temp,seconds=15)
            self.assertEqual(lock.read_text(),'another-process')


if __name__ == '__main__':
    unittest.main()
