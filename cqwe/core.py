"""Read-only Binance USD-M REST client and strict market data validation."""
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = 'https://fapi.binance.com'
PERIOD_MS = 300000


def request(path, params=None, retries=3):
    permitted = {'/fapi/v1/exchangeInfo','/fapi/v1/ticker/24hr','/fapi/v1/klines',
                 '/fapi/v1/time','/fapi/v1/openInterest','/fapi/v1/premiumIndex',
                 '/futures/data/openInterestHist'}
    if path not in permitted:
        raise ValueError('endpoint outside read-only allowlist')
    qs = urllib.parse.urlencode(params or {})
    url = BASE + path + ('?' + qs if qs else '')
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'CQWE-Research/0.5'})
            with urllib.request.urlopen(req, timeout=12) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (418, 429):
                raise RuntimeError(f'Binance rate limit HTTP {e.code}; stop and retry later') from e
            if 400 <= e.code < 500:
                raise RuntimeError(f'Binance invalid request HTTP {e.code}: {path}') from e
            if attempt == retries - 1:
                raise RuntimeError(f'Binance server unavailable HTTP {e.code}') from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == retries - 1:
                raise RuntimeError(f'Binance request failed: {path}: {e}') from e
        time.sleep(1 + attempt * 2)


def valid_symbol(symbol):
    if not symbol or not symbol.endswith('USDT') or not symbol[:-4].isalnum() or not symbol.isupper():
        raise ValueError('Only uppercase USDT symbols are allowed')
    return symbol


def valid_candles(candles, now_ms=None, period_ms=PERIOD_MS):
    if not isinstance(candles, list) or not candles:
        raise ValueError('empty candles')
    last = -1
    for c in candles:
        if not isinstance(c, list) or len(c) < 11:
            raise ValueError('invalid Binance kline shape')
        t = int(c[0]); close_time = int(c[6])
        if t <= last or (last >= 0 and t-last != period_ms):
            raise ValueError('duplicate, missing or out-of-order bars')
        if close_time != t + period_ms-1:
            raise ValueError('inconsistent kline close time')
        op, hi, lo, cl = map(float, (c[1], c[2], c[3], c[4]))
        turnover, taker_buy = float(c[7]), float(c[10])
        if not all(math.isfinite(x) for x in (op, hi, lo, cl, turnover, taker_buy)) or lo <= 0 or min(op, cl) < lo or max(op, cl) > hi or hi < lo or turnover < 0 or taker_buy < 0 or taker_buy > turnover + 0.001:
            raise ValueError('invalid price/turnover data')
        if now_ms is not None and close_time >= now_ms:
            raise ValueError('unfinished candle')
        last = t
    return candles


def save_json(path, value):
    dest = Path(path); dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(dest)
    return dest
