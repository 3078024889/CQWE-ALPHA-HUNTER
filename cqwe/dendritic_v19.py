"""CQWE V19: auditable regime-conditioned expert competition and cash-only HOLDOUT paper execution.
'Dendritic' is a computational analogy, not a claim of neural biological learning or universal profits.
No network, credentials, real orders, leverage, margin, prediction market betting or auto-self-modification.
"""
from __future__ import annotations
import argparse, hashlib, json, math, statistics
from pathlib import Path
from .core import valid_candles

EXPERTS=('breakout','reversal','trend_volume')
REGIMES=('trend_low','trend_high','range_low','range_high')
STEP=300000

def features(bars,i,window=24):
    if i<window:raise ValueError('insufficient past')
    prices=[float(b[4]) for b in bars[i-window:i+1]]
    close=prices[-1]; old=prices[0]
    rets=[math.log(prices[j]/prices[j-1]) for j in range(1,len(prices))]
    vol=math.sqrt(statistics.mean(x*x for x in rets))
    # Regime boundary fixed a priori, never fitted to holdout.
    trend=abs(close/old-1) >= max(.002,2*vol)
    turbulent=vol >= .0025
    regime=('trend' if trend else 'range')+'_'+('high' if turbulent else 'low')
    prev=prices[:-1]; prior_hi=max(prev);prior_lo=min(prev)
    prior_turnovers=[float(b[7]) for b in bars[i-window:i]]
    cur=float(bars[i][7]); mean_turnover=max(1e-12,statistics.mean(prior_turnovers))
    return {'regime':regime,'returns':close/old-1,'volume_ratio':cur/mean_turnover,
            'breakout':close > prior_hi,'reversal':close < prior_lo,'close':close}

def trigger(f,expert):
    if expert=='breakout':return f['breakout'] and f['returns']>0
    if expert=='reversal':return f['reversal'] and f['returns']<0
    if expert=='trend_volume':return f['returns']>.003 and f['volume_ratio']>=1.5
    raise ValueError('unknown expert')

def _positive_finite(v,name,allow_zero=False):
    if isinstance(v,bool):raise ValueError(name)
    try: v=float(v)
    except (TypeError,ValueError):raise ValueError(name) from None
    if not math.isfinite(v) or (v<0 if allow_zero else v<=0):raise ValueError(name)
    return v

def validate_inputs(datasets):
    if not isinstance(datasets,dict) or not 1<=len(datasets)<=12:raise ValueError('markets 1..12')
    byname={}
    for symbol,bars in datasets.items():
        if not isinstance(symbol,str) or not symbol.isupper() or not symbol.isalnum():raise ValueError('invalid market')
        valid_candles(bars)
        byname[symbol]={int(b[0]):b for b in bars}
    common=sorted(set.intersection(*(set(b) for b in byname.values())))
    if len(common)<240 or any(b-a!=STEP for a,b in zip(common,common[1:])):
        raise ValueError('insufficient continuous aligned market data')
    return common,{s:[byname[s][t] for t in common] for s in sorted(byname)}

def select_model(data,split,hold=12,lookback=24,fee_bps=5,slip_bps=2,min_events=25,z=3.0):
    """Candidate scores are training-only, outcome mature before split; each market/regime/expert separately."""
    all_scores={}
    for sym,bars in data.items():
        for expert in EXPERTS:
            events={r:[] for r in REGIMES};last={r:-999999 for r in REGIMES}
            for i in range(lookback,split-hold-1):
                f=features(bars,i,lookback);reg=f['regime']
                if not trigger(f,expert) or i<=last[reg]+hold:continue
                entry=float(bars[i+1][1])*(1+slip_bps/10000)
                exit_price=float(bars[i+1+hold][1])*(1-slip_bps/10000)
                r=exit_price/entry*(1-fee_bps/10000)**2-1
                events[reg].append(r);last[reg]=i
            for reg,xs in events.items():
                n=len(xs);mean=statistics.mean(xs) if xs else None
                std=statistics.stdev(xs) if n>=2 else None
                lcb=(mean-z*std/math.sqrt(n)) if n>=min_events and std is not None else None
                # Require positive lower confidence bound under an intentionally strict fixed threshold.
                good=lcb is not None and lcb>0
                all_scores[f'{sym}|{reg}|{expert}']={'n':n,'mean_fraction':mean,
                   'conservative_lcb_fraction':lcb,'admitted':good,'reason':'TRAIN_LCB_POSITIVE' if good else
                   ('TOO_FEW_EVENTS' if n<min_events else 'NO_CONFIDENT_POSITIVE_EDGE')}
    return all_scores

