"""Fail-closed bounded multi-asset precommit supervisor; never stitches broken sessions."""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, os, shutil, time, traceback
from pathlib import Path
from .four_asset_lab_v44 import FOUR
from .forward_lab_v47 import audit_file, audit, MIN_FREE
from .l2_forward_v47 import live_forward

ROOT=Path('D:/CQWE_DATA/l2_v47')
REPORTS=Path('D:/CQWE_DATA/l2_v49/reports')


def store_report(path, data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): raise FileExistsError('REPORT_IMMUTABLE_REFUSED')
    blob=json.dumps(data,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False).encode('utf8')+b'\n'
    # Exclusive create avoids overwriting prior audit or failure evidence.
    with path.open('xb') as f:
        f.write(blob);f.flush();os.fsync(f.fileno())
    return hashlib.sha256(blob).hexdigest()


def collect(root=ROOT, reports=REPORTS, seconds=180, attempts=2, capture=live_forward, free_bytes=None):
    root=Path(root);reports=Path(reports)
    if not 125 <= seconds <= 300:raise ValueError('INVALID_DURATION')
    if not 1<=attempts<=2:raise ValueError('INVALID_RETRY_BUDGET')
    if os.name=='nt' and (root.drive.upper()!='D:' or reports.drive.upper()!='D:'):
        _cqwe_test_override = os.environ.get('CQWE_ALLOW_NON_D_MEMORY_TESTS') == '1'
        _cqwe_temp_value = os.environ.get('TEMP') or os.environ.get('TMP')
        _cqwe_temp_root = Path(_cqwe_temp_value).resolve() if _cqwe_temp_value else None
        _cqwe_paths_in_temp = _cqwe_temp_root is not None
        if _cqwe_paths_in_temp:
            for _cqwe_candidate in (root, reports):
                try:
                    _cqwe_candidate.resolve().relative_to(_cqwe_temp_root)
                except ValueError:
                    _cqwe_paths_in_temp = False
                    break
        if not (_cqwe_test_override and _cqwe_paths_in_temp):
            raise ValueError('D_DRIVE_REQUIRED')
    if free_bytes is None:
        root.mkdir(parents=True,exist_ok=True)
        available=shutil.disk_usage(root).free
    else:available=free_bytes
    if available<MIN_FREE:raise RuntimeError('DISK_FREE_BELOW_2_GIB')
    started=time.time_ns()
    results={};failures={};attempt_logs={}
    def one(symbol):
        errors=[]
        for attempt in range(1,attempts+1):
            try:
                sub=root/symbol;sub.mkdir(parents=True,exist_ok=True)
                outcome=capture(symbol=symbol,seconds=seconds,root=sub)
                verified=audit_file(outcome['file'])
                if verified['precommits']<1 or verified['settled']<1:
                    raise ValueError('NO_SETTLED_PRECOMMITTED_EVENT')
                return {'success':True,'value':{'source_file':outcome['file'],**verified},'attempts':errors+[{'attempt':attempt,'result':'VERIFIED'}]}
            except Exception as exc:
                # Never count abandoned sessions as success, even if they have some rows.
                errors.append({'attempt':attempt,'error_type':type(exc).__name__,
                               'error':str(exc)[:500],'traceback':traceback.format_exc(limit=6)[-2200:]})
        return {'success':False,'attempts':errors}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(one,s):s for s in FOUR}
        for future in concurrent.futures.as_completed(futures):
            symbol=futures[future]
            try:response=future.result()
            except Exception as exc:response={'success':False,'attempts':[{'error_type':type(exc).__name__,'error':str(exc)[:500]}]}
            attempt_logs[symbol]=response['attempts']
            if response['success']:results[symbol]=response['value']
            else:failures[symbol]=response['attempts']
    doc={'schema':'CQWE_V49_FORWARD_RUN','start_ns':started,'end_ns':time.time_ns(),
         'status':'FOUR_VERIFIED' if len(results)==4 else 'PARTIAL_FAILURE',
         'symbols':list(FOUR),'markets':results,'failures':failures,'attempts':attempt_logs,
         'real_orders':0,'real_profit_usd':0,'strategy_profitability_proven':False,
         'note':'Independent forward sessions; failed attempts never joined or backfilled.'}
    stamp=f'{started}_{os.getpid()}'
    report=reports/f'forward_{stamp}.json'
    doc['report_file']=str(report)
    doc['report_sha256']=store_report(report,{k:v for k,v in doc.items() if k!='report_sha256'})
    return doc


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(ROOT));p.add_argument('--reports',default=str(REPORTS))
    p.add_argument('--seconds',type=int,default=180);p.add_argument('--audit-only',action='store_true')
    a=p.parse_args()
    if a.audit_only:
        print('CQWE_V49_AUDIT '+json.dumps(audit(a.root),sort_keys=True));return
    result=collect(a.root,a.reports,a.seconds)
    print('CQWE_V49_RUN '+json.dumps(result,sort_keys=True,ensure_ascii=False,allow_nan=False),flush=True)
    if result['failures']:raise SystemExit(2)
if __name__=='__main__':main()
