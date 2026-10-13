"""CQWE V1.0: strictly offline, low-cost, no API keys and no order execution.

Walk-forward-style chronological holdout with gap, train-only scaling, simple
regularized logistic model, baseline and negative-control comparison. Results
are descriptive evidence, never a trading authorization or portfolio PnL.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import random
import statistics
from pathlib import Path

STEP = 300_000
FEATURES = ('ret_30m', 'turnover_log_ratio', 'range_pct', 'taker_imbalance', 'realized_vol')


def validate(bars):
    if not isinstance(bars, list) or len(bars) < 100:
        raise ValueError('at least 100 historical candles required')
    previous = None
    for b in bars:
        if not isinstance(b, list) or len(b) < 11:
            raise ValueError('invalid Binance 5m candle')
        t, end = int(b[0]), int(b[6])
        if previous is not None and t != previous + STEP:
            raise ValueError('missing, duplicated, or unordered candle')
        if end != t + STEP - 1:
            raise ValueError('invalid candle close timestamp')
        op, high, low, close = map(float, (b[1], b[2], b[3], b[4]))
        turnover, taker = float(b[7]), float(b[10])
        if not all(math.isfinite(x) for x in (op, high, low, close, turnover, taker)):
            raise ValueError('non-finite candle')
        if min(op, high, low, close) <= 0 or high < max(op, close) or low > min(op, close):
            raise ValueError('invalid OHLC')
        if turnover < 0 or taker < 0 or taker > turnover + 0.001:
            raise ValueError('invalid turnover or taker data')
        previous = t
    return bars


def _rows(bars, lookback=24, horizon=12):
    if lookback < 12 or horizon < 1:
        raise ValueError('invalid lookback/horizon')
    validate(bars)
    out = []
    for i in range(lookback, len(bars) - horizon):
        prev = bars[i-lookback:i]
        now = bars[i]
        close = float(now[4])
        close6 = float(bars[i-6][4])
        turnovers = [float(c[7]) for c in prev]
        med = statistics.median(turnovers)
        frac = (float(now[10]) / float(now[7])) if float(now[7]) > 0 else .5
        rets = [math.log(float(bars[k][4]) / float(bars[k-1][4])) for k in range(i-11, i+1)]
        # Entire feature vector available after signal candle close.
        features = (
            math.log(close / close6),
            math.log((float(now[7]) + 1) / (med + 1)),
            (float(now[2]) - float(now[3])) / close,
            2 * frac - 1,
            statistics.pstdev(rets),
        )
        entry = float(bars[i+1][1])
        exit_price = float(bars[i+horizon][4])
        if entry <= 0:
            raise ValueError('invalid next-open entry')
        gross = exit_price / entry - 1
        out.append({'i': i, 'signal_ms': int(now[0]), 'entry_ms': int(bars[i+1][0]),
                    'exit_ms': int(bars[i+horizon][6]), 'x': features, 'gross': gross,
                    'is_breakout': close > max(float(c[2]) for c in prev),
                    'is_reversal': close < min(float(c[3]) for c in prev),
                    'taker_fraction': frac, 'turnover_ratio': float(now[7]) / med if med > 0 else 0,
                    'label': int(gross > 0)})
    return out


def _scaler(train):
    means = [statistics.mean(r['x'][j] for r in train) for j in range(len(FEATURES))]
    deviations = [max(statistics.pstdev(r['x'][j] for r in train), 1e-8) for j in range(len(FEATURES))]
    return means, deviations


def _scaled(x, means, dev):
    return [max(-8.0, min(8.0, (x[j]-means[j])/dev[j])) for j in range(len(x))]


def _sigmoid(z):
    z = max(-30., min(30., z))
    return 1 / (1 + math.exp(-z))


def train_logistic(train, labels=None, iterations=160, learning_rate=0.06, regularization=0.025):
    if len(train) < 60:
        raise ValueError('insufficient train observations')
    if iterations < 1 or learning_rate <= 0 or regularization < 0:
        raise ValueError('invalid training hyperparameters')
    if labels is None:
        labels = [r['label'] for r in train]
    if len(labels) != len(train) or any(y not in (0,1) for y in labels):
        raise ValueError('bad labels')
    means, deviations = _scaler(train)
    xs = [_scaled(r['x'], means, deviations) for r in train]
    weights = [0.] * len(FEATURES)
    bias = math.log((sum(labels)+.5) / (len(labels)-sum(labels)+.5))
    for _ in range(iterations):
        gradients = [0.] * len(FEATURES)
        bias_grad = 0.
        for x,y in zip(xs, labels):
            diff = _sigmoid(bias + sum(w*v for w,v in zip(weights,x))) - y
            bias_grad += diff
            for j,value in enumerate(x):
                gradients[j] += diff * value
        n = len(labels)
        for j in range(len(weights)):
            weights[j] -= learning_rate * (gradients[j]/n + regularization*weights[j])
        bias -= learning_rate * bias_grad/n
    return {'weights':weights, 'bias':bias, 'means':means, 'deviations':deviations}


def probability(model, row):
    x = _scaled(row['x'], model['means'], model['deviations'])
    return _sigmoid(model['bias'] + sum(w*v for w,v in zip(model['weights'],x)))


def _selected(rows, predicate, horizon):
    selected=[]
    last_exit_index=-1
    for r in rows:
        if r['i'] <= last_exit_index or not predicate(r):
            continue
        selected.append(r)
        last_exit_index=r['i'] + horizon
    return selected


def summarize(entries, fee_bps=5, slip_bps=2, min_trades=20):
    if fee_bps < 0 or slip_bps < 0 or min_trades < 1:
        raise ValueError('invalid scenario')
    cost = 2 * (fee_bps + slip_bps) / 10000
    vals = [r['gross'] - cost for r in entries]
    return {'trades':len(vals), 'eligible':len(vals)>=min_trades,
            'mean_net_pct':round(statistics.mean(vals)*100,6) if vals else None,
            'median_net_pct':round(statistics.median(vals)*100,6) if vals else None,
            'win_fraction':round(sum(v>0 for v in vals)/len(vals),6) if vals else None,
            'interpretation':'DESCRIPTIVE_ONLY' if len(vals)>=min_trades else 'INSUFFICIENT_TRADES',
            'portfolio_profit':None}


def analyze(bars, train_fraction=.7, horizon=12, min_trades=20, seed=20261013):
    if not .55 <= train_fraction <= .85 or horizon < 1:
        raise ValueError('invalid split settings')
    rows = _rows(bars, horizon=horizon)
    cut = int(len(bars)*train_fraction)
    train = [r for r in rows if r['i']+horizon < cut]
    test = [r for r in rows if r['i']+1 >= cut]
    if len(train) < 60 or len(test) < 30:
        raise ValueError('insufficient train/holdout after purge')
    model = train_logistic(train)
    # Honest negative control: shuffle training labels, fixed seed. Never shuffle time-series features.
    scrambled = [r['label'] for r in train]
    random.Random(seed).shuffle(scrambled)
    negative = train_logistic(train, labels=scrambled)
    tests = {
        'breakout':lambda r:r['is_breakout'] and r['turnover_ratio']>=2,
        'reversal_long_control':lambda r:r['is_reversal'] and r['turnover_ratio']>=2,
        'taker_confirmed':lambda r:r['is_breakout'] and r['turnover_ratio']>=2 and r['taker_fraction']>=.55,
        'ai_logistic_top_60pct':lambda r:probability(model,r)>=.6,
        'shuffled_labels_negative_control':lambda r:probability(negative,r)>=.6,
        'always_long_control':lambda r:True,
    }
    cost_scenarios=[(2,2),(5,2),(10,5),(20,10)]
    results={}
    for name,pred in tests.items():
        nonoverlap=_selected(test,pred,horizon)
        results[name]={f'fee_{f}_slip_{s}_bps_each_side':summarize(nonoverlap,f,s,min_trades)
                       for f,s in cost_scenarios}
    # Freeze predeclared model and threshold. No parameter search over the holdout.
    return {'research_only':True,'execution_mode':'NO_ORDERS', 'test_design':'purged_70_30_single_holdout',
            'train_rows':len(train), 'holdout_rows':len(test), 'signal_horizon_5m_bars':horizon,
            'features':list(FEATURES), 'cost_scenarios':cost_scenarios,
            'strategies':results, 'oi_status':'NOT_INCLUDED_UNLESS_TIMESTAMP_VALIDATED',
            'decision':'RESEARCH_ONLY_NOT_ELIGIBLE_FOR_LIVE_TRADING',
            'warnings':['Single holdout, not a walk-forward study or calibrated probabilities',
                        'No funding, spread dynamics, mark-price liquidation, queue or real order fills',
                        'No portfolio PnL: event returns are not an equity curve',
                        'Train/test exclusion gap prevents overlapping forward labels at boundary',
                        'Negative control is a diagnostic, not a significance test']}


def run_files(files, out='reports/v10_alpha_lab.json', min_trades=20):
    if not files:
        raise ValueError('no input files')
    results={}
    for path in files:
        src=Path(path)
        name=src.stem
        if name in results:
            raise ValueError('duplicate dataset names')
        bars=json.loads(src.read_text(encoding='utf-8-sig'))
        results[name]=analyze(bars,min_trades=min_trades)
    payload={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'research_only':True, 'dataset_count':len(results), 'datasets':results}
    dest=Path(out)
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix(dest.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(dest)
    return payload


def main():
    parser=argparse.ArgumentParser(description='CQWE v1.0 offline controls, NO EXCHANGE ORDER API')
    parser.add_argument('--inputs',nargs='+',required=True)
    parser.add_argument('--output',default='reports/v10_alpha_lab.json')
    parser.add_argument('--min-trades',type=int,default=20)
    args=parser.parse_args()
    output=run_files(args.inputs,args.output,args.min_trades)
    for name,study in output['datasets'].items():
        print(name,'train=',study['train_rows'],'holdout=',study['holdout_rows'])
        for key,value in study['strategies'].items():
            base=value['fee_5_slip_2_bps_each_side']
            print(f"  {key:36} n={base['trades']:3d} net_event_mean={base['mean_net_pct']}% status={base['interpretation']}")
    print('CQWE_V10_OFFLINE_RESEARCH_PASS | NO API KEYS | NO ORDERS | NO PROFIT CLAIM')


if __name__=='__main__':
    main()
