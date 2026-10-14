"""V36 read-only longitudinal scoring and operational health for V35 lineages.

Only records that passed V35/V34 hash-chain verification enter analysis.
This is a descriptive prequential research audit, NEVER a candidate promotion.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import time
from pathlib import Path
from .copernican_lab_v33 import digest
from .evolution_supervisor_v35 import audit, context_hash, lineage_names
from .public_data_v29 import PERIOD
from .forward_dendrites_v34 import GENOTYPES

MIN_SETTLED = 120
# 6 hypotheses; conservative simultaneous bound on bounded event improvement [-4, 1].
DELTA = 0.05


def _finite(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError('INVALID_CANDIDATE_SCORE')
    return float(v)


def longitudinal(root, context, *, now_ms=None):
    """Verify all epochs and compare *paired* event scores within each epoch.

    Omitted bars are NOT interpolated. Summaries are not independent evidence:
    evolving candidates and historical reuse invalidate confirmatory inference.
    """
    epochs = audit(root, context)
    counts = [0] * len(GENOTYPES)
    advantages = [0.0] * len(GENOTYPES)
    per_epoch = []
    for directory in lineage_names(root):
        frames = sorted(directory.glob('frame_*.json'), key=lambda p: int(p.stem[6:]))
        previous = None
        for path in frames:
            rec = json.loads(path.read_text(encoding='utf-8'))
            if previous is not None:
                for i, (curr, prev) in enumerate(zip(rec['candidates'], previous['candidates'])):
                    n = curr['observations'] - prev['observations']
                    if n != 1: raise ValueError('OBSERVATION_COUNTER_DISCONTINUITY')
                    error = _finite(curr['squared_error_sum'] - prev['squared_error_sum'])
                    zero = _finite(curr['zero_baseline_squared_error_sum'] - prev['zero_baseline_squared_error_sum'])
                    if error < -1e-7 or error > 4.000001 or zero < -1e-7 or zero > 1.000001:
                        raise ValueError('IMPOSSIBLE_INCREMENTAL_ERROR')
                    counts[i] += 1
                    advantages[i] += zero - error
            previous = rec
        per_epoch.append({'epoch': int(directory.name[6:]), 'settled_steps': max(len(frames)-1, 0),
                          'tip_sha256': previous['sha256']})
    observations = []
    for i, genotype in enumerate(GENOTYPES):
        n=counts[i]
        mean=advantages[i]/n if n else None
        # One-sided Hoeffding; range=5. Correction across all six candidates.
        bound = 5 * math.sqrt(math.log(len(GENOTYPES)/DELTA)/(2*n)) if n else None
        lcb=mean-bound if n else None
        status=('INSUFFICIENT_SEQUENTIAL_OBSERVATIONS' if n<MIN_SETTLED
                else 'NO_VERIFIED_EDGE' if lcb <= 0
                else 'RESEARCH_ONLY_REQUIRES_NEW_INDEPENDENT_HOLDOUT')
        observations.append({'genotype':genotype,'settled_steps':n,'mean_paired_mse_advantage':mean,
                             'conservative_descriptive_lcb':lcb, 'status':status,
                             'eligible_for_auto_promotion':False})
    if now_ms is None: now_ms = time.time_ns() // 1_000_000
    if epochs:
        # 'last_open_ms' is the open timestamp of the latest closed input candle.
        age_ms=max(0, now_ms-(epochs[-1]['last_open_ms']+PERIOD))
        fresh='FRESH' if age_ms < PERIOD+60_000 else 'STALE_OR_TASK_DELAY'
    else:
        age_ms=None;fresh='NO_LINEAGE'
    out={'version':'CQWE_V36_EVIDENCE_HEALTH', 'research_only':True,'no_orders':True,
         'no_auto_promotion':True,'epoch_count':len(epochs),'epochs':per_epoch,
         'last_open_ms':epochs[-1]['last_open_ms'] if epochs else None,
         'age_since_last_closed_ms':age_ms,'freshness':fresh,
         'candidate_comparison':observations,'observed_gaps':sum(e.get('gap_bars_from_prior',0) for e in epochs),
         'cross_epoch_state_policy':'ARCHIVE_ONLY_NO_WEIGHT_INHERITANCE',
         'limitations':'Prequential, adaptive and possibly overlapping market outcomes: descriptive only. Bounds do not establish independent trading edge, fillability, or profit.'}
    out['sha256']=digest(out)
    return out


def write_report(path, value):
    dst=Path(path);dst.parent.mkdir(parents=True,exist_ok=True)
    tmp=dst.with_name(dst.name+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False),encoding='utf-8')
    os.replace(tmp,dst)


def main():
    ap=argparse.ArgumentParser(description='V36 evidence-health audit; READ ONLY, NO ORDERS')
    ap.add_argument('--store',default='reports/v21_evidence')
    ap.add_argument('--registry',default='reports/v27_mutation_registry.json')
    ap.add_argument('--lineages',default='reports/v35_lineages')
    ap.add_argument('--output',default='reports/v36_evidence_health.json')
    args=ap.parse_args()
    context=context_hash(args.store,args.registry)
    result=longitudinal(args.lineages,context)
    write_report(args.output,result)
    print('CQWE_V36_EVIDENCE_HEALTH_PASS '+json.dumps({'epochs':result['epoch_count'],'freshness':result['freshness'], 'settled_steps':result['candidate_comparison'][0]['settled_steps']},sort_keys=True))
    print('NO WEIGHT INHERITANCE | NO PROMOTION | NO ORDERS | NO PROFIT CLAIM')

if __name__=='__main__':main()
