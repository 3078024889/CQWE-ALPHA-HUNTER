"""V24 unified $10 historical cash account for V20 frozen dendritic rule.
Read-only historical next-open assumptions. No orders, no wallet, no guaranteed liquidity.
Exploratory shadow is NOT an independent holdout when rule comes from V21/V23 research.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
from .self_evolution_v20 import offline_evolution,RULES,HORIZON
from .dendritic_v19 import features,trigger,EXPERTS,validate_inputs

def _num(x,label):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x):raise ValueError(label)
    return float(x)

def paper(datasets,mode='gate',rule=(0.12,0.0),cash0=10.0,allocation=.6,
          min_notional=5.0,fee_bps=5.0,slip_bps=2.0,extra_cost_bps=0.0):
    for n,v in [('cash0',cash0),('allocation',allocation),('min_notional',min_notional),('fee_bps',fee_bps),('slip_bps',slip_bps),('extra_cost_bps',extra_cost_bps)]:_num(v,n)
    if mode not in ('gate','shadow') or tuple(rule) not in RULES or cash0<=0 or not 0<allocation<=1 or min_notional<=0 or min_notional>cash0 or not 0<=fee_bps<1000 or not 0<=slip_bps<1000 or not 0<=extra_cost_bps<1000:raise ValueError('invalid configuration')
    clock,data=validate_inputs(datasets)
    research,checkpoint=offline_evolution(datasets,initial_cash=cash0)
    start=int(len(clock)*.8)
    selected=checkpoint.get('selected')
    if mode=='gate':
        if selected is None:
            chosen=None
        else:
            chosen=(selected['learning_rate'],selected['decay'])
    else:chosen=tuple(rule)
    state=next((v for v in checkpoint['candidate_states'] if chosen is not None and (v['learning_rate'],v['decay'])==chosen),None)
    weights=state['weights'] if state is not None else {}
    capital=float(cash0);pos=None;ledger=[];curve=[];rejections={'no_signal':0,'below_min_notional':0,'occupied':0}
    for i in range(start,len(clock)-1):
        # Decisions use only bar i close, fill at i+1 open. No future close in signal.
        if pos is not None and i+1>=pos['due_i']:
            sym=pos['symbol'];price=float(data[sym][i+1][1])*(1-slip_bps/10000)
            proceeds=pos['qty']*price;cost=proceeds*(fee_bps+extra_cost_bps/2)/10000
            capital+=proceeds-cost
            ledger.append({'side':'SELL','symbol':sym,'time_ms':clock[i+1],'price':price,'qty':pos['qty'],'fee_and_extra_usd':cost,'cash_after_usd':capital})
            pos=None
        # Only one position at once. Never reuse a fill from nonexistent future bar.
        if pos is None and weights:
            options=[]
            for sym,bars in data.items():
                f=features(bars,i)
                for expert in EXPERTS:
                    key=f'{sym}|{f["regime"]}|{expert}'
                    if weights.get(key,0)>.10 and trigger(f,expert):
                        options.append((-weights[key],sym,expert,key))
            if options:
                _,sym,expert,key=sorted(options)[0]
                budget=capital*allocation
                if budget < min_notional:rejections['below_min_notional']+=1
                else:
                    price=float(data[sym][i+1][1])*(1+slip_bps/10000)
                    # Fee deducted inside cash budget, no negative cash.
                    fee_rate=(fee_bps+extra_cost_bps/2)/10000
                    gross=budget/(1+fee_rate); fee=gross*fee_rate; qty=gross/price
                    capital-=gross+fee
                    pos={'symbol':sym,'qty':qty,'due_i':i+1+HORIZON,'expert':expert,'key':key}
                    ledger.append({'side':'BUY','symbol':sym,'time_ms':clock[i+1],'price':price,'qty':qty,'fee_and_extra_usd':fee,'cash_after_usd':capital,'expert':expert})
            else:rejections['no_signal']+=1
        elif pos is not None:rejections['occupied']+=1
        # Mark-to-market, final exposure stays open, no fictional end liquidation.
        equity=capital + (pos['qty']*float(data[pos['symbol']][i+1][4]) if pos else 0)
        curve.append({'time_ms':clock[i+1],'equity_usd':equity})
        if capital < -1e-8:raise ArithmeticError('NEGATIVE_CASH')
    replay=float(cash0);inventory={}
    for t in ledger:
        notional=t['qty']*t['price'];sym=t['symbol']
        if t['side']=='BUY':replay-=notional+t['fee_and_extra_usd'];inventory[sym]=inventory.get(sym,0)+t['qty']
        else:replay+=notional-t['fee_and_extra_usd'];inventory[sym]=inventory.get(sym,0)-t['qty']
    desired={pos['symbol']:pos['qty']} if pos else {}
    balanced=abs(replay-capital)<1e-8 and all(abs(inventory.get(sym,0)-desired.get(sym,0))<1e-8 for sym in set(inventory)|set(desired))
    if not balanced:raise ArithmeticError('LEDGER_MISMATCH')
    end_equity=curve[-1]['equity_usd'];peak=cash0;dd=0
    for e in curve:
        peak=max(peak,e['equity_usd']);dd=min(dd,e['equity_usd']/peak-1)
    return {'mode':'V24_FROZEN_RESEARCH_PORTFOLIO','research_only':True,'simulation_only':True,
      'policy':mode,'selected_rule':list(chosen) if chosen else None,'evidence_gate_pass':bool(research['promoted']),
      'independent_holdout_claim':False,'within_run_sealed_holdout':True,
      'warning':'Historical fills hypothetical. Gate has within-run time isolation, but these 30-day candles were reviewed in prior CQWE experiments: NOT a new independent evaluation. Shadow is exploratory and retrospective.',
      'initial_virtual_usd':cash0,'final_virtual_equity_usd':round(end_equity,8),'virtual_net_usd':round(end_equity-cash0,8),
      'cash_usd':round(capital,8),'entries':sum(t['side']=='BUY' for t in ledger),'exits':sum(t['side']=='SELL' for t in ledger),
      'open_position':pos,'max_drawdown_pct':round(dd*100,8),'rejections':rejections,'ledger_balanced':balanced,
      'cost_assumptions':{'fee_bps_per_side':fee_bps,'slippage_bps_per_side':slip_bps,'extra_roundtrip_bps':extra_cost_bps},
      'research_selection':{'promoted':research['promoted'],'selected_rule':research['selected_rule'],'validation_only':True},
      'holdout_start_ms':clock[start],'holdout_bars':len(clock)-start,'trades':ledger,'curve':curve,
      'verified_executable_trades':0,'realized_profit_usd':None}

def run(paths,output,**params):
    d={};fingerprints={}
    for p in paths:
        f=Path(p);sym=f.stem.split('_')[0].upper();raw=f.read_bytes()
        if sym in d:raise ValueError('DUPLICATE_SYMBOL')
        d[sym]=json.loads(raw.decode('utf-8-sig'));fingerprints[sym]=hashlib.sha256(raw).hexdigest()
    payload={'sources_sha256':fingerprints,'portfolio':paper(d,**params)}
    dest=Path(output);dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_name(dest.name+'.tmp');tmp.write_text(json.dumps(payload,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(dest)
    return payload

def main():
    a=argparse.ArgumentParser(description='V24 frozen $10 cash-only holdout research; no orders')
    a.add_argument('--inputs',nargs='+',required=True);a.add_argument('--output',default='reports/v24_gate.json')
    a.add_argument('--mode',choices=['gate','shadow'],default='gate')
    a.add_argument('--allocation',type=float,default=.6);a.add_argument('--min-notional-usd',type=float,default=5)
    a.add_argument('--extra-cost-bps',type=float,default=0)
    args=a.parse_args();result=run(args.inputs,args.output,mode=args.mode,allocation=args.allocation,
           min_notional=args.min_notional_usd,extra_cost_bps=args.extra_cost_bps)
    q=result['portfolio'];print('V24',args.mode,'gate=',q['evidence_gate_pass'],'entries=',q['entries'],
         'virtual_equity=',q['final_virtual_equity_usd'],'net=',q['virtual_net_usd'],'balanced=',q['ledger_balanced'])
    print('CQWE_V24_RESEARCH_ONLY | HISTORICAL ASSUMPTIONS | NO ORDERS')
if __name__=='__main__':main()
