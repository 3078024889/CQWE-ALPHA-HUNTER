import copy
import math
import unittest

from cqwe.copernican_experiment_v81_v85 import (
    Network, digest, experiment, features, train,
)


def source(start=0, n=160):
    bars = []
    for i in range(n):
        o = 100 + i*.02 + math.sin(i*.3)
        c = o*(1 + .002*math.sin(i*.7))
        bars.append({'time': (start+i)*3600000, 'open': str(o),
                     'high': str(max(o, c)+1), 'low': str(min(o, c)-1),
                     'close': str(c), 'volume': str(10+i%9)})
    return {'source': 'BINANCE_USDM_PUBLIC_KLINES', 'symbol': 'BTCUSDT',
            'interval': '1h', 'bars': bars, 'sha256': digest(bars), 'live_orders': False}


def run(s=None, **kw):
    return experiment(s or source(), asof_ms=10**15, **kw)


class TenResearchAudits(unittest.TestCase):
    def test_01_closed_contiguous_finite_input(self):
        for mutation in ('open', 'gap', 'nan', 'low', 'hash'):
            with self.subTest(mutation=mutation):
                s = source()
                if mutation == 'open':
                    with self.assertRaises(ValueError):
                        experiment(s, asof_ms=s['bars'][-1]['time'])
                    continue
                if mutation == 'gap':
                    s['bars'][8]['time'] += 1
                if mutation == 'nan':
                    s['bars'][8]['close'] = 'NaN'
                if mutation == 'low':
                    s['bars'][8]['low'] = '200'
                if mutation != 'hash':
                    s['sha256'] = digest(s['bars'])
                else:
                    s['sha256'] = '0'*64
                with self.assertRaises(ValueError):
                    run(s)

    def test_02_features_cannot_see_future(self):
        s = source()
        before = features(s['bars'], 20)
        for b in s['bars'][21:]:
            b['close'] = '10000'
        self.assertEqual(before, features(s['bars'], 20))

    def test_03_learning_changes_parameters_and_memory(self):
        r = run()
        state = r['model_states']['dendritic']
        self.assertGreater(state['updates'], 50)
        self.assertNotEqual(state['weights'], Network().weights)
        self.assertTrue(any(abs(v) > 1e-8 for v in state['memory']))

    def test_04_frozen_control_does_not_learn(self):
        state = run()['model_states']['frozen']
        self.assertEqual(state, Network('frozen').state())

    def test_05_mature_labels_stop_before_validation(self):
        s = source()
        stop = int(len(s['bars'])*.6)
        a, journal = train(s['bars'], stop, 'dendritic')
        self.assertLess(journal[-1]['outcome_bar_time'], s['bars'][stop]['time'])
        changed = copy.deepcopy(s['bars'])
        for b in changed[stop:]:
            b['close'] = '2000'
        b, _ = train(changed, stop, 'dendritic')
        self.assertEqual(a.state(), b.state())

    def test_06_holdout_cannot_change_selection(self):
        s = source()
        a = run(s)
        for b in s['bars'][a['split']['validation_stop']:]:
            b['close'] = str(float(b['open'])*1.2)
            b['high'] = str(float(b['close'])+1)
        s['sha256'] = digest(s['bars'])
        b = run(s)
        self.assertEqual(a['selected_on_validation'], b['selected_on_validation'])
        self.assertEqual(a['validation'], b['validation'])
        self.assertEqual(a['model_states'], b['model_states'])

    def test_07_cost_stress_and_invalid_cost(self):
        r = run()
        totals = [v['total_event_proxy_bps'] for v in r['stress'].values()]
        self.assertEqual(totals, sorted(totals, reverse=True))
        for cost in (-1, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                run(cost_bps=cost)

    def test_08_continuation_inherits_and_grows(self):
        a = run()
        b = run(source(160), previous=a)
        self.assertEqual(b['previous_report_sha256'], a['sha256'])
        self.assertGreater(b['model_states']['dendritic']['updates'],
                           a['model_states']['dendritic']['updates'])
        self.assertEqual(b['learning_journals']['dendritic'][0]['before'],
                         digest(a['model_states']['dendritic']))

    def test_09_replay_and_checkpoint_changes_rejected(self):
        a = run()
        with self.assertRaises(ValueError):
            run(previous=a)
        tampered = copy.deepcopy(a)
        tampered['model_states']['dendritic']['weights'][0] = 999
        with self.assertRaises(ValueError):
            run(source(160), previous=tampered)
        tampered['sha256'] = digest({k:v for k,v in tampered.items() if k != 'sha256'})
        with self.assertRaises(ValueError):
            run(source(160), previous=tampered)
        with self.assertRaises(ValueError):
            run(source(160), previous=a, cost_bps=21)

    def test_10_reproducible_chain_and_profit_semantics(self):
        a = run()
        self.assertEqual(a, run())
        previous = None
        for row in a['learning_journals']['dendritic']:
            self.assertEqual(row['previous'], previous)
            self.assertEqual(row['sha256'], digest({k:v for k,v in row.items() if k != 'sha256'}))
            previous = row['sha256']
        self.assertIsNone(a['realized_profit_usd'])
        self.assertEqual(a['real_orders'], 0)
        self.assertFalse(a['promotion_allowed'])


if __name__ == '__main__':
    unittest.main()
