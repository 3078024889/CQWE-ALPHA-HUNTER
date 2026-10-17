"""Five research capabilities: closed data, dendrites, causal learning, controls, stress.

Original small computational model inspired by dendritic compartmentalization;
not a reproduction of DLL, a biological simulation, or an execution engine.
"""
from __future__ import annotations
import argparse
import copy
import datetime
import hashlib
import json
import math
from pathlib import Path

from .tidal_hunter_v66_v70 import INTERVAL_MS, load_verified


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def validate(source, asof_ms):
    if source.get('live_orders') is not False:
        raise ValueError('ARCHIVE_NOT_RESEARCH_ONLY')
    bars = source['bars']
    step = INTERVAL_MS[source['interval']]
    if len(bars) < 120 or len(bars) > 100000:
        raise ValueError('HISTORY_BUDGET')
    if source.get('sha256') != digest(bars):
        raise ValueError('SOURCE_HASH_MISMATCH')
    for i, b in enumerate(bars):
        if type(b['time']) is not int or b['time'] < 0 or b['time'] % step:
            raise ValueError('BAD_TIME')
        if i and b['time'] != bars[i-1]['time'] + step:
            raise ValueError('GAP')
        o, h, l, c, v = [float(b[k]) for k in ('open', 'high', 'low', 'close', 'volume')]
        if not all(math.isfinite(x) for x in (o, h, l, c, v)) or min(o, h, l, c) <= 0 or v < 0:
            raise ValueError('INVALID_PRICE')
        if h < max(o, c, l) or l > min(o, c):
            raise ValueError('INVALID_RANGE')
        if b['time'] + step > asof_ms:
            raise ValueError('UNFINISHED_CANDLE')
    return bars


def features(bars, i):
    """Only closes/volume/range available at decision bar close i."""
    b = bars[i]
    c, prev, old = (float(bars[j]['close']) for j in (i, i-1, i-4))
    volumes = [float(bars[j]['volume']) for j in range(i-4, i)]
    ratio = (float(b['volume']) + 1e-9) / (sum(volumes)/4 + 1e-9)
    h, l = float(b['high']), float(b['low'])
    return [math.tanh(100 * (c/prev - 1)), math.tanh(30 * (c/old - 1)),
            math.tanh(math.log(ratio)/4), 0. if h == l else 2*(c-l)/(h-l)-1]


