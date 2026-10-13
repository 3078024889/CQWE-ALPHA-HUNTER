"""CQWE V09: predeclared, non-overlapping, fee-sensitive microstructure cohorts.
No exchange orders, API keys, ML profitability claims, or silent OI imputation.
"""
import argparse
import datetime as dt
import json
import math
import statistics
from pathlib import Path
from .microstructure import rows, validate_klines

HORIZON=12
LOOKBACK=24
COST_SCENARIOS=((2,2),(5,2),(10,5),(20,10)) # per side fee/slippage bps
MIN_EVENTS=30


def _unoverlap(items):
    chosen=[]; exit_ms=-1
    for r in sorted(items,key=lambda x:x['signal_ms']):
        if r['signal_ms'] > exit_ms:
            chosen.append(r)
            exit_ms=r['future_exit_ms']
    return chosen


def _metrics(events, fee_bps, slip_bps):
    if not events:
        return {'n':0,'mean_net_pct':None,'median_net_pct':None,'win_fraction':None,'worst_mae_pct':None}
    net=[r['return_next_open_to_horizon_close_pct']-2*(fee_bps+slip_bps)/100 for r in events]
    return {'n':len(events),'mean_net_pct':round(statistics.mean(net),6),
            'median_net_pct':round(statistics.median(net),6),
            'win_fraction':round(sum(x>0 for x in net)/len(net),6),
            'worst_mae_pct':round(min(x['max_adverse_long_pct'] for x in events),6)}


def _strategies(records):
    def breakout(r):return r['breakout'] and r['turnover_ratio'] is not None and r['turnover_ratio']>=2
    def taker(r):return breakout(r) and r['taker_buy_fraction'] is not None and r['taker_buy_fraction']>=0.55
    def oi(r):return taker(r) and r['oi_change_pct'] is not None and r['oi_change_pct']>0
    def no_oi(r):return taker(r) and r['oi_change_pct'] is not None and r['oi_change_pct']<=0
    return {'volume_breakout':_unoverlap([r for r in records if breakout(r)]),
            'taker_confirmed':_unoverlap([r for r in records if taker(r)]),
            'oi_rising':_unoverlap([r for r in records if oi(r)]),
            'oi_nonrising_control':_unoverlap([r for r in records if no_oi(r)])}


def analyze(bars, oi_history=None, min_events=MIN_EVENTS):
    validate_klines(bars)
    if not isinstance(min_events,int) or min_events<2:raise ValueError('invalid min_events')
    # Features only at signal close. Never forward-fill OI. Labels intentionally use future bars.
    data=rows(bars,oi_history=oi_history,lookback=LOOKBACK,horizon=HORIZON)
    cut=int(len(bars)*0.7)
    split_close=int(bars[cut-1][6]);split_open=int(bars[cut][0])
    train=[r for r in data if r['future_exit_ms']<=split_close]
    holdout=[r for r in data if r['entry_ms']>=split_open]
    splits={}
    for name,source in [('train_70pct',train),('holdout_30pct',holdout)]:
        scenarios={}
        for label,events in _strategies(source).items():
            scenarios[label]={f'fee_{f}_slip_{s}_bps_each_side':_metrics(events,f,s) for f,s in COST_SCENARIOS}
        splits[name]=scenarios
    oi_coverage=sum(r['oi_change_pct'] is not None for r in data)
    eligible = oi_coverage >= min_events and all(
        splits[p]['oi_rising']['fee_5_slip_2_bps_each_side']['n']>=min_events and
        splits[p]['oi_nonrising_control']['fee_5_slip_2_bps_each_side']['n']>=min_events
        for p in splits)
    return {'research_only':True,'execution_mode':'NO_ORDERS','bars':len(bars),
            'event_rows':len(data),'oi_covered_rows':oi_coverage,
            'oi_coverage_fraction':round(oi_coverage/len(data),6) if data else 0,
            'oi_comparison_eligible':eligible,
            'oi_coverage_status':'READY_FOR_DESCRIPTIVE_COMPARISON' if eligible else 'INSUFFICIENT_OI_HISTORY_OR_EVENTS',
            'time_split_ms':split_open,'prespecified_strategy_names':list(_strategies([])),
            'cost_scenarios_bps_each_side':[{'fee':f,'slippage':s} for f,s in COST_SCENARIOS],
            'splits':splits,
            'disclaimer':'7 days and overlapping labels are insufficient for alpha validation. Event means are NOT portfolio PnL. No spread dynamics, funding, order queue, impact, or liquidation. Min events per split+cohort is descriptive gating only.'}


def main():
    p=argparse.ArgumentParser(description='CQWE V09 conservative offline strategy lab; no API access/orders')
    p.add_argument('--klines',required=True);p.add_argument('--oi-file')
    p.add_argument('--output',default='reports/v09_strategy_lab.json')
    p.add_argument('--min-events',type=int,default=MIN_EVENTS)
    a=p.parse_args()
    bars=json.loads(Path(a.klines).read_text(encoding='utf-8-sig'))
    oi=json.loads(Path(a.oi_file).read_text(encoding='utf-8-sig')) if a.oi_file else None
    result=analyze(bars,oi,a.min_events)
    result.update({'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'oi_file':a.oi_file,'klines_file':a.klines})
    dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix(dest.suffix+'.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(dest)
    print(json.dumps({'bars':result['bars'],'oi_coverage_fraction':result['oi_coverage_fraction'],
       'oi_comparison_eligible':result['oi_comparison_eligible'],
       'holdout':result['splits']['holdout_30pct']},ensure_ascii=False,indent=2))
    print('CQWE_V09_OFFLINE_PASS | SIMULATION_ONLY | NO ORDERS')

if __name__=='__main__': main()
