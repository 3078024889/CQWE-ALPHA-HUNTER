"""V50 falsification of the websocket-receive-time vs append-time bug."""
import copy,json,tempfile,unittest
from pathlib import Path
from cqwe.forward_lab_v47 import audit_file
from cqwe.market_replay_v43 import hash_record

class CausalBookAnchor(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'capture.jsonl'
    def rows(self):
        decision=3_000_000_000
        future=64_000_000_000
        rows=[
          ('START',{'synced':True},1_000_000_000),
          ('BOOK',{'synced':True,'book_received_ns':2_000_000_000,'update_id':1},2_500_000_000),
          ('PRECOMMIT',{'decision_ns':decision,'genotype_predictions':[0]*6,'actual_fills':0},3_500_000_000),
          ('BOOK',{'synced':True,'book_received_ns':future,'update_id':2},future+50_000_000),
          ('SETTLED',{'decision_ns':decision,'settled_received_ns':future,'settlement_update_id':2,
                    'actual_fills':0,'real_profit_usd':0},future+70_000_000),
          ('STOP',{'synced':True},future+100_000_000)]
        return rows
    def write(self,rows,replace_hash=False):
        prev='0'*64
        with self.path.open('w',encoding='utf8') as f:
            for i,(kind,payload,received) in enumerate(rows):
                rec={'schema':'CQWE_V43_CAPTURE','sequence':i+1,'prev_sha256':prev,
                     'session_id':'test','received_ns':received,'kind':kind,'payload':copy.deepcopy(payload)}
                if kind=='SETTLED' and not replace_hash:
                    rec['payload']['settlement_book_sha256']=last_book_hash
                rec['sha256']=hash_record(rec)
                if kind=='BOOK':last_book_hash=rec['sha256']
                prev=rec['sha256']
                f.write(json.dumps(rec,sort_keys=True)+'\n')
        return self.path
    def test_valid_receive_time_precedes_append_time(self):
        self.assertEqual(audit_file(self.write(self.rows()))['settled'],1)
    def test_mismatched_settlement_receive_timestamp(self):
        rows=self.rows();rows[4][1]['settled_received_ns']+=1
        with self.assertRaisesRegex(ValueError,'SETTLEMENT_WITHOUT_FUTURE_BOOK'):audit_file(self.write(rows))
    def test_book_received_after_append_rejected(self):
        rows=self.rows();rows[3][1]['book_received_ns']=rows[3][2]+1
        with self.assertRaisesRegex(ValueError,'SETTLEMENT_WITHOUT_FUTURE_BOOK'):audit_file(self.write(rows))
    def test_book_update_id_forgery_rejected(self):
        rows=self.rows();rows[4][1]['settlement_update_id']=99
        with self.assertRaisesRegex(ValueError,'SETTLEMENT_BOOK_ANCHOR_MISMATCH'):audit_file(self.write(rows))
    def test_missing_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError,'SETTLEMENT_BOOK_ANCHOR_MISMATCH'):audit_file(self.write(self.rows(),replace_hash=True))
    def test_too_early_settlement_rejected(self):
        rows=self.rows();rows[3][1]['book_received_ns']=62_000_000_000;rows[4][1]['settled_received_ns']=62_000_000_000
        with self.assertRaisesRegex(ValueError,'NONCAUSAL_SETTLEMENT'):audit_file(self.write(rows))
    def test_future_book_before_precommit_rejected(self):
        rows=self.rows();rows[3][1]['book_received_ns']=2_000_000_000;rows[4][1]['settled_received_ns']=2_000_000_000
        with self.assertRaisesRegex(ValueError,'NONCAUSAL_SETTLEMENT'):audit_file(self.write(rows))
    def test_book_with_non_integer_timestamp_rejected(self):
        rows=self.rows();rows[3][1]['book_received_ns']='64000000000'
        with self.assertRaisesRegex(ValueError,'SETTLEMENT_WITHOUT_FUTURE_BOOK'):audit_file(self.write(rows))
    def test_truncated_session_rejected(self):
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_L2_SESSION'):audit_file(self.write(self.rows()[:-1]))
    def test_unsynced_stop_rejected(self):
        rows=self.rows();rows[-1][1]['synced']=False
        with self.assertRaisesRegex(ValueError,'SESSION_UNSYNCED'):audit_file(self.write(rows))
    def test_no_order_or_profit_claim(self):
        rows=self.rows();rows[4][1]['real_profit_usd']=9
        with self.assertRaisesRegex(ValueError,'INVALID_SETTLEMENT'):audit_file(self.write(rows))
    def test_hash_mismatch_cannot_be_accepted(self):
        p=self.write(self.rows());raw=p.read_text();p.write_text(raw.replace('"settlement_update_id": 2','"settlement_update_id": 3'))
        with self.assertRaises(ValueError):audit_file(p)

if __name__=='__main__':unittest.main()
