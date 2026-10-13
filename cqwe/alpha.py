"""Predeclared price/turnover signals; no model fitting or orders."""
import statistics
from .core import valid_candles


def decisions(candles, method='breakout', lookback=24, min_ratio=2.0):
    valid_candles(candles)
    if method not in ('breakout','reversal','baseline') or lookback < 3 or min_ratio <= 0:
        raise ValueError('invalid signal specification')
    result={}
    for i in range(lookback,len(candles)-1):
        bar=candles[i]; prev=candles[i-lookback:i]
        close=float(bar[4]); high=max(float(c[2]) for c in prev)
        low=min(float(c[3]) for c in prev)
        med=statistics.median(float(c[7]) for c in prev)
        ratio=float(bar[7])/med if med > 0 else 0
        if method == 'baseline':
            if i == lookback:result[i]='long'
        elif ratio>=min_ratio and ((method=='breakout' and close > high) or (method=='reversal' and close < low)):
            result[i]='long'
    return result
