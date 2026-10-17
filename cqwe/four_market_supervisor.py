"""Bounded automatic recovery using the last replay-verified virtual checkpoint.

Failed evidence is retained. Recovery creates a new attempt directory; it never
deletes locks, overwrites a failed round, changes code or expands risk limits.
"""
import argparse
import json
import os
import shutil
import time
from pathlib import Path

from .copernican_experiment_v81_v85 import digest
from .four_market_core import config
from .four_market_runner import checked, replay_round, run, sources
from .tidal_hunter import write_new


def latest_good(root, replay_fn=replay_round):
    found = []
    for pointer in root.glob('attempt_*/LATEST.json'):
        if pointer.parent.is_symlink():
            raise ValueError('SUPERVISOR_SYMLINK_NOT_ALLOWED')
        p = checked(json.loads(pointer.read_text(encoding='utf-8')))
        name = p['round_name']
        if not isinstance(name,str) or len(name)!=12 or not name.startswith('round_') or not name[6:].isdigit():
            raise ValueError('SUPERVISOR_POINTER_PATH')
        folder = pointer.parent/name
        if not folder.resolve().is_relative_to(root.resolve()):
            raise ValueError('SUPERVISOR_PATH_ESCAPE')
        st = checked(json.loads((folder/'state.json').read_text(encoding='utf-8')))
        if p['state_sha256'] != st['sha256'] or st['source_sha256'] != sources():
            raise ValueError('SUPERVISOR_STATE_SOURCE_CHANGED')
        audit = replay_fn(folder)
        if sum(type(v) is bool and v for v in audit.values()) != 10:
            raise ValueError('SUPERVISOR_CHECKPOINT_REPLAY_FAILED')
        found.append((st['engine']['rounds'],folder,p))
    return max(found,key=lambda r:r[0]) if found else None


def supervise(root, *, rounds=5, seconds=300, horizons=(300,900), attempts=3,
              catalog=True, event_inbox=None, run_fn=run, replay_fn=replay_round):
    if type(attempts) is not int or not 1 <= attempts <= 5 or type(rounds) is not int or not 1 <= rounds <= 288:
        raise ValueError('SUPERVISOR_BUDGET')
    if type(seconds) is not int or not 15 <= seconds <= 3600 or rounds*seconds > 86400:
        raise ValueError('SUPERVISOR_TIME_BUDGET')
    cfg = config(horizons)
    root = Path(root)
    root.mkdir(parents=True,exist_ok=True)
    lock = root/'supervisor.lock'
    with lock.open('x') as f:
        f.write(str(os.getpid()))
    try:
        context = {'config':cfg,'seconds':seconds,'source_sha256':sources()}
        anchor_path = root/'anchor.json'
        if anchor_path.exists():
            anchor = checked(json.loads(anchor_path.read_text(encoding='utf-8')))
            if anchor['context'] != context:
                raise ValueError('SUPERVISOR_CONTEXT_CHANGED_USE_NEW_ROOT')
        else:
            anchor = {'context':context,'created_ns':time.time_ns()}
            anchor['sha256'] = digest(anchor)
            write_new(anchor_path,anchor)
        outcomes = []
        for _ in range(attempts):
            good = latest_good(root,replay_fn)
            completed = good[0] if good else 0
            if completed >= rounds:
                return {'status':'TARGET_COMPLETED','completed_rounds':completed,'attempts_this_call':outcomes,'real_orders':0}
            existing = list(root.glob('attempt_*'))
            if len(existing) >= 1000:
                raise ValueError('SUPERVISOR_ARCHIVE_BUDGET')
            child = root/f'attempt_{len(existing)+1:04d}'
            child.mkdir(exist_ok=False)
            if good:
                # Copy rather than move: original evidence remains reviewable.
                shutil.copytree(good[1],child/good[1].name)
                write_new(child/'LATEST.json',good[2])
            try:
                run_fn(child,rounds=rounds-completed,seconds=seconds,horizons=horizons,
                       catalog=catalog,event_inbox=event_inbox)
                status,error = 'RUN_RETURNED',None
            except Exception as exc:
                status,error = 'RECOVERY_REQUIRED',type(exc).__name__+': '+str(exc)
            record = {'attempt':child.name,'status':status,'error':error,'started_from_round':completed,
                      'at_ns':time.time_ns(),'real_orders':0,'source_sha256':sources()}
            record['sha256'] = digest(record)
            write_new(child/'supervisor_result.json',record)
            outcomes.append(record)
        good = latest_good(root,replay_fn)
        completed = good[0] if good else 0
        return {'status':'TARGET_COMPLETED' if completed>=rounds else 'REPAIR_BUDGET_EXHAUSTED',
                'completed_rounds':completed,'attempts_this_call':outcomes,'real_orders':0}
    finally:
        lock.unlink()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='D:/CQWE_DATA/copernican_liquidity_v2')
    p.add_argument('--rounds',type=int,default=5)
    p.add_argument('--seconds',type=int,default=300)
    p.add_argument('--horizons',default='300,900')
    p.add_argument('--attempts',type=int,default=3)
    p.add_argument('--no-catalog',action='store_true')
    p.add_argument('--event-inbox')
    a = p.parse_args()
    result = supervise(a.root,rounds=a.rounds,seconds=a.seconds,horizons=tuple(int(h) for h in a.horizons.split(',')),
                       attempts=a.attempts,catalog=not a.no_catalog,event_inbox=a.event_inbox)
    print(json.dumps(result,ensure_ascii=False))
    if result['status'] != 'TARGET_COMPLETED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
