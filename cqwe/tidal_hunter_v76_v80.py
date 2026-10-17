"""CQWE V76-80: verifiable offline forward-research continuity; no order API.
V76 data provenance; V77 append-only rounds; V78 trailing history memory;
V79 conservative research gate; V80 adversarial evidence controls.
"""
from __future__ import annotations
import argparse, json, math, pathlib, hashlib, re, datetime
from cqwe.tidal_hunter_v66_v70 import load_verified, evaluate, sha, canonical, save_immutable
from cqwe.tidal_hunter_v71_v75 import audit_walkforward
SCHEMA='CQWE_V80_FORWARD_MEMORY'
HEX=re.compile(r'^[0-9a-f]{64}$')
def _digest(s):
    if not isinstance(s,str) or HEX.fullmatch(s) is None: raise ValueError('INVALID_DIGEST')
    return s

def validate_archive(path):
    """Require genuine archive format and internal checksums; sha is integrity, not proof of origin."""
    obj=load_verified(path)
    if obj.get('live_orders') is not False: raise ValueError('SOURCE_LIVE_FLAG')
    if not isinstance(obj.get('symbol'),str) or not re.fullmatch(r'[A-Z0-9]{5,20}',obj['symbol']):raise ValueError('BAD_SYMBOL')
    return obj

def verify_chain(folder):
    """Verify all immutable research records and chronological monotonicity."""
    path=pathlib.Path(folder)
    if not path.exists(): return []
    if not path.is_dir():raise ValueError('MEMORY_NOT_DIRECTORY')
    files=sorted(path.glob('round_*.json'))
    if len(files)>10000:raise ValueError('MEMORY_BUDGET')
    out=[]; last_hash=None; last_end=-1
    for f in files:
        if f.stat().st_size>200000:raise ValueError('MEMORY_RECORD_TOO_LARGE')
        rec=json.loads(f.read_text(encoding='utf-8'))
        if rec.get('schema')!=SCHEMA or rec.get('record_sha256')!=sha({k:v for k,v in rec.items() if k!='record_sha256'}):raise ValueError('MEMORY_TAMPERED')
        if rec.get('sequence')!=len(out)+1 or f.name!=f"round_{rec['sequence']:06d}.json":raise ValueError('MEMORY_SEQUENCE')
        if rec.get('previous_record_sha256')!=last_hash:raise ValueError('MEMORY_CHAIN_BROKEN')
        if type(rec.get('last_bar_time')) is not int or rec['last_bar_time']<=last_end:raise ValueError('MEMORY_NON_MONOTONIC')
        if rec.get('real_orders')!=0 or rec.get('live_trading') is not False or rec.get('realized_cash_profit_usd') is not None or rec.get('promotion_eligible') is not False:raise ValueError('UNSAFE_MEMORY')
        _digest(rec.get('source_sha256'))
        if not isinstance(rec.get('research'),dict):raise ValueError('INVALID_RESEARCH')
        out.append(rec);last_hash=rec['record_sha256'];last_end=rec['last_bar_time']
    return out

def memory_summary(history,lookback=20):
    if type(lookback) is not int or not 1<=lookback<=100:raise ValueError('BAD_LOOKBACK')
    prior=history[-lookback:]
    scores=[r['research']['worst_fold_bps'] for r in prior]
    if any(type(v) not in (float,int) or not math.isfinite(v) for v in scores):raise ValueError('BAD_HISTORY_SCORE')
    return {'prior_rounds':len(prior),'positive_prior_rounds':sum(v>0 for v in scores),'prior_worst_fold_bps':min(scores) if scores else None,'previous_candidate':prior[-1]['research'].get('last_fold_candidate') if prior else None}

def plan_round(source,history,*,fee_bps=5,slip_bps=5):
    if type(fee_bps) not in (int,float) or type(slip_bps) not in (int,float) or not all(math.isfinite(x) and 0<=x<=1000 for x in (fee_bps,slip_bps)):raise ValueError('BAD_COST')
    bars=source['bars']; last=bars[-1]['time']
    if history:
        prev=history[-1]
        if source['symbol']!=prev['symbol'] or source['interval']!=prev['interval']:raise ValueError('MEMORY_MARKET_MISMATCH')
        if last<=prev['last_bar_time']:raise ValueError('NO_NEW_CLOSED_BAR')
    base=evaluate(bars,fee_bps=fee_bps,slip_bps=slip_bps)
    audit=audit_walkforward(base)
    mem=memory_summary(history)
    # Past folds only support descriptive monitoring: not proof of statistically valid alpha.
    out={'fold_count':audit['fold_count'],'total_simulated_trades':audit['trades'],'worst_fold_bps':audit['worst_fold_bps'],'last_fold_candidate':base['folds'][-1]['candidate'],'prior_memory':mem,'research_review_candidate':bool(audit['research_review_candidate']) and len(history)>=3 and all(x['research']['worst_fold_bps']>0 for x in history[-3:]),'decision':'RESEARCH_ONLY_NO_EXECUTION'}
    record={'schema':SCHEMA,'sequence':len(history)+1,'symbol':source['symbol'],'interval':source['interval'],'source_sha256':_digest(source['sha256']),'last_bar_time':last,'previous_record_sha256':history[-1]['record_sha256'] if history else None,'cost':{'fee_bps':fee_bps,'slip_bps':slip_bps},'research':out,'real_orders':0,'live_trading':False,'promotion_eligible':False,'realized_cash_profit_usd':None}
    record['record_sha256']=sha(record)
    return record

def run(input_path,memory_dir,*,fee_bps=5,slip_bps=5):
    src=validate_archive(input_path);history=verify_chain(memory_dir)
    record=plan_round(src,history,fee_bps=fee_bps,slip_bps=slip_bps)
    dst=pathlib.Path(memory_dir)/f"round_{record['sequence']:06d}.json"
    save_immutable(dst,record)
    return dst,record

def main():
    p=argparse.ArgumentParser(description='Offline-only research memory. Never places live orders.')
    p.add_argument('--input',required=True);p.add_argument('--memory-dir',required=True);p.add_argument('--fee-bps',type=float,default=5);p.add_argument('--slip-bps',type=float,default=5)
    a=p.parse_args();file,rec=run(a.input,a.memory_dir,fee_bps=a.fee_bps,slip_bps=a.slip_bps)
    print('V80_FORWARD_MEMORY=PASS');print('ROUND='+str(rec['sequence']));print('RECORD='+str(file.resolve()));print('RESEARCH_REVIEW_CANDIDATE='+str(rec['research']['research_review_candidate']));print('REAL_ORDERS=0')
if __name__=='__main__':main()
