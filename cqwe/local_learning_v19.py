"""CQWE V19 persistent local-learning experiment. Offline historical research, NO orders.
Causal online update: event outcome at i+h known only after bar i+h has closed.
All mutations are bounded and deterministic. Every update is journaled and hashed.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
from .core import valid_candles
from .dendritic_v19 import features, trigger, EXPERTS, REGIMES, validate_inputs

VERSION=1

def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def new_state():
    return {'version':VERSION,'last_matured_ms':-1,'generation':0,'weights':{},'evidence':{},'mutation_round':0,
            'journal':[],'history_fingerprint':None}

def check_state(state):
    if not isinstance(state,dict) or state.get('version')!=VERSION:raise ValueError('invalid checkpoint')
    if not isinstance(state.get('weights'),dict) or not isinstance(state.get('journal'),list):raise ValueError('invalid checkpoint')
    for v in state['weights'].values():
        if not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>4.0000001:raise ValueError('bad weight')
    if state.get('last_matured_ms',-1)<-1:raise ValueError('bad watermark')
    return state

def _update(state,key,net,bar_ms,rate=0.08):
    if not math.isfinite(net):raise ValueError('nonfinite outcome')
    old=state['weights'].get(key,0.0)
    # sign-conditioned, bounded local residual learning; rate is fixed a priori
    direction=1 if net>0 else -1
    new=max(-4.,min(4.,round((1-rate)*old+rate*direction,12)))
    e=state['evidence'].setdefault(key,{'n':0,'sum_net':0.,'negative':0})
    e['n']+=1;e['sum_net']=round(e['sum_net']+net,12);e['negative']+=int(net<=0)
    state['weights'][key]=new;state['generation']+=1
    # mutation is a bounded adjustment to adaptation cadence, not executable code alteration.
    mutated=False
    if state['generation']%64==0:
        state['mutation_round']+=1;mutated=True
    entry={'generation':state['generation'],'bar_ms':bar_ms,'key':key,'net_fraction':round(net,12),
           'old_weight':old,'new_weight':new,'mutation_checkpoint':mutated}
    entry['record_sha256']=digest(entry)
    state['journal'].append(entry)

def learn(datasets,state=None,hold=12,lookback=24,fee_bps=5,slip_bps=2,threshold=.15,
          min_events=25,split_fraction=.7):
    """One-pass ONLINE observations in initial train then frozen holdout.
    Output includes a fresh state for continuation from a later snapshot, no backwards rewrite.
    This is NOT independent holdout after seeing/reusing data to tune it.
    """
    if not isinstance(hold,int) or not 1<=hold<=100 or not isinstance(lookback,int) or not 12<=lookback<=100:
        raise ValueError('window')
    if not 0<=fee_bps<=1000 or not 0<=slip_bps<=1000 or not -.99<=threshold<=.99 or min_events<2 or not .5<=split_fraction<=.85:
        raise ValueError('configuration')
    clock,data=validate_inputs(datasets);split=int(len(clock)*split_fraction)
    state=check_state(json.loads(json.dumps(state))) if state is not None else new_state()
    # avoid replaying already learned observations on the same or overlapping dataset.
    if state['last_matured_ms']>=0 and clock[lookback]<=state['last_matured_ms']:
        raise ValueError('OVERLAPPING_REPLAY_REJECTED; use new sequential data')
    scores=[]; train_n=0;holdout_n=0
    # By indexing decision i, maturity at i+1+hold open; training stops before holdout.
    for i in range(lookback,split-hold-1):
        maturity=i+1+hold
        if maturity>=split:break
        for sym,bars in data.items():
            f=features(bars,i,lookback)
            for expert in EXPERTS:
                if not trigger(f,expert):continue
                key=f'{sym}|{f["regime"]}|{expert}'
                entry=float(bars[i+1][1])*(1+slip_bps/10000)
                exit_=float(bars[maturity][1])*(1-slip_bps/10000)
                net=(exit_/entry)*(1-fee_bps/10000)**2-1
                scores.append((maturity,key,net,clock[maturity]))
    # Sort by outcome maturity so information updates NEVER arrive before being known.
    scores.sort(key=lambda r:(r[0],r[1]))
    for maturity,key,net,t in scores:
        _update(state,key,net,t)
        train_n+=1
    if scores:state['last_matured_ms']=scores[-1][3]
    # freeze policy before holdout: score only, no updates from holdout labels
    policy={k for k,e in state['evidence'].items() if e['n']>=min_events and
            state['weights'].get(k,0)>threshold and e['sum_net']>0}
    frozen_hash=digest({'policy':sorted(policy),'weights':state['weights'],'last_matured_ms':state['last_matured_ms']})
    holdout=[];last_end={}
    for i in range(split,len(clock)-hold-1):
        for sym,bars in data.items():
            f=features(bars,i,lookback)
            for expert in EXPERTS:
                key=f'{sym}|{f["regime"]}|{expert}'
                if key not in policy or not trigger(f,expert) or i<last_end.get(sym,-1):continue
                entry=float(bars[i+1][1])*(1+slip_bps/10000)
                exit_=float(bars[i+1+hold][1])*(1-slip_bps/10000)
                net=(exit_/entry)*(1-fee_bps/10000)**2-1
                holdout.append({'symbol':sym,'expert':expert,'decision_ms':clock[i],'maturity_ms':clock[i+1+hold],'net_fraction':round(net,10)})
                last_end[sym]=i+1+hold;holdout_n+=1
                break
    mean=sum(x['net_fraction'] for x in holdout)/holdout_n if holdout_n else None
    return {'mode':'CAUSAL_DENDRITIC_RESEARCH','research_only':True,'starting_state_generation':state['generation']-train_n,
            'trained_events':train_n,'policy_keys':sorted(policy),'frozen_policy_sha256':frozen_hash,
            'holdout_events':holdout_n,'holdout_mean_event_net_pct':round(mean*100,8) if mean is not None else None,
            'holdout_gross_compounded_not_computed':True,'holdout_events_detail':holdout,
            'state':state,'warning':'Holdout strategy events are not one cash portfolio. No live trades. Frozen policy, no holdout updates; sequential validation required.'}

def run(inputs,output,checkpoint=None,**kw):
    datasets={};hashes={}
    for file in inputs:
        p=Path(file);sym=p.stem.split('_')[0].upper();raw=p.read_bytes()
        if sym in datasets:raise ValueError('duplicate market')
        hashes[sym]=hashlib.sha256(raw).hexdigest();datasets[sym]=json.loads(raw.decode('utf-8-sig'))
    state=None
    if checkpoint:
        cp=Path(checkpoint)
        if cp.exists():state=json.loads(cp.read_text(encoding='utf-8'))
    result=learn(datasets,state,**kw)
    payload={'datasets_sha256':hashes,'report':{k:v for k,v in result.items() if k!='state'},
             'checkpoint_sha256':digest(result['state'])}
    destination=Path(output);destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.json.tmp');temporary.write_text(json.dumps(payload,indent=2),encoding='utf-8');temporary.replace(destination)
    if checkpoint:
        cp=Path(checkpoint);cp.parent.mkdir(parents=True,exist_ok=True)
        tmp=cp.with_suffix('.tmp');tmp.write_text(json.dumps(result['state'],indent=2),encoding='utf-8');tmp.replace(cp)
    return payload

def main():
    p=argparse.ArgumentParser(description='CQWE V19 bounded local learning; historical offline only')
    p.add_argument('--inputs',nargs='+',required=True);p.add_argument('--output',default='reports/v19_local_learning.json')
    p.add_argument('--checkpoint',default=None);p.add_argument('--min-events',type=int,default=25)
    a=p.parse_args();r=run(a.inputs,a.output,a.checkpoint,min_events=a.min_events)
    q=r['report'];print('CQWE_V19_LOCAL_LEARNING_PASS', 'trained=',q['trained_events'],'holdout_events=',q['holdout_events'],
                       'mean_pct=',q['holdout_mean_event_net_pct'],'policy_nodes=',len(q['policy_keys']),'NO ORDERS')
if __name__=='__main__':main()
