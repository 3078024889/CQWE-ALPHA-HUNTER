"""CQWE V40 public spot microstructure *observational* lab.

Independent original implementation informed by open-source design patterns.
A REST order-book snapshot cannot measure cancellations, true OFI, queue
position, market maker identity, or executable maker fills. No orders.
"""
from __future__ import annotations
import argparse, json, math, os, time, urllib.parse, urllib.request
from pathlib import Path
from .public_data_v29 import _digest

VERSION='CQWE_V40_PUBLIC_MICROSTRUCTURE_SHADOW'
BASE='https://data-api.binance.vision/api/v3/'
SYMBOLS=('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT')
HORIZON_MS=300000
MAX_SNAPSHOT_AGE_MS=30000

def _number(x, *, positive=False):
    if isinstance(x,bool): raise ValueError('INVALID_NUMERIC_VALUE')
    try: v=float(x)
    except (TypeError,ValueError) as exc: raise ValueError('INVALID_NUMERIC_VALUE') from exc
    if not math.isfinite(v) or (positive and v<=0) or (not positive and v<0): raise ValueError('INVALID_NUMERIC_VALUE')
    return v

def analyze(depth,trades,*,symbol,started_ms,ended_ms,excluded_stale_trades=0):
    if symbol not in SYMBOLS:raise ValueError('SYMBOL_NOT_ALLOWED')
    if not isinstance(started_ms,int) or not isinstance(ended_ms,int) or ended_ms<started_ms:raise ValueError('INVALID_OBSERVATION_CLOCK')
    if ended_ms-started_ms>MAX_SNAPSHOT_AGE_MS:raise ValueError('SNAPSHOT_TOO_SLOW')
    if not isinstance(depth,dict) or not isinstance(trades,list):raise ValueError('INVALID_MARKET_PAYLOAD')
    if not isinstance(excluded_stale_trades,int) or isinstance(excluded_stale_trades,bool) or excluded_stale_trades<0:raise ValueError('INVALID_STALE_TRADE_COUNT')
    def levels(side,reverse):
        raw=depth.get(side)
        if not isinstance(raw,list) or not 1<=len(raw)<=100:raise ValueError('INVALID_BOOK_LEVELS')
        values=[]
        for entry in raw:
            if not isinstance(entry,list) or len(entry)<2:raise ValueError('INVALID_LEVEL')
            price=_number(entry[0],positive=True);qty=_number(entry[1],positive=True)
            values.append((price,qty))
        if values!=sorted(values,key=lambda x:x[0],reverse=reverse):raise ValueError('BOOK_NOT_SORTED')
        if len(set(x[0] for x in values))!=len(values):raise ValueError('DUPLICATE_LEVEL')
        return values
    bids=levels('bids',True);asks=levels('asks',False)
    bid,bsize=bids[0];ask,asize=asks[0]
    if bid>=ask:raise ValueError('CROSSED_BOOK')
    mid=(bid+ask)/2
    top_imb=(bsize-asize)/(bsize+asize)
    n=min(5,len(bids),len(asks))
    bid_sum=sum(q for _,q in bids[:n]);ask_sum=sum(q for _,q in asks[:n])
    imbalance=(bid_sum-ask_sum)/(bid_sum+ask_sum)
    microprice=(ask*bsize+bid*asize)/(bsize+asize)
    buyer=0.;seller=0.;last_trade_ms=None
    if len(trades)>1000:raise ValueError('TOO_MANY_TRADES')
    for trade in trades:
        if not isinstance(trade,dict):raise ValueError('BAD_TRADE')
        tm=trade.get('T')
        if not isinstance(tm,int) or tm>ended_ms+1000 or tm<ended_ms-300000:raise ValueError('TRADE_TIMESTAMP_OUT_OF_WINDOW')
        px=_number(trade.get('p'),positive=True);qty=_number(trade.get('q'),positive=True)
        flag=trade.get('m')
        if not isinstance(flag,bool):raise ValueError('TRADE_SIDE_MISSING')
        # Binance m=true: buyer is maker, i.e. seller was aggressor.
        if flag:seller+=px*qty
        else:buyer+=px*qty
        last_trade_ms=max(tm,last_trade_ms or tm)
    total=buyer+seller
    aggression=(buyer-seller)/total if total else None
    spread_bps=(ask-bid)/mid*10000
    # Descriptive classification only, never a buy signal or observed MM identity.
    if spread_bps>=15:regime='WIDE_SPREAD_EXECUTION_RISK'
    elif abs(imbalance)>=.35 and aggression is not None and imbalance*aggression>0:
        regime='BOOK_AND_TAKER_PRESSURE_ALIGNED'
    elif aggression is not None and abs(imbalance)>=.35 and imbalance*aggression<0:
        regime='BOOK_AND_TAKER_PRESSURE_DIVERGE'
    else:regime='NO_CONFIRMED_PRESSURE'
    return {'symbol':symbol,'bid':bid,'ask':ask,'mid':mid,'spread_bps':spread_bps,
        'top_imbalance':top_imb,'depth5_imbalance':imbalance,'microprice':microprice,
        'microprice_displacement_bps':(microprice-mid)/mid*10000,
        'aggressor_buy_notional':buyer,'aggressor_sell_notional':seller,
        'aggressor_imbalance':aggression,'trade_count':len(trades),'latest_trade_ms':last_trade_ms,
        'excluded_stale_trades':excluded_stale_trades,'trade_payload_count':len(trades)+excluded_stale_trades,
        'book_update_id':depth.get('lastUpdateId'), 'regime':regime,
        'snapshot_start_ms':started_ms,'recorded_at_ms':ended_ms,
        'prediction_horizon_end_ms':ended_ms+HORIZON_MS,
        'trade_window_completeness':'STALE_RECORDS_EXCLUDED_REST_LIMITED' if excluded_stale_trades else 'UNKNOWN_REST_LIMITED',
        'queue_fill_known':False,'market_maker_identity_known':False,
        'not_a_trading_signal':True}

