"""One real-time-ordered, cash-only, multi-market HISTORICAL portfolio.
No network, broker access, leverage, margin or live orders. Uses prior closed bars only.
Hypothetical next-open execution has no actual liquidity/queue guarantees.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
from .core import valid_candles


def check_number(x,name):
    if isinstance(x,bool):raise ValueError(name)
    try: v=float(x)
    except (ValueError,TypeError):raise ValueError(name) from None
    if not math.isfinite(v):raise ValueError(name)
    return v


def portfolio(datasets,initial_cash=10,allocation=.2,fee_bps=5,slip_bps=2,hold_bars=12,
              lookback=12,min_notional_usd=5,gas_usd_per_order=0,stop_loss_pct=.05):
    if not isinstance(datasets,dict) or not datasets or len(datasets)>12:raise ValueError('markets 1..12')
    initial_cash=check_number(initial_cash,'cash');allocation=check_number(allocation,'allocation')
    fee_bps=check_number(fee_bps,'fees');slip_bps=check_number(slip_bps,'slip')
    minimum=check_number(min_notional_usd,'minimum');gas=check_number(gas_usd_per_order,'gas')
    stop_loss_pct=check_number(stop_loss_pct,'stop')
    if not (initial_cash>0 and 0<allocation<=1 and 0<=fee_bps<=10000 and 0<=slip_bps<10000 and
            minimum>0 and gas>=0 and 0<stop_loss_pct<1 and isinstance(hold_bars,int) and 1<=hold_bars<=500 and
            isinstance(lookback,int) and 2<=lookback<=500):raise ValueError('invalid parameters')
    normalized={}
    for name,bars in datasets.items():
        if not isinstance(name,str) or not name.isalnum() or not name.isupper():raise ValueError('market name')
        valid_candles(bars)
        normalized[name]={int(b[0]):b for b in bars}
    common=set.intersection(*(set(v) for v in normalized.values()))
    clock=sorted(common)
    if len(clock)<lookback+3:raise ValueError('too little overlapping history')
    if any(b-a!=300000 for a,b in zip(clock,clock[1:])):raise ValueError('missing common candle')
    symbols=sorted(normalized)
    bars={name:[normalized[name][t] for t in clock] for name in symbols}
    cash=initial_cash;positions={};trades=[];curve=[];fees_total=0;gas_total=0;rejections={'min_notional':0,'cash':0}
    def log_trade(kind,name,i,price,qty,commission,gas_paid,reason):
        trades.append({'side':kind,'symbol':name,'time_ms':clock[i], 'price':round(price,12),'quantity':round(qty,12),
                       'fee_usd':round(commission,10),'gas_usd':round(gas_paid,10),
                       'cash_after_usd':round(cash,10),'reason':reason})
    for i in range(lookback,len(clock)-1):
        # Current bar i is closed; compute all signal and exits first; actions on bar i+1 open.
        exit_names=[]
        for name,pos in positions.items():
            cl=float(bars[name][i][4])
            if i+1-pos['entry_i']>=hold_bars or cl<=pos['entry_price']*(1-stop_loss_pct):exit_names.append(name)
        for name in sorted(exit_names):
            p=positions[name];open_price=float(bars[name][i+1][1]);fill=open_price*(1-slip_bps/10000)
            gross=fill*p['quantity'];commission=gross*fee_bps/10000
            cash+=gross-commission-gas;fees_total+=commission;gas_total+=gas
            log_trade('SELL',name,i+1,fill,p['quantity'],commission,gas,'time_or_stop')
            del positions[name]
        # One deterministic opportunity per bar, highest percentage breakout signal.
        opportunities=[]
        for name in symbols:
            if name in positions:continue
            series=bars[name];cl=float(series[i][4]);prior=max(float(x[4]) for x in series[i-lookback:i])
            if cl>prior: opportunities.append(((cl/prior-1),name))
        if opportunities:
            _,name=sorted(opportunities,key=lambda x:(-x[0],x[1]))[0]
            budget=cash*allocation
            if budget<minimum:rejections['min_notional']+=1
            elif budget<=gas:rejections['cash']+=1
            else:
                entry=float(bars[name][i+1][1])*(1+slip_bps/10000)
                commission=(budget-gas)*fee_bps/10000
                qty=(budget-gas-commission)/entry
                if qty<=0:rejections['cash']+=1
                else:
                    cash-=budget;fees_total+=commission;gas_total+=gas
                    positions[name]={'quantity':qty,'entry_price':entry,'entry_i':i+1}
                    log_trade('BUY',name,i+1,entry,qty,commission,gas,'breakout')
        value=cash+sum(p['quantity']*float(bars[name][i+1][1]) for name,p in positions.items())
        if cash < -1e-8 or value< -1e-8:raise ArithmeticError('overdraw')
        curve.append({'time_ms':clock[i+1],'equity_usd':round(value,10)})
    # Explicitly distinguish hypothetical final close from a confirmed next-open fill.
    final_i=len(clock)-1
    for name,p in sorted(positions.items()):
        fill=float(bars[name][-1][4])*(1-slip_bps/10000);gross=p['quantity']*fill;commission=gross*fee_bps/10000
        cash+=gross-commission-gas;fees_total+=commission;gas_total+=gas
        log_trade('SELL_END_ASSUMPTION',name,final_i,fill,p['quantity'],commission,gas,'final_bar_synthetic')
    curve.append({'time_ms':clock[-1],'equity_usd':round(cash,10)})
    peak=initial_cash;drawdown=0
    for r in curve:
        peak=max(peak,r['equity_usd']);drawdown=min(drawdown,(r['equity_usd']/peak-1)*100)
    # Independent ledger replay reconstructs cash, position and costs from trades.
    replay_cash=initial_cash;replay_pos={}
    for trade in trades:
        name=trade['symbol'];qty=trade['quantity'];price=trade['price'];fee=trade['fee_usd'];charged_gas=trade['gas_usd']
        if trade['side']=='BUY':
            replay_cash-=qty*price+fee+charged_gas;replay_pos[name]=replay_pos.get(name,0)+qty
        else:
            replay_cash+=qty*price-fee-charged_gas;replay_pos[name]=replay_pos.get(name,0)-qty
    # Rounding of serialized trades incurs tiny replay discrepancy.
    balanced=abs(replay_cash-cash)<1e-6 and all(abs(q)<1e-9 for q in replay_pos.values()) and cash>=-1e-8
    if not balanced:raise ArithmeticError('ledger replay mismatch')
    return {'mode':'UNIFIED_HISTORICAL_PAPER','research_only':True,'initial_virtual_usd':initial_cash,
            'final_virtual_usd':round(cash,8),'virtual_net_usd':round(cash-initial_cash,8),
            'max_drawdown_pct':round(drawdown,8),'fees_usd':round(fees_total,8),'gas_assumption_usd':round(gas_total,8),
            'entries':sum(t['side']=='BUY' for t in trades),'exits':sum(t['side'].startswith('SELL') for t in trades),
            'rejected':rejections,'ledger_balanced':balanced,'symbols':symbols,'bars_aligned':len(clock),
            'trades':trades,'equity_curve':curve,'realized_profit_usd':None,
            'limitations':'Historical next-open hypothetical fills; fee/gas assumptions, no actual depth, no real orders, no exchange lot-size enforcement.'}


def run(files,out,**kwargs):
    datasets={};sources={}
    for f in files:
        p=Path(f);name=p.stem.split('_')[0].upper()
        if name in datasets:raise ValueError('duplicate symbol')
        raw=p.read_bytes();datasets[name]=json.loads(raw.decode('utf-8-sig'))
        sources[name]={'path':str(p),'sha256':hashlib.sha256(raw).hexdigest()}
    result={'sources':sources,'portfolio':portfolio(datasets,**kwargs)}
    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description='CQWE V18 historical unified cash-only paper trading')
    p.add_argument('--inputs',nargs='+',required=True);p.add_argument('--output',default='reports/v18_unified.json')
    p.add_argument('--initial-cash',type=float,default=10);p.add_argument('--allocation',type=float,default=.2)
    p.add_argument('--min-notional-usd',type=float,default=5);p.add_argument('--gas-usd-per-order',type=float,default=0)
    p.add_argument('--fee-bps',type=float,default=5);p.add_argument('--slip-bps',type=float,default=2)
    args=p.parse_args();r=run(args.inputs,args.output,initial_cash=args.initial_cash,allocation=args.allocation,
      min_notional_usd=args.min_notional_usd,gas_usd_per_order=args.gas_usd_per_order,
      fee_bps=args.fee_bps,slip_bps=args.slip_bps)
    q=r['portfolio'];print('unified_balance=',q['final_virtual_usd'],'virtual_net=',q['virtual_net_usd'],
                          'entries=',q['entries'],'ledger_balanced=',q['ledger_balanced'])
    print('CQWE_V18_UNIFIED_PAPER_PASS | HISTORICAL ONLY | NO ORDERS')
if __name__=='__main__':main()
