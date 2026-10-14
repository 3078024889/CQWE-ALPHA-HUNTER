import tempfile, unittest, json
from pathlib import Path
from unittest.mock import patch
from cqwe import profitability_lab_v39 as lab
from cqwe.public_data_v29 import _digest, PERIOD

class ProfitabilityTest(unittest.TestCase):
    def test_empty_stress(self):
        self.assertIsNone(lab._cost_stress([])['40']['mean_one_bar_proxy'])
    def test_cost_degrades(self):
        xs=[{'return':0.001},{'return':-0.001}]
        self.assertAlmostEqual(lab._cost_stress(xs)['40']['mean_one_bar_proxy'],-0.004)
    def test_causality_rejects_late_target(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);sig={'version':'CQWE_V31_PRECOMMITTED_NEXT_BAR_SIGNAL','no_orders':True,
                'observed_last_open_ms':0,'target_open_ms':PERIOD,'recorded_at_ms':PERIOD,
                'decision':{'intent':'PAPER_BUY_CANDIDATE_NOT_ORDER'}}
            sig['record_sha256']=_digest(sig)
            (root/'signal_0.json').write_text(json.dumps(sig))
            records,missing,late=lab._forward_signals(root)
            self.assertEqual((len(records),missing,late),(0,0,1))
    def test_causally_registered_signal_link(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);sig={'version':'CQWE_V31_PRECOMMITTED_NEXT_BAR_SIGNAL','no_orders':True,
                'observed_last_open_ms':0,'target_open_ms':PERIOD,'recorded_at_ms':PERIOD-100,
                'decision':{'intent':'PAPER_BUY_CANDIDATE_NOT_ORDER','symbol':'BTCUSDT'}}
            sig['record_sha256']=_digest(sig)
            (root/'signal_0.json').write_text(json.dumps(sig))
            out={'signal_sha256':sig['record_sha256'],'target_open_ms':PERIOD,
                'candidate_close_to_close_return':0.02}
            out['record_sha256']=_digest(out)
            (root/'outcome_0.json').write_text(json.dumps(out))
            records,_,_=lab._forward_signals(root)
            self.assertEqual(len(records),1)
    def test_corrupt_hash_fails(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'signal_0.json').write_text(json.dumps({'record_sha256':'bad'}))
            with self.assertRaises(ValueError):lab._forward_signals(d)
    def test_broken_outcome_link_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);sig={'version':'CQWE_V31_PRECOMMITTED_NEXT_BAR_SIGNAL','no_orders':True,
                'observed_last_open_ms':0,'target_open_ms':PERIOD,'recorded_at_ms':PERIOD-1,
                'decision':{'intent':'PAPER_BUY_CANDIDATE_NOT_ORDER','symbol':'BTCUSDT'}}
            sig['record_sha256']=_digest(sig)
            (root/'signal_0.json').write_text(json.dumps(sig))
            out={'signal_sha256':'wrong','target_open_ms':PERIOD,'candidate_close_to_close_return':0.1}
            out['record_sha256']=_digest(out)
            (root/'outcome_0.json').write_text(json.dumps(out))
            with self.assertRaisesRegex(ValueError,'OUTCOME_LINK_INVALID'):lab._forward_signals(root)
    def test_report_never_promotes(self):
        with patch.object(lab,'segment_truth',return_value={'segment_count':1,'segments':[{'status':'NO_TRADES'}],
            'latest_segment':{'last_open_ms':300000},'no_real_orders':True,'cumulative_profit_not_claimed':True}),\
            patch.object(lab,'_read_account',return_value={'status':'NO_TRADES'}),\
            patch.object(lab,'_forward_signals',return_value=([],0,0)):
            x=lab.audit(now_ms=2*PERIOD)
            self.assertFalse(x['profitability_proven']);self.assertEqual(len(x['gates']),10)
            self.assertFalse(next(g for g in x['gates'] if g['gate']=='G10_EXECUTABLE_OOS_EDGE')['passed'])
    def test_output_hash(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'report.json';lab.write(path,{'foo':5})
            content=json.loads(path.read_text())
            self.assertEqual(content['sha256'],_digest({'foo':5}))
if __name__=='__main__':unittest.main()
