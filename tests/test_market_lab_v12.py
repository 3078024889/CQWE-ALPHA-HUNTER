import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.market_lab_v12 import dataset_summary, verdict, aggregate_costs, acquire, inspect, audit_dataset


def bars(n):
    return [[i*300000,'100','101','99','100','1',(i+1)*300000-1,'100',5,'1','40','0'] for i in range(n)]

class MarketV12Tests(unittest.TestCase):
    def test_valid_dataset(self):
        self.assertEqual(dataset_summary(bars(288))['days'],1)
    def test_rejects_gap(self):
        b=bars(2);b[1][0]+=300000
        with self.assertRaises(ValueError): dataset_summary(b)
    def test_rejects_future_claim_without_history(self):
        self.assertEqual(verdict({'days':7,'events':1000,'mean':10},5),'INSUFFICIENT_HISTORY')
    def test_negative_is_not_candidate(self):
        self.assertEqual(verdict({'days':30,'events':100,'mean':-.1},5),'NEGATIVE_AFTER_COSTS')
    def test_no_trades_is_not_profit(self):
        self.assertEqual(verdict({'days':30,'events':0,'mean':None},5),'INSUFFICIENT_EVENTS')
    def test_cost_aggregate(self):
        f=[{'cost_scenarios':{'c':{'breakout':{'events':2,'mean_net_event_pct':1}}}}]
        # patch strategy names to use a focused fixture
        with patch('cqwe.market_lab_v12.STRATEGIES',('breakout',)):
            r=aggregate_costs(f)
        self.assertEqual(r['c']['breakout']['mean_net_event_pct'],1)
    def test_acquire_cap(self):
        with self.assertRaises(ValueError): acquire(['BTCUSDT']*7,1)
    def test_acquire_writes_to_temporary_directory(self):
        with tempfile.TemporaryDirectory() as d,patch('cqwe.market_lab_v12.fetch',return_value=bars(288)):
            result=acquire(['BTCUSDT'],1,d)
            self.assertEqual(result['datasets'][0]['candles'],288)
            self.assertTrue((Path(d)/'manifest.json').exists())
    def test_audit_7_days_not_proven(self):
        outcome=audit_dataset(bars(2016))
        self.assertTrue(all(v['research_gate']=='INSUFFICIENT_HISTORY' for v in outcome['strategies'].values()))
    def test_no_data_claim_on_small_dataset(self):
        self.assertEqual(audit_dataset(bars(150))['gate'],'INSUFFICIENT_HISTORY')
    def test_inspect_reads_local_only(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'BTCUSDT.json';src.write_text(json.dumps(bars(150)),encoding='utf8')
            out=inspect([str(src)],str(Path(d)/'out.json'))
            self.assertEqual(out['dataset_count'],1)
    def test_invalid_constraints(self):
        with self.assertRaises(ValueError):inspect(['a'],min_events=0)

if __name__=='__main__':unittest.main()
