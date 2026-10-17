"""Frozen holdout directional-policy proxy. Not executable-fill or profitability proof."""
import collections
import json
import math
from pathlib import Path
import statistics

from cqwe.four_market_runner import checked
from cqwe.local_autopilot import atomic


def evaluate_policy(learning,rows):
    outcomes={}
    for row in rows:
        for r in row['responses']:
            if r['status']=='OBSERVED':
                key=(row['anchor_ms'],row['symbol'],r['horizon'])
                if key in outcomes and outcomes[key]!=r['return_bps']:raise ValueError('CONFLICTING_LABEL')
                outcomes[key]=r['return_bps']
    banks=collections.defaultdict(list)
    for f in learning['forecasts']:
        if f['phase']!='holdout':continue
        symbol,h=f['key'].split(':');chosen=learning['chosen_from_validation'].get(f['key'],'frozen')
        p=f['p_up'][chosen];direction=1 if p>=.55 else -1 if p<=.45 else 0
        gross=direction*outcomes[(f['at_ms'],symbol,int(h))] if direction else 0.
        net=gross-14 if direction else 0.
        banks[f['key']].append({'at_ms':f['at_ms'],'p_up':p,'direction':direction,
                               'gross_bps':gross,'net_bps_proxy':net,'selected':chosen})
    summaries={}
    for key,records in banks.items():
        trades=[r for r in records if r['direction']]
        daily=collections.defaultdict(float)
        for r in trades:daily[r['at_ms']//86400000]+=r['net_bps_proxy']
        vals=list(daily.values());mean=statistics.mean(vals) if vals else None
        se=statistics.stdev(vals)/math.sqrt(len(vals)) if len(vals)>1 else None
        summaries[key]={'events':len(records),'counterfactual_trades':len(trades),
            'active_days':len(vals),'total_net_bps_proxy':sum(r['net_bps_proxy'] for r in trades),
            'mean_net_bps_per_trade':statistics.mean(r['net_bps_proxy'] for r in trades) if trades else None,
            'daily_mean_minus_3se':mean-3*se if se is not None else None,
            'execution_eligible':False}
    return {'summaries':summaries,'records':dict(banks),'profitability_proven':False,'real_orders':0,
            'cost_model':'14bps fixed round trip only; bid/ask, actual fills, funding and size impact missing',
            'selection_corrected':False,'closed_candle_returns_are_not_executable_fills':True,
            'calendars_and_feature_vintages_not_fully_authenticated':True}


if __name__=='__main__':
    root=Path('D:/CQWE_DATA/event_history_supplement_20261016')
    report=checked(json.loads((root/'combined_impact_report.json').read_text(encoding='utf-8')))
    learning=checked(json.loads((root/'combined_learning_report.json').read_text(encoding='utf-8')))
    rows=[checked(json.loads(Path(p).read_text(encoding='utf-8'))) for p in report['result_files']]
    result=evaluate_policy(learning,rows);result.update(input_report_sha256=report['sha256'],input_learning_sha256=learning['sha256'])
    atomic(Path('reports/event_policy_validation_20261016.json'),result)
    print(json.dumps(result['summaries']))
