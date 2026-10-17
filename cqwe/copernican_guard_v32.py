"""Public-market-data-only guarded paper runner for Copernican V32.

The engine's fill model is close-only indicative, not exchange execution or
intrabar stop/target validation. This module never sends real orders.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import math
import os
import pathlib
import sys
import time
import traceback
from contextlib import contextmanager

from . import copernican_v32 as core
from . import copernican_paper_v32 as paper

PERIOD_MS = 300_000
SYMBOLS = set(core.SYMBOLS)


def validated_report(report, now_ms=None, max_age_ms=900_000):
    if report.get('real_orders') != 0 or report.get('mode') != 'PUBLIC_DATA_PAPER_ONLY':
        raise ValueError('NOT_PAPER_ONLY')
    ds = report.get('decisions')
    if not isinstance(ds, list) or len(ds) != len(SYMBOLS) or {d.get('symbol') for d in ds} != SYMBOLS:
        raise ValueError('FOUR_ASSET_DECISIONS_REQUIRED')
    stamps = [d.get('asof_ms') for d in ds]
    if any(not isinstance(t, int) for t in stamps) or len(set(stamps)) != 1:
        raise ValueError('MISSING_OR_MISALIGNED_CLOSED_BARS')
    t = stamps[0]
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    age = now_ms - (t + PERIOD_MS)
    if t % PERIOD_MS or age < 0 or age > max_age_ms:
        raise ValueError(f'UNFINISHED_OR_STALE_CANDLE age_ms={age}')
    selected = [d for d in ds if d.get('portfolio_selected')]
    if len(selected) > 2 or len({d.get('action') for d in selected}) > 1:
        raise ValueError('CONFLICTING_BASKET_DIRECTIONS')
    for d in ds:
        p = d.get('entry_reference')
        if not isinstance(p, (float, int)) or not math.isfinite(p) or p <= 0:
            raise ValueError('INVALID_REFERENCE_PRICE')
        if d.get('action') not in ('HOLD', 'LONG', 'SHORT'):
            raise ValueError('INVALID_ACTION')
        if d.get('portfolio_selected'):
            side = d['action']
            stop, target = d.get('stop_invalidation'), d.get('dynamic_exit_reference')
            if side == 'LONG' and not (isinstance(stop, (float, int)) and isinstance(target, (float, int)) and 0 < stop < p < target):
                raise ValueError('INVALID_LONG_STRUCTURE')
            if side == 'SHORT' and not (isinstance(stop, (float, int)) and isinstance(target, (float, int)) and 0 < target < p < stop):
                raise ValueError('INVALID_SHORT_STRUCTURE')
            if d.get('event_veto'):
                raise ValueError('EVENT_VETO_WAS_NOT_APPLIED')
            trailing_distance = d.get('trailing_stop_distance_fraction')
            if trailing_distance is not None and (isinstance(trailing_distance, bool) or not isinstance(trailing_distance, (int, float)) or not math.isfinite(trailing_distance) or not 0 < trailing_distance < 0.5):
                raise ValueError('INVALID_TRAILING_STOP_DISTANCE')
            trailing_price = d.get('trailing_stop', d.get('trailing_stop_price'))
            if trailing_price is not None and (isinstance(trailing_price, bool) or not isinstance(trailing_price, (int, float)) or not math.isfinite(trailing_price) or trailing_price <= 0):
                raise ValueError('INVALID_TRAILING_STOP_PRICE')
    return t


def atomic_json(path, value):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp.' + str(os.getpid()))
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def audit_record(log_file, obj):
    p = pathlib.Path(log_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str, separators=(',', ':')) + '\n')
        f.flush()


def guarded_cycle(state_path, report_path, audit_path, *, run_once=core.run_once, now_ms=None):
    # This function is invoked under the process lock by the CLI.
    report = run_once()
    stamp = validated_report(report, now_ms=now_ms)
    state = paper.load(state_path)
    if int(state.get('last_processed_bar_ms', -1)) >= stamp:
        audit_record(audit_path, {'time': dt.datetime.now(dt.timezone.utc).isoformat(), 'event': 'SKIP_DUPLICATE_BAR', 'bar_ms': stamp})
        return {'status': 'SKIP_DUPLICATE_BAR', 'bar_ms': stamp}
    # No intrabar execution claims. Legacy V32 step uses only close references.
    candidate = copy.deepcopy(state)
    summary = paper.step(candidate, report)
    sides = {p['side'] for p in candidate['positions'].values()}
    if len(sides) > 1 or not set(candidate['positions']).issubset(SYMBOLS):
        raise ValueError('INVALID_PAPER_PORTFOLIO')
    if not math.isfinite(summary['equity']):
        raise ValueError('INVALID_EQUITY')
    candidate['last_processed_bar_ms'] = stamp
    candidate['execution_model'] = 'INDICATIVE_5M_CLOSE_ONLY_NO_INTRABAR_FILLS'
    candidate['real_orders'] = 0
    # State is committed before external evidence records so a restarted process
    # cannot accidentally re-open the same 5-minute bar.
    atomic_json(state_path, candidate)
    atomic_json(report_path, report)
    audit_record(audit_path, {'time': dt.datetime.now(dt.timezone.utc).isoformat(), 'event': 'PAPER_CYCLE',
                              'bar_ms': stamp, 'regime': report['regime'], 'selected': [d['symbol'] for d in report['decisions'] if d['portfolio_selected']],
                              'equity': summary['equity'], 'positions': summary['opened'], 'closed': summary['closed'],
                              'evidence_sha256': report['evidence_sha256'], 'real_orders': 0})
    return {'status': 'PAPER_CYCLE', 'bar_ms': stamp, **summary}


@contextmanager
def one_instance(lock_path):
    p = pathlib.Path(lock_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a+b') as f:
        f.seek(0)
        f.write(b'0')
        f.flush()
        if os.name == 'nt':
            import msvcrt
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as e:
                raise RuntimeError('ANOTHER_V32_GUARD_IS_RUNNING') from e
            try:
                yield
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as e:
                raise RuntimeError('ANOTHER_V32_GUARD_IS_RUNNING') from e
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def main(argv=None):
    ap = argparse.ArgumentParser(description='CQWE V32 guarded public-feed paper (never real orders)')
    ap.add_argument('--root', default='D:/CQWE_DATA/copernican_v32')
    ap.add_argument('--cycles', type=int, default=144)
    ap.add_argument('--poll-seconds', type=int, default=300)
    ap.add_argument('--retry-seconds', type=int, default=60)
    args = ap.parse_args(argv)
    if not 1 <= args.cycles <= 1000 or not 60 <= args.poll_seconds <= 3600 or not 30 <= args.retry_seconds <= 3600:
        ap.error('invalid cycle/poll/retry range')
    root = pathlib.Path(args.root)
    if not root.is_absolute() or root.drive.upper() == 'C:':
        ap.error('root must be an absolute path on a non-C drive')
    for sub in ('logs', 'paper', 'reports', 'temp'):
        (root / sub).mkdir(parents=True, exist_ok=True)
    state = root/'paper'/'copernican_v32_state.json'
    report = root/'reports'/'copernican_v32_latest.json'
    log = root/'logs'/'paper_guard.jsonl'
    with one_instance(root/'paper'/'copernican_v32_guard.lock'):
        audit_record(log, {'event': 'GUARD_START', 'pid': os.getpid(), 'time': dt.datetime.now(dt.timezone.utc).isoformat(), 'real_orders': 0})
        print('V32_GUARD_START | REAL_ORDERS=0 | ROOT=' + str(root), flush=True)
        for i in range(args.cycles):
            try:
                result = guarded_cycle(state, report, log)
                print(json.dumps({'cycle': i+1, **result}, ensure_ascii=False), flush=True)
                wait = args.poll_seconds
            except Exception as e:
                audit_record(log, {'event': 'ERROR', 'cycle': i+1, 'error': str(e), 'traceback': traceback.format_exc()[-4000:]})
                print(f'V32_GUARD_RETRY: {type(e).__name__}: {e}', file=sys.stderr, flush=True)
                wait = args.retry_seconds
            if i < args.cycles-1:
                time.sleep(wait)
        audit_record(log, {'event': 'GUARD_STOP', 'time': dt.datetime.now(dt.timezone.utc).isoformat()})

if __name__ == '__main__':
    main()
