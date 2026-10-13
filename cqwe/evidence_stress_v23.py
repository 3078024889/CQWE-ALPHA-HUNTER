"""CQWE V23: cost sensitivity and replication diagnostics on verified adaptive evidence.
Never infer executable PnL, independent confidence, or transaction feasibility from event summaries.
Read-only on V21 evidence store; all extra costs are *hypothetical* roundtrip basis points.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from .evidence_audit_v22 import audit
from .continuous_lab_v21 import atomic
from .self_evolution_v20 import sha

DEFAULT_COSTS=(0,5,10,20)
SCHEMA=23

def normalize_costs(costs):
    if not isinstance(costs,(tuple,list)) or not costs or len(costs)>20:
        raise ValueError('BAD_COST_SCENARIOS')
    if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<0 or v>1000 for v in costs):
        raise ValueError('BAD_EXTRA_COST_BPS')
    out=tuple(float(v) for v in costs)
    if len(out)!=len(set(out)) or tuple(sorted(out))!=out:raise ValueError('COSTS_MUST_BE_ASCENDING_UNIQUE')
    return out

def stress(audit_report,extra_cost_bps=DEFAULT_COSTS, min_separate_positive_episodes=3):
    costs=normalize_costs(extra_cost_bps)
    if not isinstance(min_separate_positive_episodes,int) or min_separate_positive_episodes<2:
        raise ValueError('BAD_REPLICATION_THRESHOLD')
    if audit_report.get('schema')!=22 or audit_report.get('decision')!='NO_AUTOMATIC_PROMOTION':
        raise ValueError('V22_AUDIT_REQUIRED')
    rows=audit_report.get('episodes')
    if not isinstance(rows,list) or not rows:raise ValueError('EPISODES_REQUIRED')
    episodes=[e for e in rows if e.get('kind')=='ADAPTIVE_PREQUENTIAL']
    if not episodes:raise ValueError('PREQUENTIAL_EVENTS_REQUIRED')
    rules=audit_report.get('rule_summary')
    if not isinstance(rules,list) or not rules:raise ValueError('RULES_REQUIRED')
    result=[]
    for obj in rules:
        rule=obj['rule']; per=[next((r for r in ep['rules'] if r['rule']==rule),None) for ep in episodes]
        if any(r is None for r in per):raise ValueError('RULE_MISSING_IN_EPISODE')
        scenarios=[]
        for bps in costs:
            drift=bps/10000.
            detail=[]; positives=0; neg=0; no_events=0; too_few=0; lower_available=0
            for ep,row in zip(episodes,per):
                n=row['matured_selected_events'];mean=row['mean_net_event_fraction'];lower=row['reported_lcb']
                if n==0:
                    if mean is not None or lower is not None:raise ValueError('EMPTY_METRIC_INCONSISTENT')
                    status='NO_EVENTS';no_events+=1; adjusted_mean=None; adjusted_lower=None
                else:
                    if not isinstance(mean,(float,int)) or not math.isfinite(mean):raise ValueError('BAD_MEAN')
                    adjusted_mean=mean-drift
                    if lower is not None:
                        if not isinstance(lower,(float,int)) or not math.isfinite(lower):raise ValueError('BAD_LOWER_BOUND')
                        adjusted_lower=lower-drift;lower_available+=1
                    else:adjusted_lower=None
                    if n<20:status='INSUFFICIENT_EVENTS';too_few+=1
                    elif adjusted_lower is None:status='BOUND_UNAVAILABLE'
                    elif adjusted_lower>0:status='POSITIVE_ADAPTIVE_RESEARCH_ONLY';positives+=1
                    else:status='NONPOSITIVE_OR_COST_ERODED';neg+=1
                detail.append({'index':ep['index'],'n':n,'mean_after_extra_cost':adjusted_mean,
                               'reported_lcb_after_extra_cost':adjusted_lower,'status':status})
            threshold_met=positives>=min_separate_positive_episodes
            scenarios.append({'extra_roundtrip_cost_bps':bps,'positive_episodes':positives,
                 'nonpositive_episodes':neg,'no_event_episodes':no_events,'low_sample_episodes':too_few,
                 'episodes_with_reported_bounds':lower_available,'replication_count_gate_met':threshold_met,
                 'note':'Count gate is descriptive only, not independent inference; overlapping adaptive learning.',
                 'episodes':detail})
        result.append({'rule':rule,'total_selected_events_reported':obj['total_selected_events'],
                       'scenarios':scenarios,'decision':'RESEARCH_ONLY_NEEDS_NEW_PROSPECTIVE_DATA'})
    data={'schema':SCHEMA,'source_v22_audit_sha256':audit_report.get('audit_sha256'),
          'verified_tip_sha256':audit_report['verified_tip_sha256'],
          'verified_episodes':audit_report['verified_episodes'],
          'extra_roundtrip_cost_bps_scenarios':list(costs),
          'rules':result,'trading_authorized':False,'automatic_promotion':False,
          'realized_profit_usd':None,'virtual_portfolio_pnl_usd':None,
          'conclusion':'ADAPTIVE_AGGREGATE_ONLY_NO_PROVEN_EXECUTABLE_EDGE',
          'limitations':['Extra cost is deterministic sensitivity, not reconstructed fills or realistic dynamic gas.',
          'Reported LCB comes from V20; not independently recalculated from raw event returns.',
          'Repeated episodes and four variants involve dependence/multiple testing; positive segment bounds are not independent proof.',
          'No unified $10 cash account, actual fills, lot filters, spreads, gas, or execution timestamps are modeled.',
          'The rule used for future trading must be frozen BEFORE collecting new validation data.']}
    data['stress_sha256']=sha(data)
    return data

def run(store,output,extra_cost_bps=DEFAULT_COSTS):
    target=Path(output)
    if target.resolve().is_relative_to(Path(store).resolve()):raise ValueError('OUTPUT_INSIDE_EVIDENCE_STORE_FORBIDDEN')
    a=audit(store)
    report=stress(a,extra_cost_bps=extra_cost_bps)
    atomic(target,report)
    return report

def main():
    p=argparse.ArgumentParser(description='CQWE V23 read-only adaptive-evidence cost and replication stress lab')
    p.add_argument('--store',required=True);p.add_argument('--output',required=True)
    p.add_argument('--extra-cost-bps',nargs='+',type=float,default=list(DEFAULT_COSTS))
    args=p.parse_args();r=run(args.store,args.output,args.extra_cost_bps)
    for item in r['rules']:
        print('rule=',item['rule'],'positive_episode_counts_by_cost=',
              [v['positive_episodes'] for v in item['scenarios']])
    print('CQWE_V23_COST_STRESS_PASS | ADAPTIVE EVIDENCE ONLY | NO ORDERS | NO PNL CLAIM')
if __name__=='__main__':main()
