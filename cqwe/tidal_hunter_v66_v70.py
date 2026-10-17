"""V66-70: public Binance candles, immutable provenance and walk-forward dendrite research.
No private API, orders, leverage or real-money accounting. Python stdlib only.
"""
from __future__ import annotations
import hashlib,json,math,re,urllib.request,urllib.parse
from decimal import Decimal
from pathlib import Path

INTERVAL_MS={'1m':60000,'5m':300000,'15m':900000,'1h':3600000,'4h':14400000,'1d':86400000}
NAMES=('macro','microstructure','temporal','antifragility','commercial','metalearning')
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def sha(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def parse_klines(raw,interval):
    if interval not in INTERVAL_MS:raise ValueError('INVALID_INTERVAL')
    if not isinstance(raw,list) or len(raw)<40:raise ValueError('INSUFFICIENT_BARS')
    step=INTERVAL_MS[interval]; result=[];previous=None
    for row in raw:
        if not isinstance(row,list) or len(row)!=12:raise ValueError('INVALID_BAR_SCHEMA')
        t=row[0];end=row[6]
        if type(t) is not int or type(end) is not int or end!=t+step-1 or (previous is not None and t!=previous+step):raise ValueError('GAP_OR_BAD_TIMESTAMP')
        try: o,h,l,c,v=map(Decimal,(row[1],row[2],row[3],row[4],row[5]))
        except Exception:raise ValueError('INVALID_BAR_VALUE') from None
        if not all(x.is_finite() for x in (o,h,l,c,v)) or min(o,h,l,c)<=0 or v<0 or h<max(o,c) or l>min(o,c):raise ValueError('INVALID_OHLC')
        result.append({'time':t,'open':str(o),'high':str(h),'low':str(l),'close':str(c),'volume':str(v)})
        previous=t
    return result

def fetch_public(symbol='BTCUSDT',interval='1h',limit=500,*,opener=None):
    if not re.fullmatch(r'[A-Z0-9]{5,20}',symbol):raise ValueError('INVALID_SYMBOL')
    if interval not in INTERVAL_MS or type(limit)!=int or not 40<=limit<=1500:raise ValueError('INVALID_REQUEST')
    url='https://fapi.binance.com/fapi/v1/klines?'+urllib.parse.urlencode({'symbol':symbol,'interval':interval,'limit':limit})
    open_fn=opener or urllib.request.urlopen
    response=open_fn(urllib.request.Request(url,headers={'User-Agent':'CQWE-offline-research/1.0'}),timeout=15)
    with response as stream:
        body=stream.read(1500000+1)
    if len(body)>1500000:raise ValueError('RESPONSE_TOO_LARGE')
    raw=json.loads(body)
    bars=parse_klines(raw,interval)
    return {'source':'BINANCE_USDM_PUBLIC_KLINES','symbol':symbol,'interval':interval,'bars':bars,'sha256':sha(bars),'live_orders':False}

def load_verified(path):
    obj=json.loads(Path(path).read_text(encoding='utf-8'))
    if obj.get('source')!='BINANCE_USDM_PUBLIC_KLINES' or obj.get('sha256')!=sha(obj.get('bars')):raise ValueError('DATA_TAMPERED')
    interval=obj.get('interval');bars=obj['bars']; step=INTERVAL_MS.get(interval)
    if step is None or len(bars)<40:raise ValueError('INVALID_ARCHIVE')
    for i,b in enumerate(bars):
        if type(b.get('time'))!=int or (i and b['time']!=bars[i-1]['time']+step):raise ValueError('ARCHIVE_GAP')
        o,h,l,c,v=map(Decimal,(b['open'],b['high'],b['low'],b['close'],b['volume']))
        if not all(x.is_finite() for x in (o,h,l,c,v)) or min(o,h,l,c)<=0 or v<0 or h<max(o,c) or l>min(o,c):raise ValueError('INVALID_ARCHIVE_BAR')
    return obj

def features_at(bars,i):
    # Inputs available strictly through prior CLOSED candle i-1.
    c=[float(b['close']) for b in bars];v=[float(b['volume']) for b in bars]
    def clamp(x):return max(-1.,min(1.,x))
    momentum=clamp((c[i-1]/c[i-6]-1)*80)
    short=clamp((c[i-1]/c[i-3]-1)*120)
    vol=abs((c[i-1]/c[i-2]-1))*100
    imbalance=clamp((v[i-1]/(sum(v[i-6:i-1])/5+1e-12)-1)/3)
    return {'macro':momentum,'microstructure':imbalance,'temporal':short,'antifragility':clamp(1-vol),'commercial':0.,'metalearning':clamp((momentum+short)/2)}

def evaluate(bars,seed=55,fee_bps=5,slip_bps=5,folds=3):
    from cqwe.dendrite_evolution_v55 import GENOTYPES
    if tuple(GENOTYPES)!=NAMES:raise ValueError('DENDRITE_SCHEMA_MISMATCH')
    if len(bars)<100 or type(folds)!=int or folds<2:raise ValueError('NOT_ENOUGH_WALK_FORWARD_DATA')
    if min(fee_bps,slip_bps)<0 or not all(math.isfinite(v) for v in (fee_bps,slip_bps)):raise ValueError('INVALID_COST')
    import random
    rng=random.Random(seed); candidates=[]
    for key in NAMES:
        base={k:0. for k in NAMES};base[key]=1.
        candidates.append({'id':'parent_'+key,'weights':base})
        for j in range(4):
            w=dict(base);k=rng.choice(NAMES);w[k]=max(-1.,min(1.,w[k]+rng.choice((-.4,-.2,.2,.4))))
            candidates.append({'id':f'parent_{key}_child{j}','weights':w})
    # Fixed nonoverlapping test folds with strictly expanding training history.
    n=len(bars);block=(n-40)//(folds+1)
    if block<12:raise ValueError('FOLD_TOO_SMALL')
    output=[]
    for f in range(folds):
        split=40+(f+1)*block;start=split;end=min(n,split+block)
        if end-start<2:raise ValueError('INVALID_TEST_FOLD')
        def signal(w,idx):
            feats=features_at(bars,idx);value=sum(w[k]*feats[k] for k in NAMES)
            return 1 if value>.05 else (-1 if value<-.05 else 0)
        def pnl(w,lo,hi):
            # Signal at t, enter at open of t+1; exit at close of t+1.
            total=0.; trades=0
            for t in range(lo,hi-1):
                s=signal(w,t);entry=float(bars[t+1]['open']);exit=float(bars[t+1]['close'])
                if s:
                    trades+=1;total+=s*(exit/entry-1)*10000-2*(fee_bps+slip_bps)
            return total,trades
        # Select ONLY using historic bars, never the held-out fold.
        rank=sorted([(pnl(c['weights'],6,split)[0],c['id'],c) for c in candidates],key=lambda v:(-v[0],v[1]))
        winner=rank[0][2]; test,trades=pnl(winner['weights'],start,end)
        output.append({'fold':f+1,'train_end_time':bars[split-1]['time'],'test_start_time':bars[start]['time'],'test_end_time':bars[end-1]['time'],'candidate':winner['id'],'simulated_net_bps':round(test,5),'trades':trades,'cash_pnl_usd':None})
    result={'schema':'CQWE_V66_V70_WALK_FORWARD','data_sha256':sha(bars),'candidate_count':len(candidates),'folds':output,'selection_uses_test_data':False,'cost_bps_each_side':fee_bps+slip_bps,'realized_cash_profit_usd':None,'real_orders':0,'auto_promotion':False,'live_trading':False}
    result['sha256']=sha(result)
    return result

def save_immutable(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:f.write(canonical(value)+'\n')

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--fetch',action='store_true');p.add_argument('--symbol',default='BTCUSDT');p.add_argument('--interval',default='1h');p.add_argument('--limit',type=int,default=500);p.add_argument('--archive');p.add_argument('--report')
    a=p.parse_args()
    if a.fetch==bool(a.input) or not a.report:raise ValueError('USE_EITHER_FETCH_OR_INPUT_AND_REPORT')
    if a.fetch:
        if not a.archive:raise ValueError('ARCHIVE_REQUIRED')
        source=fetch_public(a.symbol,a.interval,a.limit);save_immutable(a.archive,source)
    else:source=load_verified(a.input)
    report=evaluate(source['bars']);report['symbol']=source['symbol'];report['interval']=source['interval'];report['source_sha256']=source['sha256'];report['sha256']=sha({k:v for k,v in report.items() if k!='sha256'})
    save_immutable(a.report,report)
    print('V66_V70_RESEARCH=PASS');print('FOLDS='+str(len(report['folds'])));print('LIVE_ORDERS=0')
if __name__=='__main__':main()
