import json, tempfile, unittest
from pathlib import Path
from cqwe.four_asset_lab_v44 import FOUR, MIN_DISK_FREE, collect_four, inspect_capture, audit, ensure_d_root
from cqwe.market_replay_v43 import hash_record


def session(path,symbol,kind='valid'):
    prev='0'*64
    events=[('START',{'symbol':symbol,'synced':True}),
       ('BOOK',{'synced':True,'bid':'100','ask':'101','bid_qty':'2','ask_qty':'2'}),
       ('TRADE',{'price':'100','qty':'1','buyer_is_maker':True,'pre_sync':False}),
       ('STOP',{'synced':True})]
    if kind=='incomplete':events.pop()
    if kind=='wrong':events[0][1]['symbol']='WRONG'
    with open(path,'x',encoding='utf8') as f:
        for i,(tag,payload) in enumerate(events,1):
            rec=dict(schema='CQWE_V43_CAPTURE',sequence=i,prev_sha256=prev,session_id='s',received_ns=i,kind=tag,payload=payload)
            rec['sha256']=hash_record(rec);prev=rec['sha256'];f.write(json.dumps(rec)+'\n')

class FourAssetTests(unittest.TestCase):
    def test_symbol_pool_fixed(self):self.assertEqual(FOUR,('BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT'))
    def test_d_root_default(self):
        from cqwe.four_asset_lab_v44 import ROOT
        self.assertTrue(str(ROOT).startswith('D:'))
    def test_disk_fail_closed(self):
        with tempfile.TemporaryDirectory() as p:
            with self.assertRaises(RuntimeError):ensure_d_root(p,free_bytes=MIN_DISK_FREE-1)
    def test_strict_complete_capture(self):
        with tempfile.TemporaryDirectory() as p:
            f=Path(p)/'x.jsonl';session(f,'BTCUSDT')
            self.assertEqual(inspect_capture(f,'BTCUSDT')['post_sync_trades'],1)
    def test_reject_missing_stop(self):
        with tempfile.TemporaryDirectory() as p:
            f=Path(p)/'x.jsonl';session(f,'BTCUSDT','incomplete')
            with self.assertRaises(ValueError):inspect_capture(f,'BTCUSDT')
    def test_reject_wrong_symbol(self):
        with tempfile.TemporaryDirectory() as p:
            f=Path(p)/'x.jsonl';session(f,'BTCUSDT','wrong')
            with self.assertRaises(ValueError):inspect_capture(f,'BTCUSDT')
    def test_reject_tamper(self):
        with tempfile.TemporaryDirectory() as p:
            f=Path(p)/'x.jsonl';session(f,'BTCUSDT');f.write_text(f.read_text().replace('100','999'))
            with self.assertRaises(ValueError):inspect_capture(f,'BTCUSDT')
    def test_reject_invalid_capture_length(self):
        with tempfile.TemporaryDirectory() as p:
            with self.assertRaises(ValueError):collect_four(5,p,free_bytes=MIN_DISK_FREE)
    def test_four_parallel_isolation(self):
        with tempfile.TemporaryDirectory() as p:
            def collector(symbol,seconds,root):
                f=Path(root)/(symbol+'.jsonl')
                if symbol=='SOLUSDT':raise RuntimeError('DISCONNECTED')
                session(f,symbol)
                return {'file':str(f)}
            r=collect_four(75,p,collector=collector,free_bytes=MIN_DISK_FREE)
            self.assertFalse(r['all_four_valid']);self.assertEqual(len(r['markets']),3)
            self.assertIn('SOLUSDT',r['failures']);self.assertFalse(r['winner_selected'])
    def test_four_complete(self):
        with tempfile.TemporaryDirectory() as p:
            def collector(symbol,seconds,root):
                f=Path(root)/(symbol+'.jsonl');session(f,symbol);return {'file':str(f)}
            r=collect_four(75,p,collector=collector,free_bytes=MIN_DISK_FREE)
            self.assertTrue(r['all_four_valid']);self.assertEqual(len(r['markets']),4)
            a=audit(p);self.assertTrue(all(x['valid_sessions']==1 for x in a['symbols'].values()))
            self.assertEqual(a['real_profit_usd'],0)
