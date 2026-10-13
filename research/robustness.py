"""CQWE V0.4 offline, no-account robustness study over Binance 5m klines."""
import argparse
import json
import math
import statistics
from pathlib import Path


def events(candles, lookback=24, horizon=12, volume_ratio=2.0, fee_bps=5.0, slippage_bps=2.0):
    if min(lookback-1, horizon, volume_ratio, fee_bps+1, slippage_bps+1) <= 0:
        raise ValueError('invalid arguments')
    items = []
    last_exit = -1
    for i in range(lookback, len(candles)-horizon):
        if i <= last_exit:  # non-overlapping exposure
            continue
        prev = candles[i-lookback:i]
        bar = candles[i]
        vals = [float(c[7]) for c in prev]
        ref = statistics.median(vals)
        if ref <= 0 or float(bar[7])/ref < volume_ratio:
            continue
        if float(bar[4]) <= max(float(c[2]) for c in prev):
            continue
        follow = candles[i+1:i+1+horizon]
        entry, close = float(follow[0][1]), float(follow[-1][4])
        if entry <= 0 or not all(math.isfinite(x) and x > 0 for x in [entry,close]):
            continue
        gross = 100*(close/entry-1)
        net = gross - 2*(fee_bps+slippage_bps)/100
        items.append(dict(signal_ms=int(bar[0]), entry_ms=int(follow[0][0]), exit_ms=int(follow[-1][6]),
                          gross_pct=round(gross,5), net_pct=round(net,5),
                          mfe_pct=round(100*(max(float(c[2]) for c in follow)/entry-1),5),
                          mae_pct=round(100*(min(float(c[3]) for c in follow)/entry-1),5)))
        last_exit=i+horizon
    return items


def summary(items):
    if not items:
        return {'count':0,'mean_net_pct':None,'median_net_pct':None,'win_rate_pct':None,'worst_mae_pct':None}
    net=[e['net_pct'] for e in items]
    return {'count':len(items),'mean_net_pct':round(statistics.mean(net),5),
            'median_net_pct':round(statistics.median(net),5),
            'win_rate_pct':round(100*sum(x>0 for x in net)/len(net),2),
            'worst_mae_pct':min(e['mae_pct'] for e in items)}


def analyze(candles):
    if not isinstance(candles,list) or len(candles)<100:
        raise ValueError('at least 100 candles required')
    timestamps=[int(c[0]) for c in candles]
    if any(b-a != 300000 for a,b in zip(timestamps,timestamps[1:])):
        raise ValueError('missing, duplicate, or unordered 5m candles')
    midpoint=len(candles)//2
    # Split by SIGNAL TIME, with the forward horizon entirely inside each split.
    train=candles[:midpoint]
    test=candles[midpoint:]
    output={}
    for key,cs in [('first_half',train),('second_half',test)]:
        output[key]={}
        for fee in [2,5,10]:
            ev=events(cs,fee_bps=fee,slippage_bps=2)
            output[key][f'fee_{fee}bps_each_side_slippage_2bps_each_side']=summary(ev)
    return output


def main():
    p=argparse.ArgumentParser(description='Offline 5m event robustness, no orders')
    p.add_argument('--btc',default='data/klines/BTCUSDT_5m_7d.json')
    p.add_argument('--eth',default='data/klines/ETHUSDT_5m_7d.json')
    p.add_argument('--out',default='reports/v04_robustness.json')
    a=p.parse_args()
    result={'research_only':True,'strategy':'long-only next-open breakout + turnover ratio >=2',
            'holding_bars':12,'non_overlapping':True,'costs':'fixed each-side fees plus slippage',
            'limitations':'Not executable backtest: no funding, spread, liquidation, order sizing or uncertainty bounds; 7d insufficient for validation.',
            'symbols':{}}
    for sym,file in [('BTCUSDT',a.btc),('ETHUSDT',a.eth)]:
        candles=json.loads(Path(file).read_text(encoding='utf-8'))
        result['symbols'][sym]=analyze(candles)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result['symbols'],indent=2,ensure_ascii=False))
    print('CQWE_V04_OFFLINE_RESEARCH_PASS | NO ORDERS')

if __name__=='__main__':
    main()
