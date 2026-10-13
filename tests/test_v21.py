import json
import tempfile
import unittest
from pathlib import Path
from cqwe.continuous_lab_v21 import replay,verify_saved,read_markets,sha


def bars(n,seed=0):
    a=[]
    for i in range(n):
        t=1700000100000+i*300000
        p=100+seed+i*.002
        a.append([t,str(p),str(p+1),str(p-1),str(p), '1',t+299999,'1000',10,'1','450','0'])
    return a

class ContinuousLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.input=[]
        for symbol,seed in [('BTCUSDT',0),('ETHUSDT',10)]:
            path=self.root/f'{symbol}_5m_30d.json'
            path.write_text(json.dumps(bars(1600,seed)),encoding='utf-8')
            self.input.append(str(path))
        self.store=self.root/'store'
    def test_complete_replay(self):
        out=replay(self.input,self.store)
        self.assertEqual(out['completed_episodes'],out['planned_episodes'])
        self.assertGreater(out['completed_episodes'],0)
        self.assertEqual(out['verified']['verified_episodes'],out['completed_episodes']+1)
        self.assertIsNone(out['virtual_realized_profit_usd'])
    def test_resume_idempotent(self):
        part=replay(self.input,self.store,stop_after=1)
        self.assertEqual(part['newly_completed'],1)
        full=replay(self.input,self.store)
        self.assertGreater(full['newly_completed'],0)
        again=replay(self.input,self.store)
        self.assertEqual(again['newly_completed'],0)
    def test_checkpoint_tampering_rejected(self):
        replay(self.input,self.store,stop_after=1)
        p=self.store/'state_0000.json';p.write_text(p.read_text()+' ',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'DIGEST'):verify_saved(self.store)
    def test_report_tampering_rejected(self):
        replay(self.input,self.store,stop_after=1)
        p=self.store/'report_0001.json';p.write_text(p.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'REPORT_DIGEST'):verify_saved(self.store)
    def test_ledger_tampering_rejected(self):
        replay(self.input,self.store,stop_after=1)
        p=self.store/'ledger.json';ob=json.loads(p.read_text());ob['episodes'][1]['last_seen_ms']+=300000
        p.write_text(json.dumps(ob))
        with self.assertRaises(ValueError):verify_saved(self.store)
    def test_config_change_rejected(self):
        replay(self.input,self.store,stop_after=1)
        with self.assertRaisesRegex(ValueError,'DATA_OR_CONFIG_CHANGED'):replay(self.input,self.store,chunk=300)
    def test_source_change_rejected(self):
        replay(self.input,self.store,stop_after=1)
        p=Path(self.input[0]);p.write_text(p.read_text()+' ',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'DATA_OR_CONFIG_CHANGED'):replay(self.input,self.store)
    def test_nonempty_store_no_ledger(self):
        self.store.mkdir();(self.store/'junk').write_text('x')
        with self.assertRaisesRegex(ValueError,'NONEMPTY'):replay(self.input,self.store)
    def test_misalignment_rejected(self):
        p=Path(self.input[1]);z=json.loads(p.read_text());z.pop(1);z.append(bars(1601,10)[-1]);p.write_text(json.dumps(z))
        with self.assertRaises(ValueError):read_markets(self.input)
    def test_no_arbitrary_short_chunks(self):
        with self.assertRaisesRegex(ValueError,'BAD_REPLAY_SETTINGS'):replay(self.input,self.store,chunk=12)
    def test_checkpoint_removal_rejected(self):
        replay(self.input,self.store,stop_after=1)
        (self.store/'state_0001.json').unlink()
        with self.assertRaises(ValueError):verify_saved(self.store)
    def test_no_state_file_executable_code(self):
        from cqwe import continuous_lab_v21 as m
        import inspect
        s=inspect.getsource(m)
        self.assertNotIn('create_order(',s)
        self.assertNotIn('eval(',s)
        self.assertNotIn('exec(',s)
