"""Six predeclared dendritic variants in a retrospective, chronological gym.

Inspired by the novel's chapter 41 testing environment. This is level-one
historical research, NOT precommitted live predictions of these six variants.
"""
import argparse
import copy
import json
import math
from pathlib import Path

from .copernican_lab_v33 import Dendrite, specs
from .copernican_experiment_v81_v85 import digest
from .tidal_hunter import verify_capture, write_new


def samples_from_sessions(paths):
    if not 1<=len(paths)<=50:
        raise ValueError('GYM_SOURCE_BUDGET')
    samples,seen = [],set()
    last_end = -1
    sources = []
    for path in paths:
        rows = verify_capture(Path(path)/'capture.jsonl')
        if rows[-1]['payload'].get('status') != 'COMPLETE':
            raise ValueError('GYM_SOURCE_SESSION_INCOMPLETE')
        if rows[0]['written_ns'] <= last_end:
            raise ValueError('OVERLAPPING_OR_REORDERED_GYM_SESSIONS')
        last_end = rows[-1]['written_ns']
        tip = rows[-1]['sha256']
        if tip in seen:
            raise ValueError('DUPLICATE_GYM_SOURCE')
        seen.add(tip)
        sources.append(tip)
        pending = {}
        view = None
        for r in rows:
            k,p = r['kind'],r['payload']
            if k=='FRAME':
                view = p
            elif k=='FORECAST':
                pending[p['decision_ns']] = p
            elif k=='MATURED':
                f = pending.pop(p['decision_ns'])
                if view is None or view['now_ns'] < f['decision_ns']+5_000_000_000:
                    raise ValueError('GYM_NONCAUSAL_LABEL')
                move = p['move_bps']
                if move == 0:
                    continue  # ties are not manufactured into binary outcomes
                x = f['features']
                if len(x)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1 for v in x):
                    raise ValueError('GYM_INVALID_FEATURES')
                entry,exit_ = f['book'],view['view']
                samples.append({'id':digest({'source':tip,'decision':f['decision_ns']}),
                    'features':x,'label':1 if move>0 else -1,
                    'decision_ns':f['decision_ns'],'outcome_ns':view['now_ns'],
                    'long_proxy_bps':(float(exit_['bid'])/float(entry['ask'])-1)*10000-14,
                    'short_proxy_bps':(float(entry['bid'])-float(exit_['ask']))/float(entry['bid'])*10000-14})
    return samples,sources


def evaluate(rows):
    if not isinstance(rows,list) or not 20<=len(rows)<=100000:
        raise ValueError('GYM_NEEDS_20_MATURED_NONTIE_EVENTS')
    if len({r['id'] for r in rows})!=len(rows):
        raise ValueError('DUPLICATE_GYM_SAMPLE')
    t,v = int(len(rows)*.6),int(len(rows)*.8)
    for i,r in enumerate(rows):
        if (type(r['label']) is not int or r['label'] not in (-1,1)
                or type(r['decision_ns']) is not int or type(r['outcome_ns']) is not int
                or r['outcome_ns']<=r['decision_ns']):
            raise ValueError('INVALID_GYM_LABEL')
        if i and r['decision_ns']<rows[i-1]['outcome_ns']:
            raise ValueError('OVERLAPPING_GYM_LABELS')
        if len(r['features'])!=4 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1 for x in r['features']):
            raise ValueError('INVALID_GYM_FEATURES')
        if any(type(r[k]) not in (int,float) or not math.isfinite(r[k]) for k in ('long_proxy_bps','short_proxy_bps')):
            raise ValueError('INVALID_GYM_MARKOUT')

    def score(model, subset):
        losses,proxies = [],[]
        for r in subset:
            pred,_ = model.forward(r['features'])
            p = (pred+1)/2
            losses.append((p-(r['label']+1)/2)**2)
            if abs(pred)>.05:
                proxies.append(r['long_proxy_bps'] if pred>0 else r['short_proxy_bps'])
        return {'n':len(losses),'brier':sum(losses)/len(losses),
                'directional_proxy_signals':len(proxies),
                'mean_cost_adjusted_proxy_bps':sum(proxies)/len(proxies) if proxies else None}

    candidates = []
    models = []
    for index,spec in enumerate(specs()):
        m = Dendrite(spec)
        initial = list(m.w)
        for r in rows[:t]:
            pred,response = m.forward(r['features'])
            m.update(response,r['label'],pred,r['features'])
        validation = score(m,rows[t:v])
        candidates.append({'id':index,'spec':spec,'updates':m.updates,
                           'initial_weights':initial,'trained_weights':list(m.w),
                           'validation':validation})
        models.append(m)
    winner = min(candidates,key=lambda c:(c['validation']['brier'],c['id']))['id']
    test = score(copy.deepcopy(models[winner]),rows[v:])
    result = {'schema':'CQWE_SIX_VARIANT_GYM_V1','mode':'RETROSPECTIVE_REPLAY',
              'split':{'train':t,'validation':v-t,'holdout':len(rows)-v},
              'candidate_count':6,'candidates':candidates,'selected_on_validation':winner,
              'selected_holdout':test,'coin_flip_holdout_brier':.25,
              'independent_forward_evidence':False,'probabilities_calibrated':False,
              'promotion_allowed':False,'real_orders':0,'profitability_proven':False,
              'source_samples_sha256':digest(rows),
              'limitations':['Six fixed variants, not 7000 experiments or automatic code evolution.',
                  'Previously captured data; a new forward experiment is required after selection.',
                  'Brier on short-horizon direction is not event-resolution probability accuracy.',
                  'Quote-crossing proxies exclude real fills, funding, capacity and account costs.']}
    result['sha256'] = digest(result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sessions',nargs='+',required=True)
    p.add_argument('--output',required=True)
    a = p.parse_args()
    rows,sources = samples_from_sessions(a.sessions)
    report = evaluate(rows)
    report['capture_sources'] = sources
    report['sha256'] = digest({k:v for k,v in report.items() if k!='sha256'})
    dest = Path(a.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    write_new(dest,report)
    print(json.dumps({k:report[k] for k in ('candidate_count','split','selected_on_validation',
                                          'selected_holdout','profitability_proven')},indent=2))


if __name__=='__main__':
    main()
