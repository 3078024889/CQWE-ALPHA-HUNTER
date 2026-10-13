"""Offline 5-minute kline event study. Read-only; no exchange/API credentials/orders.

Input: raw Binance klines JSON array. Enter at the NEXT bar open after a
fully observed signal candle. Fixed-horizon mark-to-market is not executable PnL.
"""
import argparse
import json
import statistics
from pathlib import Path


def build_events(candles, lookback=24, horizon=12, min_volume_ratio=2.0, fee_bps=5.0):
    if lookback < 2 or horizon < 1 or min_volume_ratio <= 0 or fee_bps < 0:
        raise ValueError('invalid parameters')
    events = []
    for i in range(lookback, len(candles) - horizon):
        previous = candles[i - lookback:i]
        bar = candles[i]
        close = float(bar[4])
        high = max(float(c[2]) for c in previous)
        median_turnover = statistics.median(float(c[7]) for c in previous)
        ratio = float(bar[7]) / median_turnover if median_turnover > 0 else 0
        if close <= high or ratio < min_volume_ratio:
            continue
        future = candles[i + 1:i + 1 + horizon]
        entry = float(future[0][1])
        exit_price = float(future[-1][4])
        if entry <= 0:
            continue
        highs = [float(x[2]) for x in future]
        lows = [float(x[3]) for x in future]
        net_pct = 100 * (exit_price / entry - 1) - 2 * fee_bps / 100
        events.append({
            'signal_open_time_ms': int(bar[0]),
            'entry_open_time_ms': int(future[0][0]),
            'volume_ratio': round(ratio, 3),
            'entry': entry,
            'exit': exit_price,
            'net_return_pct_before_slippage_funding': round(net_pct, 4),
            'max_favorable_excursion_pct': round(100 * (max(highs) / entry - 1), 4),
            'max_adverse_excursion_pct': round(100 * (min(lows) / entry - 1), 4),
        })
    return events


def summarize(events):
    if not events:
        return {'events': 0, 'mean_net_return_pct': None, 'win_rate_pct': None}
    returns = [e['net_return_pct_before_slippage_funding'] for e in events]
    return {
        'events': len(events),
        'mean_net_return_pct': round(statistics.mean(returns), 4),
        'median_net_return_pct': round(statistics.median(returns), 4),
        'win_rate_pct': round(100 * sum(x > 0 for x in returns) / len(returns), 2),
        'worst_intra_trade_excursion_pct': min(e['max_adverse_excursion_pct'] for e in events),
    }


def main():
    ap = argparse.ArgumentParser(description='Offline Binance kline event study; NO orders')
    ap.add_argument('input', help='raw Binance 5m kline JSON file')
    ap.add_argument('--lookback', type=int, default=24)
    ap.add_argument('--horizon', type=int, default=12)
    ap.add_argument('--min-volume-ratio', type=float, default=2)
    ap.add_argument('--fee-bps', type=float, default=5)
    ap.add_argument('--output', default='reports/event_study.json')
    a = ap.parse_args()
    candles = json.loads(Path(a.input).read_text(encoding='utf-8'))
    if not isinstance(candles, list):
        ap.error('input must be an array of Binance klines')
    events = build_events(candles, a.lookback, a.horizon, a.min_volume_ratio, a.fee_bps)
    result = {'research_only': True, 'assumed_fill': 'next_bar_open',
              'warning': 'Excludes spread/slippage/funding/liquidation and overlapping-event adjustment.',
              'summary': summarize(events), 'events': events}
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
