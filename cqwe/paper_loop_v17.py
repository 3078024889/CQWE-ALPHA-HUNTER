"""CQWE V17: deterministic cash-only paper trading on closed historical 5m candles.
NO network; NO futures/margin, real orders, Polymarket assumed fills or live profit claims.
Signal decisions at bar i close; hypothetical fill on bar i+1 open.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
from .core import valid_candles


def finite(value, name):
    if isinstance(value, bool): raise ValueError(name)
    try: v=float(value)
    except (ValueError,TypeError): raise ValueError(name) from None
    if not math.isfinite(v): raise ValueError(name)
    return v


def simulation(bars, initial_cash=10, allocation=.2, fee_bps=5, slip_bps=2,
               hold_bars=12, lookback=12, breakout_pct=0, stop_loss_pct=.05,
               min_trade_usd=.01):
    valid_candles(bars)
    initial_cash=finite(initial_cash,'initial_cash')
    allocation=finite(allocation,'allocation')
    fee_bps=finite(fee_bps,'fee_bps')
    slip_bps=finite(slip_bps,'slip_bps')
    breakout_pct=finite(breakout_pct,'breakout_pct')
    stop_loss_pct=finite(stop_loss_pct,'stop_loss_pct')
    min_trade_usd=finite(min_trade_usd,'min_trade_usd')
    if not (initial_cash>0 and 0<allocation<=1 and 0<=fee_bps<=10000 and
            0<=slip_bps<=10000 and 0<=breakout_pct<1 and 0<stop_loss_pct<1 and
            min_trade_usd>0 and isinstance(hold_bars,int) and 1<=hold_bars<=500 and
            isinstance(lookback,int) and 2<=lookback<=500):
        raise ValueError('invalid simulation parameters')
    if len(bars)<lookback+2:raise ValueError('insufficient history')
    cash=initial_cash; qty=0.; fees=0.; entries=0; exits=0; trades=[]; equity=[]
    buy_bar=None; entry_cost=None; stop=False
    # at end of bar i, decide intent to execute next bar open; never use bar i+1 H/L/C
    for i in range(lookback,len(bars)-1):
        cl=finite(bars[i][4],'close')
        next_open=finite(bars[i+1][1],'next open')
        if next_open<=0:raise ValueError('bad open')
        if qty>0:
            # time exit or close-based protective exit; gaps are priced at *next open*
            should_exit=(i-buy_bar>=hold_bars or cl <= (entry_cost/(1+fee_bps/10000))* (1-stop_loss_pct))
            if should_exit:
                fill=next_open*(1-slip_bps/10000)
                gross=qty*fill; commission=gross*fee_bps/10000
                cash+=gross-commission;fees+=commission
                trades.append({'side':'SELL','decision_open_ms':int(bars[i][0]),'fill_open_ms':int(bars[i+1][0]),
                               'price':fill,'qty':qty,'fee':commission,'cash_after':cash})
                qty=0.;buy_bar=None;entry_cost=None;exits+=1
        elif not stop:
            prior_max=max(finite(bars[j][4],'prior close') for j in range(i-lookback,i))
            if cl>prior_max*(1+breakout_pct):
                budget=cash*allocation
                if budget>=min_trade_usd:
                    fill=next_open*(1+slip_bps/10000)
                    commission=budget*fee_bps/10000
                    new_qty=(budget-commission)/fill
                    cash-=budget;fees+=commission;qty=new_qty
                    buy_bar=i+1; entry_cost=fill; entries+=1
                    trades.append({'side':'BUY','decision_open_ms':int(bars[i][0]),'fill_open_ms':int(bars[i+1][0]),
                                   'price':fill,'qty':qty,'fee':commission,'cash_after':cash})
        marked=cash+qty*next_open
        equity.append({'open_ms':int(bars[i+1][0]),'equity':marked})
        if cash< -1e-8 or qty< -1e-12:raise ArithmeticError('negative cash or position')
    # Close at final known bar CLOSE using a separate end-of-sample mark; never declare real fills.
    last_close=finite(bars[-1][4],'last close')
    if qty:
        fill=last_close*(1-slip_bps/10000)
        gross=qty*fill; commission=gross*fee_bps/10000
        cash+=gross-commission; fees+=commission
        trades.append({'side':'SELL_MARK_TO_END','decision_open_ms':int(bars[-1][0]),
                       'fill_open_ms':None,'price':fill,'qty':qty,'fee':commission,'cash_after':cash,
                       'assumption':'synthetic end-of-sample liquidation at final close; not a real fill'})
        qty=0.;exits+=1
    equity.append({'open_ms':int(bars[-1][0]),'equity':cash})
    peak=initial_cash;dd=0.
    for v in equity:
        peak=max(peak,v['equity']);dd=min(dd,(v['equity']/peak-1)*100)
    return {'mode':'HISTORICAL_PAPER_ONLY','research_only':True,'initial_virtual_usd':initial_cash,
            'final_virtual_usd':round(cash,8),'virtual_net_usd':round(cash-initial_cash,8),
            'virtual_net_pct':round((cash/initial_cash-1)*100,8), 'assumed_fees_usd':round(fees,8),
            'max_drawdown_pct':round(dd,8),'entries':entries,'exits':exits,'cash_after':round(cash,8),
            'quantity_after':qty,'ledger_balanced':abs(qty)<1e-10 and cash>=0,
            'positions_closed_by_end_assumption':bool(trades and trades[-1]['side']=='SELL_MARK_TO_END'),
            'trades':trades,'equity_curve':equity,
            'limitations':'Historical paper fills at next open; no order book, queue, live latency, funding, real settlement or execution guarantee.'}


def run(inputs, out, **kwargs):
    reports={}
    for file in inputs:
        path=Path(file)
        if not path.is_file():raise FileNotFoundError(file)
        b=path.read_bytes(); bars=json.loads(b.decode('utf-8-sig'))
        if path.stem in reports:raise ValueError('duplicate dataset stem')
        reports[path.stem]={'source_sha256':hashlib.sha256(b).hexdigest(),
                            'bars':len(bars),'paper':simulation(bars,**kwargs)}
    result={'schema_version':1,'research_only':True,'realized_profit_usd':None,
            'markets':reports,'warning':'SIMULATED ONLY; not actual or expected profitability.'}
    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description='CQWE v17 cash-only historical paper loop, no network or orders')
    p.add_argument('--inputs',nargs='+',required=True);p.add_argument('--output',default='reports/v17_paper.json')
    p.add_argument('--initial-cash',type=float,default=10);p.add_argument('--allocation',type=float,default=.2)
    p.add_argument('--fee-bps',type=float,default=5);p.add_argument('--slip-bps',type=float,default=2)
    p.add_argument('--hold-bars',type=int,default=12);p.add_argument('--lookback',type=int,default=12)
    a=p.parse_args()
    r=run(a.inputs,a.output,initial_cash=a.initial_cash,allocation=a.allocation,
          fee_bps=a.fee_bps,slip_bps=a.slip_bps,hold_bars=a.hold_bars,lookback=a.lookback)
    for symbol,v in r['markets'].items():
        q=v['paper'];print(symbol,'virtual_net_usd=',q['virtual_net_usd'],'entries=',q['entries'],
                          'max_drawdown_pct=',q['max_drawdown_pct'],'balanced=',q['ledger_balanced'])
    print('CQWE_V17_PAPER_LOOP_PASS | HISTORICAL SIMULATION ONLY | NO ORDERS')
if __name__=='__main__':main()
