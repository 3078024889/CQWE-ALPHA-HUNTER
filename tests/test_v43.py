import json, tempfile, unittest
from pathlib import Path
from cqwe.market_replay_v43 import hash_record, read_chain, evaluate, ten_stresses
from cqwe.l2_trade_capture_v43 import append_chain

class V43Tests(unittest.TestCase):
    def frames(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events.jsonl';prev='0'*64
            with p.open('x',encoding='utf8') as f:
                for n,(t,kind,payload) in enumerate([
                  (1000,'BOOK',{'synced':True,'bid':'100','ask':'100.1','bid_qty':'4','ask_qty':'4'}),
                  (200000000,'TRADE',{'price':'100','qty':'1','buyer_is_maker':True}),
                  (300000000,'BOOK',{'synced':True,'bid':'100.05','ask':'100.15','bid_qty':'4','ask_qty':'4'}),
                  (62000000000,'BOOK',{'synced':True,'bid':'101','ask':'101.1','bid_qty':'4','ask_qty':'4'})
                ],1):
                    rec={'schema':'CQWE_V43_CAPTURE','sequence':n,'prev_sha256':prev,'session_id':'test',
                        'received_ns':t,'kind':kind,'payload':payload}
                    rec['sha256']=hash_record(rec);prev=rec['sha256'];f.write(json.dumps(rec)+'\n')
            yield p
    def test_chain_and_evaluation(self):
        for p in self.frames():
            rows=read_chain(p)
            self.assertEqual(len(rows),4)
            x=evaluate(rows,250,10,2,5,60000)
            self.assertEqual(x['status'],'HYPOTHETICAL_QUOTE_CROSS')
            self.assertFalse(x['market_actual_fill_known'])
            self.assertFalse(x['passive_queue_depletion_condition_met'])
            self.assertEqual(ten_stresses(rows)['stress_count'],10)
    def test_hash_tamper(self):
        for p in self.frames():
            v=p.read_text().replace('100.1','100.9')
            p.write_text(v)
            with self.assertRaises(ValueError):read_chain(p)
    def test_sequence_tamper(self):
        for p in self.frames():
            arr=[json.loads(x) for x in p.read_text().splitlines()]
            arr[1]['sequence']=50
            p.write_text('\n'.join(json.dumps(x) for x in arr)+'\n')
            with self.assertRaises(ValueError):read_chain(p)
    def test_no_hindsight_entry(self):
        for p in self.frames():
            x=evaluate(read_chain(p),999999999,10,2)
            self.assertEqual(x['status'],'NO_POST_LATENCY_BOOK')
    def test_missing_future(self):
        for p in self.frames():
            x=evaluate(read_chain(p),250,10,2,horizon_ms=120000)
            self.assertEqual(x['status'],'NO_FUTURE_EXIT_BOOK')
    def test_bad_cost(self):
        with self.assertRaises(ValueError):evaluate([],fee_bps=-1)
    def test_latency_sensitivity(self):
        for p in self.frames():
            rows=read_chain(p)
            self.assertTrue(all(not r['executable_profit_proven'] for r in ten_stresses(rows)['scenario_results']))
    def test_stale_without_data(self):
        self.assertEqual(evaluate([])['status'],'NO_SYNCED_BOOK')
    def test_archive_no_real_orders(self):
        for p in self.frames():
            for r in read_chain(p):self.assertNotEqual(r['kind'],'ORDER')
    def test_default_path_d(self):
        from cqwe.l2_trade_capture_v43 import DATA_ROOT
        self.assertTrue(str(DATA_ROOT).upper().startswith('D:'))
