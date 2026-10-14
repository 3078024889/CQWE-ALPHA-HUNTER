"""Bounded four-market *prospective* L2 / dendritic observations. No orders."""
from __future__ import annotations
import argparse,concurrent.futures,hashlib,json,shutil,time
from pathlib import Path
from .four_asset_lab_v44 import FOUR
from .l2_forward_v47 import live_forward
from .market_replay_v43 import read_chain
ROOT=Path('D:/CQWE_DATA/l2_v47')
MIN_FREE=2*1024**3
MAX_FILE=64*1024**2

def audit_file(file):
    p=Path(file)
    if not p.is_file() or p.stat().st_size>MAX_FILE:raise ValueError('MISSING_OR_OVERSIZE')
    rows=read_chain(p)
    if not rows or len([r for r in rows if r['kind']=='START'])!=1 or rows[-1]['kind']!='STOP':
        raise ValueError('INCOMPLETE_L2_SESSION')
    if not rows[-1]['payload'].get('synced'):raise ValueError('SESSION_UNSYNCED')
    prep={};settled=[];expired=[]
    for i,row in enumerate(rows):
        kind=row['kind'];data=row['payload']
        if kind=='PRECOMMIT':
            ns=data['decision_ns']
            if ns in prep or len(data['genotype_predictions'])!=6 or data['actual_fills']!=0:
                raise ValueError('INVALID_PRECOMMIT')
            if ns>row['received_ns'] or ns<0:raise ValueError('PRECOMMIT_CLOCK_CONFLICT')
            if i==0 or rows[i-1]['kind']!='BOOK' or rows[i-1]['received_ns']>ns:raise ValueError('PRECOMMIT_WITHOUT_PRIOR_BOOK')
            prep[ns]=(i,data)
        elif kind=='EXPIRED':
            key=data['decision_ns']
            if key not in prep or prep[key][0]>=i or key in expired or key in settled:
                raise ValueError('INVALID_EXPIRATION')
            expired.append(key)
        elif kind=='SETTLED':
            key=data['decision_ns']
            if key not in prep or prep[key][0]>=i or data['settled_received_ns']<key+60_000_000_000:
                raise ValueError('NONCAUSAL_SETTLEMENT')
            if i==0 or rows[i-1]['kind']!='BOOK' or rows[i-1]['received_ns']>data['settled_received_ns']:
                raise ValueError('SETTLEMENT_WITHOUT_FUTURE_BOOK')
            if key in expired or key in settled or data['actual_fills']!=0 or data['real_profit_usd']!=0:
                raise ValueError('INVALID_SETTLEMENT')
            settled.append(key)
    return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'precommits':len(prep),
            'settled':len(settled),'expired':len(expired),'unsettled':len(prep)-len(settled)-len(expired),'bytes':p.stat().st_size,
            'real_profit_usd':0,'independently_live_precommitted':True,
            'actual_fills':0,'eligible_for_real_trading':False}

def audit(root=ROOT):
    root=Path(root);result={}
    for symbol in FOUR:
        valid=[];invalid={}
        for f in sorted((root/symbol).glob('*.jsonl')):
            try:valid.append(audit_file(f))
            except (ValueError,TypeError,KeyError,UnicodeError,json.JSONDecodeError) as exc:
                invalid[f.name]=str(exc)[:120]
        result[symbol]={'sessions':len(valid),'precommits':sum(x['precommits'] for x in valid),
            'settled_events':sum(x['settled'] for x in valid),'expired_events':sum(x['expired'] for x in valid),'invalid_sessions':invalid}
    return {'schema':'CQWE_V47_PROSPECTIVE_AUDIT','symbols':result,'real_profit_usd':0,
            'real_orders':0,'strategy_profitable_proven':False,
            'limits':'4 symbols share regimes; correlated windows and paper quote marks are not independent fills'}

def collect(root=ROOT,seconds=180,free_bytes=None):
    root=Path(root)
    if root.drive.upper()!='D:':raise ValueError('D_DRIVE_REQUIRED')
    root.mkdir(parents=True,exist_ok=True)
    free=shutil.disk_usage(root).free if free_bytes is None else free_bytes
    if free<MIN_FREE:raise RuntimeError('DISK_FREE_BELOW_2_GIB_NO_CAPTURE')
    results={};errors={}
    def one(symbol):
        sub=root/symbol;sub.mkdir(exist_ok=True)
        out=live_forward(symbol=symbol,seconds=seconds,root=sub)
        return {'source_file':out['file'],**audit_file(out['file'])}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(one,s):s for s in FOUR}
        for future in concurrent.futures.as_completed(futures):
            symbol=futures[future]
            try:results[symbol]=future.result()
            except Exception as exc:errors[symbol]=f'{type(exc).__name__}:{str(exc)[:180]}'
    return {'status':'FOUR_ASSET_CAPTURED' if len(results)==4 else 'PARTIAL_FAILURE',
            'markets':results,'failures':errors,'no_orders':True,'real_profit_usd':0,
            'profitable_edge_proven':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(ROOT));p.add_argument('--seconds',type=int,default=180)
    p.add_argument('--audit-only',action='store_true');a=p.parse_args()
    if a.seconds<125 or a.seconds>300:raise SystemExit('CAPTURE_SECONDS_OUT_OF_RANGE')
    result=audit(a.root) if a.audit_only else collect(a.root,a.seconds)
    print('CQWE_V47_PROSPECTIVE '+json.dumps(result,ensure_ascii=False,sort_keys=True))
    if not a.audit_only and result['status']!='FOUR_ASSET_CAPTURED':raise SystemExit(2)
if __name__=='__main__':main()
