import copy,unittest,math,tempfile,json
from pathlib import Path
from cqwe.frozen_portfolio_v24 import paper
from cqwe.account_forensics_v25 import audit_one,analyze,run
from tests.test_v20 import candles

class ForensicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data={'BTCUSDT':candles(n=850),'ETHUSDT':candles(n=850,seed=1)}
        cls.gate={'portfolio':paper(data),'sources_sha256':{'BTC':'same'}}
        cls.shadow={'portfolio':paper(data,mode='shadow',min_notional=1),'sources_sha256':{'BTC':'same'}}
        cls.stress={'portfolio':paper(data,mode='shadow',min_notional=1,extra_cost_bps=10),'sources_sha256':{'BTC':'same'}}
    def test_audit_gate(self):self.assertTrue(audit_one(self.gate)['account_ledger_verified'])
    def test_audit_shadow(self):self.assertTrue(audit_one(self.shadow)['account_ledger_verified'])
    def test_comparison(self):
        x=analyze(self.gate,self.shadow,self.stress)
        self.assertEqual(x['decision'],'NO_LIVE_PROMOTION')
        self.assertFalse(x['independent_holdout_claim'])
    def test_no_fake_trade_claim(self):
        x=audit_one(self.shadow);self.assertEqual(x['entries'],self.shadow['portfolio']['entries'])
    def test_reject_mutated_cash(self):
        x=copy.deepcopy(self.shadow);x['portfolio']['cash_usd']+=1
        with self.assertRaisesRegex(ValueError,'FINAL_CASH'):audit_one(x)
    def test_reject_mutated_fee(self):
        x=copy.deepcopy(self.shadow)
        if x['portfolio']['trades']:
            x['portfolio']['trades'][0]['fee_and_extra_usd']+=.5
            with self.assertRaisesRegex(ValueError,'CASH_LEDGER'):audit_one(x)
    def test_reject_mutated_equity(self):
        x=copy.deepcopy(self.shadow);x['portfolio']['virtual_net_usd']+=1
        with self.assertRaisesRegex(ValueError,'END_EQUITY'):audit_one(x)
    def test_reject_incorrect_trade_count(self):
        x=copy.deepcopy(self.shadow);x['portfolio']['entries']+=1
        with self.assertRaisesRegex(ValueError,'COUNTS'):audit_one(x)
    def test_reject_nonfinite(self):
        x=copy.deepcopy(self.shadow);x['portfolio']['initial_virtual_usd']=float('nan')
        with self.assertRaises(ValueError):audit_one(x)
    def test_reject_wrong_mode(self):
        with self.assertRaisesRegex(ValueError,'WRONG_REPORT_MODES'):analyze(self.shadow,self.gate,self.stress)
    def test_reject_changed_sources(self):
        x=copy.deepcopy(self.stress);x['sources_sha256']={'BTC':'different'}
        with self.assertRaisesRegex(ValueError,'DATA_SOURCE'):analyze(self.gate,self.shadow,x)
    def test_reject_wrong_cost(self):
        x=copy.deepcopy(self.stress);x['portfolio']['cost_assumptions']['extra_roundtrip_bps']=0
        with self.assertRaisesRegex(ValueError,'STRESS_NOT_HIGHER'):analyze(self.gate,self.shadow,x)
    def test_serialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=[]
            for name,item in [('g',self.gate),('s',self.shadow),('t',self.stress)]:
                p=Path(tmp)/(name+'.json');p.write_text(json.dumps(item));paths.append(p)
            dest=Path(tmp)/'output.json';a=run(*paths,dest);self.assertEqual(a,json.loads(dest.read_text()))
