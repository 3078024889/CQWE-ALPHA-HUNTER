"""CQWE V14: conservative research-only liquidity and evidence laboratory.
No orders, credentials, betting or account endpoints.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path


def number(v, name):
    if isinstance(v, bool): raise ValueError(f'{name}: boolean not numeric')
    try: x = float(v)
    except (TypeError, ValueError): raise ValueError(f'{name}: nonnumeric') from None
    if not math.isfinite(x): raise ValueError(f'{name}: nonfinite')
    return x


def book_cost(levels, shares, side='asks'):
    """VWAP required to immediately take `shares`; no fill assumptions beyond available levels.
    Levels: price & size, in native outcome-share units.
    """
    shares = number(shares, 'shares')
    if shares <= 0: raise ValueError('shares must be > 0')
    if side not in ('asks', 'bids'): raise ValueError('side')
    parsed=[]
    for level in levels:
        p=number(level['price'], 'price'); q=number(level['size'], 'size')
        if not 0 < p < 1 or q <= 0: raise ValueError('invalid orderbook level')
        parsed.append((p,q))
    parsed.sort(key=lambda t:t[0], reverse=side=='bids')
    left=shares; total=0.0
    for price,qty in parsed:
        take=min(left,qty); total+=take*price; left-=take
        if left <= 1e-9: break
    if left>1e-9: return {'fillable':False,'cost':None,'vwap':None,'filled':shares-left}
    return {'fillable':True,'cost':round(total,10),'vwap':round(total/shares,10),'filled':shares}


def complete_set_no_yes(yes_asks, no_asks, shares, fee_usd=0, slippage_buffer_usd=0,
                        market_age_ms=None, max_age_ms=1500, verified_complementary=False):
    """Assess *same-event* exhaustive YES+NO payouts at settlement = $1 per share.
    Ignores settlement disputes, execution sequencing, custody, chain and operational risk.
    To avoid false opportunity claims, unverified outcome matching always disqualifies.
    """
    fee=number(fee_usd,'fee'); buffer=number(slippage_buffer_usd,'slippage')
    if fee<0 or buffer<0 or max_age_ms<=0: raise ValueError('invalid cost/age')
    y=book_cost(yes_asks,shares); n=book_cost(no_asks,shares)
    result={'type':'complementary_outcomes','simulation_only':True,'book_fillable':y['fillable'] and n['fillable'],
            'verified_complementary':bool(verified_complementary),'yes':y,'no':n,
            'expected_guaranteed_profit':None,'executable':False}
    fresh=(market_age_ms is not None and 0 <= number(market_age_ms,'age') <= max_age_ms)
    result['fresh']=fresh
    if not result['book_fillable']:
        result['decision']='REJECT_DEPTH'; return result
    gross=number(shares,'shares')-y['cost']-n['cost']
    bound=round(gross-fee-buffer,8)
    result['gross_spread_usd']=round(gross,8)
    result['indicative_net_after_buffers_usd']=bound
    if not result['verified_complementary']:result['decision']='REJECT_UNVERIFIED_MARKET_MATCH'
    elif not fresh:result['decision']='REJECT_STALE_OR_UNKNOWN_AGE'
    elif bound<=0:result['decision']='REJECT_COSTS'
    else:result['decision']='RESEARCH_CANDIDATE_ONLY'
    return result


def strategy_evidence(returns, costs_bps=(0,5,10,20), min_events=100, holdout=True):
    """Event-level gross returns as fractions, NOT executable portfolio results.
    Returns a descriptive report with mandatory insufficiency/cost gates.
    """
    xs=[number(x,'event return') for x in returns]
    if not costs_bps or min_events<1: raise ValueError('bad settings')
    out={'n':len(xs),'holdout':bool(holdout),'descriptive_only':True,'cases':{}}
    for bps in costs_bps:
        bps=number(bps,'bps')
        if bps<0:raise ValueError('negative cost')
        # explicitly roundtrip cost = 2 * cost_each_side
        net=[x-2*bps/10000 for x in xs]
        mean=statistics.mean(net) if net else None
        if not holdout:gate='REJECT_NO_HOLDOUT'
        elif len(xs)<min_events:gate='REJECT_INSUFFICIENT_EVENTS'
        elif mean is None or mean<=0:gate='REJECT_NONPOSITIVE_MEAN'
        else:gate='FURTHER_INDEPENDENT_VALIDATION_REQUIRED'
        out['cases'][str(bps)]={'net_event_mean_fraction':round(mean,10) if mean is not None else None,
                                'positive_fraction':round(sum(x>0 for x in net)/len(net),6) if net else None,
                                'gate':gate}
    return out


def audit_manifest(inputs):
    out=[]
    for path in inputs:
        p=Path(path)
        if not p.is_file(): raise FileNotFoundError(str(path))
        data=p.read_bytes(); obj=json.loads(data)
        if not isinstance(obj,list) or not obj: raise ValueError('dataset must be nonempty kline list')
        from .core import valid_candles
        valid_candles(obj)
        out.append({'file':str(path),'sha256':hashlib.sha256(data).hexdigest(),
                    'bars':len(obj),'first_open_ms':int(obj[0][0]),'last_open_ms':int(obj[-1][0])})
    return out


def main():
    p=argparse.ArgumentParser(description='CQWE V14: offline evidence only; no trades')
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('books'); a.add_argument('--input',required=True);a.add_argument('--output',default='reports/v14_books.json')
    a=sub.add_parser('manifest');a.add_argument('--inputs',nargs='+',required=True);a.add_argument('--output',default='reports/v14_manifest.json')
    a=sub.add_parser('evidence');a.add_argument('--input',required=True);a.add_argument('--output',default='reports/v14_evidence.json')
    q=p.parse_args()
    if q.cmd=='books':
        x=json.loads(Path(q.input).read_text(encoding='utf-8'))
        # explicit allowlist prevents hidden auth or broker commands
        data=complete_set_no_yes(x['yes_asks'],x['no_asks'],x['shares'],x.get('fee_usd',0),
                                 x.get('slippage_buffer_usd',0),x.get('market_age_ms'),
                                 verified_complementary=x.get('verified_complementary',False))
    elif q.cmd=='manifest':data={'datasets':audit_manifest(q.inputs)}
    else:
        x=json.loads(Path(q.input).read_text(encoding='utf-8'))
        data=strategy_evidence(x['event_gross_returns_fraction'],min_events=x.get('min_events',100),holdout=x.get('holdout',False))
    dest=Path(q.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(data,indent=2,ensure_ascii=False));print('CQWE_V14_RESEARCH_ONLY_PASS | NO ORDERS')

if __name__=='__main__':main()
