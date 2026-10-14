"""V46 independent falsification of V45 competitive replay and $10 feasibility.

This is NOT a paper execution engine. No fill, maker identity or profit claim.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
from .evolution_cycle_v45 import audit as replay_audit, extract_events
from .four_asset_lab_v44 import FOUR
from .market_replay_v43 import read_chain

DATA=Path('D:/CQWE_DATA/l2_v44')
OUT=Path('D:/CQWE_DATA/research_v46')
CAPITAL=10.0
MAX_ORDER_FRACTION=.6
MIN_NOTIONAL_ASSUMED=5.0
MIN_TRAIN=100
MIN_HOLDOUT=100


def _sha(d):
    return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def assess(root=DATA, outdir=OUT, *, preserve=True):
    root=Path(root);outdir=Path(outdir)
    base=replay_audit(root,outdir/'v45_replay')
    markets={};alerts=[]
    for symbol in FOUR:
        info=base['markets'][symbol]
        n=info['decisions'];train=int(n*.60);holdout=n-train
        files=list(sorted((root/symbol).glob('*.jsonl')))
        verified=info['sessions'];rejected=[k for k in base['rejected_sessions'] if k in {f.name for f in files}]
        # Static feasibility illustration only, exchange symbol filters and actual fees unknown.
        max_ticket=CAPITAL*MAX_ORDER_FRACTION
        eligibility='SYMBOL_FILTERS_UNVERIFIED'
        gates={
          'verified_complete_capture':verified>0 and not rejected,
          'enough_training_events':train>=MIN_TRAIN,
          'enough_independent_holdout_events':holdout>=MIN_HOLDOUT,
          'precommitted_live_oos':False,
          'actual_order_fills':False,
          'exchange_filters_verified':False,
          'real_fee_tier_verified':False,
          'execution_latency_measured':False,
          'net_profit_after_costs_verified':False,
          'no_account_reset_compounding':True,
        }
        if n==0:reason='NO_CAUSALLY_MATURED_EVENTS'
        elif not gates['enough_training_events']:reason='INSUFFICIENT_TRAINING_EVENTS'
        elif not gates['enough_independent_holdout_events']:reason='INSUFFICIENT_HOLDOUT_EVENTS'
        else:reason='NO_PRECOMMITTED_EXECUTABLE_OOS'
        if not gates['verified_complete_capture']:alerts.append(symbol+':MISSING_OR_INVALID_SESSIONS')
        markets[symbol]={'sealed_sessions':verified,'rejected_sessions':len(rejected),
          'nonoverlap_events':n,'train_events':train,'historical_holdout_events':holdout,
          'max_hypothetical_ticket_usd':max_ticket,'assumed_min_notional_usd':MIN_NOTIONAL_ASSUMED,
          'symbol_filter_status':eligibility,'gates':gates,'candidate_status':reason,
          'proven_trading_profit_usd':0.0,'promoted_candidates':0}
    result={'schema':'CQWE_V46_FALSIFICATION','markets':markets,'alerts':alerts,
      'source_replay_sha256':base['sha256'],'real_order_count':0,
      'real_profit_usd':0.0,'promotion_allowed':False,'research_only':True,
      'rankable_markets':[],
      'trade_readiness':'BLOCKED_NO_INDEPENDENT_EXECUTABLE_OOS',
      'disk_policy':'NO_AUTOMATIC_DELETION_OF_RAW_DATA_OR_LOGS',
      'limitations':'Replay cannot prove live execution. Exchange min-notional and actual fee schedules not retrieved. '
                    'No maker order identity/queue position or real fills; $10 budget cannot be treated as leverage.'}
    result['sha256']=_sha(result)
    if preserve:
        outdir.mkdir(parents=True,exist_ok=True)
        dest=outdir/('readiness_'+result['sha256']+'.json')
        if dest.exists():
            if json.loads(dest.read_text('utf8'))!=result:raise ValueError('AUDIT_OUTPUT_CONFLICT')
        else:dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(DATA));p.add_argument('--output-dir',default=str(OUT));a=p.parse_args()
    d=assess(a.root,a.output_dir)
    print('CQWE_V46_READINESS',json.dumps({'events':{s:v['nonoverlap_events'] for s,v in d['markets'].items()},
      'train':{s:v['train_events'] for s,v in d['markets'].items()},'holdout':{s:v['historical_holdout_events'] for s,v in d['markets'].items()},
      'promotion_allowed':d['promotion_allowed'],'sha256':d['sha256']},sort_keys=True))
    print('NO FILL CLAIM | NO TRADING | NO RANKING ON SMALL DATA | D DRIVE DATA')
if __name__=='__main__':main()
