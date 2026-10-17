"""V71-75 audit extension: regime analysis, decision gating, lineage and research records.
No account access, no real orders and no claims of profit. Stdlib only.
"""
from __future__ import annotations
import argparse, datetime, hashlib, json, math, os, pathlib, statistics
from decimal import Decimal, InvalidOperation
from cqwe.tidal_hunter_v66_v70 import load_verified, evaluate, fetch_public, save_immutable, canonical, sha

SCHEMA='CQWE_V75_RESEARCH_RECORD'

def money(value):
    if isinstance(value, float) or isinstance(value, bool): raise ValueError('MONEY_MUST_BE_DECIMAL_STRING')
    try: x=Decimal(value)
    except (InvalidOperation, TypeError, ValueError): raise ValueError('INVALID_MONEY') from None
    if not x.is_finite() or x<0: raise ValueError('INVALID_MONEY')
    return x

def classify_regimes(bars,window=12):
    if not isinstance(bars,list) or len(bars)<100 or window<4: raise ValueError('INSUFFICIENT_REGIME_DATA')
    closes=[float(b['close']) for b in bars]
    if not all(math.isfinite(x) and x>0 for x in closes): raise ValueError('INVALID_CLOSE')
    out=[]
    for i in range(window,len(closes)):
        # Classify time i using ONLY history through i-1.
        r=[math.log(closes[j]/closes[j-1]) for j in range(i-window+1,i)]
        direction=sum(r)
        volatility=statistics.pstdev(r)
        out.append({'time':bars[i]['time'],'state':('up' if direction>0 else 'down') if abs(direction)>volatility*math.sqrt(len(r)) else 'range','volatility':round(volatility,10)})
    return out

def execution_gate(*,cash_usd='10',price,quantity,step,min_notional,leverage=1,fee_bps='5',slip_bps='5'):
    if type(leverage) is not int or leverage!=1: raise ValueError('LEVERAGE_FORBIDDEN')
    c,p,q,s,n,f,sl=map(money,(cash_usd,price,quantity,step,min_notional,fee_bps,slip_bps))
    if min(p,q,s,n)<=0 or c>Decimal('10'): raise ValueError('INVALID_EXECUTION_INPUT')
    if q%s!=0: return {'eligible':False,'reason':'LOT_STEP','notional_usd':str(p*q)}
    notional=p*q
    if notional<n:return {'eligible':False,'reason':'MIN_NOTIONAL','notional_usd':str(notional)}
    upfront=notional*(Decimal(1)+(f+sl)/Decimal(10000))
    if upfront>c:return {'eligible':False,'reason':'INSUFFICIENT_CASH','notional_usd':str(notional)}
    return {'eligible':True,'reason':'OFFLINE_FEASIBILITY_ONLY','notional_usd':str(notional),'required_usd':str(upfront)}

def audit_walkforward(base):
    if base.get('schema')!='CQWE_V66_V70_WALK_FORWARD' or base.get('selection_uses_test_data') is not False or base.get('real_orders')!=0 or base.get('live_trading') is not False:raise ValueError('INVALID_BASE_RESEARCH')
    folds=base.get('folds')
    if not isinstance(folds,list) or len(folds)<2: raise ValueError('MISSING_FOLDS')
    if any(type(x.get('trades')) is not int or x['trades']<0 or not math.isfinite(x.get('simulated_net_bps',float('nan'))) for x in folds):raise ValueError('INVALID_FOLD')
    for prev,cur in zip(folds,folds[1:]):
        if prev['test_end_time']>=cur['test_start_time']:raise ValueError('OVERLAPPING_TEST_FOLDS')
    values=[x['simulated_net_bps'] for x in folds]
    active=[x for x in folds if x['trades']>0]
    # Do not claim statistical performance with few folds or trades.
    trades=sum(x['trades'] for x in folds)
    positive=sum(x['simulated_net_bps']>0 for x in active)
    passed=trades>=30 and len(active)>=3 and positive>=3 and min(values)>0
    return {'fold_count':len(folds),'trades':trades,'positive_active_folds':positive,'worst_fold_bps':min(values),'promotion_eligible':False,'research_review_candidate':bool(passed),'interpretation':'RESEARCH_ONLY_NOT_LIVE_READY'}

def record_lineage(output, *, parent_digest, previous_digest=None):
    if not isinstance(parent_digest,str) or len(parent_digest)!=64 or any(x not in '0123456789abcdef' for x in parent_digest):raise ValueError('BAD_PARENT_DIGEST')
    if previous_digest is not None and (not isinstance(previous_digest,str) or len(previous_digest)!=64):raise ValueError('BAD_PREVIOUS_DIGEST')
    payload={'schema':SCHEMA,'source_sha256':parent_digest,'previous_record_sha256':previous_digest,'analysis':output,'simulated':True,'cash_income_usd':None,'auto_promotion':False,'live_order_enabled':False}
    payload['record_sha256']=sha(payload)
    return payload

def run_archive(input_path,report_path,*,fee_bps=5,slip_bps=5,seed=55):
    data=load_verified(input_path)
    base=evaluate(data['bars'],seed=seed,fee_bps=fee_bps,slip_bps=slip_bps)
    regimes=classify_regimes(data['bars'])
    stats={'regimes':{name:sum(x['state']==name for x in regimes) for name in ('up','down','range')},'walk_forward':audit_walkforward(base),'v70_evaluation':base,'source':data['source'],'symbol':data['symbol'],'interval':data['interval']}
    rec=record_lineage(stats,parent_digest=data['sha256'])
    save_immutable(report_path,rec)
    return rec

def main():
    p=argparse.ArgumentParser(description='Offline futures research. No live orders.')
    p.add_argument('--input');p.add_argument('--fetch',action='store_true');p.add_argument('--symbol',default='BTCUSDT');p.add_argument('--interval',default='1h');p.add_argument('--limit',type=int,default=500);p.add_argument('--archive');p.add_argument('--report',required=True)
    args=p.parse_args()
    if args.fetch==bool(args.input):p.error('choose exactly one of --fetch or --input')
    if args.fetch:
        if not args.archive:p.error('--archive required for fetch')
        obj=fetch_public(args.symbol,args.interval,args.limit)
        save_immutable(args.archive,obj)
        archive=args.archive
    else:archive=args.input
    result=run_archive(archive,args.report)
    print('V75_OFFLINE_RESEARCH=PASS')
    print('DATA_SHA256='+result['source_sha256'])
    print('REPORT='+str(pathlib.Path(args.report).resolve()))
    print('REAL_ORDERS=0')
    print('RESEARCH_REVIEW_CANDIDATE='+str(result['analysis']['walk_forward']['research_review_candidate']))

if __name__=='__main__':main()