def _fetch(endpoint,params):
    query=urllib.parse.urlencode(params)
    req=urllib.request.Request(BASE+endpoint+'?'+query,headers={'User-Agent':'CQWE-v40-public-observer/1.0'})
    with urllib.request.urlopen(req,timeout=12) as response:
        if response.status!=200:raise RuntimeError('PUBLIC_API_HTTP_NOT_OK')
        raw=response.read(1_000_001)
    if len(raw)>1_000_000:raise ValueError('PUBLIC_RESPONSE_TOO_LARGE')
    return json.loads(raw)

def collect_once(symbol='BNBUSDT',fetch=_fetch,clock=lambda:time.time_ns()//1_000_000):
    if symbol not in SYMBOLS:raise ValueError('SYMBOL_NOT_ALLOWED')
    start=clock()
    depth=fetch('depth',{'symbol':symbol,'limit':20})
    trades=fetch('aggTrades',{'symbol':symbol,'limit':100})
    end=clock()
    # The public aggTrades endpoint returns the most recent prints, NOT a guaranteed
    # five-minute sample. Older valid prints are quarantined, never used as current
    # aggression; malformed or future-dated prints still fail closed in analyze().
    if not isinstance(trades,list):raise ValueError('INVALID_MARKET_PAYLOAD')
    if len(trades)>1000:raise ValueError('TOO_MANY_TRADES')
    fresh=[];old=0
    for trade in trades:
        if not isinstance(trade,dict):raise ValueError('BAD_TRADE')
        tm=trade.get('T')
        if not isinstance(tm,int) or isinstance(tm,bool):raise ValueError('TRADE_TIMESTAMP_OUT_OF_WINDOW')
        if tm<end-300000:
            # Validate excluded rows too; never silently conceal malformed prices.
            _number(trade.get('p'),positive=True)
            _number(trade.get('q'),positive=True)
            if not isinstance(trade.get('m'),bool):raise ValueError('TRADE_SIDE_MISSING')
            old+=1
        else:
            fresh.append(trade)
    return analyze(depth,fresh,symbol=symbol,started_ms=start,ended_ms=end,excluded_stale_trades=old)

def _verify(record):
    if record.get('sha256')!=_digest({k:v for k,v in record.items() if k!='sha256'}):raise ValueError('MICRO_RECORD_HASH_MISMATCH')

def store_record(result,root='reports/v40_microstructure'):
    folder=Path(root);folder.mkdir(parents=True,exist_ok=True)
    if result.get('not_a_trading_signal') is not True:raise ValueError('NOT_OBSERVATIONAL')
    record={'version':VERSION,'research_only':True,'no_orders':True,'no_real_profit':True,
        'observed_market':result,'source':'Binance Spot public REST depth and aggTrades; non-atomic',
        'limitations':'Depth is snapshot, trades are last up to 100 aggregate prints; queue, latency, cancel flow, fill and maker identities unknown'}
    record['sha256']=_digest(record)
    name=f"observation_{result['symbol']}_{result['recorded_at_ms']}.json"
    target=folder/name
    if target.exists():
        old=json.loads(target.read_text(encoding='utf-8'));_verify(old)
        if old!=record:raise ValueError('OBSERVATION_COLLISION')
        return str(target),'ALREADY_RECORDED'
    with target.open('x',encoding='utf-8') as f:json.dump(record,f,sort_keys=True,indent=2,allow_nan=False)
    return str(target),'OBSERVATION_RECORDED'

def audit(root='reports/v40_microstructure'):
    records=[]
    for p in sorted(Path(root).glob('observation_*.json')):
        r=json.loads(p.read_text(encoding='utf-8'));_verify(r)
        if r.get('version')!=VERSION or r.get('no_orders') is not True:raise ValueError('UNTRUSTED_RECORD')
        records.append(r['observed_market'])
    by_symbol={}
    for r in records:by_symbol.setdefault(r['symbol'],[]).append(r)
    return {'version':VERSION,'total_observations':len(records),'by_symbol':{
        sym:{'count':len(seq),'latest_recorded_at_ms':max(x['recorded_at_ms'] for x in seq),
        'median_spread_bps':sorted(x['spread_bps'] for x in seq)[len(seq)//2],
        'regime_counts':{k:sum(x['regime']==k for x in seq) for k in sorted(set(x['regime'] for x in seq))}}
        for sym,seq in by_symbol.items()},'profitable_edge_proven':False,'real_profit_usd':0.,
        'strictly_observational':True,'next_step':'Collect 100+ independent timestamped depth/trade snapshots; evaluate future quote changes only after registration; never infer limit-order fills from REST snapshot.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--symbol',choices=SYMBOLS,default='BNBUSDT')
    p.add_argument('--root',default='reports/v40_microstructure')
    p.add_argument('--offline-audit',action='store_true');a=p.parse_args()
    if not a.offline_audit:
        r=collect_once(a.symbol);path,status=store_record(r,a.root)
        print('CQWE_V40_MICROSTRUCTURE_PASS '+json.dumps({'status':status,'record':path,'regime':r['regime'],'spread_bps':r['spread_bps'],'depth5_imbalance':r['depth5_imbalance'],'aggressor_imbalance':r['aggressor_imbalance']},sort_keys=True))
    print('CQWE_V40_AUDIT '+json.dumps(audit(a.root),sort_keys=True))
    print('PUBLIC MARKET DATA | NO ORDERS | NO MARKET MAKER IDENTIFICATION | NO PROFIT CLAIM')
if __name__=='__main__':main()
