"""V28 pre-registered, frozen-weight next-open $10 experimental portfolio.
Strictly later offline bars, no model fitting, network, trading, promotion or profit claim.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
from .continuous_lab_v21 import verify_saved, read_markets
from .dendritic_v19 import features, trigger, EXPERTS
from .self_evolution_v20 import HORIZON
from .mutation_governor_v27 import digest

RULE=(0.12,0.0)
THRESHOLDS=(0.10,0.20)

def _load_checked(registry_path,store):
    p=Path(registry_path); raw=p.read_bytes(); r=json.loads(raw.decode('utf-8-sig'))
    stamp=r.get('registry_sha256');assert isinstance(stamp,str)
    if digest({k:v for k,v in r.items() if k!='registry_sha256'})!=stamp:raise ValueError('REGISTRY_TAMPERED')
    if r.get('version')!='CQWE_V27_MUTATION_REGISTRY' or r.get('auto_promotion') is not False or r.get('independent_forward_evidence') is not False:raise ValueError('UNTRUSTED_REGISTRY')
    if not any(x.get('finding')=='PRICE_DIRECTION' for x in r.get('experiments',[])):raise ValueError('DIRECTION_EXPERIMENT_NOT_REGISTERED')
    checked=verify_saved(store)
    ledger=json.loads((Path(store)/'ledger.json').read_text(encoding='utf-8'))
    row=ledger['episodes'][-1]
    state=json.loads((Path(store)/row['checkpoint']).read_text(encoding='utf-8'))
    candidates=[x for x in state['candidate_states'] if (x['learning_rate'],x['decay'])==RULE]
    if len(candidates)!=1:raise ValueError('FROZEN_RULE_MISSING')
    return r,stamp,checked,candidates[0]['weights'],ledger['config']['source_sha256']

def _simulate(times,data,weights,threshold,fee_bps,slip_bps,extra_cost_bps,min_notional):
    cash=10.0;pos=None; trades=[];curve=[]; rejections={'no_signal':0,'notional':0,'occupied':0}
    # First 24 newly observed bars are warmup; no old data can leak through boundary.
    for i in range(24,len(times)-1):
        if pos is not None and i+1>=pos['due']:
            price=float(data[pos['symbol']][i+1][1])*(1-slip_bps/10000)
            proceeds=pos['qty']*price; fee=proceeds*(fee_bps+extra_cost_bps/2)/10000
            cash+=proceeds-fee
            trades.append({'side':'SELL','symbol':pos['symbol'],'time_ms':times[i+1],'qty':pos['qty'],'price':price,'fee_usd':fee,'cash_after_usd':cash})
            pos=None
        if pos is None:
            options=[]
            for sym,bars in data.items():
                f=features(bars,i)
                for expert in EXPERTS:
                    key=f'{sym}|{f["regime"]}|{expert}'
                    if weights.get(key,0)>threshold and trigger(f,expert): options.append((-weights[key],sym,expert))
            if options:
                _,sym,expert=sorted(options)[0]
                budget=cash*.6
                if budget < min_notional:rejections['notional']+=1
                else:
                    price=float(data[sym][i+1][1])*(1+slip_bps/10000)
                    rate=(fee_bps+extra_cost_bps/2)/10000
                    gross=budget/(1+rate);fee=gross*rate;qty=gross/price
                    cash-=gross+fee
                    pos={'symbol':sym,'qty':qty,'due':i+1+HORIZON}
                    trades.append({'side':'BUY','symbol':sym,'time_ms':times[i+1],'qty':qty,'price':price,'fee_usd':fee,'cash_after_usd':cash,'expert':expert})
            else:rejections['no_signal']+=1
        else:rejections['occupied']+=1
        equity=cash+(pos['qty']*float(data[pos['symbol']][i+1][4]) if pos else 0)
        if cash < -1e-8:raise ArithmeticError('NEGATIVE_CASH')
        curve.append({'time_ms':times[i+1],'equity_usd':equity})
    replay=10.0;inventory={}
    for t in trades:
        val=t['qty']*t['price'];sym=t['symbol']
        if t['side']=='BUY':replay-=val+t['fee_usd'];inventory[sym]=inventory.get(sym,0)+t['qty']
        else:replay+=val-t['fee_usd'];inventory[sym]=inventory.get(sym,0)-t['qty']
        if abs(replay-t['cash_after_usd'])>1e-7:raise ArithmeticError('CASH_REPLAY_MISMATCH')
    desired={pos['symbol']:pos['qty']} if pos else {}
    if abs(replay-cash)>1e-7 or any(abs(inventory.get(s,0)-desired.get(s,0))>1e-8 for s in set(inventory)|set(desired)):raise ArithmeticError('INVENTORY_REPLAY_MISMATCH')
    peak=10.;dd=0.
    for row in curve:
        peak=max(peak,row['equity_usd']);dd=min(dd,row['equity_usd']/peak-1)
    return {'threshold':threshold,'entries':sum(t['side']=='BUY' for t in trades),'exits':sum(t['side']=='SELL' for t in trades),
            'virtual_equity_usd':round(curve[-1]['equity_usd'],8),'virtual_net_usd':round(curve[-1]['equity_usd']-10,8),
            'max_drawdown_pct':round(dd*100,8),'cash_usd':round(cash,8),'ledger_balanced':True,
            'open_position':pos,'rejections':rejections,'trades':trades,'curve':curve}

def evaluate(registry_path,store,inputs,output=None,fee_bps=5.,slip_bps=2.,extra_cost_bps=0.,min_notional=5.):
    for n,v in [('fee',fee_bps),('slippage',slip_bps),('extra',extra_cost_bps),('min_notional',min_notional)]:
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or (v<=0 if n=='min_notional' else v<0) or v>1000:raise ValueError('BAD_COST_ASSUMPTION')
    reg,stamp,check,weights,prior=_load_checked(registry_path,store)
    times,data,origins=read_markets(inputs)
    if len(times)<240:raise ValueError('INSUFFICIENT_FORWARD_BARS')
    if times[0]<=check['last_seen_ms']:raise ValueError('REUSED_OR_OVERLAPPING_HISTORY')
    if times[0]!=check['last_seen_ms']+300000:raise ValueError('GAP_AFTER_CHECKPOINT')
    if set(origins)!=set(prior):raise ValueError('MARKET_SET_CHANGED')
    if any(origins[s]==prior[s] for s in origins):raise ValueError('SAME_SOURCE_BYTES')
    if not weights:raise ValueError('FROZEN_WEIGHTS_EMPTY')
    variants=[_simulate(times,data,weights,t,fee_bps,slip_bps,extra_cost_bps,min_notional) for t in THRESHOLDS]
    result={'version':'CQWE_V28_FROZEN_FORWARD_EXPERIMENT','research_only':True,'simulation_only':True,'no_orders':True,
        'auto_promotion':False,'independent_profit_claim':False,'event_watermark_verified':True,
        'independent_source_claim':False,'note':'Chronologically later input checked, but independence of market/provider, execution liquidity and choice of input not established.',
        'frozen_learning_rule':list(RULE),'registry_sha256':stamp,'checkpoint_tip_sha256':check['tip_sha256'],
        'checkpoint_last_seen_ms':check['last_seen_ms'],'future_first_ms':times[0],'future_last_ms':times[-1],
        'future_sources_sha256':origins,'cost_assumptions':{'fee_bps_per_side':fee_bps,'slip_bps_per_side':slip_bps,'extra_roundtrip_bps':extra_cost_bps,'min_notional_usd':min_notional},
        'cash_baseline_usd':10.,'variants':variants,'decision':'EXPLORATORY_ONLY_NO_PROMOTION'}
    result['audit_sha256']=digest(result)
    if output is not None:
        p=Path(output);p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_name(p.name+'.tmp')
        temp.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');temp.replace(p)
    return result

def main():
    p=argparse.ArgumentParser(description='V28 causally later frozen-weight experiment, offline only')
    p.add_argument('--registry',required=True);p.add_argument('--store',required=True);p.add_argument('--inputs',nargs='+',required=True)
    p.add_argument('--output',default='reports/v28_forward_experiment.json');p.add_argument('--extra-cost-bps',type=float,default=0)
    a=p.parse_args();r=evaluate(a.registry,a.store,a.inputs,a.output,extra_cost_bps=a.extra_cost_bps)
    for v in r['variants']:print('V28 frozen threshold=',v['threshold'],'entries=',v['entries'],'virtual_net=',v['virtual_net_usd'],'balanced=',v['ledger_balanced'])
    print('CQWE_V28_LATER_DATA_EXPERIMENT_PASS | NO AUTO PROMOTION | NO ORDERS | NO REAL PROFIT CLAIM')
if __name__=='__main__':main()
