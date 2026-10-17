"""Chronological fusion-only diagnostic, not a replay of intrabar risk or news gates."""
import hashlib
import json
import math
from pathlib import Path
from cqwe.strategy_candidates import candidates,SYMBOLS
from cqwe.unified_dendritic_paper import FAMILIES

HOUR=3600000


def fuse(series):
    n=len(next(iter(series.values())));out=[];held={};cooldown=False
    for i in range(n):
        vectors=[]
        for family in FAMILIES:
            members=[v for k,v in series.items() if k.startswith(family+':')]
            vector={s:sum(v[i].get(s,0) for v in members)/len(members) for s in SYMBOLS}
            vectors.append(vector)
        weights={s:sum(v[s] for v in vectors)/4 for s in SYMBOLS}
        weights={s:w for s,w in weights.items() if abs(w)>.0001}
        active=sum(any(abs(w)>1e-6 for w in v.values()) for v in vectors)
        if held:
            opposite=any(s in weights and w*weights[s]<0 for s,w in held.items())
            supported=any(s in weights and w*weights[s]>0 for s,w in held.items())
            if opposite or not supported:held={};cooldown=True
        elif cooldown:cooldown=False
        elif active>=2 and sum(abs(w) for w in weights.values())>=.05:held=weights
        out.append(held.copy())
    return out


def replay(data,funding,targets,left,right,slip):
    cash=10.;held={};current={};peak=10.;dd=0.;fees=0.;funding_cash=0.;closed=0
    fb={s:{} for s in data}
    for s,rows in funding.items():
        for f in rows:fb[s].setdefault(int(f['fundingTime'])//HOUR*HOUR,[]).append(f)
    active=[i for i,b in enumerate(data['BTCUSDT']) if left<=b['time']<right]
    def close(i,key):
        nonlocal cash,fees,held,closed,current
        for s,(q,entry) in held.items():
            price=data[s][i][key]*(1-math.copysign(slip,q));fee=abs(q)*price*.0005
            cash+=q*(price-entry)-fee;fees+=fee
        closed+=bool(held);held={};current={}
    for i in active:
        target=targets[i];t=data['BTCUSDT'][i]['time']
        if target!=current:
            if held:close(i,'open')
            if target:
                equity=cash
                for s,w in target.items():
                    price=data[s][i]['open']*(1+math.copysign(slip,w));q=equity*.5*w/price;fee=abs(q)*price*.0005
                    held[s]=(q,price);cash-=fee;fees+=fee
                current=target.copy()
        for s,(q,entry) in held.items():
            for f in fb[s].get(t,[]):
                payment=-q*float(f['markPrice'])*float(f['fundingRate']);cash+=payment;funding_cash+=payment
        worst=cash+sum(q*(data[s][i]['low' if q>0 else 'high']-entry) for s,(q,entry) in held.items())
        dd=max(dd,1-worst/peak)
        equity=cash+sum(q*(data[s][i]['close']-entry) for s,(q,entry) in held.items());peak=max(peak,equity)
    if held:close(active[-1],'close')
    return {'net':cash-10,'return_pct':(cash/10-1)*100,'fees':fees,'funding_cashflow':funding_cash,
            'groups_closed':closed,'max_adverse_bar_drawdown_pct':max(dd,1-cash/peak)*100}


def main():
    data={};funding={};hashes={}
    for s in SYMBOLS:
        p=Path('D:/CQWE_DATA/strategy_lab_20261016')/(s+'.json');r=json.loads(p.read_text(encoding='utf-8'));d=r['data']
        if r['sha256']!=hashlib.sha256(json.dumps(d,separators=(',',':')).encode()).hexdigest():raise ValueError('DATA_HASH')
        data[s]=d['bars'];funding[s]=d['funding'];hashes[s]=r['sha256']
    source=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    targets=fuse(candidates(data));start=data['BTCUSDT'][0]['time'];cuts=[0,182,365,547,730];results=[]
    for slip in (.0002,.0005):
        for fold,(a,b) in enumerate(zip(cuts,cuts[1:])):
            result=replay(data,funding,targets,start+a*86400000,start+b*86400000,slip)
            results.append({'fold':fold,'slippage_each_side_bps':slip*10000,**result})
    report={'policy':'UNIFIED_DENDRITIC_PAPER_V1','source_sha256':source,'data_sha256':hashes,'results':results,
        'blind_holdout':False,'trained_or_optimized':False,'profitability_proven':False,'real_orders':0,
        'scope':'Family-normalized portfolio target fusion diagnostic, not exact live strategy backtest',
        'limitations':['No historical book, event veto, 90-second activation or intrabar stops/trailing replay',
            'Next hourly open used; conservative full-bar reentry delay','Prior inspected data; not independent new validation',
            'No minimum order, partial fills, market impact, exact margin or liquidation model']}
    Path('reports/unified_fusion_validation_20261016.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(results))


if __name__=='__main__':main()
