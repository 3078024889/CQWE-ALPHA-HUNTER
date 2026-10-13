"""CQWE V1.1 chronological multi-fold research diagnostics; no API or orders.

Uses V1.0 _rows, train_logistic and probability with train-only scaling.
Non-overlapping trades are selected within each forward test fold; parameters are frozen.
Neither simulated event returns nor fold scores represent real-account profits.
"""
import argparse
import datetime as dt
import json
import math
import statistics
from pathlib import Path
from cqwe.alpha_lab_v10 import _rows, _selected, probability, train_logistic, validate

COSTS = ((2, 2), (5, 2), (10, 5), (20, 10))
STRATEGIES = ('breakout', 'reversal', 'taker_confirmed', 'ai_at_50', 'ai_at_60', 'always_long')


def folds(n, initial_fraction=.5, fold_fraction=.1, horizon=12, lookback=24):
    if n < 300 or not .3 <= initial_fraction <= .8 or not .05 <= fold_fraction <= .25 or horizon < 1:
        raise ValueError('invalid walk-forward parameters')
    initial = int(n * initial_fraction)
    step = max(30, int(n * fold_fraction))
    result = []
    end = initial
    while end + step <= n:
        result.append((0, end, end, end + step))
        end += step
    if not result:
        raise ValueError('no test folds')
    return result


def diagnostics(predictions, expected):
    if len(predictions) != len(expected) or not predictions:
        return {'observations': 0, 'brier_score': None, 'predicted_positive_rate': None,
                'observed_positive_rate': None, 'above_50': 0, 'above_60': 0,
                'probability_quantiles': None}
    if any(not math.isfinite(p) or p < 0 or p > 1 for p in predictions):
        raise ValueError('invalid predicted probabilities')
    q = sorted(predictions)
    return {'observations':len(q),
            'brier_score':round(statistics.mean((p-y)**2 for p,y in zip(predictions,expected)),6),
            'predicted_positive_rate':round(statistics.mean(predictions),6),
            'observed_positive_rate':round(statistics.mean(expected),6),
            'above_50':sum(p >= .5 for p in predictions),
            'above_60':sum(p >= .6 for p in predictions),
            'probability_quantiles':{'min':round(q[0],6),'median':round(statistics.median(q),6), 'max':round(q[-1],6)}}


def _strategy_matches(r, model):
    base = r['turnover_ratio'] >= 2
    p = probability(model, r)
    return {'breakout':base and r['is_breakout'],
            'reversal':base and r['is_reversal'],
            'taker_confirmed':base and r['is_breakout'] and r['taker_fraction'] >= .55,
            'ai_at_50':p >= .5,
            'ai_at_60':p >= .6,
            'always_long':True}


def analyze(bars, horizon=12, initial_fraction=.5, fold_fraction=.1, fee_bps=5, slip_bps=2, min_events=20):
    validate(bars)
    if horizon < 1 or fee_bps < 0 or slip_bps < 0 or min_events < 1:
        raise ValueError('invalid parameters')
    rows = _rows(bars, horizon=horizon)
    out = []
    for _, train_end, test_start, test_end in folds(len(bars), initial_fraction, fold_fraction, horizon):
        # Forward outcomes for training samples must be fully observable BEFORE fold boundary.
        train = [r for r in rows if r['i'] + horizon < train_end]
        test = [r for r in rows if r['i'] + 1 >= test_start and r['i'] + horizon < test_end]
        if len(train) < 60 or not test:
            continue
        model = train_logistic(train)
        ps = [probability(model,r) for r in test]
        diag = diagnostics(ps,[r['label'] for r in test])
        matched = {name:[] for name in STRATEGIES}
        for r in test:
            for name, yes in _strategy_matches(r,model).items():
                if yes: matched[name].append(r)
        selected = {name:_selected(rs,lambda _:True,horizon) for name,rs in matched.items()}
        scenarios={}
        for f,s in COSTS:
            scenario={}
            for name,selected_rows in selected.items():
                v=[r['gross']-2*(f+s)/10000 for r in selected_rows]
                scenario[name]={'events':len(v),
                                'mean_net_event_pct':round(statistics.mean(v)*100,6) if v else None,
                                'positive_fraction':round(sum(x>0 for x in v)/len(v),6) if v else None}
            scenarios[f'fee_{f}_slip_{s}_bps_each_side']=scenario
        out.append({'train_end_ms_exclusive':int(bars[train_end][0]),
                    'test_start_ms':int(bars[test_start][0]),
                    'test_end_ms_exclusive':int(bars[test_end][0]) if test_end<len(bars) else int(bars[-1][0])+300000,
                    'train_rows':len(train),'test_rows':len(test),'ai_probability_diagnostics':diag,
                    'cost_scenarios':scenarios})
    aggregation={}
    for name in STRATEGIES:
        counts=[fold['cost_scenarios']['fee_5_slip_2_bps_each_side'][name]['events'] for fold in out]
        means=[fold['cost_scenarios']['fee_5_slip_2_bps_each_side'][name]['mean_net_event_pct'] for fold in out]
        total=sum(counts)
        mean=sum(n*m for n,m in zip(counts,means) if m is not None)/total if total else None
        aggregation[name]={'folds':len(out),'total_events':total,'mean_net_event_pct_weighted':round(mean,6) if mean is not None else None,
                           'eligible_for_further_research':total>=min_events and sum(n>0 for n in counts)>=3,
                           'folds_with_events':sum(n>0 for n in counts),
                           'warning':'Descriptive only; sample dependence and multiple-testing risk.'}
    return {'research_only':True,'mode':'NO_ORDERS','fold_count':len(out),'horizon_5m_bars':horizon,
            'historical_oi_status':'NOT_ASSUMED_AVAILABLE',
            'aggregate':aggregation,'folds':out,
            'warnings':['No future information used for signals or training labels',
                        'Events are not a cash-account return or executable PnL',
                        'Single market, overlapping training sets, multiple comparisons; no statistical profit claim',
                        'Real fills, spread, funding, mark-price liquidation and exchange filters not modeled']}


def run_files(paths, output):
    if not paths: raise ValueError('at least one input required')
    results={}
    for path in paths:
        p=Path(path)
        if p.stem in results: raise ValueError('duplicate input dataset')
        bars=json.loads(p.read_text(encoding='utf-8-sig'))
        results[p.stem]=analyze(bars)
    target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix(target.suffix+'.tmp')
    payload={'timestamp_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'datasets':results,'research_only':True}
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(target)
    return payload


def main():
    p=argparse.ArgumentParser(description='CQWE V1.1 walk-forward lab; no trade API')
    p.add_argument('--inputs',nargs='+',required=True)
    p.add_argument('--output',default='reports/v11_walkforward.json')
    a=p.parse_args()
    v=run_files(a.inputs,a.output)
    for name,r in v['datasets'].items():
        print(f'{name}: folds={r["fold_count"]}')
        for key,one in r['aggregate'].items():
            print(f'  {key:20} events={one["total_events"]:3} folds_with_events={one["folds_with_events"]} mean={one["mean_net_event_pct_weighted"]} research_eligible={one["eligible_for_further_research"]}')
    print('CQWE_V11_OFFLINE_RESEARCH_PASS | NO ORDERS | NO PROFIT CLAIM')

if __name__ == '__main__':main()
