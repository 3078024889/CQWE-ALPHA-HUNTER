"""CQWE V20: finite deterministic tree-node local-learning mutations with sealed chronological holdout.
No networking, broker, credentials, self-written executable code, live orders, or claims of independent profits.
This is a *controlled algorithm mutation study*, not automated discovery of reliable alpha.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
from .dendritic_v19 import EXPERTS, REGIMES, features, trigger, validate_inputs

RULES = ((0.02,0.00),(0.06,0.00),(0.12,0.00),(0.06,0.02)) # learning rate and decay
HORIZON = 12
WARMUP = 24
FEE_BPS = 5.0
SLIP_BPS = 2.0
SCHEMA = 20

def sha(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def valid_float(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)

def event_return(bars,i,horizon=HORIZON,fee_bps=FEE_BPS,slip_bps=SLIP_BPS):
    # Signal observes the *closed* bar at i; entry and exit at future opens.
    entry=float(bars[i+1][1])*(1+slip_bps/10000)
    exit_=float(bars[i+1+horizon][1])*(1-slip_bps/10000)
    return (exit_/entry)*(1-fee_bps/10000)**2-1

def build_events(datasets):
    clock,data=validate_inputs(datasets)
    events=[]
    for symbol,bars in data.items():
        for i in range(WARMUP,len(clock)-1-HORIZON):
            f=features(bars,i)
            for expert in EXPERTS:
                if trigger(f,expert):
                    events.append({'symbol':symbol,'key':f'{symbol}|{f["regime"]}|{expert}',
                                   'decision_i':i,'maturity_i':i+1+HORIZON,'decision_ms':clock[i],
                                   'maturity_ms':clock[i+1+HORIZON],
                                   'net':event_return(bars,i)})
    # Sort by maturity: learning is not allowed to see outcomes ahead of their appearance.
    events.sort(key=lambda e:(e['maturity_i'],e['symbol'],e['key'],e['decision_i']))
    return clock, data, events

def step(weight,net,rate,decay):
    # Local weight reacts to signed *matured* return only; confidence bounded.
    direction = 1 if net>0 else -1
    return round(max(-2.,min(2.,(1-decay-rate)*weight+rate*direction)),12)

def score_events(events,rate,decay,threshold=.10):
    """Purely sequential online evaluation: at each maturity, evaluate prior weight BEFORE update.
    Returns an event score (not account PnL), and updated weights for next episode.
    """
    weights={}; out=[]
    for e in events:
        key=e['key'];w=weights.get(key,0.)
        if w>threshold:
            out.append(e['net'])
        weights[key]=step(w,e['net'],rate,decay)
    return weights,out

def stable_improvement(xs, min_events=20, z=2.0):
    if len(xs)<min_events:return {'eligible':False,'reason':'INSUFFICIENT_EVENTS','n':len(xs),'lcb':None,'mean':statistics.mean(xs) if xs else None}
    mu=statistics.mean(xs);sd=statistics.stdev(xs)
    lcb=mu-z*sd/math.sqrt(len(xs))
    return {'eligible':lcb>0,'reason':'POSITIVE_LOWER_BOUND' if lcb>0 else 'NO_POSITIVE_LOWER_BOUND',
            'n':len(xs),'mean':mu,'lcb':lcb}

def segment(events,start,end):
    # Requires outcome maturity INSIDE the segment; decision inside too => purge across boundaries.
    return [e for e in events if start<=e['decision_i'] and e['maturity_i']<end]

def offline_evolution(datasets,min_events=20,initial_cash=10.0):
    if not isinstance(min_events,int) or min_events<5:raise ValueError('min_events')
    if not valid_float(initial_cash) or initial_cash<=0:raise ValueError('initial_cash')
    clock,data,events=build_events(datasets)
    n=len(clock)
    if n<500:raise ValueError('at least 500 aligned bars required')
    train_end=int(n*.60);validation_end=int(n*.80)
    train=segment(events,WARMUP,train_end)
    valid=segment(events,train_end,validation_end)
    hold=segment(events,validation_end,n)
    candidates=[]
    # Candidate learning-rule variants are predeclared; no holdout data enters mutation selection.
    for lr,decay in RULES:
        w,_=score_events(train,lr,decay)
        w_val=dict(w); vals=[]
        for e in valid:
            old=w_val.get(e['key'],0.)
            if old>.10:vals.append(e['net'])
            w_val[e['key']]=step(old,e['net'],lr,decay)
        verdict=stable_improvement(vals,min_events)
        candidates.append({'learning_rate':lr,'decay':decay,'validation':verdict,
                           'trained_node_count':len(w),'weight_sha256':sha(w),
                           'next_weights':w_val})
    # Promote only with demonstrable positive validation bound; otherwise safe abstain.
    admissible=[(i,c) for i,c in enumerate(candidates) if c['validation']['eligible']]
    chosen=max(admissible,key=lambda p:(p[1]['validation']['lcb'],-p[0])) if admissible else None
    promoted=chosen is not None
    hold_events=[];held_node_count=0
    if promoted:
        index,c=chosen; lr=c['learning_rate']; decay=c['decay'];w=dict(c['next_weights'])
        held_node_count=len(w)
        # Sealed holdout: no weight update or re-selection based on holdout outcomes.
        last_maturity={}
        for e in hold:
            if w.get(e['key'],0.)<=.10:continue
            if e['decision_i']<last_maturity.get(e['symbol'],-1):continue
            hold_events.append(e['net']);last_maturity[e['symbol']]=e['maturity_i']
    hold_mean=statistics.mean(hold_events) if hold_events else None
    hold_gate=stable_improvement(hold_events,min_events)
    # No simulated cash investment without explicit fully specified portfolio execution;
    # a zero-trade policy is represented by 10 unchanged virtual USD.
    preserved_cash=initial_cash if not promoted else None
    legacy={'model_id': 'V19','reported_holdout_events':6,'reported_holdout_mean_pct':-0.86142714,
            'source':'user-provided V19 console output','not_directly_comparable':True}
    public_candidates=[{k:v for k,v in c.items() if k!='next_weights'} for c in candidates]
    frozen_config=({'learning_rate':chosen[1]['learning_rate'],'decay':chosen[1]['decay'],
                   'node_weights':chosen[1]['next_weights']} if promoted else None)
    tails={sym:bars[-(WARMUP+HORIZON+3):] for sym,bars in data.items()}
    candidate_states=[{'learning_rate':c['learning_rate'],'decay':c['decay'],'weights':c['next_weights']} for c in candidates]
    checkpoint={'tails':tails,'candidate_states':candidate_states,'last_seen_ms':clock[-1],
                'continuations':0,'journal':[],'schema':SCHEMA,'generation':1,'status':'PROMOTED_RESEARCH_ONLY' if promoted else 'NO_PROMOTION',
                'data_last_open_ms':clock[-1],
                'training_end_ms_exclusive':clock[train_end],
                'validation_end_ms_exclusive':clock[validation_end],
                'selection_sha256':sha(public_candidates),
                'selected':frozen_config,'mutation_log':public_candidates,
                'legacy_reference':legacy}
    report={'research_only':True,'validation_protocol':'TRAIN_60_VALIDATION_20_SEALED_HOLDOUT_20',
            'aligned_bars':n,'markets':sorted(data),'events_total':len(events),
            'train_events':len(train),'validation_events':len(valid),'sealed_events_observed':len(hold),
            'mutations_tested':len(candidates),'mutations':public_candidates,
            'promoted':promoted,'selected_rule':frozen_config and {k:frozen_config[k] for k in ('learning_rate','decay')},
            'holdout_selected_events':len(hold_events),'holdout_mean_net_event_fraction':hold_mean,
            'holdout_gate':hold_gate,'initial_virtual_usd':initial_cash,
            'idle_policy_final_virtual_usd':preserved_cash,
            'virtual_portfolio_pnl_usd':None,
            'model_warning':'Event returns are not an executable multi-asset cash portfolio. Validation-selected strategies require a future independent period.','legacy_reference':legacy,
            'timestamp_boundaries':{'training_end_exclusive':clock[train_end],
                 'validation_end_exclusive':clock[validation_end],'last_bar':clock[-1]},
            'checkpoint_sha256':sha(checkpoint)}
    return report,checkpoint


def continuation_update(old,new_data):
    """Prequential adaptation to strictly unseen contiguous *new* candles.
    Event outcomes are updated only after expiry. Mutations are finite and predeclared.
    Saved evidence includes a hash-chained continuation journal; no sealed holdout retuning.
    """
    if old.get('schema')!=SCHEMA or not isinstance(old.get('tails'),dict) or not isinstance(old.get('candidate_states'),list):
        raise ValueError('INVALID_CHECKPOINT')
    prior=int(old['last_seen_ms'])
    expected_symbols=sorted(old['tails'])
    if sorted(new_data)!=expected_symbols:raise ValueError('MARKET_SET_CHANGED')
    clk, aligned=validate_inputs(new_data)
    if clk[0]<=prior:raise ValueError('OVERLAPPING_REPLAY_REJECTED')
    if clk[0]!=prior+300000:raise ValueError('NONCONTIGUOUS_FUTURE_DATA')
    if len(clk)<240:raise ValueError('NEED_AT_LEAST_240_NEW_BARS')
    merged={sym:old['tails'][sym]+aligned[sym] for sym in expected_symbols}
    times,all_bars,events=build_events(merged)
    after=[e for e in events if e['maturity_ms']>prior]
    if any(e['maturity_ms']<=prior for e in after):raise ArithmeticError('causal event watermark')
    states=[];research=[]
    for st in old['candidate_states']:
        lr=st['learning_rate'];decay=st['decay']
        if (lr,decay) not in RULES:raise ValueError('UNAUTHORIZED_MUTATION')
        w=dict(st['weights']);observed=[]
        for e in after:
            prior_weight=w.get(e['key'],0.)
            if prior_weight>.1:observed.append(e['net'])
            w[e['key']]=step(prior_weight,e['net'],lr,decay)
        summary=stable_improvement(observed)
        states.append({'learning_rate':lr,'decay':decay,'weights':w})
        research.append({'learning_rate':lr,'decay':decay,'events':len(observed),
                         'prequential':summary,'weight_sha256':sha(w)})
    # This segment is adaptive/prequential, NOT an untouched holdout. Mutation choice
    # is NOT upgraded based on newly observed returns; no silent selection.
    out=json.loads(json.dumps(old))
    out['candidate_states']=states
    out['tails']={sym:all_bars[sym][-(WARMUP+HORIZON+3):] for sym in expected_symbols}
    out['last_seen_ms']=clk[-1]
    out['data_last_open_ms']=clk[-1]
    out['continuations']=old['continuations']+1
    previous_hash=old['journal'][-1]['entry_sha256'] if old['journal'] else old['selection_sha256']
    entry={'segment_start_ms':clk[0],'segment_end_ms':clk[-1],
           'new_bars':len(clk),'matured_events':len(after), 'research':research,
           'previous_hash':previous_hash,'status':'ADAPTIVE_PREQUENTIAL_NOT_INDEPENDENT_HOLDOUT'}
    entry['entry_sha256']=sha(entry)
    out['journal'].append(entry)
    return out,entry


def resume(inputs,output,checkpoint):
    cp=Path(checkpoint)
    if not cp.is_file():raise FileNotFoundError('CHECKPOINT_REQUIRED')
    state=json.loads(cp.read_text(encoding='utf-8'))
    datasets={};digests={}
    for f in inputs:
        p=Path(f);sym=p.stem.split('_')[0].upper();raw=p.read_bytes()
        if sym in datasets:raise ValueError('DUPLICATE_MARKET')
        datasets[sym]=json.loads(raw.decode('utf-8-sig'))
        digests[sym]=hashlib.sha256(raw).hexdigest()
    new_state,entry=continuation_update(state,datasets)
    target=Path(output)
    if target.resolve()==cp.resolve():raise ValueError('OUTPUT_CHECKPOINT_COLLISION')
    target.parent.mkdir(parents=True,exist_ok=True)
    # Write report before checkpoint; checkpoint is authoritative on restart.
    payload={'mode':'V20_PREQUENTIAL_CONTINUATION','research_only':True,
             'new_data_sha256':digests,'entry':entry,'checkpoint_sha256':sha(new_state),
             'warning':'Adaptive historical continuation, not independent holdout or real profits.'}
    temp=target.with_name(target.name+'.tmp');temp.write_text(json.dumps(payload,indent=2,allow_nan=False),encoding='utf-8');temp.replace(target)
    tmp=cp.with_name(cp.name+'.tmp');tmp.write_text(json.dumps(new_state,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(cp)
    return payload

def run(inputs,output,checkpoint,min_events=20):
    data={};digests={}
    for path in inputs:
        p=Path(path)
        sym=p.stem.split('_')[0].upper()
        if not sym.isalnum() or sym in data:raise ValueError('duplicate/invalid dataset')
        raw=p.read_bytes();data[sym]=json.loads(raw.decode('utf-8-sig'));digests[sym]=hashlib.sha256(raw).hexdigest()
    report,state=offline_evolution(data,min_events=min_events)
    report['dataset_sha256']=digests
    cp=Path(checkpoint)
    if cp.exists():
        previous=json.loads(cp.read_text(encoding='utf-8'))
        if previous.get('schema')!=SCHEMA:raise ValueError('CHECKPOINT_VERSION_MISMATCH')
        if previous['data_last_open_ms']>=state['data_last_open_ms']:
            raise ValueError('OVERLAPPING_REPLAY_REJECTED')
        # Do not overwrite a checkpoint with a new selected model unless clean new data regime
        # and validation protocol can be independently repeated.
        raise ValueError('CHECKPOINT_CONTINUATION_NOT_IMPLEMENTED_USE_NEW_EXPERIMENT_ID')
    op=Path(output)
    if op.resolve()==cp.resolve():raise ValueError('checkpoint and report paths collide')
    op.parent.mkdir(parents=True,exist_ok=True);cp.parent.mkdir(parents=True,exist_ok=True)
    op_tmp=op.with_name(op.name+'.tmp');cp_tmp=cp.with_name(cp.name+'.tmp')
    op_tmp.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    cp_tmp.write_text(json.dumps(state,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    op_tmp.replace(op);cp_tmp.replace(cp)
    return report

def main():
    parser=argparse.ArgumentParser(description='CQWE V20 finite mutation validation; no real orders')
    parser.add_argument('--mode',choices=('initial','continue'),default='initial')
    parser.add_argument('--inputs',nargs='+',required=True)
    parser.add_argument('--output',default='reports/v20_evolution.json')
    parser.add_argument('--checkpoint',default='reports/v20_evolution_state.json')
    parser.add_argument('--min-events',type=int,default=20)
    args=parser.parse_args()
    if args.mode=='continue':
        r=resume(args.inputs,args.output,args.checkpoint)
        print('CQWE_V20_CONTINUATION_PASS',r['entry']['matured_events'],'MATURED EVENTS, NO ORDERS');return
    r=run(args.inputs,args.output,args.checkpoint,args.min_events)
    print('CQWE_V20_RESEARCH_PASS | TRAIN=',r['train_events'],'VALID=',r['validation_events'],
          'PROMOTED=',r['promoted'],'SEALED_EVENTS=',r['holdout_selected_events'],
          'SEALED_MEAN=',r['holdout_mean_net_event_fraction'],'NO ORDERS')
if __name__=='__main__':main()
