"""Bounded offline catch-up. Historical learning is separate from live evidence."""
import copy
import json
import math
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import urlopen

from .four_market_core import Model, SYMBOLS

STEP = 300000


def public(endpoint, params=None):
    if endpoint not in ('time','klines'):
        raise ValueError('HISTORY_ENDPOINT_NOT_ALLOWED')
    url = 'https://fapi.binance.com/fapi/v1/'+endpoint
    if params:
        url += '?'+urlencode(params)
    with urlopen(url,timeout=10) as response:
        raw = response.read(1500001)
    if len(raw)>1500000:
        raise ValueError('HISTORY_RESPONSE_BUDGET')
    return json.loads(raw)


def closed_bars(raw, now_ms):
    if not isinstance(raw,list) or len(raw)>1000:
        raise ValueError('HISTORY_PAGE_SCHEMA')
    bars=[]
    for row in raw:
        if not isinstance(row,list) or len(row)!=12:
            raise ValueError('HISTORY_BAR_SCHEMA')
        t,end=row[0],row[6]
        if type(t) is not int or type(end) is not int or end!=t+STEP-1:
            raise ValueError('HISTORY_TIME')
        if end>=now_ms:
            continue
        o,h,l,c,v=map(Decimal,(row[1],row[2],row[3],row[4],row[5]))
        if not all(x.is_finite() for x in (o,h,l,c,v)) or min(o,h,l,c)<=0 or v<0 or h<max(o,c) or l>min(o,c):
            raise ValueError('HISTORY_OHLC')
        if bars and t!=bars[-1]['time']+STEP:
            raise ValueError('HISTORY_PAGE_GAP')
        bars.append({'time':t,'close':str(c),'volume':str(v)})
    return bars


def initial(now_ms, days=30):
    if type(days) is not int or not 1<=days<=730:
        raise ValueError('HISTORY_BOOTSTRAP_DAYS')
    start=(now_ms//STEP)*STEP-days*86400000
    return {'schema':'CQWE_OFFLINE_CURRICULUM_V1','historical_only':True,
            'bootstrap_days':days,'symbols':{s:{'cursor':start,'tail':[], 'pending':{},
             'models':{str(h):{k:Model(k).state() for k in ('branch2','branch4','linear','frozen')}
                       for h in (300,900)},'labels':{'300':0,'900':0},'dropped':0,
             'loss':{str(h):{k:0. for k in ('branch2','branch4','linear','frozen')} for h in (300,900)}}
             for s in SYMBOLS},'next_symbol':0,'pages':0,'profitability_proven':False}


def learn_page(state,symbol,bars):
    d=state['symbols'][symbol]
    models={h:{} for h in d['models']}
    for h,bank in d['models'].items():
        for k,st in bank.items():
            m=Model(k);m.__dict__.update(copy.deepcopy(st));m.validate();models[h][k]=m
    for bar in bars:
        t=bar['time']
        if t<d['cursor']:
            continue
        if d['tail'] and t!=d['tail'][-1]['time']+STEP:
            d['dropped']+=len(d['pending']);d['pending']={};d['tail']=[]
        price=float(bar['close'])
        for h,f in list(d['pending'].items()):
            if t<f['due']:
                continue
            del d['pending'][h]
            if t!=f['due'] or price==f['price']:
                d['dropped']+=1
                continue
            y=int(price>f['price']);d['labels'][h]+=1
            for k,m in models[h].items():
                p,cache=f['predictions'][k]
                d['loss'][h][k]+=(p-y)**2
                m.learn(f['x'],y,p,cache)
        tail=d['tail']
        if len(tail)>=3:
            x=[math.tanh((price/float(tail[-i]['close'])-1)*100) for i in (1,2,3)]
            x+=[math.tanh((float(bar['volume'])/(float(tail[-1]['volume'])+1e-12)-1)/3),0.,0.,0.,0.]
            for h,bank in models.items():
                if h not in d['pending']:
                    d['pending'][h]={'due':t+int(h)*1000,'price':price,'x':x,
                                    'predictions':{k:list(m.predict(x)) for k,m in bank.items()}}
        d['tail']=(tail+[bar])[-3:]
        d['cursor']=t+STEP
    d['models']={h:{k:m.state() for k,m in bank.items()} for h,bank in models.items()}


def catch_up(state,now_ms,save_page,*,pages=4,fetch=public):
    if type(pages) is not int or not 1<=pages<=32:
        raise ValueError('HISTORY_REQUEST_BUDGET')
    out=copy.deepcopy(state)
    for _ in range(pages):
        s=SYMBOLS[out['next_symbol']%4];out['next_symbol']+=1
        cursor=out['symbols'][s]['cursor']
        if cursor+STEP>now_ms:
            continue
        params={'symbol':s,'interval':'5m','startTime':cursor,'endTime':now_ms-1,'limit':1000}
        raw=fetch('klines',params)
        bars=closed_bars(raw,now_ms)
        if bars and (bars[0]['time']<cursor or bars[-1]['time']>=now_ms):
            raise ValueError('HISTORY_RANGE')
        save_page({'symbol':s,'requested':params,'observed_ms':now_ms,'raw':raw,
                   'historical_only':True,'orderbook_reconstructed':False})
        learn_page(out,s,bars);out['pages']+=1
    return out
