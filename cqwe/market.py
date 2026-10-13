"""Snapshot market screening. OI snapshots are NOT changes in OI."""
import statistics
from .core import request, valid_symbol


def discover(limit=20, min_turnover=10_000_000):
    info = request('/fapi/v1/exchangeInfo')
    allowed = {s['symbol'] for s in info['symbols'] if s.get('status') == 'TRADING'
               and s.get('contractType') == 'PERPETUAL' and s.get('quoteAsset') == 'USDT'}
    tickers = request('/fapi/v1/ticker/24hr')
    pool = [t for t in tickers if t.get('symbol') in allowed and float(t.get('quoteVolume', 0)) >= min_turnover]
    pool.sort(key=lambda t: float(t['quoteVolume']), reverse=True)
    return [t['symbol'] for t in pool[:limit]]


def snapshot(symbol, limit=100):
    symbol = valid_symbol(symbol)
    raw = request('/fapi/v1/klines', {'symbol':symbol,'interval':'5m','limit':limit})
    now = int(request('/fapi/v1/time')['serverTime'])
    bars = [c for c in raw if int(c[6]) < now]
    if len(bars) < 30:
        raise ValueError('insufficient closed candles')
    from .core import valid_candles
    valid_candles(bars, now_ms=now)
    prev = bars[-25:-1]; last = bars[-1]
    ref = statistics.median(float(c[7]) for c in prev)
    vol_ratio = float(last[7])/ref if ref > 0 else 0
    taker_ratio = float(last[10])/float(last[7]) if float(last[7]) > 0 else None
    oi = request('/fapi/v1/openInterest', {'symbol':symbol})
    premium = request('/fapi/v1/premiumIndex', {'symbol':symbol})
    return {'symbol':symbol,'closed_bar_ms':int(last[0]),'price':float(last[4]),
            'volume_ratio':round(vol_ratio,4),'taker_buy_quote_fraction':round(taker_ratio,4) if taker_ratio is not None else None,
            'breakout':float(last[4]) > max(float(c[2]) for c in prev),
            'oi_contract_units_snapshot':float(oi['openInterest']),
            'funding_rate_snapshot':float(premium['lastFundingRate']),
            'classification':'RESEARCH_SNAPSHOT_NOT_ORDER','warning':'OI snapshot alone does not show inflow.'}


def historical_oi(symbol, period='5m', limit=100):
    symbol=valid_symbol(symbol)
    if period not in ('5m','15m','30m','1h','4h','1d') or not 2 <= limit <= 500:
        raise ValueError('invalid OI query')
    records = request('/futures/data/openInterestHist', {'symbol':symbol,'period':period,'limit':limit})
    if not isinstance(records, list): raise ValueError('bad OI response')
    records.sort(key=lambda x: int(x['timestamp']))
    return [{'timestamp':int(x['timestamp']), 'oi_value':float(x['sumOpenInterestValue'])} for x in records]
