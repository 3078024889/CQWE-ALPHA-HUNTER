"""Bounded, resumable public-data learning rounds with ten evidence checks.

This supervises research, not real trading. Code/criteria are anchored before
new captures. A failed round retains the preceding accepted model checkpoint.
"""
import argparse
import datetime
import hashlib
import json
import math
import time
from pathlib import Path

from .copernican_experiment_v81_v85 import digest
from .tidal_hunter import capture, replay, verify_capture, write_new

SOURCE_FILES = ('learning_cycle.py','tidal_hunter.py','tidal_research.py',
                'futures_orderbook.py','copernican_experiment_v81_v85.py')


def source_hashes():
    root = Path(__file__).parent
    return {n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in SOURCE_FILES}


def checked(obj):
    if obj.get('sha256') != digest({k:v for k,v in obj.items() if k != 'sha256'}):
        raise ValueError('CYCLE_RECORD_CHANGED')
    return obj


def read_history(root, anchor):
    history = []
    previous = anchor['sha256']
    for path in sorted(root.glob('round_*.json')):
        if len(history) >= 10000 or path.stat().st_size > 500000:
            raise ValueError('CYCLE_MEMORY_BUDGET')
        row = checked(json.loads(path.read_text(encoding='utf-8')))
        if row['sequence'] != len(history)+1 or row['previous'] != previous:
            raise ValueError('CYCLE_CHAIN_BROKEN')
        if path.name != f"round_{row['sequence']:06d}.json":
            raise ValueError('CYCLE_FILENAME')
        history.append(row)
        previous = row['sha256']
    return history


def audit_round(folder, report, seed, registered_ns, last_end_ns, expected_sources):
    rows = verify_capture(Path(folder)/'capture.jsonl')
    replay_result = replay(folder)
    start = rows[0]
    forecasts = {}
    matured = 0
    now = -1
    causal = True
    for row in rows:
        k,p = row['kind'],row['payload']
        if k == 'FRAME':
            now = p['now_ns']
        elif k == 'FORECAST':
            forecasts[p['decision_ns']] = row['sequence']
        elif k == 'MATURED':
            decision = p['decision_ns']
            causal &= (decision in forecasts and forecasts[decision] < row['sequence']
                       and now >= decision+5_000_000_000)
            matured += 1
    before = seed['settled'] if seed else 0
    c = report['checkpoint']
    bounded = all(m['updates'] == (0 if k == 'frozen' else c['settled'])
                  and all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=1
                          for name in ('weights','memory') for v in m[name])
                  for k,m in c['models'].items())
    checks = {
        'capture_chain': replay_result['capture_chain_verified'],
        'raw_depth_reconstruction': True,  # replay raises on a raw-vs-derived mismatch
        'model_replay': replay_result['causal_model_replay_equal'],
        'virtual_ledger_replay': replay_result['virtual_ledger_replay_equal'],
        'complete_public_session': report['status']=='COMPLETE' and not report['feed_faults'],
        'checkpoint_lineage': start['payload']['previous']==seed and c['previous_sha256']==(seed['sha256'] if seed else None),
        'mature_labels_after_forecast': bool(causal) and c['settled']-before==matured,
        'new_nonoverlapping_time': start['written_ns']>=max(registered_ns,last_end_ns),
        'source_code_frozen': source_hashes()==expected_sources,
        'model_bounds_and_account_separation': bounded and report['real_orders']==0
            and report['realized_account_profit_usdt'] is None
            and report['virtual_account']['simulated'] is True,
    }
    return checks,rows[-1]['written_ns'],matured


def summarize(anchor, history):
    accepted = [r for r in history if r['accepted_memory']]
    days = {datetime.datetime.fromtimestamp(r['end_ns']/1e9,datetime.timezone.utc).date().isoformat()
            for r in accepted}
    newest = accepted[-1]['checkpoint'] if accepted else anchor['seed_checkpoint']
    total = sum(r['new_matured_forecasts'] for r in accepted)
    gaps = [k for k,ok in {
        'at_least_5_forward_sessions':len(accepted)>=5,
        'at_least_3_utc_dates':len(days)>=3,
        'at_least_300_new_matured_forecasts':total>=300,
    }.items() if not ok]
    # Even meeting sample floors is not statistical or economic proof of alpha.
    positive = bool(newest) and any(s['n']>=30 and s['mean']>0 for k,s in newest['stats'].items()
                                    if k in ('dendritic','linear'))
    if not positive:
        gaps.append('positive_cost_adjusted_candidate_evidence')
    return {'schema':'CQWE_RECURSIVE_RESEARCH_SUMMARY_V1','recorded_rounds':len(history),
            'accepted_rounds':len(accepted),'new_matured_forecasts':total,'distinct_utc_dates':len(days),
            'missing_research_evidence':gaps,'stage':'COLLECT_MORE_EVIDENCE' if gaps else 'MANUAL_RESEARCH_REVIEW',
            'algorithm_structure_search_implemented':False,
            'model_memory_recursion_implemented':True,'real_orders':0,
            'execution_allowed':False,'profitability_proven':False}


