"""Bounded public Binance USD-M historical 5m kline fetcher. No credentials or orders."""
import argparse
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = 'https://fapi.binance.com/fapi/v1/klines'
STEP = 300_000

def fetch(symbol, days=7, now_ms=None, opener=None, pause=0.35):
    if not symbol.endswith('USDT') or not symbol.replace('_','').isalnum() or len(symbol)>24:
        raise ValueError('invalid USDT symbol')
    if not 1 <= days <= 14:
        raise ValueError('days must be 1..14')
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    end_exclusive = (now_ms // STEP) * STEP  # no still-forming 5m candle
    start = end_exclusive - days * 24 * 60 * 60 * 1000
    results = {}
    open_url = opener or urllib.request.urlopen
    while start < end_exclusive:
        params = {'symbol':symbol,'interval':'5m','startTime':start,
                  'endTime':end_exclusive-1,'limit':499}
        req = urllib.request.Request(BASE+'?'+urllib.parse.urlencode(params),headers={'User-Agent':'CQWE-Research/0.3'})
        try:
            with open_url(req, timeout=15) as response:
                batch = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError('market data fetch failed; no orders attempted') from exc
        if not isinstance(batch,list) or not batch:
            break
        for bar in batch:
            if not isinstance(bar,list) or len(bar)<12:
                raise RuntimeError('invalid exchange kline format')
            stamp=int(bar[0]); close_time=int(bar[6])
            if start <= stamp < end_exclusive and close_time < now_ms:
                results[stamp]=bar
        last=int(batch[-1][0]); new_start=last+STEP
        if new_start<=start:
            raise RuntimeError('pagination made no progress')
        start=new_start
        if pause: time.sleep(pause)
    rows=[results[k] for k in sorted(results)]
    # Fail closed on missing intervals to avoid skewed backtests.
    if any(int(b[0])-int(a[0])!=STEP for a,b in zip(rows,rows[1:])):
        raise RuntimeError('KLINE_GAP_DETECTED')
    return rows

def main():
    p=argparse.ArgumentParser(description='CQWE bounded read-only futures history downloader')
    p.add_argument('--symbols',nargs='+',default=['BTCUSDT','ETHUSDT'])
    p.add_argument('--days',type=int,default=7)
    p.add_argument('--out',default='data/klines')
    a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    for sym in a.symbols:
        rows=fetch(sym,a.days)
        if len(rows)<40:
            raise RuntimeError(f'insufficient historical data for {sym}: {len(rows)}')
        path=out/f'{sym}_5m_{a.days}d.json'
        path.write_text(json.dumps(rows),encoding='utf-8')
        print(f'{sym}: {len(rows)} fully closed 5m candles -> {path}')
    print('CQWE_HISTORY_FETCH_PASS | RESEARCH_ONLY')
if __name__=='__main__':main()