def simulate(datasets,initial_cash=10.0,split_fraction=.70,allocation=.6,min_notional=5.0,
             fee_bps=5.0,slip_bps=2.0,hold=12,lookback=24,min_train_events=25,z=3.0):
    initial_cash=_positive_finite(initial_cash,'cash');allocation=_positive_finite(allocation,'allocation')
    min_notional=_positive_finite(min_notional,'min_notional');fee_bps=_positive_finite(fee_bps,'fee',True)
    slip_bps=_positive_finite(slip_bps,'slip',True);z=_positive_finite(z,'z')
    if not (.5<=split_fraction<=.85 and 0<allocation<=1 and fee_bps<1000 and slip_bps<1000 and
            isinstance(hold,int) and 1<=hold<=100 and isinstance(lookback,int) and 12<=lookback<=100 and
            isinstance(min_train_events,int) and min_train_events>=2):raise ValueError('bad settings')
    clock,data=validate_inputs(datasets);n=len(clock);split=int(n*split_fraction)
    if split<lookback+hold+40 or n-split<hold+10:raise ValueError('too little train or holdout')
    model=select_model(data,split,hold,lookback,fee_bps,slip_bps,min_train_events,z)
    permitted={(k.split('|')[0],k.split('|')[1],k.split('|')[2]):v for k,v in model.items() if v['admitted']}
    cash=initial_cash;position=None;trades=[];equity=[];denied={'notional':0,'no_signal':0}
    for i in range(split,n-1):
        # i close observed; sell and buy only at next bar open; no access to i+1 close for signal.
        if position is not None and i+1-position['entry_i']>=hold:
            sym=position['symbol'];price=float(data[sym][i+1][1])*(1-slip_bps/10000)
            total=position['quantity']*price;fee=total*fee_bps/10000
            cash+=total-fee
            trades.append({'side':'SELL','symbol':sym,'time_ms':clock[i+1],'quantity':position['quantity'],
                           'price':price,'fee':fee,'cash_after':cash,'reason':'time_exit'})
            position=None
        if position is None:
            proposals=[]
            for sym,bars in data.items():
                f=features(bars,i,lookback)
                for ex in EXPERTS:
                    k=(sym,f['regime'],ex)
                    if k in permitted and trigger(f,ex):
                        proposals.append((permitted[k]['conservative_lcb_fraction'],sym,ex,f['regime']))
            if not proposals:denied['no_signal']+=1
            else:
                _,sym,ex,reg=sorted(proposals,key=lambda r:(-r[0],r[1],r[2]))[0]
                budget=cash*allocation
                if budget<min_notional:denied['notional']+=1
                else:
                    price=float(data[sym][i+1][1])*(1+slip_bps/10000)
                    qty=(budget/(1+fee_bps/10000))/price;gross=qty*price;fee=gross*fee_bps/10000
                    cash-=gross+fee
                    position={'symbol':sym,'quantity':qty,'entry_i':i+1,'expert':ex,'regime':reg}
                    trades.append({'side':'BUY','symbol':sym,'time_ms':clock[i+1],'quantity':qty,
                                   'price':price,'fee':fee,'cash_after':cash,'expert':ex,'regime':reg})
        marked=cash+(position['quantity']*float(data[position['symbol']][i+1][4]) if position else 0)
        if cash < -1e-9:raise ArithmeticError('overdraw')
        equity.append({'time_ms':clock[i+1],'virtual_equity_usd':marked})
    # No end-of-data fabricated exit. Open exposure is marked and separately disclosed.
    final_equity=equity[-1]['virtual_equity_usd'];peak=initial_cash;max_dd=0
    for e in equity:
        peak=max(peak,e['virtual_equity_usd']);max_dd=min(max_dd,e['virtual_equity_usd']/peak-1)
    # Independently replay recorded costs, cash and inventory.
    replay_cash=initial_cash;replay_pos={}
    for t in trades:
        qty=t['quantity'];val=qty*t['price'];sym=t['symbol']
        if t['side']=='BUY':replay_cash-=val+t['fee'];replay_pos[sym]=replay_pos.get(sym,0)+qty
        else:replay_cash+=val-t['fee'];replay_pos[sym]=replay_pos.get(sym,0)-qty
    pos_inventory={position['symbol']:position['quantity']} if position else {}
    balanced=abs(replay_cash-cash)<1e-7 and all(abs(replay_pos.get(s,0)-pos_inventory.get(s,0))<1e-8
                                                 for s in set(replay_pos)|set(pos_inventory))
    if not balanced:raise ArithmeticError('independent replay failed')
    admitted=[k for k,v in model.items() if v['admitted']]
    return {'mode':'DENDRITIC_ADAPTIVE_HISTORICAL_PAPER','simulation_only':True,
            'model_semantics':'Fixed regime tree + train-only expert competition, not biological neuron simulation',
            'split_index':split,'train_end_ms_exclusive':clock[split],'holdout_start_ms':clock[split],
            'holdout_bars':n-split,'train_total_candles_per_market':split,
            'lookback':lookback,'hold':hold,'train_only_model':model,'admitted_experts':admitted,
            'initial_virtual_usd':initial_cash,'final_virtual_equity_usd':round(final_equity,8),
            'virtual_net_usd':round(final_equity-initial_cash,8),'cash_usd':round(cash,8),
            'open_position':position,'max_drawdown_pct':round(max_dd*100,8),
            'entries':sum(t['side']=='BUY' for t in trades),'exits':sum(t['side']=='SELL' for t in trades),
            'rejections':denied,'ledger_balanced':balanced,'trades':trades,'equity_curve':equity,
            'realized_account_profit_usd':None,'warning':
            'Research simulation only; no real liquidity or exchange minima verified, no real orders; market selection bias and multiple testing remain.'}

