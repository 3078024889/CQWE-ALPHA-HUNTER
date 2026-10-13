"""CQWE V31 observational next-candle ledger, read-only public Binance 5m.
Separate public historical warmup from pre-registered forward predictions.
Never trade, retrain, mutate active weights or claim profitability.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,time,urllib.parse,urllib.request
from pathlib import Path
from .public_data_v29 import SYMBOLS,PERIOD,_bar,_digest
from .continuous_lab_v21 import verify_saved
from .forward_experiment_v28 import _load_checked,RULE
from .dendritic_v19 import features,trigger,EXPERTS

WINDOW=400
BASE='https://data-api.binance.vision/api/v3/klines'

def fetch_public(symbol,start_ms,end_ms):
    qs=urllib.parse.urlencode({'symbol':symbol,'interval':'5m','startTime':start_ms,'endTime':end_ms,'limit':1000})
    req=urllib.request.Request(BASE+'?'+qs,headers={'User-Agent':'CQWE-V31-readonly/1.0'})
    with urllib.request.urlopen(req,timeout=15) as r:
        if r.status!=200:raise RuntimeError('PUBLIC_MARKET_HTTP_FAILURE')
        data=r.read(2_000_001)
        if len(data)>2_000_000:raise ValueError('RESPONSE_TOO_LARGE')
        return json.loads(data)

def market_snapshot(*,fetch=fetch_public,now_ms=None,window=WINDOW):
    if not isinstance(window,int) or window<50 or window>1000:raise ValueError('BAD_WINDOW')
    if now_ms is None:now_ms=time.time_ns()//1_000_000
    if not isinstance(now_ms,int):raise ValueError('BAD_CLOCK')
    last_open=(now_ms//PERIOD-1)*PERIOD
    first=last_open-(window-1)*PERIOD
    markets={}
    for sym in SYMBOLS:
        raw=fetch(sym,first,last_open)
        if not isinstance(raw,list) or len(raw)!=window:raise ValueError('HISTORY_NOT_COMPLETE')
        bars=[_bar(x,now_ms) for x in raw]
        if any(x is None for x in bars):raise ValueError('UNFINISHED_BAR')
        if any(int(bar[0])!=first+i*PERIOD for i,bar in enumerate(bars)):
            raise ValueError('HISTORY_GAP_OR_MISALIGNMENT')
        markets[sym]=bars
    return last_open,markets

def _read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def _write_new(path,payload):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive create prohibits silent rewriting historical predictions.
    with p.open('x',encoding='utf-8') as f:json.dump(payload,f,sort_keys=True,indent=2,allow_nan=False)

def _digest_record(record):return _digest({k:v for k,v in record.items() if k!='record_sha256'})
def _verify(record):
    if record.get('record_sha256')!=_digest_record(record):raise ValueError('PREDICTION_RECORD_TAMPERED')

def _score(markets,weights,threshold):
    opts=[]
    for sym,bars in markets.items():
        feat=features(bars,len(bars)-1)
        for ex in EXPERTS:
            key=f'{sym}|{feat["regime"]}|{ex}'
            value=float(weights.get(key,0))
            if math.isfinite(value) and value>threshold and trigger(feat,ex):
                opts.append((-value,sym,ex,feat['regime']))
    if not opts:return {'intent':'HOLD_CASH','symbol':None,'expert':None,'weight':None}
    strength,sym,ex,reg=sorted(opts)[0]
    return {'intent':'PAPER_BUY_CANDIDATE_NOT_ORDER','symbol':sym,'expert':ex,'regime':reg,'weight':-strength}

def _settle_pending(root,last_open,markets):
    done=0
    for file in sorted(root.glob('signal_*.json')):
        record=_read(file);_verify(record)
        settle=root/('outcome_'+file.name.removeprefix('signal_'))
        if settle.exists():
            old=_read(settle);_verify(old)
            if old['signal_sha256']!=record['record_sha256']:raise ValueError('OUTCOME_LINK_BROKEN')
            continue
        target=record['target_open_ms']
        if target>last_open:continue
        # Only settle exactly when the target bar is present in the current public snapshot.
        sym=record['decision']['symbol']
        aligned={int(b[0]):b for b in markets[sym or SYMBOLS[0]]}
        if target not in aligned:continue
        b=aligned[target]
        # This is one-bar CLOSE-to-CLOSE research score, not a filled trade or net account PnL.
        at=record['observed_close'];change=(float(b[4])/float(at)-1) if sym else None
        outcome={'version':'CQWE_V31_NEXT_BAR_OUTCOME','research_only':True,'no_orders':True,
            'signal_sha256':record['record_sha256'],'target_open_ms':target,
            'observed_target_close_ms':int(b[6]),'observed_target_close':float(b[4]),
            'candidate_close_to_close_return':change,
            'not_executable_pnl':True}
        outcome['record_sha256']=_digest_record(outcome)
        _write_new(settle,outcome);done+=1
    return done

def run(store,registry,output_dir,*,fetch=fetch_public,now_ms=None,threshold=0.12):
    if threshold not in (0.10,0.12,0.20):raise ValueError('UNREGISTERED_THRESHOLD')
    reg,reg_hash,checkpoint,weights,_=_load_checked(registry,store)
    last_open,markets=market_snapshot(fetch=fetch,now_ms=now_ms)
    if last_open<=checkpoint['last_seen_ms']:raise ValueError('NO_CHRONOLOGICALLY_NEW_BAR')
    root=Path(output_dir);root.mkdir(parents=True,exist_ok=True)
    settled=_settle_pending(root,last_open,markets)
    path=root/f'signal_{last_open}.json'
    if path.exists():
        rec=_read(path);_verify(rec)
        if rec.get('checkpoint_tip_sha256')!=checkpoint['tip_sha256'] or rec.get('registry_sha256')!=reg_hash:
            raise ValueError('EXISTING_SIGNAL_CONTEXT_MISMATCH')
        return {'status':'ALREADY_RECORDED','latest_closed_open_ms':last_open,'new_outcomes':settled,'decision':rec['decision']}
    proposal=_score(markets,weights,threshold)
    # A forecast of the currently forming target bar is only valid if written
    # before it closes. Record the decision time to expose any polling delay.
    recorded_at_ms = time.time_ns()//1_000_000 if now_ms is None else now_ms
    if recorded_at_ms >= last_open + 2*PERIOD:
        raise ValueError('TARGET_CANDLE_ALREADY_CLOSED')
    close=float(markets[proposal['symbol'] or SYMBOLS[0]][-1][4])
    record={'version':'CQWE_V31_PRECOMMITTED_NEXT_BAR_SIGNAL','research_only':True,'no_orders':True,
        'not_tradable':True,'no_model_update':True,'threshold':threshold,'rule':list(RULE),
        'checkpoint_tip_sha256':checkpoint['tip_sha256'],'registry_sha256':reg_hash,
        'history_bars':WINDOW,'history_first_ms':last_open-(WINDOW-1)*PERIOD,
        'observed_last_open_ms':last_open,'target_open_ms':last_open+PERIOD,
        'observed_close':close,'recorded_at_ms':recorded_at_ms,
        'target_candle_started_before_decision':recorded_at_ms >= last_open+PERIOD,
        'markets_sha256':_digest(markets),'decision':proposal}
    record['record_sha256']=_digest_record(record)
    _write_new(path,record)
    return {'status':'SIGNAL_RECORDED','latest_closed_open_ms':last_open,'new_outcomes':settled,'decision':proposal}

def main():
    p=argparse.ArgumentParser(description='V31 read-only rolling 5m signal + next bar verification')
    p.add_argument('--store',default='reports/v21_evidence');p.add_argument('--registry',default='reports/v27_mutation_registry.json')
    p.add_argument('--output-dir',default='reports/v31_rolling_signals')
    args=p.parse_args();print('CQWE_V31_ROLLING_PASS '+json.dumps(run(args.store,args.registry,args.output_dir),sort_keys=True))
    print('HISTORICAL WARMUP | PRECOMMITTED SHADOW SIGNAL | NO ORDERS | NO PROFIT CLAIM')
if __name__=='__main__':main()
