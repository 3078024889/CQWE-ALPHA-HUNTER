import copy, hashlib, unittest
from cqwe.dendrite_evolution_v55 import evaluate, GENOTYPES


def samples(n=50):
    rows=[]
    for i in range(n):
        rows.append({'id':f'event-{i}', 'time':1_000_000+i*60,
           'features':{k: float(((i+j)%7)-3)/3 for j,k in enumerate(GENOTYPES)},
           'target':(-1,0,1)[i%3], 'source_sha256':hashlib.sha256(str(i).encode()).hexdigest()})
    return rows

class DendriteV55(unittest.TestCase):
    def test_repeatable(self):
        self.assertEqual(evaluate(samples()),evaluate(samples()))
    def test_30_candidates(self):
        self.assertEqual(evaluate(samples())['candidate_count'],30)
    def test_immutable_no_promotion(self):
        x=evaluate(samples());self.assertFalse(x['promotion_allowed']);self.assertIsNone(x['realized_profit_usd']);self.assertEqual(x['executed_orders'],0)
    def test_separated_time(self):
        z=evaluate(samples())['split'];self.assertLess(z['train_last'],z['dev_first']);self.assertLess(z['dev_last'],z['holdout_first'])
    def test_duplicate_rejected(self):
        x=samples();x[-1]['id']=x[0]['id']
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):evaluate(x)
    def test_leakage_rejected(self):
        x=samples();x[2]['time']=x[1]['time']
        with self.assertRaisesRegex(ValueError,'NON_CAUSAL'):evaluate(x)
    def test_nonfinite_rejected(self):
        x=samples();x[0]['features']['macro']=float('nan')
        with self.assertRaisesRegex(ValueError,'INVALID_FEATURE'):evaluate(x)
    def test_missing_source_hash(self):
        x=samples();x[0]['source_sha256']=''
        with self.assertRaisesRegex(ValueError,'SOURCE_PROVENANCE'):evaluate(x)
    def test_small_sample_rejected(self):
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):evaluate(samples(10))
    def test_no_negative_cost(self):
        with self.assertRaisesRegex(ValueError,'CONFIG'):evaluate(samples(),cost_bps=-1)
    def test_source_is_not_mutated(self):
        x=samples();orig=copy.deepcopy(x);evaluate(x);self.assertEqual(x,orig)
    def test_cost_changes_result(self):
        a=evaluate(samples(),cost_bps=0);b=evaluate(samples(),cost_bps=18)
        self.assertNotEqual(a['holdout'],b['holdout'])

if __name__=='__main__':unittest.main()
