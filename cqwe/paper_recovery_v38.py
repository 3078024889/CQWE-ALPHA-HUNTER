"""V38: conservative, auditable restart of a flat, untraded $10 paper study.

Historical journals remain immutable; each new segment is a fresh experiment,
NOT a continuation of PnL, and must be reported separately. No real trading.
"""
from __future__ import annotations
import argparse, json, os, time
from pathlib import Path
from .live_paper_v33 import cycle, CASH0
from .operational_truth_v37 import _read_account
from .public_data_v29 import PERIOD, _digest

VERSION='CQWE_V38_FLAT_ONLY_SEGMENT_RECOVERY'


def _manifest_hash(rec):
    return _digest({k:v for k,v in rec.items() if k!='sha256'})


def _atomic_new(path:Path, rec):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(rec,f,sort_keys=True,indent=2,allow_nan=False)
        f.flush();os.fsync(f.fileno())


def _inspect(path:Path, now:int):
    info=_read_account(path,now_ms=now)
    if info['status']=='NO_ACCOUNT_FRAMES':return None
    # Ledger audit includes frame SHA chain, event replay, fee reconciliation.
    return info


def _safe_restart(info):
    if info is None:raise ValueError('NO_PREVIOUS_JOURNAL_TO_RECOVER')
    if info['paper_open_position'] is not None or info['paper_pending_intent'] is not None:
        raise ValueError('UNRESOLVED_POSITION_OR_PENDING_MANUAL_REVIEW_REQUIRED')
    if (info['paper_buys'] or info['paper_adds'] or info['paper_sells'] or
        info['paper_completed_positions'] or abs(info['paper_equity_usd']-CASH0)>1e-8 or
        abs(info['paper_cash_usd']-CASH0)>1e-8 or info['recorded_paper_fees_usd']>1e-8):
        raise ValueError('NONZERO_TRADE_OR_PNL_REQUIRES_MANUAL_REVIEW')
    return True


def _load_manifests(root:Path):
    records=[]
    for path in sorted(root.glob('segment_*.json')):
        try: rec=json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError,UnicodeError) as e:raise ValueError('SEGMENT_MANIFEST_UNREADABLE') from e
        if rec.get('sha256')!=_manifest_hash(rec):raise ValueError('SEGMENT_MANIFEST_HASH_MISMATCH')
        if rec.get('version')!=VERSION or not rec.get('no_orders'):raise ValueError('SEGMENT_MANIFEST_BAD_VERSION')
        if path.name!=f"segment_{rec['index']:06d}.json" or rec['index']!=len(records):
            raise ValueError('SEGMENT_MANIFEST_SEQUENCE_INVALID')
        if rec['previous_manifest_sha256']!=(records[-1]['sha256'] if records else None):
            raise ValueError('SEGMENT_MANIFEST_CHAIN_BROKEN')
        folder=root/rec['directory']
        if not folder.is_dir():raise ValueError('SEGMENT_DIRECTORY_MISSING')
        # Never silently accept an invalid existing account, including intermediate segments.
        _inspect(folder,time.time_ns()//1_000_000)
        records.append(rec)
    unknown=[p for p in root.glob('segment_*') if p.is_dir() and not (root/(p.name+'.json')).exists()]
    if unknown:raise ValueError('UNREGISTERED_SEGMENT_DIRECTORY_REQUIRES_REVIEW')
    return records


def run(*,store='reports/v21_evidence',registry='reports/v27_mutation_registry.json',
        legacy='reports/v33_cash_account',root='reports/v38_cash_segments',now_ms=None,cycle_fn=cycle):
    if now_ms is None:now_ms=time.time_ns()//1_000_000
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    lock=root/'.writer.lock'
    try:lock.mkdir()
    except FileExistsError as e:raise ValueError('PAPER_WRITER_BUSY_MANUAL_CHECK_LOCK') from e
    try:
        records=_load_manifests(root)
        if not records:
            old=_inspect(Path(legacy),now_ms)
            _safe_restart(old)
            from_source={'kind':'V33_LEGACY','last_open_ms':old['last_open_ms'],
                         'verified_frame_count':old['frame_count'],'verified_equity_usd':old['paper_equity_usd']}
        else:
            active=root/records[-1]['directory'];current=_inspect(active,now_ms)
            if current is None:
                raise ValueError('ACTIVE_SEGMENT_EMPTY_REQUIRES_REVIEW')
            from_source=None
            try:
                output=cycle_fn(store,registry,str(active))
                return {'status':output['status'],'segment':records[-1]['index'],
                        'paper_equity_usd':output['equity_usd'],'no_orders':True,
                        'real_profit_usd':0.,'not_continuous_pnl':True}
            except ValueError as e:
                if str(e)!='MISSED_BARS_FAIL_CLOSED_NO_RETROSPECTIVE_FILLS':raise
                _safe_restart(current)
                from_source={'kind':'V38_SEGMENT','last_open_ms':current['last_open_ms'],
                             'verified_frame_count':current['frame_count'],
                             'verified_equity_usd':current['paper_equity_usd']}
        index=len(records)
        directory=f'segment_{index:06d}'
        folder=root/directory
        folder.mkdir(exist_ok=False)
        manifest={'version':VERSION,'index':index,'directory':directory,
                  'previous_manifest_sha256':records[-1]['sha256'] if records else None,
                  'source':from_source,'no_orders':True,'no_autopromotion':True,
                  'new_experiment_start_cash_usd':CASH0,
                  'historical_fills_replayed':False,'real_profit_usd':0.0}
        manifest['sha256']=_manifest_hash(manifest)
        _atomic_new(root/f'segment_{index:06d}.json',manifest)
        output=cycle_fn(store,registry,str(folder))
        return {'status':'SEGMENT_STARTED','segment':index,'cycle_status':output['status'],
                'paper_equity_usd':output['equity_usd'],'no_orders':True,
                'real_profit_usd':0.,'not_continuous_pnl':True}
    finally:
        lock.rmdir()


def main():
    p=argparse.ArgumentParser(description='Conservative flat paper restart, no real orders')
    p.add_argument('--store',default='reports/v21_evidence')
    p.add_argument('--registry',default='reports/v27_mutation_registry.json')
    p.add_argument('--legacy',default='reports/v33_cash_account')
    p.add_argument('--root',default='reports/v38_cash_segments')
    a=p.parse_args();result=run(store=a.store,registry=a.registry,legacy=a.legacy,root=a.root)
    print('CQWE_V38_PAPER_RECOVERY_PASS '+json.dumps(result,sort_keys=True))
    print('INDEPENDENT PAPER SEGMENTS | NO LIVE ORDERS | NO CONTINUOUS PROFIT CLAIM')
if __name__=='__main__':main()


def segment_truth(*,root='reports/v38_cash_segments',now_ms=None):
    if now_ms is None:now_ms=time.time_ns()//1_000_000
    base=Path(root);records=_load_manifests(base)
    items=[]
    for rec in records:
        info=_inspect(base/rec['directory'],now_ms)
        if info is None:raise ValueError('SEGMENT_WITHOUT_ACCOUNT_RECORD')
        items.append({'index':rec['index'],'status':info['status'],'frames':info['frame_count'],
                      'paper_net_equity_usd':info['paper_net_equity_usd'],
                      'last_open_ms':info['last_open_ms'],'manifest_sha256':rec['sha256']})
    return {'version':VERSION,'segment_count':len(items),'segments':items,
            'latest_segment':items[-1] if items else None,
            'independent_starting_balances':True,'cumulative_profit_not_claimed':True,
            'real_profit_usd':0.,'no_real_orders':True}
