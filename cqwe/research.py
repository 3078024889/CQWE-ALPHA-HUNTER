"""Non-overlapping event research with train/test split and uncertainty context."""
import math
import statistics
from .core import valid_candles


def evaluate(candles, lookback=24, horizon=12, min_ratio=2.0, fee_bps=5, slippage_bps=2,
             stop_pct=None):
    valid_candles(candles)
    if lookback < 2 or horizon < 1 or min_ratio <= 0 or fee_bps < 0 or slippage_bps < 0:
        raise ValueError('invalid strategy parameters')
    if stop_pct is not None and not 0 < stop_pct < 100:
        raise ValueError('invalid stop')
    events=[]; next_allowed=lookback
    while next_allowed+horizon < len(candles):
        i=next_allowed; prev=candles[i-lookback:i]; curr=candles[i]
        turnover=statistics.median(float(x[7]) for x in prev)
        ratio=float(curr[7])/turnover if turnover>0 else 0
        if ratio < min_ratio or float(curr[4]) <= max(float(x[2]) for x in prev):
            next_allowed+=1; continue
        future=candles[i+1:i+horizon+1]; entry=float(future[0][1])
        if entry<=0: next_allowed+=1; continue
        exit_price=float(future[-1][4]); stopped=False; stop_fill=None
        if stop_pct is not None:
            trigger=entry*(1-stop_pct/100)
            for j,bar in enumerate(future):
                if float(bar[3])<=trigger:
                    # Gap through stop: do not assume fill at trigger if bar opens below it
                    exit_price=min(float(bar[1]),trigger);stopped=True;stop_fill=j
                    break
        gross=100*(exit_price/entry-1)
        # proportional approximation, explicitly labeled
        net=gross-2*(fee_bps+slippage_bps)/100
        observed=future[:stop_fill+1] if stopped else future
        events.append({'signal_ms':int(curr[0]),'entry_ms':int(future[0][0]),
                       'exit_ms':int(observed[-1][6]),'volume_ratio':round(ratio,4),
                       'gross_pct':round(gross,5),'net_pct_before_funding':round(net,5),
                       'mfe_pct':round(100*(max(float(c[2]) for c in observed)/entry-1),5),
                       'mae_pct':round(100*(min(float(c[3]) for c in observed)/entry-1),5),
                       'stop_triggered':stopped})
        # Signal at exit bar unavailable until bar close. Prevent overlapping exposure.
        next_allowed=i+len(observed)+1
    return events


def stats(events):
    returns=[e['net_pct_before_funding'] for e in events]
    if not returns: return {'count':0,'mean_net_pct':None,'win_rate_pct':None,'worst_mae_pct':None}
    n=len(returns); p=sum(x>0 for x in returns)/n
    # Wilson interval is descriptive only; time-correlated observations violate iid assumption.
    z=1.96; denom=1+z*z/n; midpoint=(p+z*z/(2*n))/denom
    radius=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/denom
    return {'count':n,'mean_net_pct':round(statistics.mean(returns),5),
            'median_net_pct':round(statistics.median(returns),5),'win_rate_pct':round(100*p,2),
            'wilson_95pct_descriptive':[round(100*(midpoint-radius),2),round(100*(midpoint+radius),2)],
            'worst_mae_pct':min(e['mae_pct'] for e in events)}


def walkforward(candles, split=0.7, **kwargs):
    valid_candles(candles)
    if not .5<=split<=.9: raise ValueError('bad split')
    cut=int(len(candles)*split)
    # Separate splits, forward exposure cannot leak from train to test.
    train=evaluate(candles[:cut],**kwargs)
    test=evaluate(candles[cut:],**kwargs)
    return {'train':stats(train),'test':stats(test), 'train_events':train,'test_events':test,
            'note':'No parameter tuning was performed. Not an executable PnL or investment recommendation.'}