def run(root, *, symbol='BTCUSDT', rounds=5, seconds=30, seed_checkpoint=None,
        capture_fn=capture, audit_fn=audit_round):
    if type(rounds) is not int or not 1<=rounds<=30 or type(seconds) is not int or not 15<=seconds<=600:
        raise ValueError('INVALID_RESEARCH_ROUND_BUDGET')
    root = Path(root)
    root.mkdir(parents=True,exist_ok=True)
    lock = root/'supervisor.lock'
    with lock.open('x') as f:
        f.write(str(time.time_ns()))
    try:
        path = root/'anchor.json'
        if path.exists():
            anchor = checked(json.loads(path.read_text(encoding='utf-8')))
            if seed_checkpoint is not None:
                raise ValueError('SEED_ONLY_AT_EXPERIMENT_GENESIS')
            if anchor['symbol'] != symbol or anchor['seconds_per_round'] != seconds or anchor['source_sha256'] != source_hashes():
                raise ValueError('EXPERIMENT_CONTEXT_CHANGED_USE_NEW_ROOT')
        else:
            anchor = {'schema':'CQWE_RESEARCH_ANCHOR_V1','registered_ns':time.time_ns(),
                      'symbol':symbol,'seconds_per_round':seconds,'source_sha256':source_hashes(),
                      'seed_checkpoint':seed_checkpoint,'policy':'RESEARCH_ONLY_NO_EXECUTION'}
            anchor['sha256'] = digest(anchor)
            write_new(path,anchor)
        history = read_history(root,anchor)
        good = [r for r in history if r['accepted_memory']]
        seed = good[-1]['checkpoint'] if good else anchor['seed_checkpoint']
        last_end = history[-1]['end_ns'] if history else anchor['registered_ns']
        for _ in range(rounds):
            folder,report = capture_fn(symbol,seconds,root/'sessions',seed)
            try:
                checks,end_ns,matured = audit_fn(folder,report,seed,anchor['registered_ns'],
                                                last_end,anchor['source_sha256'])
                accepted = len(checks)==10 and all(checks.values())
                error = None
            except Exception as exc:
                checks = {'evidence_replay_failed':False}
                end_ns,matured,accepted = time.time_ns(),0,False
                error = type(exc).__name__+': '+str(exc)
            row = {'sequence':len(history)+1,'previous':history[-1]['sha256'] if history else anchor['sha256'],
                   'session_dir':str(folder),'checks':checks,'accepted_memory':accepted,
                   'end_ns':end_ns,'new_matured_forecasts':matured,'error':error,
                   'checkpoint':report['checkpoint'] if accepted else seed,
                   'report_sha256':report['sha256'],'real_orders':0}
            row['sha256'] = digest(row)
            write_new(root/f"round_{row['sequence']:06d}.json",row)
            history.append(row)
            last_end = end_ns
            if not accepted:
                break  # Failure preserves the preceding accepted checkpoint.
            seed = report['checkpoint']
        result = summarize(anchor,history)
        result['history_tip_sha256'] = history[-1]['sha256'] if history else anchor['sha256']
        result['sha256'] = digest(result)
        write_new(root/f"summary_{len(history):06d}.json",result)
        return result
    finally:
        lock.unlink()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True)
    p.add_argument('--rounds',type=int,default=5)
    p.add_argument('--seconds',type=int,default=30)
    p.add_argument('--symbol',default='BTCUSDT')
    p.add_argument('--seed')
    a = p.parse_args()
    seed = json.loads(Path(a.seed).read_text(encoding='utf-8')) if a.seed else None
    print(json.dumps(run(a.root,symbol=a.symbol,rounds=a.rounds,seconds=a.seconds,seed_checkpoint=seed),indent=2))


if __name__ == '__main__':
    main()
