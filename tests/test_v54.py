"""V54 adversarial forward competition validation."""
import json, tempfile, unittest
from pathlib import Path
from cqwe.forward_competition_v54 import events_from_capture, evaluate
from cqwe.market_replay_v43 import hash_record

class Competition54(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def evidence(self, label=1, n=6, baseline=None):
        file=self.root/'capture.jsonl';rows=[];prev='0'*64
        def add(kind,ts,payload):
            nonlocal prev
            r={'schema':'CQWE_V43_CAPTURE','sequence':len(rows)+1,'prev_sha256':prev,
                'session_id':'adversarial','received_ns':ts,'kind':kind,'payload':payload}
            r['sha256']=hash_record(r);prev=r['sha256'];rows.append(r);return r
        add('START',100,{'synced':True,'symbol':'BTCUSDT'})
        b=add('BOOK',200,{'book_received_ns':190,'update_id':1})
        add('PRECOMMIT',230,{'decision_ns':220,'decision_book_sha256':b['sha256'],
            'decision_book_received_ns':190,'exchange_update_id':1,'genotype_predictions':[.1]*n,
            'baseline_directions':baseline or {'cash':0,'cross_long':1,'book_imbalance':0,'trend_agreement':1},
            'actual_fills':0})
        f=add('BOOK',60_000_000_400,{'book_received_ns':60_000_000_350,'update_id':2})
        add('SETTLED',60_000_000_500,{'decision_ns':220,'settled_received_ns':60_000_000_350,
          'settlement_book_sha256':f['sha256'],'settlement_update_id':2,
          'move_bps':1.,'long_cross_proxy_bps':-22.,'label':label,'real_profit_usd':0,'actual_fills':0})
        add('STOP',60_000_000_600,{'synced':True})
        file.write_text(''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows))
        return file
    def test_valid_evidence(self):
        x=events_from_capture(self.evidence());self.assertEqual(len(x),1)
        self.assertEqual(x[0]['predictions'],[.1]*6)
    def test_wrong_prediction_count(self):
        with self.assertRaisesRegex(ValueError,'INVALID_PRECOMMIT'):
            events_from_capture(self.evidence(n=5))
    def test_invalid_prediction_direction(self):
        with self.assertRaisesRegex(ValueError,'INVALID_PRECOMMIT'):
            events_from_capture(self.evidence(n=7))
    def test_invalid_baseline(self):
        with self.assertRaisesRegex(ValueError,'INVALID_BASELINE_DIRECTIONS'):
            events_from_capture(self.evidence(baseline={'cash':1}))
    def test_label_zero(self):
        self.assertEqual(events_from_capture(self.evidence(label=0))[0]['label'],0)
    def test_missing_source_fails(self):
        with self.assertRaisesRegex(ValueError,'MISSING_OR_OVERSIZE'):
            events_from_capture(self.root/'missing.jsonl')
    def test_cannot_approve_too_few_events(self):
        with self.assertRaises(ValueError):evaluate(self.root,self.root/'out',minimum_events=1)
    def test_repeated_report_deterministic(self):
        # Missing checkpoints must produce no winners or faux PnL; repeated runs identical.
        a=evaluate(self.root,self.root/'out');b=evaluate(self.root,self.root/'out')
        self.assertEqual(a['sha256'],b['sha256']);self.assertFalse(a['promotion_allowed'])
        self.assertEqual(a['real_profit_usd'],0)
        self.assertTrue(all(x['winner'] is None for x in a['symbols'].values()))
    def test_bad_settlement_is_rejected(self):
        file=self.evidence();rows=[json.loads(s) for s in file.read_text().splitlines()]
        rows[-2]['payload']['settled_received_ns']=1
        prev='0'*64
        for r in rows:
            r['prev_sha256']=prev;r['sha256']=hash_record(r);prev=r['sha256']
        file.write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in rows))
        with self.assertRaises(ValueError):events_from_capture(file)
    def test_no_independent_profit_claim(self):
        r=evaluate(self.root,self.root/'other');self.assertFalse(r['profitability_proven'])
        self.assertEqual(r['actual_fills'],0)

if __name__=='__main__':unittest.main()
