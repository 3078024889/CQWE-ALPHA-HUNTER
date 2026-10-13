"""CQWE V1.2: bounded multi-market dataset acquisition and conservative evidence audit.
Standard library only. Public Binance GET endpoints only, no authentication/orders.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import statistics
from pathlib import Path

from cqwe.core import valid_candles, save_json
from cqwe.history import fetch
from cqwe.market import discover
from cqwe.walkforward_v11 import analyze, STRATEGIES


def dataset_summary(bars):
    valid_candles(bars)
    start = int(bars[0][0]); end = int(bars[-1][0])
    days = len(bars)/288
    return {'candles':len(bars),'days':round(days,3),'first_open_ms':start,'last_open_ms':end,
            'sha256':hashlib.sha256(json.dumps(bars,separators=(',',':')).encode()).hexdigest()}


def verdict(stats, folds, min_events=100, min_folds=4, min_days=30):
    """Research gate, deliberately more conservative than v11 event-count flag."""
    if stats['days'] < min_days:
        return 'INSUFFICIENT_HISTORY'
    if folds < min_folds:
        return 'INSUFFICIENT_FOLDS'
    if stats['events'] < min_events:
        return 'INSUFFICIENT_EVENTS'
    if stats['mean'] is None:
        return 'INSUFFICIENT_RESULTS'
    if stats['mean'] <= 0:
        return 'NEGATIVE_AFTER_COSTS'
    return 'CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION'


def aggregate_costs(folds):
    result={}
    if not folds:
        return result
    names=list(folds[0]['cost_scenarios'])
    for cost in names:
        per={}
        for strategy in STRATEGIES:
            entries=[f['cost_scenarios'][cost][strategy] for f in folds]
            total=sum(e['events'] for e in entries)
            mean=(sum(e['events']*e['mean_net_event_pct'] for e in entries
                      if e['mean_net_event_pct'] is not None)/total if total else None)
            per[strategy]={'events':total,'mean_net_event_pct':round(mean,6) if mean is not None else None}
        result[cost]=per
    return result


def audit_dataset(bars, min_days=30, min_events=100):
    stats=dataset_summary(bars)
    if len(bars)<300:
        return {'dataset':stats,'gate':'INSUFFICIENT_HISTORY','folds':0,'strategies':{}}
    run=analyze(bars)
    costs=aggregate_costs(run['folds'])
    primary=costs.get('fee_5_slip_2_bps_each_side',{})
    strategies={}
    for name in STRATEGIES:
        p=primary.get(name,{'events':0,'mean_net_event_pct':None})
        spec={'days':stats['days'],'events':p['events'],'mean':p['mean_net_event_pct']}
        # The gate is not a proof of edge, even if it returns CANDIDATE.
        strategies[name]={'event_count':p['events'],'mean_net_event_pct':p['mean_net_event_pct'],
                         'research_gate':verdict(spec,run['fold_count'],min_events=min_events,min_days=min_days),
                         'v11_event_eligibility':run['aggregate'][name]['eligible_for_further_research']}
    return {'dataset':stats,'folds':run['fold_count'],'strategies':strategies,
            'cost_scenarios':costs,'funding_and_liquidation_modeled':False,
            'caveat':'Sample-selected markets and multiple testing bias; event mean not account PnL.'}


def acquire(symbols, days, outdir='data/v12', max_symbols=6):
    if not 1<=days<=30 or not 1<=len(symbols)<=max_symbols:
        raise ValueError('bounded requests only: days 1..30 and symbols 1..6')
    if len(set(symbols)) != len(symbols):
        raise ValueError('duplicate symbols')
    manifest=[]
    for symbol in symbols:
        bars=fetch(symbol,days=days)
        details=dataset_summary(bars)
        path=f'{outdir}/{symbol}_5m_{days}d.json'
        save_json(path,bars)
        manifest.append({'symbol':symbol,'path':path,**details})
    result={'research_only':True,'selection_bias_warning':'Symbols selected using current liquidity; historical universe is not reconstructed.',
            'created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'datasets':manifest}
    save_json(f'{outdir}/manifest.json',result)
    return result


def inspect(files,output='reports/v12_audit.json',min_days=30,min_events=100):
    if not files or len(files)>30 or not 1<=min_days<=90 or min_events<1:
        raise ValueError('invalid research constraints')
    results={}
    for file in files:
        p=Path(file)
        if p.stem in results: raise ValueError('duplicate dataset name')
        bars=json.loads(p.read_text(encoding='utf-8-sig'))
        results[p.stem]=audit_dataset(bars,min_days,min_events)
    payload={'research_only':True,'status':'NOT_A_PROFIT_CERTIFICATION',
             'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'dataset_count':len(results),'results':results}
    save_json(output,payload)
    return payload


def main():
    p=argparse.ArgumentParser(description='CQWE V12 multi-market research, public GET and offline only')
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('fetch');a.add_argument('--symbols',nargs='+');a.add_argument('--auto-top',type=int,default=0)
    a.add_argument('--days',type=int,default=30);a.add_argument('--outdir',default='data/v12')
    b=sub.add_parser('audit');b.add_argument('--inputs',nargs='+',required=True)
    b.add_argument('--output',default='reports/v12_audit.json');b.add_argument('--min-days',type=int,default=30)
    b.add_argument('--min-events',type=int,default=100)
    args=p.parse_args()
    if args.command=='fetch':
        if args.auto_top:
            if args.symbols or not 1<=args.auto_top<=6: p.error('use --symbols OR --auto-top 1..6')
            symbols=discover(limit=args.auto_top)
        else:
            symbols=args.symbols or ['BTCUSDT','ETHUSDT']
        r=acquire(symbols,args.days,args.outdir)
        print(json.dumps(r,ensure_ascii=False,indent=2))
    else:
        r=inspect(args.inputs,args.output,args.min_days,args.min_events)
        for symbol,result in r['results'].items():
            print(symbol,'days=',result['dataset']['days'],'folds=',result.get('folds',0))
            for name,v in result['strategies'].items():
                print(' ',name,'n=',v['event_count'],'mean_pct=',v['mean_net_event_pct'],'GATE=',v['research_gate'])
    print('CQWE_V12_RESEARCH_PASS | NO ORDERS | NO PROFIT CLAIM')

if __name__=='__main__':main()
