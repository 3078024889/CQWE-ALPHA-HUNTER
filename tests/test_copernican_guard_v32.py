import json
import tempfile
import unittest
from pathlib import Path
from cqwe.copernican_guard_v32 import validated_report, guarded_cycle

SYMBOLS=('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT')
T=1800000000000

def report(stamp=T, side='HOLD'):
    ds=[]
    for sym in SYMBOLS:
        selected=(sym=='BTCUSDT' and side!='HOLD')
        ds.append(dict(symbol=sym,asof_ms=stamp,action=side if selected else 'HOLD',portfolio_selected=selected,
            event_veto=False,entry_reference=100.,stop_invalidation=99. if side=='LONG' and selected else 101. if side=='SHORT' and selected else None,
            dynamic_exit_reference=102. if side=='LONG' and selected else 98. if side=='SHORT' and selected else None))
    return dict(mode='PUBLIC_DATA_PAPER_ONLY',real_orders=0,decisions=ds,generated_utc='2026-10-16T00:00:00Z',regime=side,evidence_sha256='sha')

class GuardTests(unittest.TestCase):
    def test_valid_neutral(self):
        self.assertEqual(validated_report(report(), now_ms=T+300000), T)
    def test_reject_stale(self):
        with self.assertRaises(ValueError):validated_report(report(),now_ms=T+300000+900001)
    def test_reject_mixed_asof(self):
        x=report();x['decisions'][1]['asof_ms']=T-300000
        with self.assertRaises(ValueError):validated_report(x,now_ms=T+300000)
    def test_reject_order_mode(self):
        x=report();x['real_orders']=1
        with self.assertRaises(ValueError):validated_report(x,now_ms=T+300000)
    def test_reject_bad_stop(self):
        x=report(side='LONG');x['decisions'][0]['stop_invalidation']=110
        with self.assertRaises(ValueError):validated_report(x,now_ms=T+300000)
    def test_dedup_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=[str(Path(d)/x) for x in ('state.json','report.json','audit.jsonl')]
            x=report()
            first=guarded_cycle(a,b,c,run_once=lambda:x,now_ms=T+300000)
            self.assertEqual(first['status'],'PAPER_CYCLE')
            second=guarded_cycle(a,b,c,run_once=lambda:x,now_ms=T+300000)
            self.assertEqual(second['status'],'SKIP_DUPLICATE_BAR')
            self.assertEqual(len(json.loads(Path(a).read_text())['equity_history']),1)
    def test_single_direction(self):
        x=report(side='LONG')
        x['decisions'][1].update(action='SHORT',portfolio_selected=True,stop_invalidation=101.,dynamic_exit_reference=98.)
        with self.assertRaises(ValueError):validated_report(x,now_ms=T+300000)

if __name__=='__main__': unittest.main()
