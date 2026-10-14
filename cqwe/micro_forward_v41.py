"""CQWE V41 causal public-book forward quote experiment.

A *recorded* V40 REST snapshot is a prospective observation, not an executable
order nor a synchronized L2 event stream. Only later recorded snapshots can
settle forecasts. Read-only evidence; no funds, orders or market-maker labels.
"""
from __future__ import annotations
import argparse, json, math, statistics, time
from pathlib import Path
from .microstructure_v40 import SYMBOLS, collect_once, store_record, _verify, VERSION as OBS_VERSION
from .public_data_v29 import _digest

VERSION='CQWE_V41_CAUSAL_BOOK_FORWARD'
HORIZONS=(60_000,300_000)
TOLERANCE={60_000:25_000,300_000:45_000}
REQUIRED_PAIRS=100


def _load(root):
    out={s:[] for s in SYMBOLS}
    seen=set()
    for path in sorted(Path(root).glob('observation_*.json')):
        r=json.loads(path.read_text(encoding='utf-8'))
        _verify(r)
        if r.get('version')!=OBS_VERSION or r.get('research_only') is not True or r.get('no_orders') is not True:raise ValueError('UNTRUSTED_OBSERVATION')
        m=r.get('observed_market')
        if not isinstance(m,dict) or m.get('symbol') not in SYMBOLS or not isinstance(m.get('recorded_at_ms'),int):raise ValueError('MALFORMED_OBSERVATION')
        for name in ('bid','ask','mid','microprice_displacement_bps','depth5_imbalance','spread_bps'):
            if not isinstance(m.get(name),(int,float)) or not math.isfinite(m[name]):raise ValueError('INVALID_OBS_PRICE_OR_FEATURE')
        if not (0<m['bid']<m['ask'] and m['bid']<m['mid']<m['ask']):raise ValueError('INVALID_BBO')
        if m['spread_bps']<0 or abs(m['depth5_imbalance'])>1.000001:raise ValueError('INVALID_FEATURE')
        if m.get('snapshot_start_ms',0)>m['recorded_at_ms']:raise ValueError('INVALID_OBS_CLOCK')
        key=(m['symbol'],m['recorded_at_ms'])
        if key in seen:raise ValueError('DUPLICATE_MARKET_TIMESTAMP')
        seen.add(key)
        out[m['symbol']].append((m,r['sha256']))
    for s in out:out[s].sort(key=lambda v:v[0]['recorded_at_ms'])
    return out


def rule(m):
    """Fixed conservative zero/plus/minus pressure *research* classifier.

    No tuning based on observed future outcome. This function is deliberately
    simple as a frozen benchmark; it cannot infer market-maker identity.
    """
    if m['spread_bps']>5:return 0
    micro=m['microprice_displacement_bps'];depth=m['depth5_imbalance']
    if micro>=0.2 and depth>=0.15:return 1
    if micro<=-0.2 and depth<=-0.15:return -1
    return 0


def _match(obs, idx, horizon):
    a=obs[idx][0];target=a['recorded_at_ms']+horizon
    # Never use an observation recorded BEFORE the intended forecast maturity.
    for b, b_hash in obs[idx+1:]:
        t=b['recorded_at_ms']
        if t<target:continue
        if t-target<=TOLERANCE[horizon]:return b,b_hash
        break
    return None


def evaluate(root='reports/v40_microstructure', *, now_ms=None):
    now_ms=int(time.time()*1000) if now_ms is None else now_ms
    data=_load(root)
    results={};events=[]
    for sym,seq in data.items():
        per={}
        for horizon in HORIZONS:
            candidates=0;matched=0;signals=0;correct=0;directional=[];gross=[];crossing=[]
            for i,(m,source_hash) in enumerate(seq):
                if m['recorded_at_ms']+horizon>now_ms:continue
                candidates+=1
                result=_match(seq,i,horizon)
                if result is None:continue
                future,future_hash=result
                if future['recorded_at_ms']>now_ms:continue
                matched+=1
                side=rule(m)
                movement_bps=(future['mid']/m['mid']-1)*10000
                # Read-only market-taker quote crossing proxy, not an assumed fill.
                buy_cross_bps=(future['bid']/m['ask']-1)*10000
                sell_cross_bps=(m['bid']/future['ask']-1)*10000
                if side:
                    signals+=1
                    pnl=side*movement_bps
                    directional.append(pnl)
                    gross.append(pnl)
                    crossing.append(buy_cross_bps if side>0 else sell_cross_bps)
                    if pnl>0:correct+=1
                events.append({'symbol':sym,'horizon_ms':horizon,'source_ms':m['recorded_at_ms'],
                    'source_sha256':source_hash,'future_ms':future['recorded_at_ms'],
                    'future_sha256':future_hash,'direction':side,'mid_move_bps':round(movement_bps,9),
                    'quote_cross_proxy_bps':round(buy_cross_bps if side>0 else sell_cross_bps,9) if side else None})
            per[str(horizon//1000)+'s']={'matured_attempts':candidates,'matched_pairs':matched,
                 'coverage':round(matched/candidates,6) if candidates else None,
                 'directional_signals':signals,'directional_correct':correct,
                 'mean_signed_mid_move_bps':round(statistics.mean(directional),8) if directional else None,
                 'mean_quote_cross_proxy_bps':round(statistics.mean(crossing),8) if crossing else None,
                 'passes_sample_floor':signals>=REQUIRED_PAIRS}
        results[sym]={'observations':len(seq),'horizons':per}
    # Event hashes link source and future; report is derived, never overwrite raw observations.
    return {'version':VERSION,'symbol_results':results,'matched_event_count':len(events),
        'events':events,'profitable_edge_proven':False,'real_profit_usd':0.0,
        'limitations':['REST snapshots are not synchronized L2 sequence','No queue position, cancellation flow or real order latency',
        'Quote-crossing is an executable-price proxy, not a trade fill','At most one minute cadence cannot validate 30s horizon',
        'Forward results are overlapping and cannot be treated as independent trades'],
        'research_only':True,'no_orders':True}


def run_once(symbol='BNBUSDT',root='reports/v40_microstructure',fetch=None,clock=None):
    opts={}
    if fetch is not None:opts['fetch']=fetch
    if clock is not None:opts['clock']=clock
    snap=collect_once(symbol,**opts)
    path,status=store_record(snap,root)
    return {'record':path,'status':status,'symbol':symbol,'recorded_at_ms':snap['recorded_at_ms']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--symbol',choices=SYMBOLS,default='BNBUSDT')
    parser.add_argument('--root',default='reports/v40_microstructure')
    parser.add_argument('--offline-audit',action='store_true')
    args=parser.parse_args()
    if not args.offline_audit:
        print('CQWE_V41_COLLECT_PASS '+json.dumps(run_once(args.symbol,args.root),sort_keys=True))
    result=evaluate(args.root)
    # Keep reports compact: event details are reproducible from hashed raw files.
    summary={k:v for k,v in result.items() if k!='events'}
    print('CQWE_V41_FORWARD_AUDIT '+json.dumps(summary,sort_keys=True))
    print('PUBLIC QUOTE RESEARCH | NO ORDERS | NO MARKET MAKER IDENTITY | NO PROFIT CLAIM')
if __name__=='__main__':main()
