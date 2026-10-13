import json
import tempfile
import unittest
from pathlib import Path
from cqwe.evidence_stress_v23 import stress,normalize_costs,run
from cqwe.continuous_lab_v21 import replay
from tests.test_v21 import bars


def toy():
    rules=[]
    for lr,decay in ((.02,0.),(.06,0.),(.12,0.),(.06,.02)):
        rules.append({'rule':[lr,decay],'total_selected_events':75})
    ep=[]
    for ix in range(1,4):
        rs=[]
        for rule in rules:
            row={'rule':rule['rule'],'matured_selected_events':75,'mean_net_event_fraction':.0013,
                'reported_lcb':.00019,'status':'POSITIVE_RESEARCH_SIGNAL_NOT_TRADABLE'}
            rs.append(row)
        ep.append({'index':ix,'kind':'ADAPTIVE_PREQUENTIAL','rules':rs})
    return {'schema':22,'decision':'NO_AUTOMATIC_PROMOTION','episodes':ep,'rule_summary':rules,
            'verified_tip_sha256':'abc','verified_episodes':4,'audit_sha256':'def'}

class V23Test(unittest.TestCase):
    def test_cost_degrades(self):
        r=stress(toy(),(0,1,2,5))['rules'][0]['scenarios']
        self.assertEqual([x['positive_episodes'] for x in r],[3,3,0,0])
        self.assertAlmostEqual(r[2]['episodes'][0]['reported_lcb_after_extra_cost'],-.00001)
    def test_not_promotion(self):
        r=stress(toy())
        self.assertFalse(r['automatic_promotion']);self.assertFalse(r['trading_authorized'])
        self.assertIsNone(r['virtual_portfolio_pnl_usd'])
    def test_determinism(self):
        self.assertEqual(stress(toy()),stress(toy()))
    def test_no_events(self):
        a=toy()
        for e in a['episodes']:
            e['rules'][0].update(matured_selected_events=0,mean_net_event_fraction=None,reported_lcb=None)
        z=stress(a)['rules'][0]['scenarios'][0]
        self.assertEqual(z['no_event_episodes'],3)
    def test_insufficient(self):
        a=toy();a['episodes'][0]['rules'][0]['matured_selected_events']=8
        r=stress(a)['rules'][0]['scenarios'][0]
        self.assertEqual(r['low_sample_episodes'],1)
    def test_bad_costs(self):
        for cases in ([],[-1],[0,0],[3,2],[float('nan')],[1001]):
            with self.subTest(cases=cases),self.assertRaises(ValueError):normalize_costs(cases)
    def test_bad_audit(self):
        with self.assertRaises(ValueError):stress({'schema':22,'decision':'READY'})
    def test_missing_rule(self):
        a=toy();a['episodes'][0]['rules'].pop()
        with self.assertRaisesRegex(ValueError,'RULE_MISSING'):stress(a)
    def test_tamper_checks_v22(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);paths=[]
            for symbol,seed in [('BTCUSDT',0),('ETHUSDT',10)]:
                p=root/f'{symbol}_5m_30d.json';p.write_text(json.dumps(bars(1600,seed)))
                paths.append(str(p))
            store=root/'evidence';out=root/'v23.json'
            replay(paths,store)
            report=run(store,out)
            self.assertEqual(report['verified_episodes'],3)
            self.assertTrue(out.is_file())
            before=(store/'ledger.json').read_bytes()
            with self.assertRaisesRegex(ValueError,'OUTPUT_INSIDE'):
                run(store,store/'malicious.json')
            self.assertEqual((store/'ledger.json').read_bytes(),before)
            path=store/'report_0001.json';path.write_text(path.read_text()+' ')
            with self.assertRaisesRegex(ValueError,'DIGEST'):run(store,out)

if __name__=='__main__':unittest.main()
