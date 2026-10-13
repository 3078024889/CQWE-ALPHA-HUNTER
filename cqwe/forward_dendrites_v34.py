"""Pre-registered, read-only, continually evaluated dendritic candidates.

No live orders, no synthetic trade fills, no account PnL. Each observed bar is
recorded before its next target CLOSE; learning occurs ONLY after maturation.
The six candidates have separate, bounded states and immutable SHA-chained
records. Skipped 5m bars fail closed (no hindsight reconstruction).
"""
from __future__ import annotations
import argparse
import json
import math
import time
from pathlib import Path
from .copernican_lab_v33 import Dendrite, specs, features, digest
from .public_data_v29 import PERIOD, SYMBOLS
from .rolling_signal_v31 import market_snapshot, _load_checked, _write_new

VERSION='CQWE_V34_FORWARD_DENDRITES'
SYMBOL='BNBUSDT'  # prespecified for the first continuous controlled experiment
GENOTYPES=specs()
MAX_WEIGHT=1.0


def hash_record(record):
    return digest({k:v for k,v in record.items() if k!='sha256'})


def clean_float(v):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
        raise ValueError('NONFINITE_MODEL_VALUE')
    return float(v)


def state_of(model):
    return {'weights':[clean_float(x) for x in model.w],
            'trace':[clean_float(x) for x in model.trace],
            'memory':[clean_float(x) for x in model.memory],
            'prev_error':clean_float(model.prev_error),
            'updates':model.updates}


def restore(spec,state):
    obj=Dendrite(spec)
    for field,attribute in [('weights','w'),('trace','trace'),('memory','memory')]:
        seq=state[field]
        if len(seq)!=4:raise ValueError('BAD_MODEL_DIMENSIONS')
        values=[clean_float(x) for x in seq]
        if attribute=='w' and any(abs(x)>MAX_WEIGHT+1e-9 for x in values):raise ValueError('UNBOUNDED_WEIGHTS')
        setattr(obj,attribute,values)
    obj.prev_error=clean_float(state['prev_error'])
    if not isinstance(state['updates'],int) or state['updates']<0:raise ValueError('BAD_UPDATES')
    obj.updates=state['updates']
    return obj


def validate(rec,previous=None,expected_context=None):
    if rec.get('sha256')!=hash_record(rec):raise ValueError('DENDRITE_EVIDENCE_HASH_MISMATCH')
    if rec.get('version')!=VERSION or not rec.get('research_only') or not rec.get('no_orders') or not rec.get('no_autopromotion'):
        raise ValueError('DENDRITE_EVIDENCE_VERSION')
    if rec.get('symbol')!=SYMBOL or len(rec.get('candidates',[]))!=len(GENOTYPES):raise ValueError('DENDRITE_CANDIDATES_CHANGED')
    if expected_context is not None and rec['context_sha256']!=expected_context:raise ValueError('DENDRITE_CONTEXT_CHANGED')
    if previous is not None:
        if rec['last_open_ms']!=previous['last_open_ms']+PERIOD:raise ValueError('DENDRITE_GAP_IN_JOURNAL')
        if rec.get('previous_sha256')!=previous['sha256']:raise ValueError('DENDRITE_CHAIN_BROKEN')
    elif rec.get('previous_sha256') is not None:raise ValueError('DENDRITE_GENESIS_BROKEN')
    for index,candidate in enumerate(rec['candidates']):
        if candidate['genotype']!=GENOTYPES[index]:raise ValueError('DENDRITE_GENOTYPE_CHANGED')
        restore(GENOTYPES[index],candidate['model'])
        if candidate['observations']<30 and candidate['diagnosis']!='INSUFFICIENT_FORWARD_EVIDENCE':
            raise ValueError('INVALID_DIAGNOSIS')
        clean_float(candidate['prediction'])
        if not -1<=candidate['prediction']<=1:raise ValueError('BAD_PREDICTION')
    return True


def replay_journal(root,context):
    previous=None
    for path in sorted(root.glob('frame_*.json'),key=lambda p:int(p.stem.removeprefix('frame_'))):
        rec=json.loads(path.read_text(encoding='utf-8'))
        validate(rec,previous,context)
        if path.name!=f"frame_{rec['last_open_ms']}.json":raise ValueError('DENDRITE_FILENAME_CHANGED')
        previous=rec
    return previous


