"""Capture public Binance USD-M candles and run two chronological research batches.
No account API. Fixed BTC/ETH/SOL, 1500 hourly bars, 20bp round-trip proxy cost.
"""
import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

from cqwe.copernican_experiment_v81_v85 import digest, experiment
from cqwe.tidal_hunter_v66_v70 import parse_klines


def get(path, params=None):
    url = 'https://fapi.binance.com' + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as response:
        raw = response.read(2000001)
    if len(raw) > 2000000:
        raise ValueError('RESPONSE_BUDGET')
    return url, raw, json.loads(raw)


def write(path, obj):
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', required=True)
    a = p.parse_args()
    out = Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    summary = []
    for symbol in ('BTCUSDT', 'ETHUSDT', 'SOLUSDT'):
        url, raw, rows = get('/fapi/v1/klines', {'symbol': symbol, 'interval': '1h', 'limit': 1500})
        _, time_raw, clock = get('/fapi/v1/time')
        now = clock['serverTime']
        rows = [r for r in rows if r[6] < now]
        bars = parse_klines(rows, '1h')
        raw_path = out / (symbol + '.response.json')
        with raw_path.open('xb') as f:
            f.write(raw)
        write(out / (symbol + '.capture.json'), {'url': url, 'server_time_ms': now,
              'response_sha256': hashlib.sha256(raw).hexdigest(),
              'clock_response': json.loads(time_raw), 'closed_bars': len(bars)})
        previous = None
        split = len(bars)//2
        for batch, chunk in enumerate((bars[:split], bars[split:]), 1):
            source = {'source': 'BINANCE_USDM_PUBLIC_KLINES', 'symbol': symbol,
                      'interval': '1h', 'bars': chunk, 'sha256': digest(chunk), 'live_orders': False}
            write(out / f'{symbol}.batch{batch}.data.json', source)
            report = experiment(source, asof_ms=now, previous=previous)
            write(out / f'{symbol}.batch{batch}.report.json', report)
            chosen = report['selected_on_validation']
            summary.append({'symbol': symbol, 'batch': batch,
                            'selected': chosen, 'holdout': report['holdout'][chosen],
                            'updates': report['model_states']['dendritic']['updates'],
                            'report_sha256': report['sha256'], 'real_orders': 0,
                            'realized_profit_usd': None})
            previous = report
    write(out / 'summary.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
