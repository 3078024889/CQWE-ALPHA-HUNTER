"""Matched two-leg carry research. No strategy is activated by these results."""
import hashlib
from collections import deque
import json
import math
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen

HOUR=3600000
SYMBOLS=('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT')


def spot_history(symbol,start,end,root):
    path=root/(symbol+'_spot.json')
    if path.exists():
        payload=json.loads(path.read_text(encoding='utf-8'));data=payload['data']
        if payload['sha256']!=hashlib.sha256(json.dumps(data,separators=(',',':')).encode()).hexdigest():raise ValueError('SPOT_HASH')
        return data
    cursor=start;bars=[]
    while cursor<end:
        url='https://data-api.binance.vision/api/v3/klines?'+urlencode({'symbol':symbol,'interval':'1h','startTime':cursor,'endTime':end-1,'limit':1000})
        with urlopen(url,timeout=8) as r:raw=r.read(1500001)
        if len(raw)>1500000:raise ValueError('SPOT_PAGE_SIZE')
        page=json.loads(raw)
        if not page:raise ValueError('SPOT_MISSING_PAGE')
        for row in page:
            t=int(row[0]);o,h,l,c=map(float,(row[1],row[2],row[3],row[4]))
            if not start<=t<end or int(row[6])!=t+HOUR-1 or not all(math.isfinite(x) and x>0 for x in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('SPOT_BAR')
            if bars and t-bars[-1]['time']!=HOUR:raise ValueError('SPOT_GAP')
            bars.append({'time':t,'open':o,'high':h,'low':l,'close':c})
        new=int(page[-1][0])+HOUR
        if new<=cursor:raise ValueError('SPOT_CURSOR')
        cursor=new
    if len(bars)!=(end-start)//HOUR:raise ValueError('SPOT_COVERAGE')
    payload={'data':bars,'sha256':hashlib.sha256(json.dumps(bars,separators=(',',':')).encode()).hexdigest(),
             'endpoint':'https://data-api.binance.vision/api/v3/klines'}
    path.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8')
    return bars


def replay(spot,perp,funding,start,end,rule,slip):
    if len(spot)!=len(perp) or any(a['time']!=b['time'] for a,b in zip(spot,perp)):raise ValueError('LEG_ALIGNMENT')
    funds=sorted(funding,key=lambda f:int(f['fundingTime']));cursor=0;known=deque();cash=10.;position=None
    trades=[];peak=10.;drawdown=0.;payments=0.;fees=0.;margin_flags=0
    def close(i,at,reason):
        nonlocal cash,position,fees
        p=position;q=p['quantity'];sx=spot[i]['open']*(1-slip);px=perp[i]['open']*(1+slip)
        fee=q*(sx*.001+px*.0005);cash+=q*sx+q*(p['perp_entry']-px)-fee;fees+=fee
        basis_pnl=q*(sx-p['spot_entry'])+q*(p['perp_entry']-px)
        net=basis_pnl+p['funding']-p['entry_fees']-fee
        trades.append({**p,'closed_ms':at,'spot_exit':sx,'perp_exit':px,'basis_pnl':basis_pnl,'exit_fees':fee,'net':net,'reason':reason})
        position=None
    selected=[i for i,b in enumerate(spot) if start<=b['time']<end]
    for i in selected:
        t=spot[i]['time']
        while cursor<len(funds) and int(funds[cursor]['fundingTime'])<t:
            known.append(funds[cursor]);cursor+=1
        while known and int(known[0]['fundingTime'])<t-7*86400000:known.popleft()
        recent=list(known)
        mean=sum(float(f['fundingRate']) for f in recent)/len(recent) if recent else 0.
        if position and rule=='lagged_funding' and (mean<=0 or t-position['opened_ms']>=14*86400000):close(i,t,'FUNDING_OR_14D_LIMIT')
        # Do not repeatedly re-enter the control after a research margin warning exit.
        enter=(rule=='hold_carry' and not trades or rule=='lagged_funding' and len(recent)>=18 and
               mean*42>(.003+4*slip+.0005))
        if not position and i>=168 and enter and (not trades or trades[-1]['closed_ms']<t):
            se=spot[i]['open']*(1+slip);pe=perp[i]['open']*(1-slip);q=cash*.5/se
            entry_fee=q*(se*.001+pe*.0005);position={'opened_ms':t,'quantity':q,'spot_entry':se,'perp_entry':pe,
                'entry_fees':entry_fee,'funding':0.,'margin_warning':False,'lagged_mean_funding':mean}
            cash-=q*se+entry_fee;fees+=entry_fee
        # A settlement exactly at entry is deliberately NOT collected.
        for f in funds[cursor:cursor+4]:
            ft=int(f['fundingTime'])
            if ft>=t+HOUR:break
            if position and position['opened_ms']<ft:
                payment=position['quantity']*float(f['markPrice'])*float(f['fundingRate'])
                cash+=payment;position['funding']+=payment;payments+=payment
        if position:
            q=position['quantity'];pe=position['perp_entry']
            collateral_worst=cash+q*(pe-perp[i]['high'])
            if collateral_worst<=q*perp[i]['high']*.011 and not position['margin_warning']:
                position['margin_warning']=True;margin_flags+=1
            worst=cash+q*spot[i]['low']+q*(pe-perp[i]['high'])
            equity=cash+q*spot[i]['close']+q*(pe-perp[i]['close'])
        else:worst=equity=cash
        drawdown=max(drawdown,1-worst/peak);peak=max(peak,equity)
    if position:
        # Separate terminal close prices, not an invented next-bar opening fill.
        i=selected[-1];s=spot[i].copy();p=perp[i].copy()
        spot=spot.copy();perp=perp.copy();spot[i]={**s,'open':s['close']};perp[i]={**p,'open':p['close']}
        close(i,end-1,'PERIOD_END')
    if not math.isclose(cash-10,sum(t['net'] for t in trades),abs_tol=1e-8):raise ValueError('CARRY_LEDGER_MISMATCH')
    return {'return_pct':(cash/10-1)*100,'net':cash-10,'funding_cashflow':payments,'fees':fees,'trades':len(trades),
            'adverse_bar_drawdown_pct':max(drawdown,1-cash/peak)*100,'margin_warning_positions':margin_flags,
            'ledger':trades,'research_eligible':False}


def main():
    root=Path('D:/CQWE_DATA/spot_perp_carry_20261016');root.mkdir(exist_ok=True,parents=True)
    planpath=root/'locked_plan.json';code=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    plan={'created_ms':time.time_ns()//1000000,'source_sha256':code,'symbols':SYMBOLS,'rules':['hold_carry','lagged_funding'],
          'spot_fee_each_side':.001,'perp_fee_each_side':.0005,'slip_each_fill':[.0002,.0005],
          'spot_notional_equity_fraction':.5,'lagged_funding_days':7,'minimum_records':18,'expected_settlements':42,
          'maximum_hold_days':14,'expected_profit_buffer':.0005,'fold_days':[0,182,365,547,730],
          'parameter_search':False,'known_futures_history_reused':True}
    if planpath.exists():
        plan=json.loads(planpath.read_text(encoding='utf-8'))
        if plan['source_sha256']!=code:raise ValueError('CARRY_PLAN_CHANGED_USE_NEW_ROOT')
    else:planpath.write_text(json.dumps(plan,indent=2),encoding='utf-8')
    results=[];coverage={}
    for symbol in SYMBOLS:
        path=Path('D:/CQWE_DATA/strategy_lab_20261016')/(symbol+'.json');p=json.loads(path.read_text(encoding='utf-8'));d=p['data']
        if p['sha256']!=hashlib.sha256(json.dumps(d,separators=(',',':')).encode()).hexdigest():raise ValueError('PERP_HASH')
        spot=spot_history(symbol,d['start_ms'],d['end_ms'],root);coverage[symbol]={'spot_bars':len(spot),'perp_bars':len(d['bars']),'funding':len(d['funding'])}
        for slip in (.0002,.0005):
            for rule in plan['rules']:
                for fold,(a,b) in enumerate(zip(plan['fold_days'],plan['fold_days'][1:])):
                    r=replay(spot,d['bars'],d['funding'],d['start_ms']+a*86400000,d['start_ms']+b*86400000,rule,slip)
                    ledger=r.pop('ledger');out=root/(f'{symbol}_{rule}_{slip}_{fold}.json');out.write_text(json.dumps(ledger),encoding='utf-8')
                    results.append({'symbol':symbol,'rule':rule,'fold':fold,'slippage_each_fill_bps':slip*10000,'ledger':str(out),**r})
        print(json.dumps({'symbol':symbol,**coverage[symbol]}),flush=True)
    report={'plan':plan,'coverage':coverage,'results':results,'real_orders':0,'activated':False,'profitability_proven':False,
        'limits':['Research returns only; no executable small-account order filters','A short perp can run out of collateral while spot rises; warnings invalidate deployment claims',
                  'Margin warning uses 1%+0.1% proxy, not exact liquidation; PNL after a warning is not executable',
                  'Adverse simultaneous spot-low/perp-high drawdown is conservative','No partial fills, basis depth, borrowing, exact fees or subhour matching',
                  'Funding exactly at entry not collected; no future funding used for the entry decision']}
    Path('reports/spot_perp_carry_screen_20261016.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'configurations':len(results),'report':'reports/spot_perp_carry_screen_20261016.json'}),flush=True)


if __name__=='__main__':main()