def cycle(store,registry,output_dir,*,fetch=None,now_ms=None):
    # _load_checked performs immutable V21 history and registry verification.
    _,registry_hash,checkpoint,_,_=_load_checked(registry,store)
    context=digest({'checkpoint_tip':checkpoint['tip_sha256'],'registry_sha256':registry_hash,
                    'genotypes':GENOTYPES,'symbol':SYMBOL,'version':VERSION})
    if now_ms is None:now_ms=time.time_ns()//1_000_000
    # No historical data downloads masquerading as new, precommitted predictions.
    if fetch is None:
        last_open,markets=market_snapshot(now_ms=now_ms)
    else:
        last_open,markets=market_snapshot(fetch=fetch,now_ms=now_ms)
    if last_open<=checkpoint['last_seen_ms']:raise ValueError('NOT_NEW_MARKET_DATA')
    if now_ms>=last_open+2*PERIOD:raise ValueError('PREDICTION_TARGET_ALREADY_CLOSED')
    root=Path(output_dir)
    previous=replay_journal(root,context)
    if previous and last_open==previous['last_open_ms']:
        return {'status':'ALREADY_RECORDED','last_open_ms':last_open,'settled_events':0,
                'no_orders':True,'sha256':previous['sha256']}
    if previous and last_open!=previous['last_open_ms']+PERIOD:
        raise ValueError('MISSED_BARS_REFUSE_HINDSIGHT_REPLAY')
    bars=markets[SYMBOL]
    current_close=clean_float(float(bars[-1][4]))
    if current_close<=0:raise ValueError('BAD_PRICE')
    x=features(bars,len(bars)-1)
    if len(x)!=4:raise ValueError('BAD_FEATURE_DIMENSIONS')
    out=[];settled=0
    for i,spec in enumerate(GENOTYPES):
        if previous:
            last=previous['candidates'][i]
            model=restore(spec,last['model'])
            prev_close=clean_float(previous['observed_close'])
            observed_return=current_close/prev_close-1
            label=1. if observed_return>0 else -1. if observed_return<0 else 0.
            # Previous response was frozen at the time of previous prediction.
            model.update(last['response'],label,last['prediction'],last['features'])
            settled+=1
            # Causal next-close directional accuracy proxy, not executable trading PnL.
            correct=int((last['prediction']>0)==(observed_return>0))
            cumulative=last['cumulative_correct']+correct
            observations=last['observations']+1
            squared_error_sum=last['squared_error_sum']+(label-last['prediction'])**2
        else:
            cumulative=observations=0;squared_error_sum=0.
            model=Dendrite(spec)
        prediction,response=model.forward(x)
        comparison=('INSUFFICIENT_FORWARD_EVIDENCE' if observations<30 else
                    'UNDERPERFORMS_ZERO_BASELINE' if squared_error_sum/observations>=1.0 else
                    'LOWER_SQUARED_ERROR_UNVERIFIED')
        out.append({'genotype':spec,'model':state_of(model),'prediction':clean_float(prediction),
                    'response':[clean_float(v) for v in response],
                    'features':[clean_float(v) for v in x],
                    'observations':observations,'cumulative_correct':cumulative,
                    'squared_error_sum':clean_float(squared_error_sum),
                    'zero_baseline_squared_error_sum':float(observations),
                    'diagnosis':comparison})
    rec={'version':VERSION,'research_only':True,'no_orders':True,'no_autopromotion':True,
         'symbol':SYMBOL,'last_open_ms':last_open,'recorded_at_ms':now_ms,
         'target_open_ms':last_open+PERIOD,'target_already_opened':now_ms>=last_open+PERIOD,
         'target_not_yet_closed':now_ms<last_open+2*PERIOD,
         'observed_close':current_close,'market_sha256':digest(bars),
         'context_sha256':context,'previous_sha256':previous['sha256'] if previous else None,
         'candidates':out,
         'caution':'Event direction scores are not independent fills, cash PnL or trading returns. No promotion.'}
    rec['sha256']=hash_record(rec)
    validate(rec,previous,context)
    _write_new(root/f'frame_{last_open}.json',rec)
    return {'status':'FRAME_RECORDED','last_open_ms':last_open,'settled_events':settled,
            'observations_per_candidate':out[0]['observations'],'no_orders':True,'sha256':rec['sha256']}


def main():
    p=argparse.ArgumentParser(description='V34 frozen six-candidate 5m continuous forward dendrites; NO ORDERS')
    p.add_argument('--store',default='reports/v21_evidence')
    p.add_argument('--registry',default='reports/v27_mutation_registry.json')
    p.add_argument('--output-dir',default='reports/v34_dendrite_forward')
    a=p.parse_args();r=cycle(a.store,a.registry,a.output_dir)
    print('CQWE_V34_FORWARD_DENDRITES_PASS '+json.dumps(r,sort_keys=True))
    print('PRECOMMITTED OBSERVATIONS | READ ONLY | NO ORDERS | NO PROMOTION | NO PROFIT CLAIM')
if __name__=='__main__':main()
