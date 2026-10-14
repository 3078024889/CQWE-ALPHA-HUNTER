"""Historical lineage red-team cases for V53."""
import json, tempfile, unittest, hashlib
from pathlib import Path
from cqwe.copernican_lab_v33 import Dendrite, specs
from cqwe.memory_v52 import load, commit, symbol_lock, _bytes
from cqwe.market_replay_v43 import hash_record

class Lineage53(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'memory'; self.models=[Dendrite(s) for s in specs()]
    def evidence(self, suffix, previous):
        path=Path(self.tmp.name)/f'{suffix}.jsonl'; seq=0;prev='0'*64;rows=[]
        def rec(kind,ns,payload):
            nonlocal seq,prev
            seq+=1
            r={'schema':'CQWE_V43_CAPTURE','sequence':seq,'prev_sha256':prev,'session_id':suffix,'received_ns':ns,'kind':kind,'payload':payload}
            r['sha256']=hash_record(r);prev=r['sha256'];rows.append(r);return r
        rec('START',100,{'synced':True,'symbol':'BTCUSDT','initial_memory_checkpoint_sha256':previous})
        b=rec('BOOK',200,{'book_received_ns':190,'update_id':1})
        rec('PRECOMMIT',230,{'decision_ns':220,'decision_book_sha256':b['sha256'],'decision_book_received_ns':190,'exchange_update_id':1,'genotype_predictions':[0.]*6,'actual_fills':0})
        future=rec('BOOK',60_000_000_330,{'book_received_ns':60_000_000_300,'update_id':2})
        rec('SETTLED',60_000_000_350,{'decision_ns':220,'settled_received_ns':60_000_000_300,'settlement_book_sha256':future['sha256'],'settlement_update_id':2,'actual_fills':0,'real_profit_usd':0})
        rec('STOP',60_000_000_380,{'synced':True})
        path.write_text(''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows))
        return path
    def update(self):
        for m in self.models:
            p,r=m.forward([.1]*4);m.update(r,1,p,[.1]*4)
    def two(self):
        with symbol_lock(self.root,'BTCUSDT'):
            a=self.evidence('a',None);self.update();commit(self.root,'BTCUSDT',self.models,a,None,None)
            prev,sha=load(self.root,'BTCUSDT')
            b=self.evidence('b',sha);self.update();commit(self.root,'BTCUSDT',self.models,b,sha,prev)
        return a,b
    def test_two_generations_load(self):
        self.two();last,_=load(self.root,'BTCUSDT');self.assertEqual(last['generation'],2)
    def test_first_source_changed_refused(self):
        a,_=self.two();a.write_text(a.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'HISTORICAL_SOURCE_EVIDENCE'):
            load(self.root,'BTCUSDT')
    def test_first_source_missing_refused(self):
        a,_=self.two();a.unlink()
        with self.assertRaisesRegex(ValueError,'HISTORICAL_SOURCE_EVIDENCE'):
            load(self.root,'BTCUSDT')
    def test_first_checkpoint_count_forged_refused_even_with_digest(self):
        self.two();f=self.root/'BTCUSDT'/'checkpoint_00000001.json';doc=json.loads(f.read_bytes());doc['state'][0]['updates']+=1
        raw=_bytes(doc);f.write_bytes(raw);f.with_suffix('.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
        with self.assertRaisesRegex(ValueError,'HISTORICAL_MEMORY_UPDATE_COUNT'):
            load(self.root,'BTCUSDT')
    def test_second_capture_wrong_start_lineage_refused(self):
        self.two();p=self.root/'BTCUSDT'/'checkpoint_00000002.json';doc=json.loads(p.read_bytes()); source=Path(doc['source_file'])
        rows=[json.loads(x) for x in source.read_text().splitlines()]
        rows[0]['payload']['initial_memory_checkpoint_sha256']='0'*64
        prev='0'*64
        for row in rows:
            row['prev_sha256']=prev;row['sha256']=hash_record(row);prev=row['sha256']
        source.write_text(''.join(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n' for row in rows))
        doc['source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        raw=_bytes(doc);p.write_bytes(raw);p.with_suffix('.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
        with self.assertRaisesRegex(ValueError,'HISTORICAL_SESSION_LINEAGE|CAPTURE_HASH_MISMATCH'):
            load(self.root,'BTCUSDT')

if __name__=='__main__':unittest.main()
