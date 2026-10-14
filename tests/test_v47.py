import tempfile,unittest,json
from pathlib import Path
from cqwe.forward_lab_v47 import audit_file,audit,collect
from cqwe.market_replay_v43 import hash_record
class TestV47(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)
 def fixture(self,late=False,tamper=False):
  path=self.path/'test.jsonl';prev='0'*64;seq=0
  items=[('START',{'synced':True},0),('BOOK',{'synced':True},2_000_000_000),
    ('PRECOMMIT',{'decision_ns':3_000_000_000,'genotype_predictions':[0]*6,'actual_fills':0},4_000_000_000),
    ('BOOK',{'synced':True},65_000_000_000),
    ('SETTLED',{'decision_ns':3_000_000_000,'settled_received_ns':65_000_000_000 if not late else 4_000_000_000,'actual_fills':0,'real_profit_usd':0},66_000_000_000),
    ('STOP',{'synced':True},67_000_000_000)]
  with path.open('w') as stream:
   for kind,payload,ns in items:
    seq+=1;r={'schema':'CQWE_V43_CAPTURE','sequence':seq,'prev_sha256':prev,'session_id':'x','received_ns':ns,'kind':kind,'payload':payload};r['sha256']=hash_record(r)
    if tamper and kind=='SETTLED':r['sha256']='x'*64
    prev=r['sha256'];stream.write(json.dumps(r)+'\n')
  return path
 def test_valid_precommitted_settled(self):self.assertEqual(audit_file(self.fixture())['settled'],1)
 def test_future_must_mature(self):
  with self.assertRaises(ValueError):audit_file(self.fixture(late=True))
 def test_hash_tamper(self):
  with self.assertRaises(ValueError):audit_file(self.fixture(tamper=True))
 def test_no_profit_claim(self):self.assertFalse(audit_file(self.fixture())['eligible_for_real_trading'])
 def test_empty_audit(self):self.assertEqual(audit(self.path)['symbols']['BTCUSDT']['settled_events'],0)
 def test_expired_outcome_never_becomes_profit(self):
  file=self.fixture();text=file.read_text();rows=[json.loads(x) for x in text.splitlines()]
  rows[4]['kind']='EXPIRED';rows[4]['payload']={'decision_ns':3_000_000_000,'reason':'NO_TIMELY_FUTURE_QUOTE','actual_fills':0,'real_profit_usd':0}
  prev='0'*64
  for row in rows:
   row['prev_sha256']=prev;row['sha256']=hash_record({k:v for k,v in row.items() if k!='sha256'});prev=row['sha256']
  file.write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
  r=audit_file(file);self.assertEqual(r['settled'],0);self.assertEqual(r['expired'],1)
 def test_cannot_collect_on_c(self):
  with self.assertRaises(ValueError):collect('C:/forbidden',seconds=180,free_bytes=10000000000)
if __name__=='__main__':unittest.main()
