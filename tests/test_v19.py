import copy, unittest, json, tempfile
from pathlib import Path
from cqwe.local_learning_v19 import new_state,check_state,learn,digest,_update,run

def bars(n=420,drift=.0003):
    out=[];p=100.
    for i in range(n):
        op=p;p*=1+drift+(0.003 if i%34==0 else (-.002 if i%17==0 else 0))
        high=max(op,p)*1.001;low=min(op,p)*.999
        t=i*300000
        out.append([t,str(op),str(high),str(low),str(p),'1',t+299999,'100',1,'1','55','0'])
    return out
class EvolutionTests(unittest.TestCase):
    def test_repeat_determinism(self):
        d={'BTCUSDT':bars()};a=learn(d);b=learn(d)
        self.assertEqual(digest(a),digest(b))
    def test_no_future_label_leakage(self):
        d={'BTCUSDT':bars()};a=learn(d)
        e=copy.deepcopy(d);split=int(len(e['BTCUSDT'])*.7)
        for i in range(split+1,len(e['BTCUSDT'])):
            x=e['BTCUSDT'][i];cl=float(x[4]);op=float(x[1]);x[4]=str(cl*1.01);x[2]=str(max(cl*1.01,op)*1.002);x[3]=str(min(cl*1.01,op)*.998)
        b=learn(e)
        self.assertEqual(a['frozen_policy_sha256'],b['frozen_policy_sha256'])
        self.assertEqual(a['state'],b['state'])
    def test_blank_state(self):self.assertEqual(new_state()['generation'],0)
    def test_bad_state(self):
        s=new_state();s['weights']['x']=float('nan')
        with self.assertRaises(ValueError):check_state(s)
    def test_locality(self):
        s=new_state();_update(s,'A',.1,123)
        self.assertNotIn('B',s['weights']);self.assertEqual(s['generation'],1)
    def test_bounded_mutation(self):
        s=new_state()
        for i in range(128):_update(s,'A',.1,i)
        self.assertEqual(s['mutation_round'],2);self.assertTrue(-4<=s['weights']['A']<=4)
    def test_negative_learning(self):
        s=new_state();_update(s,'A',-.03,0)
        self.assertLess(s['weights']['A'],0)
    def test_prevent_overlap(self):
        d={'BTCUSDT':bars()};s=learn(d)['state']
        with self.assertRaisesRegex(ValueError,'OVERLAPPING'):learn(d,s)
    def test_holdout_never_mutates_state(self):
        a=learn({'BTCUSDT':bars()});self.assertEqual(a['state']['generation'],a['trained_events'])
    def test_cost_sensitivity(self):
        d={'BTCUSDT':bars()};a=learn(d,fee_bps=0,slip_bps=0);b=learn(d,fee_bps=10,slip_bps=5)
        self.assertGreaterEqual(sum(v['sum_net'] for v in a['state']['evidence'].values()),sum(v['sum_net'] for v in b['state']['evidence'].values()))
    def test_no_spurious_profit(self):
        a=learn({'BTCUSDT':bars(n=450,drift=-.0009)})
        self.assertNotIn('realized_profit_usd',a)
    def test_report_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'BTCUSDT_5m_2d.json';path.write_text(json.dumps(bars()),encoding='utf-8')
            cp=Path(d)/'state.json';r=run([path],Path(d)/'report.json',cp)
            self.assertTrue(cp.exists());self.assertIn('checkpoint_sha256',r)
            with self.assertRaises(ValueError):run([path],Path(d)/'report2.json',cp)
    def test_bad_config(self):
        with self.assertRaises(ValueError):learn({'BTCUSDT':bars()},fee_bps=-1)
    def test_journal_hash(self):
        s=new_state();_update(s,'x',.1,100)
        x=s['journal'][0];self.assertEqual(x['record_sha256'],digest({k:v for k,v in x.items() if k!='record_sha256'}))
