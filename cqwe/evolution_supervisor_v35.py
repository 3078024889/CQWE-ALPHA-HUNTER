"""V35 evidence-preserving lineage recovery and non-promoting candidate audit.

Research only. Old V34 journals stay immutable. Missing time is NEVER backfilled
with predictions, and observed candidate metrics are not executable PnL.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import time
from pathlib import Path
from .forward_dendrites_v34 import (cycle as v34_cycle, replay_journal,
                                     GENOTYPES, SYMBOL, validate, hash_record)
from .forward_experiment_v28 import _load_checked
from .copernican_lab_v33 import digest
from .public_data_v29 import PERIOD
from .rolling_signal_v31 import market_snapshot, _write_new

ROOT_DEFAULT='reports/v35_lineages'
MIN_OBSERVATIONS=120   # an audit floor, not sufficient evidence for promotion


def context_hash(store,registry):
    _, registry_hash, checkpoint, _, _ = _load_checked(registry,store)
    ctx=digest({'checkpoint_tip':checkpoint['tip_sha256'], 'registry_sha256':registry_hash,
                'genotypes':GENOTYPES, 'symbol':SYMBOL,
                'version':'CQWE_V34_FORWARD_DENDRITES'})
    return ctx


def lineage_names(root):
    result=[]
    for p in Path(root).iterdir() if Path(root).exists() else []:
        if p.is_dir() and p.name.startswith('epoch_') and len(p.name)==18 and p.name[6:].isdigit():
            result.append(p)
    return sorted(result)


def audit(root,context):
    """Validate every frame and every boundary before reading scientific scores."""
    root=Path(root)
    epochs=lineage_names(root)
    summaries=[]
    prior=None
    for i,path in enumerate(epochs):
        ident=int(path.name[6:]); expected=0 if i==0 else int(epochs[i-1].name[6:])+1
        if ident!=expected:raise ValueError('EPOCH_SEQUENCE_BROKEN')
        rec=replay_journal(path,context)
        if rec is None:raise ValueError('EMPTY_EPOCH')
        head=json.loads((path/'lineage.json').read_text(encoding='utf-8'))
        if head.get('sha256')!=digest({k:v for k,v in head.items() if k!='sha256'}):
            raise ValueError('LINEAGE_MANIFEST_TAMPERED')
        if head.get('epoch')!=ident or head.get('context_sha256')!=context:
            raise ValueError('LINEAGE_CONTEXT_MISMATCH')
        if head.get('previous_epoch_tip')!=(prior['tip_sha256'] if prior else None):
            raise ValueError('LINEAGE_TIP_LINK_BROKEN')
        if head.get('initial_last_open_ms')!=int(min(p.stem[6:] for p in path.glob('frame_*.json'))):
            raise ValueError('LINEAGE_GENESIS_MISMATCH')
        if prior and head['initial_last_open_ms']<=prior['last_open_ms']:
            raise ValueError('LINEAGE_OVERLAP')
        first=json.loads((path/f"frame_{head['initial_last_open_ms']}.json").read_text(encoding='utf-8'))
        if first['previous_sha256'] is not None:raise ValueError('LINEAGE_BAD_GENESIS')
        if first['candidates'][0]['observations']!=0:raise ValueError('LINEAGE_NOT_RESET')
        summaries.append({'epoch':ident,'frames':len(list(path.glob('frame_*.json'))),
                          'last_open_ms':rec['last_open_ms'],'tip_sha256':rec['sha256'],
                          'initial_last_open_ms':head['initial_last_open_ms'],
                          'gap_bars_from_prior':head['gap_bars_from_prior']})
        prior=summaries[-1]
    return summaries


def review_candidate(candidate):
    n=candidate['observations']
    mse=candidate['squared_error_sum']/n if n else None
    baseline=candidate['zero_baseline_squared_error_sum']/n if n else None
    # Even a seemingly positive difference is not tradability or independent proof.
    if n<MIN_OBSERVATIONS:status='INSUFFICIENT_SEQUENTIAL_OBSERVATIONS'
    elif mse is None or not math.isfinite(mse):status='INVALID_SCORE'
    elif mse>=baseline:status='NOT_BETTER_THAN_ZERO_FORECAST'
    else:status='RESEARCH_ADVANTAGE_NEEDS_HOLDOUT_AND_ACCOUNT_PNL'
    return {'observations':n,'mean_squared_error':mse,'baseline_mean_squared_error':baseline,
            'status':status, 'eligible_for_auto_promotion':False}


def report(root,context):
    summaries=audit(root,context)
    if not summaries:return {'status':'NO_EXPERIMENTS','epochs':[],'no_promotion':True}
    last=Path(root)/f"epoch_{summaries[-1]['epoch']:012d}"/f"frame_{summaries[-1]['last_open_ms']}.json"
    record=json.loads(last.read_text(encoding='utf-8'))
    data={'status':'AUDITED_NOT_PROMOTED','epochs':summaries,
          'candidates':[{'genotype':c['genotype'],**review_candidate(c)} for c in record['candidates']],
          'no_orders':True,'no_promotion':True,
          'limitations':'Sequentially adapted one-bar directional proxies; no independent holdout, no multiple-testing correction, no executable PnL.'}
    data['sha256']=digest(data)
    return data


def run(store,registry,root,*,fetch=None,now_ms=None,report_path=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    # Exclusive-create lock: fail closed on stale/interrupted lock. Never remove another process lock.
    lock=root/'.run.lock'
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:
        raise RuntimeError('RESEARCH_LOCK_EXISTS_INSPECT_BEFORE_RETRY')
    try:
        with os.fdopen(fd,'w') as fp:fp.write(str(os.getpid()))
        context=context_hash(store,registry)
        summaries=audit(root,context)
        if now_ms is None:now_ms=time.time_ns()//1_000_000
        # Reuse V34 canonical market validation. No historical resimulation.
        if fetch is None:
            last_open,_=market_snapshot(now_ms=now_ms)
        else:
            last_open,_=market_snapshot(fetch=fetch,now_ms=now_ms)
        # Refuse to open a new epoch after its prediction target has already closed.
        if now_ms >= last_open + 2*PERIOD:
            raise ValueError('PREDICTION_TARGET_ALREADY_CLOSED')
        if summaries and last_open<summaries[-1]['last_open_ms']:
            raise ValueError('CLOCK_OR_MARKET_REGRESSION')
        if summaries and last_open==summaries[-1]['last_open_ms']:
            result={'status':'ALREADY_RECORDED','last_open_ms':last_open,'epoch':summaries[-1]['epoch']}
        else:
            if summaries and (last_open-summaries[-1]['last_open_ms'])%PERIOD:
                raise ValueError('UNALIGNED_GAP')
            fresh=not summaries or last_open>summaries[-1]['last_open_ms']+PERIOD
            epoch=(summaries[-1]['epoch']+1 if summaries else 0) if fresh else summaries[-1]['epoch']
            folder=root/f'epoch_{epoch:012d}'
            if fresh:
                gap=(int((last_open-summaries[-1]['last_open_ms'])//PERIOD)-1) if summaries else 0
                manifest={'version':'CQWE_V35_LINEAGE','epoch':epoch,
                          'context_sha256':context,'initial_last_open_ms':last_open,
                          'previous_epoch_tip':summaries[-1]['tip_sha256'] if summaries else None,
                          'gap_bars_from_prior':gap,'research_only':True,'no_orders':True,
                          'reset_on_gap':True}
                manifest['sha256']=digest(manifest)
                # Start with a new scientific lineage; never overwrite prior observations.
                folder.mkdir(parents=True,exist_ok=False)
                _write_new(folder/'lineage.json',manifest)
            try:
                kwargs={'now_ms':now_ms}
                if fetch is not None:kwargs['fetch']=fetch
                result=v34_cycle(store,registry,folder,**kwargs)
            except Exception:
                # Keep manifest for postmortem; user must inspect partial creation.
                raise
            result['epoch']=epoch
            if fresh and summaries:result['recovered_gap_bars']=gap
        check=report(root,context)
        if report_path:
            dst=Path(report_path);dst.parent.mkdir(parents=True,exist_ok=True)
            tmp=dst.with_name(dst.name+'.tmp')
            tmp.write_text(json.dumps(check,indent=2,sort_keys=True,allow_nan=False),encoding='utf-8')
            os.replace(tmp,dst) # only mutable derived diagnostic summary, not predictions
        result['candidate_statuses']=[c['status'] for c in check.get('candidates',[])]
        result['no_orders']=True
        return result
    finally:
        lock.unlink(missing_ok=True)


def main():
    ap=argparse.ArgumentParser(description='V35 gap-safe forward evidence supervisor; NO ORDERS')
    ap.add_argument('--store',default='reports/v21_evidence')
    ap.add_argument('--registry',default='reports/v27_mutation_registry.json')
    ap.add_argument('--output-dir',default=ROOT_DEFAULT)
    ap.add_argument('--report',default='reports/v35_candidate_audit.json')
    args=ap.parse_args()
    result=run(args.store,args.registry,args.output_dir,report_path=args.report)
    print('CQWE_V35_SUPERVISOR_PASS '+json.dumps(result,sort_keys=True))
    print('OBSERVATION ONLY | EPOCH RESET ON GAP | NO AUTO PROMOTION | NO ORDERS')

if __name__=='__main__':main()
