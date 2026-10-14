"""Four-asset durable forward learning; each symbol locked and fail-closed."""
from __future__ import annotations
import argparse, concurrent.futures, json, os, shutil, time, traceback
from pathlib import Path
from .four_asset_lab_v44 import FOUR
from .forward_lab_v47 import MIN_FREE, audit_file
from .forward_supervisor_v49 import store_report
from .l2_forward_v47 import live_forward
from .memory_v52 import ROOT as MEMORY_ROOT, symbol_lock, load, restored, commit
from .copernican_lab_v33 import Dendrite, specs

DATA=Path('D:/CQWE_DATA/l2_v47')
REPORTS=Path('D:/CQWE_DATA/l2_v52/reports')

def collect(root=DATA,memory=MEMORY_ROOT,reports=REPORTS,seconds=180):
    root=Path(root);memory=Path(memory);reports=Path(reports)
    if not 125<=seconds<=300:raise ValueError('INVALID_DURATION')
    for p in (root,memory,reports):
        if os.name=='nt' and p.drive.upper()!='D:':raise ValueError('D_DRIVE_REQUIRED')
        p.mkdir(parents=True,exist_ok=True)
    if min(shutil.disk_usage(p).free for p in (root,memory,reports))<MIN_FREE:raise RuntimeError('DISK_FREE_BELOW_2_GIB')
    begin=time.time_ns()
    def one(symbol):
        with symbol_lock(memory,symbol):
            past,past_sha=load(memory,symbol)
            models=restored(past['state']) if past else [Dendrite(sp) for sp in specs()]
            data=root/symbol;data.mkdir(parents=True,exist_ok=True)
            # One session; never splice market observations across capture restarts.
            outcome=live_forward(symbol=symbol,seconds=seconds,root=data,models=models,checkpoint_sha256=past_sha)
            validated=audit_file(outcome['file'])
            if not validated['settled']:raise ValueError('NO_VALID_SETTLEMENT')
            checkpoint=commit(memory,symbol,models,outcome['file'],past_sha,past)
            return {'source_file':outcome['file'],**validated,'memory':checkpoint}
    results={};failures={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(one,s):s for s in FOUR}
        for future in concurrent.futures.as_completed(futures):
            sym=futures[future]
            try:results[sym]=future.result()
            except Exception as exc:
                failures[sym]={'type':type(exc).__name__,'message':str(exc)[:500],
                               'traceback':traceback.format_exc(limit=5)[-1600:]}
    report={'schema':'CTI_V52_DURABLE_FORWARD','started_ns':begin,'ended_ns':time.time_ns(),
            'status':'FOUR_VERIFIED' if not failures and len(results)==4 else 'PARTIAL_FAILURE',
            'markets':results,'failures':failures,'real_orders':0,'real_profit_usd':0,
            'profitability_proven':False,'autopromotion_allowed':False}
    dest=reports/f'forward_{begin}_{os.getpid()}.json'
    report['report_file']=str(dest)
    report['report_sha256']=store_report(dest,report.copy())
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(DATA));p.add_argument('--memory',default=str(MEMORY_ROOT));p.add_argument('--reports',default=str(REPORTS));p.add_argument('--seconds',type=int,default=180)
    a=p.parse_args();result=collect(a.root,a.memory,a.reports,a.seconds)
    print('CQWE_V52_DURABLE '+json.dumps(result,sort_keys=True,ensure_ascii=False,allow_nan=False),flush=True)
    if result['status']!='FOUR_VERIFIED':raise SystemExit(2)
if __name__=='__main__':main()