def run(paths,out,**kwargs):
    data={};hashes={}
    for f in paths:
        p=Path(f);symbol=p.stem.split('_')[0].upper();raw=p.read_bytes()
        if symbol in data:raise ValueError('duplicate market')
        data[symbol]=json.loads(raw.decode('utf-8-sig'));hashes[symbol]=hashlib.sha256(raw).hexdigest()
    result={'data_sha256':hashes,'portfolio':simulate(data,**kwargs)}
    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix(dest.suffix+'.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(dest)
    return result

def main():
    ap=argparse.ArgumentParser(description='CQWE V19: leakage-isolated adaptive paper research')
    ap.add_argument('--inputs',nargs='+',required=True);ap.add_argument('--output',default='reports/v19_dendritic.json')
    ap.add_argument('--min-notional-usd',type=float,default=5);ap.add_argument('--min-train-events',type=int,default=25)
    a=ap.parse_args();result=run(a.inputs,a.output,min_notional=a.min_notional_usd,min_train_events=a.min_train_events)
    p=result['portfolio'];print('CQWE_V19_PAPER:', 'selected=',len(p['admitted_experts']),
           'entries=',p['entries'],'equity=',p['final_virtual_equity_usd'],'net=',p['virtual_net_usd'],
           'balanced=',p['ledger_balanced']);print('CQWE_V19_HOLDOUT_RESEARCH_ONLY | NO REAL ORDERS')
if __name__=='__main__':main()
