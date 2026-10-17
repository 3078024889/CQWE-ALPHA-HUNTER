"""Small deterministic strategy screen; no exchange orders or imported EA execution.

Independent textbook baselines, NOT reproductions of the attached MT5 EA or
third-party performance. Frozen before downloading; all configurations reported.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen

SYMBOLS=('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT')
HOUR=3600000
RULES={'ema_20_80':{'fast':20,'slow':80},'donchian_55_20':{'entry':55,'exit':20},
       'mean_revert_20_z2':{'window':20,'entry_z':2},'flat':{}}


def public(endpoint,params=None):
    if endpoint not in ('time','klines','fundingRate'):raise ValueError('ENDPOINT_NOT_ALLOWED')
    with urlopen('https://fapi.binance.com/fapi/v1/'+endpoint+'?'+urlencode(params or {}),timeout=10) as r:
        raw=r.read(1500001)
    if len(raw)>1500000:raise ValueError('RESPONSE_BUDGET')
    return json.loads(raw)


def signals(bars,kind):
    """Signal for bar i uses closes/highs/lows through i-1 only."""
    if kind not in RULES:raise ValueError('UNKNOWN_RULE')
    out=[];closes=[];highs=[];lows=[];fast=slow=None;direction=0
    for b in bars:
        if len(closes)<200 or kind=='flat':direction=0
        elif kind=='ema_20_80':direction=1 if fast>slow else -1 if fast<slow else 0
        elif kind=='donchian_55_20':
            # Prior close is compared with a channel ending one bar earlier.
            if closes[-1]>max(highs[-56:-1]):direction=1
            elif closes[-1]<min(lows[-56:-1]):direction=-1
            elif direction==1 and closes[-1]<min(lows[-21:-1]):direction=0
            elif direction==-1 and closes[-1]>max(highs[-21:-1]):direction=0
        else:
            window=closes[-20:];mean=sum(window)/20
            sd=math.sqrt(sum((x-mean)**2 for x in window)/20)
            z=(closes[-1]-mean)/sd if sd else 0
            if z<=-2:direction=1
            elif z>=2:direction=-1
            elif direction*z>=0:direction=0
        out.append(direction)
        c=b['close'];closes.append(c);highs.append(b['high']);lows.append(b['low'])
        fast=c if fast is None else fast+2/21*(c-fast)
        slow=c if slow is None else slow+2/81*(c-slow)
    return out


def replay(bars,funding,kind,start,end,fee=.0005,slip=.0002):
    target=signals(bars,kind);cash=10.;quantity=0.;entry=None;entry_equity=None
    peak=10.;dd=0.;fees=0.;funding_net=0.;trades=[];position_fee=0.;position_funding=0.
    funding_index=0;funding=sorted(funding,key=lambda f:f['fundingTime'])
    active=[(i,b) for i,b in enumerate(bars) if start<=b['time']<end]
    def close(price,at,reason):
        nonlocal cash,quantity,fees,entry,position_fee,position_funding
        direction=1 if quantity>0 else -1
        fill=price*(1-direction*slip);exit_fee=abs(quantity)*fill*fee
        gross=quantity*(fill-entry);cash+=gross-exit_fee;fees+=exit_fee
        trades.append({'entry_time':entry_at,'exit_time':at,'direction':direction,'gross':gross,
            'fees':position_fee+exit_fee,'funding_cashflow':position_funding,
            'net':gross-position_fee-exit_fee+position_funding,'reason':reason})
        quantity=0.;entry=None;position_fee=0.;position_funding=0.
    for i,b in active:
        direction=1 if quantity>0 else -1 if quantity<0 else 0
        if target[i]!=direction:
            if quantity:close(b['open'],b['time'],'SIGNAL_CHANGE')
            if target[i] and cash>0:
                entry_equity=cash;entry_at=b['time'];entry=b['open']*(1+target[i]*slip)
                quantity=target[i]*cash*.5/entry  # 5% margin x10 = 50% gross notional.
                position_fee=abs(quantity)*entry*fee;fees+=position_fee;cash-=position_fee
        while funding_index<len(funding) and funding[funding_index]['fundingTime']<b['time']:
            funding_index+=1
        while funding_index<len(funding) and funding[funding_index]['fundingTime']<b['time']+HOUR:
            f=funding[funding_index]
            # If entry occurs exactly at settlement, assume payment (conservative ordering uncertainty).
            delta=-quantity*float(f['markPrice'])*float(f['fundingRate'])
            cash+=delta;funding_net+=delta;position_funding+=delta
            funding_index+=1
        adverse=b['low'] if quantity>0 else b['high']
        worst=cash+quantity*(adverse-entry) if quantity else cash
        dd=max(dd,1-worst/peak)
        equity=cash+quantity*(b['close']-entry) if quantity else cash
        peak=max(peak,equity)
        if equity<=0:raise ValueError('SIMULATED_BANKRUPTCY')
    if quantity and active:close(active[-1][1]['close'],active[-1][1]['time']+HOUR-1,'PERIOD_END')
    dd=max(dd,1-cash/peak)
    wins=sum(t['net']>0 for t in trades);gains=sum(max(t['net'],0) for t in trades)
    losses=-sum(min(t['net'],0) for t in trades)
    return {'strategy':kind,'start_ms':start,'end_ms':end,'bars':len(active),'initial':10.,'final':cash,
        'net':cash-10,'return_pct':(cash/10-1)*100,'max_drawdown_pct':dd*100,'fees':fees,
        'funding_cashflow':funding_net,'closed':len(trades),'wins':wins,'profit_factor':gains/losses if losses else None,
        'trades':trades,'exchange_order_filters_validated':False,'profitability_proven':False}


def download(symbol,start,end,root):
    path=root/(symbol+'.json')
    if path.exists():
        payload=json.loads(path.read_text(encoding='utf-8'))
        raw=payload['data'];assert payload['sha256']==hashlib.sha256(json.dumps(raw,separators=(',',':')).encode()).hexdigest()
        return raw
    rows=[];cursor=start
    while cursor<end:
        page=public('klines',{'symbol':symbol,'interval':'1h','startTime':cursor,'endTime':end-1,'limit':1000})
        if not page:raise ValueError('MISSING_KLINE_PAGE')
        rows.extend(page);next_cursor=int(page[-1][0])+HOUR
        if next_cursor<=cursor:raise ValueError('NONADVANCING_PAGE')
        cursor=next_cursor
    bars=[]
    for r in rows:
        t=int(r[0])
        if not start<=t<end:continue
        o,h,l,c=map(float,(r[1],r[2],r[3],r[4]))
        if int(r[6])!=t+HOUR-1 or not 0<l<=min(o,c)<=max(o,c)<=h:raise ValueError('BAD_BAR')
        if bars and t-bars[-1]['time']!=HOUR:raise ValueError('KLINE_GAP')
        bars.append({'time':t,'open':o,'high':h,'low':l,'close':c})
    if len(bars)!=(end-start)//HOUR:raise ValueError('INCOMPLETE_HISTORY')
    funding=[];cursor=start
    while cursor<end:
        page=public('fundingRate',{'symbol':symbol,'startTime':cursor,'endTime':end-1,'limit':1000})
        if not page:break
        funding.extend(page);cursor=int(page[-1]['fundingTime'])+1
        if len(page)<1000:break
    times=[f['fundingTime'] for f in funding]
    if len(times)!=len(set(times)) or any(not math.isfinite(float(f['markPrice'])) or float(f['markPrice'])<=0 or not math.isfinite(float(f['fundingRate'])) for f in funding):raise ValueError('BAD_FUNDING')
    # These four established markets should not have multi-day missing funding records.
    if not times or times[0]-start>43200000 or end-times[-1]>43200000 or any(b-a>43200000 for a,b in zip(times,times[1:])):raise ValueError('FUNDING_GAP')
    data={'bars':bars,'funding':funding,'symbol':symbol,'start_ms':start,'end_ms':end,
          'endpoints':['https://fapi.binance.com/fapi/v1/klines','https://fapi.binance.com/fapi/v1/fundingRate']}
    payload={'data':data,'sha256':hashlib.sha256(json.dumps(data,separators=(',',':')).encode()).hexdigest()}
    path.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8')
    return data


def grid_stress():
    # Scenario arithmetic for a single losing side, not a tick replay of both sides.
    lots=[1+i*.1 for i in range(20)];steps=[20,15,35,18,53,25,80,40,120,60,180,90,270,135,210,105,150,215,100,200]
    price=150.;entries=[]
    for i,lot in enumerate(lots):
        if i:price-=steps[i-1]*.001
        entries.append((lot,price))
    return {'kind':'SYNTHETIC_ONE_SIDE_STRESS_NOT_MT5_BACKTEST','assumptions':{'USDJPY_start':150,'point':.001,
            'contract_size_USD':100000,'original_lots':True,'margin_commission_swap_excluded':True},
            'total_lots':sum(lots),'last_entry':price,'USD_base_notional':sum(lots)*100000,
            'scenarios':[{'USDJPY':mark,'unrealized_USD':sum(lot*100000*(mark-entry)/mark for lot,entry in entries),
                          'all_levels_already_filled_assumption':True} for mark in (price,145.,140.)]}


def main():
    p=argparse.ArgumentParser();p.add_argument('--days',type=int,default=730);p.add_argument('--root',default='D:/CQWE_DATA/strategy_lab_20261016');a=p.parse_args()
    if not 180<=a.days<=730:raise ValueError('DAYS_BUDGET')
    root=Path(a.root);root.mkdir(exist_ok=True,parents=True)
    plan_path=root/'preregistered.json'
    if plan_path.exists():plan=json.loads(plan_path.read_text(encoding='utf-8'))
    else:
        end=public('time')['serverTime']//HOUR*HOUR
        plan={'created_ms':time.time_ns()//1000000,'end_ms':end,'start_ms':end-a.days*86400000,
              'rules':RULES,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'symbols':SYMBOLS,'holdout_days':90,'fee':.0005,'slippage_cases':[.0002,.0005],
              'notional_equity_fraction':.5,'parameter_search':False,'unreported_trials':0,
              'limitations':['Not MT5 tick backtest','Not orderbook/market-making reproduction','No exchange minimum filters',
                             'No borrowing/liquidation/margin emulation','Funding settlement order at bar open is uncertain',
                             'Multiple comparisons; descriptive results, no automatic model promotion']}
        plan_path.write_text(json.dumps(plan,indent=2),encoding='utf-8')
    if plan['source_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest():raise ValueError('PLAN_SOURCE_CHANGED_USE_NEW_ROOT')
    results=[];coverage={};end=plan['end_ms'];start=plan['start_ms'];hold=end-90*86400000
    for symbol in SYMBOLS:
        data=download(symbol,start,end,root);bars=data['bars'];funding=data['funding']
        coverage[symbol]={'bars':len(bars),'funding_records':len(funding),'sha256':hashlib.sha256((root/(symbol+'.json')).read_bytes()).hexdigest()}
        print(json.dumps({'symbol':symbol,**coverage[symbol]}),flush=True)
        for slip in plan['slippage_cases']:
            for phase,left,right in (('earlier',start,hold),('reserved_90d',hold,end)):
                for rule in RULES:
                    r=replay(bars,funding,rule,left,right,plan['fee'],slip)
                    r.update(symbol=symbol,phase=phase,slippage_each_side_bps=slip*10000)
                    trades=r.pop('trades');trade_path=root/(f'{symbol}_{phase}_{rule}_{slip}.trades.json')
                    trade_path.write_text(json.dumps(trades,separators=(',',':')),encoding='utf-8')
                    r['trade_file']=str(trade_path);results.append(r)
    report={'plan':plan,'coverage':coverage,'results':results,'grid_stress':grid_stress(),'profitability_proven':False,'real_orders':0}
    out=Path('reports/open_strategy_screen_20261016.json');out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'report':str(out),'configurations':len(results),'real_orders':0}),flush=True)


if __name__=='__main__':main()
