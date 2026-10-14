import copy, json, tempfile, unittest
from cqwe.l2_replay_v42 import LocalBook,SequenceGap,cost_crossing,emit,verify
S={'lastUpdateId':10,'bids':[['99','2'],['98','1']],'asks':[['101','2'],['102','1']]}
def ev(U,u,b=None,a=None):return {'e':'depthUpdate','s':'BNBUSDT','U':U,'u':u,'b':b or [],'a':a or []}
class TestV42(unittest.TestCase):
 def test_buffer_snapshot_bridge(self):
  b=LocalBook('BNBUSDT');b.queue(ev(10,12,[['99','4']]),123);b.synchronize(S,124)
  self.assertEqual(b.update_id,12);self.assertEqual(b.summary()['best_bid'],'99')
 def test_book_qty_and_remove(self):
  b=LocalBook('BNBUSDT');b.synchronize(S);b.apply(ev(11,11,[['99','0'],['97','4']]))
  self.assertEqual(b.summary()['best_bid'],'98')
 def test_gap_disables_prediction(self):
  b=LocalBook('BNBUSDT');b.synchronize(S)
  with self.assertRaises(SequenceGap):b.apply(ev(13,13))
  self.assertFalse(b.synced)
  with self.assertRaises(SequenceGap):b.summary()
 def test_ignore_stale(self):
  b=LocalBook('BNBUSDT');b.synchronize(S)
  self.assertEqual(b.apply(ev(9,10)),'STALE_IGNORED')
 def test_snapshot_behind_buffer(self):
  b=LocalBook('BNBUSDT');b.queue(ev(15,16))
  with self.assertRaises(SequenceGap):b.synchronize(S)
 def test_invalid_book_rejected(self):
  b=LocalBook('BNBUSDT');b.synchronize(S)
  with self.assertRaises(SequenceGap):b.apply(ev(11,11,[['110','2']]))
 def test_no_fake_fill(self):
  a={'synced':True,'best_bid':'99','best_ask':'101'}
  r=cost_crossing(a,a,'LONG',10,2)
  self.assertLess(r['hypothetical_net_bps'],0);self.assertFalse(r['execution_verified'])
 def test_tampering(self):
  with tempfile.TemporaryDirectory() as t:
   p=emit(t,'GAP',{'reason':'GAP'});self.assertEqual(verify(t)['counts']['GAP'],1)
   d=json.loads(p.read_text());d['data']['reason']='FAKE';p.write_text(json.dumps(d))
   with self.assertRaises(ValueError):verify(t)
 def test_invalid_events(self):
  b=LocalBook('BNBUSDT');b.synchronize(S)
  with self.assertRaises(ValueError):b.apply(ev(13,11))
 def test_no_unknown_coin(self):
  with self.assertRaises(ValueError):LocalBook('DOGEUSDT')
from cqwe.l2_replay_v42 import quote_forward
class TestV42QuoteSessions(unittest.TestCase):
 def test_dont_match_across_sessions(self):
  with tempfile.TemporaryDirectory() as folder:
   a={'symbol':'BNBUSDT','synced':True,'best_bid':'99','best_ask':'101','imbalance_l5':.5,'update_id':10,'received_ms':123}
   b=dict(a,update_id=12,received_ms=124)
   emit(folder,'START',a);emit(folder,'STOP',a);emit(folder,'START',b)
   self.assertEqual(quote_forward(folder)['evaluated_nonoverlap_pairs'],0)
