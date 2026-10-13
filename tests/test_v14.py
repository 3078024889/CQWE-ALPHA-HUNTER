import json
import tempfile
import unittest
from pathlib import Path
from cqwe.edge_lab_v14 import book_cost, complete_set_no_yes, strategy_evidence, audit_manifest


def candle(i):
    t=i*300000
    return [t,'100','101','99','100','1',t+299999,'100',1,'1','40','0']


class EdgeLabTests(unittest.TestCase):
    def test_depth_vwap(self):
        r=book_cost([{'price':'0.45','size':'2'},{'price':'0.48','size':'3'}],4)
        self.assertTrue(r['fillable'])
        self.assertAlmostEqual(r['cost'],1.86)

    def test_depth_reject(self):
        self.assertFalse(book_cost([{'price':0.5,'size':1}],2)['fillable'])

    def test_wrong_prices_reject(self):
        for p in (0,1,-.1,1.2,float('nan')):
            with self.assertRaises(ValueError):book_cost([{'price':p,'size':1}],1)

    def test_unverified_match_not_opportunity(self):
        r=complete_set_no_yes([{'price':.4,'size':100}],[{'price':.4,'size':100}],10,
                              market_age_ms=50)
        self.assertEqual(r['decision'],'REJECT_UNVERIFIED_MARKET_MATCH')

    def test_stale_never_positive_gate(self):
        r=complete_set_no_yes([{'price':.4,'size':100}],[{'price':.4,'size':100}],10,
                              market_age_ms=3000,verified_complementary=True)
        self.assertEqual(r['decision'],'REJECT_STALE_OR_UNKNOWN_AGE')

    def test_fees_remove_illusion(self):
        r=complete_set_no_yes([{'price':.49,'size':100}],[{'price':.49,'size':100}],10,
                              fee_usd=.25,market_age_ms=20,verified_complementary=True)
        self.assertEqual(r['decision'],'REJECT_COSTS')

    def test_insufficient_depth_reject(self):
        r=complete_set_no_yes([{'price':.45,'size':1}],[{'price':.45,'size':5}],2,
                              verified_complementary=True,market_age_ms=20)
        self.assertEqual(r['decision'],'REJECT_DEPTH')

    def test_valid_illustration_only(self):
        r=complete_set_no_yes([{'price':.4,'size':50}],[{'price':.4,'size':50}],10,
                              fee_usd=.1,slippage_buffer_usd=.1,market_age_ms=20,verified_complementary=True)
        self.assertEqual(r['decision'],'RESEARCH_CANDIDATE_ONLY')
        self.assertFalse(r['executable'])
        self.assertIsNone(r['expected_guaranteed_profit'])

    def test_cost_monotonic(self):
        r=strategy_evidence([.005]*100,costs_bps=(0,10,30))
        means=[e['net_event_mean_fraction'] for e in r['cases'].values()]
        self.assertEqual(means,sorted(means,reverse=True))
        self.assertEqual(r['cases']['30.0']['gate'],'REJECT_NONPOSITIVE_MEAN')

    def test_not_holdout_rejected(self):
        r=strategy_evidence([.01]*120,holdout=False)
        self.assertEqual(r['cases']['0.0']['gate'],'REJECT_NO_HOLDOUT')

    def test_tiny_sample_rejected(self):
        r=strategy_evidence([.5]*2,holdout=True)
        self.assertEqual(r['cases']['0.0']['gate'],'REJECT_INSUFFICIENT_EVENTS')

    def test_empty_data_no_fake_zero(self):
        r=strategy_evidence([],holdout=True)
        self.assertIsNone(r['cases']['0.0']['net_event_mean_fraction'])

    def test_negative_cost_rejected(self):
        with self.assertRaises(ValueError):strategy_evidence([.1],costs_bps=(-1,))

    def test_manifest_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'k.json';p.write_text(json.dumps([candle(i) for i in range(3)]),encoding='utf-8')
            r=audit_manifest([p]);self.assertEqual(r[0]['bars'],3)
            self.assertEqual(len(r[0]['sha256']),64)

    def test_manifest_gap_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_text(json.dumps([candle(0),candle(2)]),encoding='utf-8')
            with self.assertRaises(ValueError):audit_manifest([p])

    def test_does_not_import_broker(self):
        import inspect
        import cqwe.edge_lab_v14 as mod
        source=inspect.getsource(mod)
        self.assertNotIn('create_order(',source)
        self.assertNotIn('private_key',source)


if __name__=='__main__':unittest.main()
