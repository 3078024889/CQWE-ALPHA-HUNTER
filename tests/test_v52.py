import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.copernican_lab_v33 import Dendrite,specs
from cqwe.memory_v52 import snapshot,restored,load,commit,symbol_lock
from cqwe.market_replay_v43 import hash_record
from cqwe.forward_lab_v47 import audit_file

class V52Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'memory'
        self.source=Path(self.temp.name)/'capture.jsonl'
        self.models=[Dendrite(s) for s in specs()]

    def make_evidence(self, prior=None):
        rows=[];last='0'*64;session='v52_test';seq=0
        def add(kind,ns,payload):
            nonlocal last,seq
            seq+=1
            r={'schema':'CQWE_V43_CAPTURE','sequence':seq,'prev_sha256':last,'session_id':session,
               'received_ns':ns,'kind':kind,'payload':payload}
            r['sha256']=hash_record(r);last=r['sha256'];rows.append(r)
            return r
        add('START',100,{'synced':True,'symbol':'BTCUSDT','initial_memory_checkpoint_sha256':prior})
        b1=add('BOOK',200,{'book_received_ns':190,'update_id':1})
        add('PRECOMMIT',230,{'decision_ns':220,'decision_book_sha256':b1['sha256'],
             'decision_book_received_ns':190,'exchange_update_id':1,
             'genotype_predictions':[0.0]*6,'actual_fills':0})
        b2=add('BOOK',60_000_000_330,{'book_received_ns':60_000_000_300,'update_id':2})
        add('SETTLED',60_000_000_350,{'decision_ns':220,'settled_received_ns':60_000_000_300,
             'settlement_book_sha256':b2['sha256'],'settlement_update_id':2,
             'actual_fills':0,'real_profit_usd':0})
        add('STOP',60_000_000_380,{'synced':True})
        self.source.write_text(''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows))
        return rows

    def updated(self):
        for m in self.models:
            pred,response=m.forward([.1,.1,.1,.1]);m.update(response,1,pred,[.1,.1,.1,.1])

    def test_clean_initial_memory(self):
        last,sha=load(self.root,'BTCUSDT');self.assertIsNone(last);self.assertIsNone(sha)
    def test_restore_all_dendrite_fields(self):
        self.updated();state=snapshot(self.models);new=restored(state)
        self.assertEqual(snapshot(new),state)
    def test_nan_rejected(self):
        self.models[0].w[0]=float('nan')
        with self.assertRaises(ValueError):snapshot(self.models)
    def test_invalid_symbol_rejected(self):
        with self.assertRaises(ValueError):load(self.root,'DOGEUSDT')
    def test_audit_sample_valid(self):
        self.make_evidence();self.assertEqual(audit_file(self.source)['settled'],1)
    def test_commit_then_load(self):
        self.make_evidence();self.updated()
        with symbol_lock(self.root,'BTCUSDT'):
            result=commit(self.root,'BTCUSDT',self.models,self.source,None,None)
            record,digest=load(self.root,'BTCUSDT')
        self.assertEqual(record['generation'],1);self.assertEqual(digest,result['checkpoint_sha256'])
    def test_repeated_source_refused(self):
        self.make_evidence();self.updated()
        with symbol_lock(self.root,'BTCUSDT'):
            info=commit(self.root,'BTCUSDT',self.models,self.source,None,None)
            old,sha=load(self.root,'BTCUSDT')
            self.updated()
            with self.assertRaises(ValueError):commit(self.root,'BTCUSDT',self.models,self.source,sha,old)
    def test_changed_source_refused(self):
        self.make_evidence();self.updated()
        with symbol_lock(self.root,'BTCUSDT'):
            commit(self.root,'BTCUSDT',self.models,self.source,None,None)
            self.source.write_text(self.source.read_text()+'\n')
            with self.assertRaises(ValueError):load(self.root,'BTCUSDT')
    def test_tampered_checkpoint_refused(self):
        self.make_evidence();self.updated()
        with symbol_lock(self.root,'BTCUSDT'):
            result=commit(self.root,'BTCUSDT',self.models,self.source,None,None)
            file=Path(result['checkpoint_file']);doc=json.loads(file.read_text());doc['state'][0]['w'][0]=.99
            file.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'CHECKPOINT_DIGEST_MISMATCH'):
                load(self.root,'BTCUSDT')
    def test_missing_frozen_lineage_refused(self):
        self.make_evidence('incorrect');self.updated()
        with symbol_lock(self.root,'BTCUSDT'):
            with self.assertRaises(ValueError):commit(self.root,'BTCUSDT',self.models,self.source,None,None)
    def test_unsettled_refused(self):
        self.make_evidence();self.models[0].updates=1
        with symbol_lock(self.root,'BTCUSDT'):
            with self.assertRaises(ValueError):commit(self.root,'BTCUSDT',self.models,self.source,None,None)
    def test_lock_contention_refused(self):
        with symbol_lock(self.root,'BTCUSDT'):
            with self.assertRaises(RuntimeError):
                with symbol_lock(self.root,'BTCUSDT'):pass

if __name__=='__main__':unittest.main()
