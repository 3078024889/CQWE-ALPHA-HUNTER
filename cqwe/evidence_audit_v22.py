"""CQWE V22: independent, read-only evidence audit of V21 sequential learning.
The evidence ledger is hash-consistency-verified by V21 before use. No fills / account PnL.
A recomputed hash chain is not an external signature or proof of chain provenance.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from .continuous_lab_v21 import verify_saved, atomic
from .self_evolution_v20 import RULES, sha

SCHEMA_V22=22
MIN_EVENTS=20
Z=2.0

def _finite(x):
    return isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x)

def _verdict(event,previous=None,min_events=MIN_EVENTS):
    if not isinstance(event,dict) or event.get('n') is None or not isinstance(event['n'],int) or event['n']<0:
        raise ValueError('INVALID_EVENT_COUNT')
    n=event['n']; avg=event.get('mean'); lcb=event.get('lcb')
    if n==0:
        if avg is not None or lcb is not None:raise ValueError('EMPTY_METRIC_INCONSISTENT')
        return 'NO_EVENTS'
    if not _finite(avg):raise ValueError('NONFINITE_MEAN')
    if n<min_events:return 'INSUFFICIENT_EVENTS'
    if not _finite(lcb):raise ValueError('NONFINITE_LCB')
    if lcb>avg+1e-9:raise ValueError('LCB_ABOVE_MEAN')
    if lcb>0:return 'POSITIVE_RESEARCH_SIGNAL_NOT_TRADABLE'
    return 'NO_VERIFIED_POSITIVE_EDGE'

def audit(store,min_events=MIN_EVENTS):
    if not isinstance(min_events,int) or min_events<5:raise ValueError('BAD_MIN_EVENTS')
    provenance=verify_saved(store)
    root=Path(store)
    ledger=json.loads((root/'ledger.json').read_text(encoding='utf-8'))
    records=[]; overall={rule:[] for rule in RULES}
    first=None
    for ep in ledger['episodes']:
        ix=ep['index']
        if ix!=len(records):raise ValueError('EPISODE_ORDER_MISMATCH')
        report=json.loads((root/ep['report']).read_text(encoding='utf-8'))
        state=json.loads((root/ep['checkpoint']).read_text(encoding='utf-8'))
        if ix==0:
            if report.get('research_only') is not True or state.get('schema')!=20:
                raise ValueError('INITIAL_RESEARCH_EVIDENCE_INVALID')
            first={'promoted':report.get('promoted'), 'holdout_selected_events':report.get('holdout_selected_events'),
                   'holdout_mean_net_event_fraction':report.get('holdout_mean_net_event_fraction'),
                   'research_only':True}
            records.append({'index':0,'kind':'INITIAL_SELECTION','status':'SEALED_DIAGNOSTIC_NOT_REPEATABLE',
                            'mutations_tested':report.get('mutations_tested')})
            continue
        entry=report.get('event')
        if report.get('mode')!='PREQUENTIAL' or report.get('not_independent_holdout') is not True or not isinstance(entry,dict):
            raise ValueError('PREQUENTIAL_REPORT_INVALID')
        if entry!=state['journal'][-1] or entry.get('status')!='ADAPTIVE_PREQUENTIAL_NOT_INDEPENDENT_HOLDOUT':
            raise ValueError('JOURNAL_REPORT_MISMATCH')
        if entry['segment_end_ms']!=ep['last_seen_ms'] or entry['segment_start_ms']>entry['segment_end_ms']:
            raise ValueError('INVALID_SEGMENT_TIME')
        if len(entry['research'])!=len(RULES):raise ValueError('MISSING_MUTATION_EVIDENCE')
        decisions=[]
        if not isinstance(entry['matured_events'],int) or entry['matured_events']<0:raise ValueError('BAD_MATURITY')
        for item,expected_rule in zip(entry['research'],RULES):
            rule=(item.get('learning_rate'),item.get('decay'))
            if rule!=expected_rule or not isinstance(item.get('weight_sha256'),str) or len(item['weight_sha256'])!=64:
                raise ValueError('RULE_NOT_REPRODUCIBLE')
            event=item.get('prequential')
            status=_verdict(event,min_events=min_events)
            if item.get('events')!=event['n'] or item['events']>entry['matured_events']:
                raise ValueError('EVENT_COUNT_MISMATCH')
            row={'rule':list(rule),'matured_selected_events':event['n'],
                 'mean_net_event_fraction':event.get('mean'), 'reported_lcb':event.get('lcb'),
                 'status':status}
            decisions.append(row)
            overall[rule].append(row)
        records.append({'index':ix,'kind':'ADAPTIVE_PREQUENTIAL',
                        'start_ms':entry['segment_start_ms'],'end_ms':entry['segment_end_ms'],
                        'total_matured_events':entry['matured_events'],'rules':decisions})
    rule_summary=[]
    for rule,rows in overall.items():
        eligible=sum(r['status']=='POSITIVE_RESEARCH_SIGNAL_NOT_TRADABLE' for r in rows)
        negatives=sum(r['status']=='NO_VERIFIED_POSITIVE_EDGE' for r in rows)
        rule_summary.append({'rule':list(rule),'segments':len(rows),
                             'positive_research_segments':eligible,'nonpositive_segments':negatives,
                             'total_selected_events':sum(r['matured_selected_events'] for r in rows),
                             'conclusion':'INSUFFICIENT_INDEPENDENT_EVIDENCE',
                             'notes':'Repeated segments and candidate variants cannot be pooled as iid returns.'})
    summary={'schema':SCHEMA_V22,'research_only':True,'trading_authorized':False,
             'realized_profit_usd':None,'virtual_portfolio_pnl_usd':None,
             'verified_tip_sha256':provenance['tip_sha256'],
             'verified_episodes':provenance['verified_episodes'],
             'initial_sealed_diagnostic':first,'rule_summary':rule_summary,'episodes':records,
             'decision':'NO_AUTOMATIC_PROMOTION',
             'why':'A positive selected-event bound is not evidence of executable account profit; repeated adaptation contaminates independent claims.',
             'audit_sha256':None}
    summary['audit_sha256']=sha({k:v for k,v in summary.items() if k!='audit_sha256'})
    return summary

def main():
    parser=argparse.ArgumentParser(description='CQWE V22 evidence-gated read-only evolution audit')
    parser.add_argument('--store',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--min-events',type=int,default=MIN_EVENTS)
    a=parser.parse_args()
    target=Path(a.output)
    if target.resolve()==(Path(a.store)/'ledger.json').resolve() or target.resolve().is_relative_to(Path(a.store).resolve()):
        raise ValueError('OUTPUT_INSIDE_EVIDENCE_STORE_FORBIDDEN')
    result=audit(a.store,a.min_events)
    atomic(target,result)
    print('CQWE_V22_EVIDENCE_AUDIT_PASS episodes=',result['verified_episodes'],
          'autopromotion=DISABLED | NO ORDERS | NO PROFIT CLAIM')
if __name__=='__main__':main()
