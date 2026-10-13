"""Paginated read-only closed-bar downloader with bounded resource use."""
import time
from .core import PERIOD_MS, request, save_json, valid_candles, valid_symbol


def fetch(symbol, days=7, now_ms=None, max_days=30):
    symbol=valid_symbol(symbol)
    if not 1 <= days <= max_days:
        raise ValueError('days must be 1..30')
    if now_ms is None: now_ms=int(request('/fapi/v1/time')['serverTime'])
    last_open = (now_ms // PERIOD_MS - 1) * PERIOD_MS
    first_open = last_open - (days * 288-1)*PERIOD_MS
    cur=first_open; out=[]
    while cur <= last_open:
        count = min(1000, (last_open-cur)//PERIOD_MS+1)
        page=request('/fapi/v1/klines',{'symbol':symbol,'interval':'5m','startTime':cur,
                                          'endTime':last_open+PERIOD_MS-1,'limit':count})
        if not isinstance(page,list) or not page:
            raise ValueError('empty paginated result')
        page=[c for c in page if int(c[0]) <= last_open and int(c[6]) < now_ms]
        if not page or int(page[0][0]) != cur:
            raise ValueError('pagination gap or unfinished candle')
        out.extend(page)
        cur=int(page[-1][0])+PERIOD_MS
        time.sleep(0.16)
    if len(out) != days*288:
        raise ValueError(f'expected {days*288} candles, got {len(out)}')
    return valid_candles(out,now_ms=now_ms)


def download(symbols, days=7, outdir='data/klines'):
    results={}
    for symbol in symbols:
        rows=fetch(symbol,days)
        dest=save_json(f'{outdir}/{symbol}_5m_{days}d.json',rows)
        results[symbol]={'count':len(rows),'path':str(dest)}
    return results
