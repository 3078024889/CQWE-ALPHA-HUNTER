"""CQWE V07 offline microstructure feature and forward-label research.
Public historical 5m klines and optional OI history only. Never place orders.
"""
import json
import math
import statistics
from pathlib import Path

STEP = 300_000


def _number(x):
    v = float(x)
    if not math.isfinite(v):
        raise ValueError('nonfinite numeric data')
    return v


def validate_klines(bars):
    if not isinstance(bars, list) or len(bars) < 50:
        raise ValueError('need >=50 klines')
    prior = None
    for b in bars:
        if not isinstance(b, list) or len(b) < 11:
            raise ValueError('bad kline shape')
        t = int(b[0])
        if prior is not None and t - prior != STEP:
            raise ValueError('duplicate, missing, or unordered klines')
        if int(b[6]) != t + STEP - 1:
            raise ValueError('invalid close time')
        op, hi, low, cl = map(_number, b[1:5])
        turnover, bought = _number(b[7]), _number(b[10])
        if low <= 0 or not low <= min(op, cl) <= max(op, cl) <= hi:
            raise ValueError('invalid OHLC')
        if turnover < 0 or bought < 0 or bought > turnover + 1e-6:
            raise ValueError('invalid taker turnover')
        prior = t
    return bars


def _oi_index(history):
    """Binance OI history timestamps refer to sample timestamps, not candle closes.
    Conservative rule: only use records with timestamp <= signal bar close time.
    Does not infer unobserved OI changes or backfill future samples.
    """
    if history is None:
        return {}
    if isinstance(history, dict):
        history = history.get('series', [])
    result = {}
    for rec in history:
        t = int(rec['timestamp'])
        value = _number(rec.get('oi_value', rec.get('sumOpenInterestValue')))
        if value <= 0:
            raise ValueError('invalid OI')
        if t in result:
            raise ValueError('duplicate OI timestamp')
        result[t] = value
    return result


def rows(bars, oi_history=None, lookback=24, horizon=12, max_oi_age_ms=600_000):
    """Features use only completed signal bar & past; label is next-open to horizon close.
    Repeated rows are overlapping observations, NOT independent trade outcomes.
    """
    validate_klines(bars)
    if lookback < 3 or horizon < 1 or max_oi_age_ms < 0:
        raise ValueError('invalid parameters')
    oi = _oi_index(oi_history)
    times = sorted(oi)
    out = []
    for i in range(lookback, len(bars)-horizon):
        b = bars[i]
        old = bars[i-lookback:i]
        open_next = _number(bars[i+1][1])
        exit_close = _number(bars[i+horizon][4])
        turnovers = [_number(x[7]) for x in old]
        median = statistics.median(turnovers)
        current = _number(b[7])
        signal_close = int(b[6])
        record = {
            'signal_ms': signal_close,
            'entry_ms': int(bars[i+1][0]),
            'future_exit_ms': int(bars[i+horizon][6]),
            'close': _number(b[4]),
            'turnover_ratio': current/median if median > 0 else None,
            'taker_buy_fraction': _number(b[10])/current if current > 0 else None,
            'breakout': _number(b[4]) > max(_number(x[2]) for x in old),
            'breakdown': _number(b[4]) < min(_number(x[3]) for x in old),
            'return_next_open_to_horizon_close_pct': 100 * (exit_close/open_next - 1),
            'max_adverse_long_pct': 100 * (min(_number(x[3]) for x in bars[i+1:i+horizon+1])/open_next - 1),
            'oi_change_pct': None,
        }
        if times:
            # Match 2 OI observations: latest valid <= close and nearest <= prior bar close.
            now = next((t for t in reversed(times) if t <= signal_close and signal_close-t <= max_oi_age_ms), None)
            earlier = next((t for t in reversed(times) if t <= signal_close - STEP and
                            signal_close - STEP - t <= max_oi_age_ms), None)
            if now is not None and earlier is not None and now > earlier:
                record['oi_change_pct'] = 100 * (oi[now]/oi[earlier]-1)
        out.append(record)
    return out


def describe(records, fee_bps=5, slippage_bps=2):
    if fee_bps < 0 or slippage_bps < 0:
        raise ValueError('negative costs')
    # Predeclared descriptive cohort, no optimization or probabilistic claims.
    selected = [r for r in records if r['breakout'] and
                r['turnover_ratio'] is not None and r['turnover_ratio'] >= 2 and
                r['taker_buy_fraction'] is not None and r['taker_buy_fraction'] > .5]
    values = [r['return_next_open_to_horizon_close_pct'] - 2*(fee_bps+slippage_bps)/100 for r in selected]
    return {'observations':len(records), 'matched_signals':len(selected),
            'mean_assumed_net_pct':round(statistics.mean(values),6) if values else None,
            'win_fraction':round(sum(v>0 for v in values)/len(values),6) if values else None,
            'worst_mae_pct':round(min(r['max_adverse_long_pct'] for r in selected),6) if selected else None,
            'oi_coverage_count':sum(r['oi_change_pct'] is not None for r in selected),
            'warning':'Descriptive overlapping event labels, NOT portfolio return; no funding, impact, liquidation or orderbook replay.'}


def study(klines_path, oi_path=None, output='reports/v07_microstructure.json'):
    candles = json.loads(Path(klines_path).read_text(encoding='utf-8-sig'))
    oi = json.loads(Path(oi_path).read_text(encoding='utf-8-sig')) if oi_path else None
    observations = rows(candles, oi)
    cut = int(len(candles)*.7)
    # An event belongs to train only when its outcome is entirely in train.
    signal_last_train = int(candles[cut-1][6])
    train = [r for r in observations if r['future_exit_ms'] <= signal_last_train]
    test = [r for r in observations if r['entry_ms'] >= int(candles[cut][0])]
    summary = {'mode':'RESEARCH_ONLY_NO_ORDERS','source':str(klines_path),
               'oi_source':str(oi_path) if oi_path else None,
               'train':describe(train),'holdout':describe(test),
               'split_time_ms':int(candles[cut][0]),
               'warning':'Predeclared descriptive cohort, non-independent overlapping events, no statistical significance asserted.'}
    dest = Path(output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp = dest.with_suffix(dest.suffix+'.tmp')
    tmp.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    tmp.replace(dest)
    return summary