class Network:
    def __init__(self, kind='dendritic'):
        if kind not in ('dendritic', 'linear', 'frozen'):
            raise ValueError('BAD_KIND')
        self.kind = kind
        self.weights = [.15, -.10, .05, .08]
        self.memory = [0.] * 4
        self.updates = 0

    def predict(self, x):
        if self.kind == 'linear':
            z = sum(w*v for w, v in zip(self.weights, x))
            return math.tanh(z), (list(x), [z])
        u = [v + .1*m for v, m in zip(x, self.memory)]
        branches = [math.tanh(sum(self.weights[j]*u[j] for j in group))
                    for group in ((0, 1), (2, 3))]
        return math.tanh(sum(branches)/2), (u, branches)

    def learn(self, x, label, pred, cache):
        if self.kind == 'frozen':
            return
        u, branches = cache
        error = (label-pred)*(1-pred*pred)
        for j in range(4):
            slope = 1. if self.kind == 'linear' else .5*(1-branches[j//2]**2)
            self.weights[j] = max(-1., min(1., self.weights[j]+.03*error*slope*u[j]))
            self.memory[j] = .9*self.memory[j] + .1*x[j]*label
        self.updates += 1

    def state(self):
        return copy.deepcopy(vars(self))


def restore(previous, source, cost_bps):
    if previous.get('sha256') != digest({k: v for k, v in previous.items() if k != 'sha256'}):
        raise ValueError('CHECKPOINT_HASH_MISMATCH')
    if previous.get('schema') != 'CQWE_V81_V85_CAUSAL_DENDRITIC_EXPERIMENT':
        raise ValueError('CHECKPOINT_SCHEMA')
    if (previous.get('research_only') is not True or previous.get('real_orders') != 0
            or previous.get('realized_profit_usd') is not None or previous.get('promotion_allowed') is not False):
        raise ValueError('CHECKPOINT_SEMANTICS')
    if any(source[k] != previous[k] for k in ('symbol', 'interval')):
        raise ValueError('CHECKPOINT_MARKET_MISMATCH')
    if previous['config']['cost_bps_round_trip'] != cost_bps:
        raise ValueError('CHECKPOINT_CONFIG_MISMATCH')
    if source['bars'][0]['time'] <= previous['last_observed_bar_time']:
        raise ValueError('REPEATED_RESEARCH_DATA')
    result = {}
    for kind in ('dendritic', 'linear', 'frozen'):
        state = previous['model_states'][kind]
        if set(state) != {'kind', 'weights', 'memory', 'updates'} or state['kind'] != kind:
            raise ValueError('CHECKPOINT_STATE')
        if type(state['updates']) is not int or state['updates'] < 0:
            raise ValueError('CHECKPOINT_UPDATES')
        for field in ('weights', 'memory'):
            values = state[field]
            if not isinstance(values, list) or len(values) != 4 or any(
                    type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1 for v in values):
                raise ValueError('CHECKPOINT_PARAMETERS')
        model = Network(kind)
        model.__dict__.update(copy.deepcopy(state))
        result[kind] = model
    return result


def train(bars, stop, kind, model=None):
    model = copy.deepcopy(model) if model is not None else Network(kind)
    journal = []
    previous = None
    for i in range(4, stop-1):
        x = features(bars, i)
        pred, cache = model.predict(x)
        # Enter at NEXT open. Outcome only updates after that next bar has closed.
        realized = float(bars[i+1]['close'])/float(bars[i+1]['open'])-1
        label = math.tanh(realized*100)
        before = digest(model.state())
        model.learn(x, label, pred, cache)
        row = {'decision_time': bars[i]['time'], 'outcome_bar_time': bars[i+1]['time'],
               'before': before, 'after': digest(model.state()), 'previous': previous}
        row['sha256'] = digest(row)
        previous = row['sha256']
        journal.append(row)
    return model, journal


def score(bars, model, start, stop, cost_bps):
    state = digest(model.state())
    returns = []
    for i in range(start, stop-1):
        pred, _ = model.predict(features(bars, i))
        if pred > .05:
            r = (float(bars[i+1]['close'])/float(bars[i+1]['open'])-1)*10000-cost_bps
            returns.append(r)
    if digest(model.state()) != state:
        raise ArithmeticError('EVALUATION_CHANGED_MODEL')
    return {'observations': stop-start-1, 'signals': len(returns),
            'total_event_proxy_bps': sum(returns),
            'mean_event_proxy_bps': sum(returns)/len(returns) if returns else None}


def experiment(source, *, asof_ms, cost_bps=20., previous=None):
    if type(cost_bps) not in (int, float) or not math.isfinite(cost_bps) or not 0 <= cost_bps <= 1000:
        raise ValueError('INVALID_COST')
    bars = validate(source, asof_ms)
    n = len(bars)
    t, v = int(n*.6), int(n*.8)
    ancestors = restore(previous, source, cost_bps) if previous is not None else {}
    models, journals = {}, {}
    for kind in ('dendritic', 'linear', 'frozen'):
        models[kind], journals[kind] = train(bars, t, kind, ancestors.get(kind))
    # The boundary candle belongs to neither evaluated set: labels never cross splits.
    validation = {k: score(bars, m, t, v, cost_bps) for k, m in models.items()}
    validation['cash'] = {'observations': v-t-1, 'signals': 0, 'total_event_proxy_bps': 0.,
                          'mean_event_proxy_bps': None}
    chosen = sorted(validation, key=lambda k: (-validation[k]['total_event_proxy_bps'], k))[0]
    holdout = {k: score(bars, m, v, n, cost_bps) for k, m in models.items()}
    holdout['cash'] = {'observations': n-v-1, 'signals': 0, 'total_event_proxy_bps': 0.,
                       'mean_event_proxy_bps': None}
    stress = {}
    for extra in (0, 10, 30):
        stress[str(cost_bps+extra)] = (score(bars, models[chosen], v, n, cost_bps+extra)
                                      if chosen != 'cash' else copy.deepcopy(holdout['cash']))
    report = {'schema': 'CQWE_V81_V85_CAUSAL_DENDRITIC_EXPERIMENT',
              'source_sha256': source['sha256'], 'symbol': source['symbol'],
              'interval': source['interval'], 'asof_ms': asof_ms,
              'last_observed_bar_time': bars[-1]['time'],
              'previous_report_sha256': previous['sha256'] if previous is not None else None,
              'split': {'train_stop': t, 'validation_stop': v, 'bars': n},
              'config': {'cost_bps_round_trip': cost_bps, 'threshold': .05, 'learning_rate': .03},
              'selected_on_validation': chosen, 'validation': validation, 'holdout': holdout,
              'stress': stress, 'model_states': {k: m.state() for k, m in models.items()},
              'learning_journals': journals,
              'research_only': True, 'real_orders': 0, 'realized_profit_usd': None,
              'promotion_allowed': False, 'independent_forward_evidence': False,
              'limitations': ['Historical data may already have been inspected.',
                  'OHLC event proxies, not fills, account PnL or capital-compounded returns.',
                  'No exchange filters, margin, liquidation, funding, latency or account fees verified.',
                  'Continuation requires entirely later bars; 4 initial bars are feature warmup.',
                  'Hash verifies internal consistency, not source authenticity or research precommitment.']}
    report['sha256'] = digest(report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--cost-bps', type=float, default=20.)
    p.add_argument('--previous', help='Prior report; new input must be strictly later and nonoverlapping')
    args = p.parse_args()
    source = load_verified(args.input)
    asof = int(datetime.datetime.now(datetime.timezone.utc).timestamp()*1000)
    previous = json.loads(Path(args.previous).read_text(encoding='utf-8')) if args.previous else None
    report = experiment(source, asof_ms=asof, cost_bps=args.cost_bps, previous=previous)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'selected': report['selected_on_validation'],
                      'holdout': report['holdout'][report['selected_on_validation']],
                      'real_orders': 0, 'realized_profit_usd': None}, indent=2))


if __name__ == '__main__':
    main()
