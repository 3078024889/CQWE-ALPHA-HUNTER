"""Read-only, closed-candle, resumable Binance Spot 5m collection for CQWE V29.
No credentials, accounts, trades or private endpoints. Do not fabricate missing candles.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from .continuous_lab_v21 import verify_saved
from .dendritic_v19 import validate_inputs

PERIOD = 300000
BASE = 'https://data-api.binance.vision/api/v3/klines'
SYMBOLS = ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT')
MAX_PAGES = 12

def _atomic_json(path, obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    tmp.replace(p)

def _digest(obj):
    raw=json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()

def _bar(source, now_ms):
    if not isinstance(source,list) or len(source)<12:raise ValueError('MALFORMED_KLINE')
    opened=int(source[0]); close_ms=int(source[6])
    if opened%PERIOD or close_ms!=opened+PERIOD-1:raise ValueError('UNEXPECTED_KLINE_TIME')
    if close_ms>=now_ms: return None # still forming, never include
    nums=[float(source[i]) for i in (1,2,3,4,5,7)]
    if any(not math.isfinite(x) for x in nums):raise ValueError('NONFINITE_KLINE')
    o,h,l,c,vol,quote=nums
    if min(o,h,l,c)<=0 or vol<0 or quote<0 or l>min(o,c) or h<max(o,c):raise ValueError('BAD_PRICE_OR_VOLUME')
    return [opened,o,h,l,c,vol,close_ms,quote,int(source[8]),float(source[9]),float(source[10]),str(source[11])]

def _download(symbol,start_ms,end_ms,fetch):
    rows=[]; cursor=start_ms
    for _ in range(MAX_PAGES):
        if cursor>end_ms:break
        raw=fetch(symbol,cursor,end_ms)
        if not isinstance(raw,list):raise ValueError('BAD_API_RESPONSE')
        if not raw:break
        prev=cursor-PERIOD
        for item in raw:
            # Verify candle is fully closed using agreed end_time, never mutable latest bar.
            bar=_bar(item,end_ms+PERIOD) # end_ms=last permitted open; closed at end_ms+PERIOD
            if bar is None:continue
            if bar[0]!=prev+PERIOD:raise ValueError('API_GAP_OR_DUPLICATE')
            rows.append(bar);prev=bar[0]
        if not rows or prev<cursor:raise ValueError('API_NO_FORWARD_PROGRESS')
        cursor=prev+PERIOD
        if len(raw)<1000:
            if cursor<=end_ms:raise ValueError('API_DATA_NOT_YET_AVAILABLE_OR_GAP')
            break
    if cursor<=end_ms:raise ValueError('API_INCOMPLETE_OR_PAGE_LIMIT')
    return rows

def _http_fetch(symbol,start,end):
    params=urllib.parse.urlencode({'symbol':symbol,'interval':'5m','startTime':start,'endTime':end,'limit':1000})
    req=urllib.request.Request(BASE+'?'+params,headers={'User-Agent':'CQWE-V29-research-market-data/1.0','Accept':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status!=200:raise RuntimeError('PUBLIC_DATA_HTTP_ERROR')
            payload=response.read(2_000_001)
            if len(payload)>2_000_000:raise ValueError('API_RESPONSE_TOO_LARGE')
            return json.loads(payload)
    except urllib.error.HTTPError as e:
        raise RuntimeError('PUBLIC_DATA_HTTP_'+str(e.code)+' (availability or regional restriction; do not bypass)') from e
    except urllib.error.URLError as e:
        raise RuntimeError('PUBLIC_DATA_NETWORK_UNAVAILABLE: '+str(e.reason)) from e

def collect(store,output_dir,fetch=None,now_ms=None):
    verified=verify_saved(store)
    first=verified['last_seen_ms']+PERIOD
    if now_ms is None:now_ms=time.time_ns()//1_000_000
    if not isinstance(now_ms,int) or now_ms<first:raise ValueError('CLOCK_BEFORE_CHECKPOINT')
    # Last candle's open must be <= now-300000 to exclude current forming candle.
    last_open=((now_ms//PERIOD)-1)*PERIOD
    root=Path(output_dir)
    manifest_path=root/'manifest_v29.json'
    existing=None
    if manifest_path.exists():
        existing=json.loads(manifest_path.read_text(encoding='utf-8'))
        unsigned={k:v for k,v in existing.items() if k!='manifest_sha256'}
        if existing.get('manifest_sha256')!=_digest(unsigned):raise ValueError('MANIFEST_TAMPERED')
        if existing.get('checkpoint_tip_sha256')!=verified['tip_sha256'] or existing.get('start_ms')!=first:
            raise ValueError('CHECKPOINT_CHANGED')
    bars_by_symbol={};new_counts={}
    for symbol in SYMBOLS:
        p=root/(symbol+'_5m.json')
        prev=[]
        if p.exists():
            if existing is None:raise ValueError('UNVERIFIED_EXISTING_DATA')
            raw=p.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=existing['source_sha256'][symbol]:raise ValueError('EXISTING_DATA_TAMPERED')
            prev=json.loads(raw.decode('utf-8'))
            if prev:
                if int(prev[0][0])!=first or any(int(b[0])!=first+i*PERIOD for i,b in enumerate(prev)):
                    raise ValueError('EXISTING_DATA_GAP')
                if int(prev[-1][0])>last_open:raise ValueError('EXISTING_BAR_FROM_FUTURE')
        start=first+len(prev)*PERIOD
        extra=_download(symbol,start,last_open,fetch or _http_fetch) if start<=last_open else []
        merged=prev+extra
        bars_by_symbol[symbol]=merged;new_counts[symbol]=len(extra)
    # Validate all four completely and synchronously *before* modifying any files.
    lengths=set(map(len,bars_by_symbol.values()))
    if len(lengths)!=1:raise ValueError('MARKET_LENGTHS_DIFFER')
    num=next(iter(lengths))
    if num>=240:
        validate_inputs(bars_by_symbol)
    else:
        for bars in bars_by_symbol.values():
            if any(int(b[0])!=first+i*PERIOD for i,b in enumerate(bars)):
                raise ValueError('INCOMPLETE_MARKET_TIMELINE')
    # Write data files before manifest; interrupted writes fail closed on next invocation.
    for sym,bars in bars_by_symbol.items():_atomic_json(root/(sym+'_5m.json'),bars)
    origins={sym:hashlib.sha256((root/(sym+'_5m.json')).read_bytes()).hexdigest() for sym in SYMBOLS}
    report={'version':'CQWE_V29_READONLY_COLLECTOR','research_only':True,'no_orders':True,
            'provider':'Binance Spot public market-data only','interval':'5m',
            'symbols':list(SYMBOLS),'checkpoint_tip_sha256':verified['tip_sha256'],
            'start_ms':first,'last_open_ms':first+(num-1)*PERIOD if num else None,
            'bars_per_symbol':num,'new_bars_by_symbol':new_counts,
            'source_sha256':origins,'forward_ready':num>=240,
            'required_bars':240,'reason':'READY_FOR_V28_OFFLINE_TEST' if num>=240 else 'WAIT_FOR_CLOSED_BARS'}
    report['manifest_sha256']=_digest(report)
    _atomic_json(manifest_path,report)
    return report

def main():
    p=argparse.ArgumentParser(description='CQWE V29 public read-only 5m closed-candle collector')
    p.add_argument('--store',default='reports/v21_evidence')
    p.add_argument('--output-dir',default='data/future')
    a=p.parse_args()
    r=collect(a.store,a.output_dir)
    print('CQWE_V29_COLLECT_PASS bars=',r['bars_per_symbol'],'new=',r['new_bars_by_symbol'],'forward_ready=',r['forward_ready'])
    print('READ ONLY | PUBLIC DATA | NO ORDERS | NO PROFIT CLAIM')
if __name__=='__main__':main()
