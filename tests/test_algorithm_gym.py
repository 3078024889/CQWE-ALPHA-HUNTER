import copy
import unittest

from cqwe.algorithm_gym import evaluate


def samples(n=40):
    return [{'id':str(i),'features':[1.,(i%5-2)/2,(i%3-1)/2,.1],
             'label':1 if i%2 else -1,'decision_ns':i*10,'outcome_ns':i*10+5,
             'long_proxy_bps':2. if i%2 else -22.,
             'short_proxy_bps':-22. if i%2 else 2.} for i in range(n)]


class AlgorithmGymChecks(unittest.TestCase):
    def test_01_six_real_variants_are_trained(self):
        r = evaluate(samples())
        self.assertEqual(r['candidate_count'],6)
        self.assertEqual(len({str(c['spec']) for c in r['candidates']}),6)
        self.assertTrue(all(c['updates']==24 for c in r['candidates']))
        self.assertNotEqual(r['candidates'][0]['initial_weights'],r['candidates'][0]['trained_weights'])

    def test_02_holdout_cannot_select_the_winner(self):
        rows = samples()
        a = evaluate(rows)
        for r in rows[32:]:
            r['label'] *= -1
            r['features'] = [-x for x in r['features']]
        b = evaluate(rows)
        self.assertEqual(a['selected_on_validation'],b['selected_on_validation'])
        self.assertEqual(a['candidates'],b['candidates'])

    def test_03_validation_does_not_train_parameters(self):
        rows = samples()
        a = evaluate(rows)
        for r in rows[24:32]:
            r['label'] *= -1
        b = evaluate(rows)
        self.assertEqual([c['trained_weights'] for c in a['candidates']],
                         [c['trained_weights'] for c in b['candidates']])

    def test_04_repeated_sample_rejected(self):
        rows = samples()
        rows[-1]['id'] = rows[0]['id']
        with self.assertRaises(ValueError):
            evaluate(rows)

    def test_05_overlapping_labels_rejected(self):
        rows = samples()
        rows[1]['decision_ns'] = 1
        with self.assertRaises(ValueError):
            evaluate(rows)

    def test_06_invalid_features_and_labels(self):
        for value in (True,0,2):
            rows = samples()
            rows[0]['label'] = value
            with self.assertRaises(ValueError):
                evaluate(rows)
        rows = samples()
        rows[0]['features'][0] = float('nan')
        with self.assertRaises(ValueError):
            evaluate(rows)

    def test_07_too_little_data_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(samples(19))

    def test_08_costs_affect_markouts_without_manufacturing_accuracy(self):
        rows = samples()
        a = evaluate(rows)
        for r in rows:
            r['long_proxy_bps'] -= 100
            r['short_proxy_bps'] -= 100
        b = evaluate(rows)
        self.assertEqual(a['selected_holdout']['brier'],b['selected_holdout']['brier'])
        if b['selected_holdout']['directional_proxy_signals']:
            self.assertLess(b['selected_holdout']['mean_cost_adjusted_proxy_bps'],0)

    def test_09_historical_selection_is_not_a_live_winner(self):
        r = evaluate(samples())
        self.assertEqual(r['mode'],'RETROSPECTIVE_REPLAY')
        self.assertFalse(r['independent_forward_evidence'])
        self.assertFalse(r['promotion_allowed'])

    def test_10_deterministic_and_input_immutable(self):
        rows = samples()
        previous = copy.deepcopy(rows)
        a = evaluate(rows)
        self.assertEqual(a,evaluate(rows))
        self.assertEqual(rows,previous)


if __name__=='__main__':
    unittest.main()
