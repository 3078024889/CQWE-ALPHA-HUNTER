import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from cqwe.self_evolution_v20 import (RULES,SCHEMA,sha,step,stable_improvement,
    offline_evolution,continuation_update,run,resume)


def candles(start=0,n=850,seed=0):
    out=[]
    for k in range(n):
        i=start+k;t=i*300000
        op=100*(1+.0001*i+.004*math.sin(i/9+seed))
        cl=op*(1+.0015*math.sin(i*1.4+seed))
        volume=15+10*(1+math.sin(i/6))
        out.append([t,str(op),str(max(op,cl)*1.003),str(min(op,cl)*.997),str(cl),'1',t+299999,str(volume),1,'1',str(volume*.45),'0'])
    return out


class V20Tests(unittest.TestCase):
    def test_deterministic_initial(self):
        a,s=offline_evolution({'BTCUSDT':candles()})
        b,t=offline_evolution({'BTCUSDT':candles()})
        self.assertEqual(a,b)
        self.assertEqual(s,t)

    def test_sealed_future_no_selection_leak(self):
        bars=candles()
        _,original=offline_evolution({'BTCUSDT':bars})
        altered=copy.deepcopy(bars)
        for i in range(690,len(bars)):
            price=float(altered[i][4]);altered[i][4]=str(price*1.005)
            altered[i][2]=str(float(altered[i][2])*1.01)
        _,later=offline_evolution({'BTCUSDT':altered})
        self.assertEqual(original['selection_sha256'],later['selection_sha256'])
        self.assertEqual(original['selected'],later['selected'])

    def test_insufficient_is_not_alpha(self):
        x=stable_improvement([.1,.1],20)
        self.assertFalse(x['eligible']);self.assertEqual(x['reason'],'INSUFFICIENT_EVENTS')

    def test_negative_rejected(self):
        x=stable_improvement([-.01]*100)
        self.assertFalse(x['eligible'])

    def test_positive_control_only(self):
        x=stable_improvement([.02]*100)
        self.assertTrue(x['eligible'])

    def test_bounded_local_update(self):
        v=0
        for _ in range(1000):v=step(v,.1,.12,0)
        self.assertLessEqual(v,2)
        for _ in range(1000):v=step(v,-.1,.12,0)
        self.assertGreaterEqual(v,-2)

    def test_zero_promotion_is_cash_preserving(self):
        report,state=offline_evolution({'BTCUSDT':candles()},min_events=9999)
        self.assertFalse(report['promoted'])
        self.assertEqual(report['idle_policy_final_virtual_usd'],10)
        self.assertIsNone(report['virtual_portfolio_pnl_usd'])
        self.assertEqual(state['status'],'NO_PROMOTION')

    def test_multiple_markets(self):
        report,state=offline_evolution({'BTCUSDT':candles(seed=1),'ETHUSDT':candles(seed=2)})
        self.assertEqual(report['markets'],['BTCUSDT','ETHUSDT'])
        self.assertEqual(len(state['candidate_states']),len(RULES))

    def test_too_few_candles(self):
        with self.assertRaises(ValueError):offline_evolution({'BTCUSDT':candles(n=300)})

    def test_bad_cash(self):
        with self.assertRaises(ValueError):offline_evolution({'BTCUSDT':candles()},initial_cash=float('nan'))

    def test_continuation_hashed(self):
        _,s=offline_evolution({'BTCUSDT':candles()})
        nxt,entry=continuation_update(s,{'BTCUSDT':candles(start=850,n=260)})
        self.assertEqual(nxt['continuations'],1)
        self.assertEqual(entry['previous_hash'],s['selection_sha256'])
        self.assertEqual(entry['entry_sha256'],sha({k:v for k,v in entry.items() if k!='entry_sha256'}))

    def test_repeated_future_rejected(self):
        _,s=offline_evolution({'BTCUSDT':candles()})
        nxt,_=continuation_update(s,{'BTCUSDT':candles(start=850,n=260)})
        with self.assertRaisesRegex(ValueError,'OVERLAPPING_REPLAY'):
            continuation_update(nxt,{'BTCUSDT':candles(start=850,n=260)})

    def test_future_gap_rejected(self):
        _,s=offline_evolution({'BTCUSDT':candles()})
        with self.assertRaisesRegex(ValueError,'NONCONTIGUOUS'):
            continuation_update(s,{'BTCUSDT':candles(start=860,n=260)})

    def test_changed_universe_rejected(self):
        _,s=offline_evolution({'BTCUSDT':candles()})
        with self.assertRaisesRegex(ValueError,'MARKET_SET_CHANGED'):
            continuation_update(s,{'ETHUSDT':candles(start=850,n=260)})

    def test_end_to_end_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);p=d/'BTCUSDT_5m_3d.json';p.write_text(json.dumps(candles()))
            checkpoint=d/'state.json';report=d/'report.json'
            a=run([p],report,checkpoint)
            self.assertTrue(report.exists() and checkpoint.exists())
            with self.assertRaisesRegex(ValueError,'OVERLAPPING_REPLAY'):
                run([p],report,checkpoint)
            q=d/'BTCUSDT_5m_next.json';q.write_text(json.dumps(candles(start=850,n=260)))
            payload=resume([q],d/'next_report.json',checkpoint)
            self.assertEqual(payload['entry']['new_bars'],260)
            with self.assertRaisesRegex(ValueError,'OVERLAPPING_REPLAY'):
                resume([q],d/'next_report.json',checkpoint)

if __name__=='__main__':unittest.main()
