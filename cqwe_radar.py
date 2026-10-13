#!/usr/bin/env python3
"""CQWE Binance USD-M Futures public-data radar, read-only. Python 3.10+.
No API keys, orders or account access. Research signals only.
"""
import argparse
import csv
import datetime as dt
import json
import math
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = 'https://fapi.binance.com'
HEADERS = {'User-Agent': 'CQWE-Research-Radar/0.1 (public market data)'}


def get(path, params=None):
    query = urllib.parse.urlencode(params or {})
    url = BASE + path + ('?' + query if query else '')
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=18) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == 2:
                raise RuntimeError(f'Binance market data unavailable: {path}: {exc}') from exc
            time.sleep(1.2 * (attempt + 1))


def safe_float(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (ValueError, TypeError):
        return default


def select_contracts(exchange):
    return {s['symbol'] for s in exchange['symbols']
            if s.get('status') == 'TRADING'
            and s.get('contractType') == 'PERPETUAL'
            and s.get('quoteAsset') == 'USDT'}


def candidates(tickers, allowed, min_quote, max_symbols):
    pool = [t for t in tickers if t.get('symbol') in allowed
            and safe_float(t.get('quoteVolume')) >= min_quote
            and safe_float(t.get('lastPrice')) > 0]
    pool.sort(key=lambda t: safe_float(t.get('quoteVolume')), reverse=True)
    return pool[:max_symbols]


def analyze(ticker, candles, funding=None, oi=None):
    # Binance supplies the currently forming bar: EXCLUDE it to avoid look-ahead.
    completed = candles[:-1]
    if len(completed) < 27:
        raise ValueError('not enough completed candles')
    latest = completed[-1]
    closes = [safe_float(x[4]) for x in completed]
    volumes = [safe_float(x[7]) for x in completed]  # USDT turnover per bar
    close = closes[-1]
    if close <= 0 or closes[-7] <= 0:
        raise ValueError('bad prices')
    momentum_30 = (close / closes[-7] - 1) * 100
    turnover_ratio = volumes[-1] / max(statistics.median(volumes[-25:-1]), 1)
    previous_high = max(safe_float(x[2]) for x in completed[-25:-1])
    breakout = close > previous_high
    funding_pct = safe_float((funding or {}).get('lastFundingRate')) * 100
    oi_amount = safe_float((oi or {}).get('openInterest'))
    # Anomaly rank, NOT probability of profit or executable signal.
    score = (min(max(momentum_30, -10), 30) * 0.6
             + min(max(math.log2(max(turnover_ratio, 0.01)), -4), 5) * 3
             + (4 if breakout else 0))
    return {
        'symbol': ticker['symbol'],
        'last_closed_5m_utc': dt.datetime.fromtimestamp(int(latest[6]) / 1000, dt.timezone.utc).isoformat(),
        'close': close,
        'change_24h_pct': safe_float(ticker.get('priceChangePercent')),
        'momentum_30m_pct': round(momentum_30, 3),
        'volume_ratio_vs_prior_24_5m_bars': round(turnover_ratio, 3),
        'breakout_above_prior_2h': breakout,
        'quote_turnover_24h_usdt': round(safe_float(ticker.get('quoteVolume')), 2),
        'funding_rate_pct': round(funding_pct, 5),
        'open_interest_contract_units': oi_amount,
        'anomaly_score_not_profit_probability': round(score, 3),
        'signal': 'RESEARCH_ONLY_NO_ORDERS',
    }


def run(args):
    print('CQWE MARKET RADAR | PUBLIC DATA ONLY | NO ACCOUNT ACCESS | NO ORDERS')
    allowed = select_contracts(get('/fapi/v1/exchangeInfo'))
    pool = candidates(get('/fapi/v1/ticker/24hr'), allowed, args.min_quote_volume, args.scan)
    print(f'USDT perpetual contracts screened: {len(pool)} | 24h quote turnover floor: {args.min_quote_volume:,.0f} USDT')
    result = []
    for index, ticker in enumerate(pool, 1):
        symbol = ticker['symbol']
        try:
            bars = get('/fapi/v1/klines', {'symbol': symbol, 'interval': '5m', 'limit': 60})
            # Additional public endpoints; tolerate individual missing values.
            try:
                funding = get('/fapi/v1/premiumIndex', {'symbol': symbol})
            except RuntimeError:
                funding = {}
            try:
                oi = get('/fapi/v1/openInterest', {'symbol': symbol})
            except RuntimeError:
                oi = {}
            result.append(analyze(ticker, bars, funding, oi))
        except (RuntimeError, ValueError, KeyError, IndexError) as exc:
            print(f'[{index}/{len(pool)}] {symbol}: skipped ({exc})')
        if args.pause:
            time.sleep(args.pause)
    result.sort(key=lambda x: x['anomaly_score_not_profit_probability'], reverse=True)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S_UTC')
    jsonfile = output / f'radar_{stamp}.json'
    csvfile = output / f'radar_{stamp}.csv'
    jsonfile.write_text(json.dumps({'generated_utc': stamp, 'research_only': True, 'results': result}, ensure_ascii=False, indent=2), encoding='utf-8')
    if result:
        with csvfile.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(result[0]))
            writer.writeheader()
            writer.writerows(result)
    print('\nTOP ANOMALIES (NOT BUY RECOMMENDATIONS)')
    for x in result[:args.top]:
        print(f"{x['symbol']:14} 24h {x['change_24h_pct']:8.2f}%  30m {x['momentum_30m_pct']:7.2f}%  vol x{x['volume_ratio_vs_prior_24_5m_bars']:5.2f}  breakout={str(x['breakout_above_prior_2h']):5}  score={x['anomaly_score_not_profit_probability']:6.2f}")
    print(f'\nSaved JSON: {jsonfile}')
    if result:
        print(f'Saved CSV : {csvfile}')
    print('Score measures unusual movement, NOT a validated expected return. No trading was performed.')


def main():
    parser = argparse.ArgumentParser(description='Binance read-only futures market anomaly radar')
    parser.add_argument('--scan', type=int, default=25, help='number of high-liquidity USDT perpetual symbols')
    parser.add_argument('--top', type=int, default=10)
    parser.add_argument('--min-quote-volume', type=float, default=10_000_000)
    parser.add_argument('--pause', type=float, default=0.12, help='seconds between symbols')
    parser.add_argument('--out', default='cqwe_output')
    args = parser.parse_args()
    if not 1 <= args.scan <= 100 or args.top < 1 or args.min_quote_volume < 0 or args.pause < 0:
        parser.error('invalid numeric arguments')
    run(args)


if __name__ == '__main__':
    main()
