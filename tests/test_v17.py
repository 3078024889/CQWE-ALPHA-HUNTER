import json,tempfile,unittest
from pathlib import Path
from cqwe.paper_loop_v17 import simulation,run

def candles(n=100,increment=.4):
    out=[]
    for i in range(n):
        o=100+i*increment;c=o+increment*.6
        out.append([i*300000,str(o),str(o+1),str(o-1),str(c),'1',i*300000+299999,'100',1,'1','40','0'])
    return out

class PaperLoopTests(unittest.TestCase):
    def test_closed_and_balanced(self):
        r=simulation(candles());self.assertTrue(r['ledger_balanced']);self.assertEqual(r['quantity_after'],0)
    def test_deterministic(self):
        a=simulation(candles());b=simulation(candles());self.assertEqual(a,b)
    def test_no_borrowing(self):
        r=simulation(candles(),allocation=1);self.assertGreaterEqual(min(t['cash_after'] for t in r['trades']),0)
    def test_costs_reduce_final(self):
        a=simulation(candles(),fee_bps=0,slip_bps=0)
        b=simulation(candles(),fee_bps=20,slip_bps=20)
        self.assertLess(b['final_virtual_usd'],a['final_virtual_usd'])
    def test_no_signal(self):
        r=simulation(candles(increment=0));self.assertEqual(r['entries'],0);self.assertEqual(r['final_virtual_usd'],10)
    def test_next_bar_entry(self):
        r=simulation(candles());self.assertGreater(r['entries'],0)
        for t in r['trades']:
            if t['fill_open_ms'] is not None:self.assertGreater(t['fill_open_ms'],t['decision_open_ms'])
    def test_budget_bounded(self):
        r=simulation(candles(),allocation=.2)
        for t in r['trades']:
            self.assertGreaterEqual(t['cash_after'],-1e-8)
    def test_reject_leverage(self):
        with self.assertRaises(ValueError):simulation(candles(),allocation=1.01)
    def test_reject_negative_fees(self):
        with self.assertRaises(ValueError):simulation(candles(),fee_bps=-1)
    def test_reject_nan(self):
        with self.assertRaises(ValueError):simulation(candles(),initial_cash=float('nan'))
    def test_reject_missing_bar(self):
        x=candles();del x[20]
        with self.assertRaises(ValueError):simulation(x)
    def test_run_report(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'k.json';p.write_text(json.dumps(candles()))
            q=run([str(p)],str(Path(d)/'report.json'))
            self.assertIsNone(q['realized_profit_usd']);self.assertEqual(len(q['markets']['k']['source_sha256']),64)
    def test_invalid_sample(self):
        with self.assertRaises(ValueError):simulation(candles(12))
    def test_early_final_liquidation(self):
        r=simulation(candles(28),hold_bars=40)
        self.assertEqual(r['quantity_after'],0)
        self.assertTrue(r['positions_closed_by_end_assumption'])

if __name__=='__main__':unittest.main()
