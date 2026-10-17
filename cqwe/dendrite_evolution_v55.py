"""CQWE V55: reproducible, fail-closed dendrite evolution research.
Pure offline evaluator. No trades, network, account secrets or automatic promotion.
"""
from __future__ import annotations
import argparse, hashlib, json, math, random
from pathlib import Path

GENOTYPES = ("macro", "microstructure", "temporal", "antifragility", "commercial", "metalearning")
SCHEMA = "CQWE_V55_DENDRITE_EXPERIMENT"

def canonical(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

def digest(x):
    return hashlib.sha256(canonical(x).encode("utf-8")).hexdigest()

def validate(samples):
    if not isinstance(samples,list) or len(samples)<24:
        raise ValueError("INSUFFICIENT_INDEPENDENT_SAMPLES")
    seen=set(); result=[]
    for x in samples:
        if not isinstance(x,dict) or set(x)!={"id","time","features","target","source_sha256"}:
            raise ValueError("INVALID_SAMPLE_SCHEMA")
        if not isinstance(x["id"],str) or not x["id"] or x["id"] in seen:
            raise ValueError("DUPLICATE_SAMPLE_ID")
        seen.add(x["id"])
        if not isinstance(x["time"],int) or isinstance(x["time"],bool):
            raise ValueError("INVALID_TIMESTAMP")
        if not isinstance(x["source_sha256"],str) or len(x["source_sha256"])!=64 or any(c not in '0123456789abcdef' for c in x['source_sha256']):
            raise ValueError("SOURCE_PROVENANCE_MISSING")
        if not isinstance(x["target"],int) or isinstance(x["target"],bool) or x["target"] not in (-1,0,1):
            raise ValueError("INVALID_TARGET")
        f=x["features"]
        if not isinstance(f,dict) or set(f)!=set(GENOTYPES):
            raise ValueError("INVALID_FEATURES")
        if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or abs(v)>1 for v in f.values()):
            raise ValueError("INVALID_FEATURE_VALUE")
        result.append(x)
    result.sort(key=lambda v:(v['time'],v['id']))
    if any(a['time']>=b['time'] for a,b in zip(result,result[1:])):
        raise ValueError("NON_CAUSAL_OR_OVERLAPPING_TIMES")
    return result

def score(weights, rows, *, cost_bps=15):
    """Net signed 1-unit markout proxy; NOT actual executable PnL."""
    total=0.; wins=0
    for x in rows:
        signal=sum(weights[k]*x['features'][k] for k in GENOTYPES)
        direction=1 if signal>0.05 else (-1 if signal<-.05 else 0)
        # Each correct one-step directional forecast earns a synthetic 20bp;
        # each wrong one loses 20bp, with an explicitly assumed round-trip cost.
        payoff=direction*x['target']*20-abs(direction)*cost_bps
        total+=payoff
        wins+=int(payoff>0)
    return {'proxy_net_bps_per_event':round(total/len(rows),6),
            'positive_events':wins,'events':len(rows)}

def evaluate(samples, *, seed=55, minimum_holdout=8, cost_bps=15):
    rows=validate(samples)
    if not isinstance(seed,int) or isinstance(seed,bool) or not isinstance(cost_bps,(int,float)) or not math.isfinite(cost_bps) or cost_bps<0:
        raise ValueError('INVALID_EXPERIMENT_CONFIG')
    ntrain=int(len(rows)*.6); nvalidation=int(len(rows)*.2)
    train, dev, holdout=rows[:ntrain],rows[ntrain:ntrain+nvalidation],rows[ntrain+nvalidation:]
    if len(holdout)<minimum_holdout or not train or not dev:
        raise ValueError('INSUFFICIENT_HOLDOUT')
    rng=random.Random(seed)
    ancestors=[]
    for k in GENOTYPES:
        w={name:0. for name in GENOTYPES};w[k]=1.;ancestors.append({'id':'parent_'+k,'weights':w})
    offspring=[]
    for parent in ancestors:
        for i in range(4):
            w=dict(parent['weights'])
            k=rng.choice(GENOTYPES)
            w[k]=max(-1.,min(1.,w[k]+rng.choice((-0.4,-0.2,0.2,0.4))))
            offspring.append({'id':parent['id']+'_child'+str(i),'parent':parent['id'],'weights':w})
    # Search strictly on train, choose on dev, evaluate once on holdout.
    pool=ancestors+offspring
    scored=[{'id':c['id'],'parent':c.get('parent'), 'weights':c['weights'],
             'train':score(c['weights'],train,cost_bps=cost_bps),
             'dev':score(c['weights'],dev,cost_bps=cost_bps)} for c in pool]
    chosen=sorted(scored,key=lambda x:(-x['dev']['proxy_net_bps_per_event'],-x['train']['proxy_net_bps_per_event'],x['id']))[0]
    final=score(chosen['weights'],holdout,cost_bps=cost_bps)
    baseline=score({k:0. for k in GENOTYPES},holdout,cost_bps=cost_bps)
    report={'schema':SCHEMA,'seed':seed,'cost_bps_assumption':cost_bps,
            'source_digest':digest(rows), 'split':{'train':len(train),'validation':len(dev),'holdout':len(holdout),
            'train_last':train[-1]['time'],'dev_first':dev[0]['time'],'dev_last':dev[-1]['time'],'holdout_first':holdout[0]['time']},
            'candidate_count':len(pool),'selected_candidate':chosen['id'],
            'selected_parent':chosen['parent'],'selected_weights':chosen['weights'],
            'selected_train':chosen['train'],'selected_validation':chosen['dev'],
            'holdout':final,'cash_baseline':baseline,
            'holdout_improvement_proxy_bps':round(final['proxy_net_bps_per_event']-baseline['proxy_net_bps_per_event'],6),
            'promotion_allowed':False,'realized_profit_usd':None,'executed_orders':0,
            'remarks':'Research-only synthetic label proxy; holdout is never used for selection. No market order or real profit is implied.'}
    report['sha256']=digest(report)
    return report

def cli():
    p=argparse.ArgumentParser(description='CQWE V55 offline dendritic tournament')
    p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    args=p.parse_args(); inp=Path(args.input);out=Path(args.output)
    if not inp.is_file() or inp.stat().st_size>20_000_000:raise ValueError('MISSING_OR_OVERSIZE_INPUT')
    rows=[json.loads(x) for x in inp.read_text(encoding='utf-8').splitlines() if x.strip()]
    report=evaluate(rows)
    if out.exists():raise ValueError('IMMUTABLE_REPORT_ALREADY_EXISTS')
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as f:f.write(canonical(report)+'\n')
    print('V55_EXPERIMENT_WRITTEN='+str(out))
    print('V55_REPORT_SHA256='+report['sha256'])

if __name__=='__main__':cli()
