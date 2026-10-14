"""CQWE V3.7 read-only operational / cash-account truth gate.

Combines *verified* tree-lineage evidence with the separate V3.3 $10 paper
account. This is an audit, not a trading or promotion engine. No API keys,
no orders, no historical backfilling. Account outcomes are not real money.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import time
from pathlib import Path
from .evolution_supervisor_v35 import context_hash
from .evidence_health_v36 import longitudinal
from .live_paper_v33 import _check_existing, _safe, CASH0, MIN_NOTIONAL
from .copernican_lab_v33 import digest
from .public_data_v29 import PERIOD


def _read_account(root: str | Path, *, now_ms: int) -> dict:
    folder=Path(root)
    frames=list(folder.glob('frame_*.json')) if folder.is_dir() else []
    if not frames:
        return {'status':'NO_ACCOUNT_FRAMES', 'frame_count':0, 'account_profit_proven':False,
                'real_profit_usd':0.0, 'paper_net_equity_usd':None,
                'paper_equity_usd':None, 'notional_minimum_unverified_usd':MIN_NOTIONAL}
    frames.sort(key=lambda p:int(p.stem.removeprefix('frame_')))
    # Scan the whole chain via V33's canonical verifier, not just the last frame.
    first=json.loads(frames[0].read_text(encoding='utf-8'))
    context=first['context_sha256']
    last_open=int(frames[-1].stem.removeprefix('frame_'))
    last=_check_existing(folder,last_open,context)
    if last is None or len(frames)<1:raise ValueError('ACCOUNT_CHAIN_EMPTY')
    state=last['state']
    equity=_safe(state['equity']);cash=_safe(state['cash']);fees=_safe(state['fees'])
    if fees<0 or state['closed_positions']<0:raise ValueError('ACCOUNT_INVALID_TOTALS')
    # Fee reconciliation: only count actual *paper* events, not rejected intents.
    event_fees=0.;buys=sells=adds=0
    replay_cash=CASH0;replay_qty=0.0
    for path in frames:
        rec=json.loads(path.read_text(encoding='utf-8'))
        for event in rec['events']:
            action=event['action']
            if action in ('BUY','SELL','ADD'):
                if event.get('hypothetical') is not True:raise ValueError('PAPER_EVENT_NOT_HYPOTHETICAL')
                event_fees+=_safe(event['fee_usd'])
                qty=_safe(event['qty']);gross=_safe(event['gross_usd']);fee=_safe(event['fee_usd'])
                if qty<=0 or gross<=0 or fee<0:raise ValueError('INVALID_PAPER_FILL')
                if action=='BUY':buys+=1
                elif action=='SELL':sells+=1
                else:adds+=1
                if action in ('BUY','ADD'):
                    replay_cash-=gross+fee;replay_qty+=qty
                else:
                    replay_cash+=gross-fee;replay_qty-=qty
                if replay_cash < -1e-6 or replay_qty < -1e-8:raise ValueError('PAPER_REPLAY_NEGATIVE_CASH_OR_POSITION')
            elif action != 'REJECT_MIN_NOTIONAL':raise ValueError('UNKNOWN_PAPER_EVENT')
    if abs(event_fees-fees)>1e-7:raise ValueError('ACCOUNT_FEE_LEDGER_MISMATCH')
    if abs(replay_cash-cash)>1e-6 or abs(replay_qty-_safe(state['qty']))>1e-8:
        raise ValueError('ACCOUNT_EVENT_CASH_OR_INVENTORY_MISMATCH')
    if sells!=state['closed_positions']:raise ValueError('ACCOUNT_EXIT_COUNTER_MISMATCH')
    net=equity-CASH0
    if buys==0 and abs(net)<1e-8:status='NO_TRADES'
    elif net < -1e-8:status='PAPER_LOSS'
    elif net > 1e-8:status='PAPER_POSITIVE_NOT_REAL_PROFIT'
    else:status='PAPER_FLAT'
    return {'status':status,'frame_count':len(frames), 'last_open_ms':last_open,
            'age_since_last_closed_ms':max(0,now_ms-(last_open+PERIOD)),
            'paper_equity_usd':equity,'paper_cash_usd':cash,'paper_net_equity_usd':net,
            'recorded_paper_fees_usd':fees,'paper_buys':buys,'paper_adds':adds,'paper_sells':sells,
            'paper_completed_positions':sells,'paper_open_position':state['symbol'],
            'paper_pending_intent':last['pending'], 'paper_max_drawdown_pct':_safe(state['max_drawdown_pct']),
            'account_profit_proven':False,'real_profit_usd':0.0,
            'notional_minimum_unverified_usd':MIN_NOTIONAL,
            'limitations':'Paper open-price fill assumptions, exchange min-notional unverified, no real receipts or independent validated edge.'}


def evaluate(*, store, registry, lineages, account, now_ms=None):
    if now_ms is None:now_ms=time.time_ns()//1_000_000
    context=context_hash(store,registry)
    evidence=longitudinal(lineages,context,now_ms=now_ms)
    paper=_read_account(account,now_ms=now_ms)
    flags=[]
    if evidence['freshness']!='FRESH':flags.append('RESEARCH_DATA_NOT_FRESH')
    if evidence['observed_gaps']>0:flags.append('PAST_MISSING_BARS_NO_HINDSIGHT_FILL')
    if paper['status']=='NO_ACCOUNT_FRAMES':flags.append('NO_ACCOUNT_EVIDENCE')
    elif paper['age_since_last_closed_ms']>2*PERIOD+60_000:flags.append('PAPER_ACCOUNT_STALE_OR_TASK_DELAY')
    if paper['status']=='PAPER_LOSS':flags.append('PAPER_ACCOUNT_LOSING')
    if paper['status']=='PAPER_POSITIVE_NOT_REAL_PROFIT':flags.append('PAPER_GAIN_NOT_PROVEN_EDGE')
    if any(x['status']=='RESEARCH_ONLY_REQUIRES_NEW_INDEPENDENT_HOLDOUT' for x in evidence['candidate_comparison']):
        flags.append('UNCONFIRMED_RESEARCH_SIGNALS')
    result={'version':'CQWE_V37_OPERATIONAL_TRUTH','generated_at_ms':now_ms,
            'research_only':True,'no_orders':True,'no_auto_promotion':True,
            'realized_real_profit_usd':0.0,'real_receipts_verified':False,
            'paper_account':paper,
            'dendrite_research':{'epoch_count':evidence['epoch_count'],'settled_steps_by_candidate':
                [x['settled_steps'] for x in evidence['candidate_comparison']],
                'candidate_statuses':[x['status'] for x in evidence['candidate_comparison']],
                'freshness':evidence['freshness'],'observed_gap_bars':evidence['observed_gaps'],
                'last_open_ms':evidence['last_open_ms'],'evidence_sha256':evidence['sha256'],
                'weight_inheritance_enabled':False},
            'alerts':flags,
            'decision':'RESEARCH_ONLY_NO_LIVE_TRADING',
            'next_action':'Continue audited forward observations; do not infer profit or change production model.'}
    result['sha256']=digest(result)
    return result


def atomic_write(output,report):
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False),encoding='utf-8')
    os.replace(temp,path)


def main():
    parser=argparse.ArgumentParser(description='V37 audited paper-account and longitudinal research truth gate, NO ORDERS')
    parser.add_argument('--store',default='reports/v21_evidence')
    parser.add_argument('--registry',default='reports/v27_mutation_registry.json')
    parser.add_argument('--lineages',default='reports/v35_lineages')
    parser.add_argument('--account',default='reports/v33_cash_account')
    parser.add_argument('--output',default='reports/v37_operational_truth.json')
    args=parser.parse_args()
    report=evaluate(store=args.store,registry=args.registry,lineages=args.lineages,account=args.account)
    atomic_write(args.output,report)
    print('CQWE_V37_TRUTH_PASS '+json.dumps({'paper_status':report['paper_account']['status'],
        'paper_net_usd':report['paper_account']['paper_net_equity_usd'],
        'research_freshness':report['dendrite_research']['freshness'],
        'alerts':report['alerts']},sort_keys=True))
    print('NO REAL ORDERS | NO VERIFIED PROFIT | NO AUTO PROMOTION')

if __name__=='__main__':main()
