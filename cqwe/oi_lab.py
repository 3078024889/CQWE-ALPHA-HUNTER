"""CQWE V08 conservative open-interest history collector and signal attribution.
Uses public endpoints only, never API keys/orders.
Historical OI is rolling-retention data and cannot be reconstructed when expired.
"""
import argparse
import datetime as dt
import json
import math
import statistics
import time
from pathlib import Path
from .core import request, save_json, valid_symbol
from .microstructure import rows, validate_klines

STEP=300_000

def fetch_oi(symbol, start_ms, end_ms, page_limit=500, pause=0.2, get=request):
    symbol=valid_symbol(symbol)
    if start_ms<0 or end_ms<start_ms or not 2<=page_limit<=500 or pause<0:
        raise ValueError('invalid OI query')
    # Timestamp pagination with a strict advancement guard and a page budget.
    # Binance retains only recent samples; missing historical data must stay missing.
    cursor=int(start_ms)
    observed={}
    for _ in range(200):
        if cursor>end_ms:break
        page=get('/futures/data/openInterestHist', {'symbol':symbol,'period':'5m',
                            'startTime':cursor,'endTime':int(end_ms),'limit':page_limit})
        if not isinstance(page,list):raise ValueError('unexpected OI response')
        if not page:break
        parsed=[]
        for item in page:
            t=int(item['timestamp']); v=float(item['sumOpenInterestValue'])
            if not math.isfinite(v) or v<=0:raise ValueError('bad OI value')
            if start_ms<=t<=end_ms:
                if t in observed and observed[t]!=v:raise ValueError('conflicting OI sample')
                observed[t]=v
            parsed.append(t)
        maximum=max(parsed)
        if maximum<cursor:break
        if maximum==cursor and len(parsed)>1:raise ValueError('OI pagination failed to advance')
        cursor=maximum+1
        if len(page)<page_limit:break
        if pause:time.sleep(pause)
    else:raise ValueError('OI page budget exceeded')
    return [{'timestamp':t,'oi_value':observed[t]} for t in sorted(observed)]


def paired_study(bars, oi_series=None, fee_bps=5, slip_bps=2, min_samples=25):
    validate_klines(bars)
    if fee_bps<0 or slip_bps<0 or min_samples<1:raise ValueError('invalid cost/sample configuration')
    records=rows(bars,oi_history=oi_series)
    # Non-overlapping event labels, conservative OI-coverage gating.
    selected=[];last_exit=-1
    for r in records:
        if r['signal_ms']<=last_exit:continue
        if not r['breakout'] or r['turnover_ratio'] is None or r['turnover_ratio']<2:continue
        selected.append(r)
        last_exit=r['future_exit_ms']
    def stats(items):
        returns=[x['return_next_open_to_horizon_close_pct']-2*(fee_bps+slip_bps)/100 for x in items]
        return {'count':len(items),'mean_net_pct':round(statistics.mean(returns),6) if returns else None,
                'win_fraction':round(sum(x>0 for x in returns)/len(returns),6) if returns else None,
                'worst_mae_pct':round(min(x['max_adverse_long_pct'] for x in items),6) if items else None}
    with_oi=[x for x in selected if x['oi_change_pct'] is not None]
    rising=[x for x in with_oi if x['oi_change_pct']>0]
    falling=[x for x in with_oi if x['oi_change_pct']<=0]
    # NO automatic claim of advantage with insufficient historical OI coverage.
    eligible=len(with_oi)>=min_samples and len(rising)>=min_samples//2 and len(falling)>=min_samples//2
    return {'research_only':True,'signal':'volume_breakout','events_all':stats(selected),
            'events_with_oi':stats(with_oi),'oi_rising':stats(rising),'oi_flat_or_falling':stats(falling),
            'oi_coverage_fraction':round(len(with_oi)/len(selected),6) if selected else 0,
            'eligible_for_oi_comparison':eligible,
            'conclusion':'INSUFFICIENT_OI_SAMPLES' if not eligible else 'DESCRIPTIVE_ONLY_NO_CAUSAL_CLAIM',
            'warning':'OI value is not capital inflow; OHLC forward labels omit funding, bid-ask spread, queue, liquidation. No profitability claim.'}


def main():
    ap=argparse.ArgumentParser(description='V08 offline/online OI study; NEVER places orders')
    ap.add_argument('--klines',required=True)
    ap.add_argument('--symbol',default='BTCUSDT')
    ap.add_argument('--oi-file',default=None)
    ap.add_argument('--fetch-oi',action='store_true')
    ap.add_argument('--output',default='reports/v08_oi_study.json')
    a=ap.parse_args()
    bars=json.loads(Path(a.klines).read_text(encoding='utf-8'))
    validate_klines(bars)
    if a.fetch_oi and a.oi_file:ap.error('choose only one OI source')
    if a.fetch_oi:
        oi=fetch_oi(a.symbol,int(bars[0][0]),int(bars[-1][6]))
        save_json(f'data/oi/{a.symbol}_v08_history.json',oi)
    elif a.oi_file:
        oi=json.loads(Path(a.oi_file).read_text(encoding='utf-8'))
    else:oi=[]
    result=paired_study(bars,oi)
    result.update({'symbol':a.symbol,'oi_records_downloaded':len(oi),
                   'source_kline_count':len(bars),'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
    save_json(a.output,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('CQWE_V08_STUDY_PASS | NO ORDERS | NO ACCOUNT ACCESS')

if __name__=='__main__':main()
