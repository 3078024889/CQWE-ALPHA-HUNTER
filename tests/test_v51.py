"""V51 regression: legal BOOK -> SETTLED -> PRECOMMIT ordering and strict anchors."""
import copy,json,tempfile,unittest
from pathlib import Path
from cqwe.forward_lab_v47 import audit_file
from cqwe.market_replay_v43 import hash_record

class OrderingProof(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'forward.jsonl'
    def emit(self, mutate=None):
        t=1_000_000_000; b=2_000_000_000; dec=3_000_000_000
        future=64_000_000_000; dec2=65_000_000_000; future2=126_000_000_000
        payloads=[
          ('START',{'synced':True},t),
          ('BOOK',{'synced':True,'book_received_ns':b,'update_id':101},b+100),
          ('PRECOMMIT',{'decision_ns':dec,'genotype_predictions':[0.0]*6,'actual_fills':0,
                        'exchange_update_id':101,'decision_book_received_ns':b},dec+100),
          ('BOOK',{'synced':True,'book_received_ns':future,'update_id':102},future+100),
          ('SETTLED',{'decision_ns':dec,'settled_received_ns':future,'settlement_update_id':102,
                      'actual_fills':0,'real_profit_usd':0},future+200),
          ('PRECOMMIT',{'decision_ns':dec2,'genotype_predictions':[0.0]*6,'actual_fills':0,
                         'exchange_update_id':102,'decision_book_received_ns':future},dec2+100),
          ('BOOK',{'synced':True,'book_received_ns':future2,'update_id':103},future2+100),
          ('SETTLED',{'decision_ns':dec2,'settled_received_ns':future2,'settlement_update_id':103,
                     'actual_fills':0,'real_profit_usd':0},future2+200),
          ('STOP',{'synced':True},future2+300)]
        prev='0'*64;latest=None
        with self.path.open('w',encoding='utf8') as fp:
          for i,(kind,payload,rx) in enumerate(payloads):
            payload=copy.deepcopy(payload)
            if kind=='PRECOMMIT':payload['decision_book_sha256']=latest
            if kind=='SETTLED':payload['settlement_book_sha256']=latest
            if mutate:mutate(i,kind,payload)
            row={'schema':'CQWE_V43_CAPTURE','sequence':i+1,'prev_sha256':prev,'session_id':'test',
                 'received_ns':rx,'kind':kind,'payload':payload}
            row['sha256']=hash_record(row)
            if kind=='BOOK':latest=row['sha256']
            prev=row['sha256'];fp.write(json.dumps(row,sort_keys=True)+'\n')
        return self.path
    def test_settled_then_precommit_accepted_with_latest_book_anchor(self):
        audit=audit_file(self.emit())
        self.assertEqual(audit['precommits'],2)
        self.assertEqual(audit['settled'],2)
    def test_first_decision_wrong_anchor_rejected(self):
        def f(i,k,p):
            if i==2:p['decision_book_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'PRECOMMIT_BOOK_ANCHOR_MISMATCH'):
            audit_file(self.emit(f))
    def test_second_decision_wrong_anchor_rejected(self):
        def f(i,k,p):
            if i==5:p['decision_book_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'PRECOMMIT_BOOK_ANCHOR_MISMATCH'):
            audit_file(self.emit(f))
    def test_second_decision_wrong_receive_time_rejected(self):
        def f(i,k,p):
            if i==5:p['decision_book_received_ns']-=1
        with self.assertRaisesRegex(ValueError,'PRECOMMIT_BOOK_ANCHOR_MISMATCH'):
            audit_file(self.emit(f))
    def test_second_decision_wrong_update_id_rejected(self):
        def f(i,k,p):
            if i==5:p['exchange_update_id']=101
        with self.assertRaisesRegex(ValueError,'PRECOMMIT_BOOK_ANCHOR_MISMATCH'):
            audit_file(self.emit(f))
    def test_second_decision_missing_anchor_rejected(self):
        def f(i,k,p):
            if i==5:p.pop('decision_book_sha256')
        with self.assertRaisesRegex(ValueError,'PRECOMMIT_WITHOUT_PRIOR_BOOK'):
            audit_file(self.emit(f))
    def test_future_anchor_rejected(self):
        def f(i,k,p):
            if i==5:p['decision_book_received_ns']=126_000_000_000
        with self.assertRaisesRegex(ValueError,'PRECOMMIT_BOOK_ANCHOR_MISMATCH'):
            audit_file(self.emit(f))
    def test_no_future_settlement_rejected(self):
        def f(i,k,p):
            if i==7:p['settled_received_ns']=64_000_000_000
        with self.assertRaisesRegex(ValueError,'NONCAUSAL_SETTLEMENT'):
            audit_file(self.emit(f))
    def test_no_profit_claim(self):
        def f(i,k,p):
            if i==7:p['real_profit_usd']=1
        with self.assertRaisesRegex(ValueError,'INVALID_SETTLEMENT'):
            audit_file(self.emit(f))
    def test_invalid_session_hash_rejected(self):
        p=self.emit();p.write_text(p.read_text().replace('"update_id": 102','"update_id": 999'))
        with self.assertRaises(ValueError):audit_file(p)

if __name__=='__main__':unittest.main()
