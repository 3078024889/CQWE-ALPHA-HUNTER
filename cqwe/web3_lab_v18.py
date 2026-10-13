"""V18 read-only Web3 research math. No network, wallets, private keys, orders or real fills.
CPMM x*y=k quote assumes fee deducted from amount-in, reserves strictly positive.
All hypothetical returns are indications, not executable arbitrage.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path


def numeric(x, name):
    if isinstance(x, bool): raise ValueError(name)
    try: v = float(x)
    except (ValueError, TypeError): raise ValueError(name) from None
    if not math.isfinite(v): raise ValueError(name)
    return v


def cpmm_quote(amount_in, reserve_in, reserve_out, fee_bps=30):
    a=numeric(amount_in,'amount_in'); x=numeric(reserve_in,'reserve_in'); y=numeric(reserve_out,'reserve_out'); f=numeric(fee_bps,'fee_bps')
    if a<=0 or x<=0 or y<=0 or not 0<=f<10000: raise ValueError('invalid AMM reserves, amount or fee')
    effective=a*(1-f/10000)
    out=y*effective/(x+effective)
    spot=y/x
    execution=out/a
    return {'input':a,'output':out,'spot_reference':spot,'execution_rate':execution,
            'total_degradation_bps':round((1-execution/spot)*10000,8),
            'fee_bps':f,'simulation_only':True}


def route_evidence(route_quotes, gas_usd=0, quote_age_ms=None, max_age_ms=1500):
    """Predeclared same-asset route comparison; no arbitrary token-to-USD conversion.
    No price/profit claims when gas currency cannot be normalized.
    """
    gas=numeric(gas_usd,'gas_usd')
    if gas<0 or max_age_ms<=0 or not route_quotes: raise ValueError('invalid routes / gas')
    candidates=[]
    for item in route_quotes:
        if not isinstance(item,dict):raise ValueError('bad route')
        output=numeric(item['output_usd'],'output_usd')
        if output<0:raise ValueError('negative output')
        candidates.append({'id':str(item['id']),'output_usd':output})
    if len({i['id'] for i in candidates})!=len(candidates):raise ValueError('duplicate routes')
    age=numeric(quote_age_ms,'age') if quote_age_ms is not None else None
    fresh=age is not None and 0<=age<=max_age_ms
    sorted_routes=sorted(candidates,key=lambda r:(-r['output_usd'],r['id']))
    return {'routes':sorted_routes,'best_quoted_output_usd':sorted_routes[0]['output_usd'],
            'best_after_assumed_gas_usd':round(sorted_routes[0]['output_usd']-gas,8),
            'freshness_verified':fresh,'executable':False,'realized_profit_usd':None,
            'decision':'OBSERVATION_ONLY' if fresh else 'REJECT_STALE_OR_UNKNOWN_AGE',
            'warning':'Quotes do not prove fill, atomicity or token equivalence. Gas provided as normalized USD assumption.'}


def audit(path):
    p=Path(path); raw=p.read_bytes(); obj=json.loads(raw)
    if obj.get('type')=='cpmm': report=cpmm_quote(obj['amount_in'],obj['reserve_in'],obj['reserve_out'],obj.get('fee_bps',30))
    elif obj.get('type')=='routes': report=route_evidence(obj['routes'],obj.get('gas_usd',0),obj.get('quote_age_ms'))
    else: raise ValueError('unsupported research input')
    return {'sha256':hashlib.sha256(raw).hexdigest(),'file':str(p),'result':report,'no_orders':True}


def main():
    p=argparse.ArgumentParser(description='CQWE offline Web3 pricing experiments; no orders')
    p.add_argument('--input',required=True);p.add_argument('--output',default='reports/v18_web3.json')
    a=p.parse_args();result=audit(a.input);dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2));print('CQWE_V18_WEB3_OFFLINE_PASS | NO ORDERS')
if __name__=='__main__':main()
