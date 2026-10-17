"""Chronological event-node research with delayed labels and a frozen holdout."""
import argparse
import collections
import heapq
import json
import math
from pathlib import Path

from cqwe.copernican_experiment_v81_v85 import digest
from cqwe.four_market_runner import checked
from cqwe.liquidity_research import Branch16
from cqwe.local_autopilot import atomic


def features(types,anchor,responses):
    categories=[]
    for name in types:
        categories.append(0 if name in ('US_CPI','US_PPI','US_PCE','US_ECI') else
                          1 if name in ('US_NFP','US_ADP','US_JOLTS','US_CLAIMS') else
                          2 if name in ('US_GDP','US_RETAIL') else
                          3 if name.startswith('US_') else 4 if name=='FED_RATE' else
                          5 if name.endswith('_RATE') else 6 if 'CONFERENCE' in name else 7)
    x=[categories.count(i)/len(categories) for i in range(8)]
    by={r['horizon']:r for r in responses}
    x += [math.tanh((by[h].get('pre_return_bps') or 0.)/50) for h in (300,900,3600)]
    day=anchor/86400000
    x += [math.sin(day*2*math.pi),math.cos(day*2*math.pi),
          math.sin(day*2*math.pi/7),math.cos(day*2*math.pi/7),1.]
    return x


def evaluate(rows):
    # One asset/outcome per simultaneous event cluster, not one per headline.
    groups=collections.defaultdict(dict)
    for row in rows:
        groups[row['anchor_ms']].setdefault(row['symbol'],[]).append(row)
    times=sorted(groups)
    if len(times)<15:raise ValueError('EVENT_HISTORY_TOO_SHORT_FOR_THREE_SPLITS')
    train_end=times[int(len(times)*.6)];holdout_start=times[int(len(times)*.8)]
    models={};beta={};scores={};pending=[];serial=0;forecasts=[];chosen={};last_train_due=-1
    def bank(key):
        if key not in models:
            models[key]=Branch16();beta[key]=collections.defaultdict(lambda:[1.,1.])
            scores[key]={phase:{kind:{'n':0,'brier_sum':0.} for kind in ('frozen','global','family','dendritic')}
                         for phase in ('validation','holdout')}
    def mature(now):
        nonlocal last_train_due
        while pending and pending[0][0]<=now:
            due,_,f=heapq.heappop(pending);key=f['key'];y=f['y']
            if f['phase']=='train' and due<train_end:
                p,cache=f['dendrite'];models[key].learn(f['x'],y,p,cache)
                for name in ('global',f['family']):
                    beta[key][name][0]+=y;beta[key][name][1]+=1-y
                last_train_due=max(last_train_due,due)
            elif f['phase'] in ('validation','holdout'):
                if f['phase']=='validation' and due>=holdout_start:continue
                for name,p in f['predictions'].items():
                    s=scores[key][f['phase']][name];s['n']+=1;s['brier_sum']+=(p-y)**2
    for t in times:
        mature(t)
        if t>=holdout_start and not chosen:
            for key in scores:
                eligible={name:s for name,s in scores[key]['validation'].items() if s['n']>=10}
                chosen[key]=min(eligible,key=lambda n:eligible[n]['brier_sum']/eligible[n]['n']) if eligible else 'frozen'
        for symbol,items in groups[t].items():
            types=sorted({r['event_type'] for r in items});base=items[0]
            family='+'.join(types);x=features(types,t,base['responses'])
            for r in base['responses']:
                if r['status']!='OBSERVED' or r['label']==0:continue
                h=r['horizon'];key=f'{symbol}:{h}';bank(key)
                p,cache=models[key].predict(x)
                priors={name:beta[key][name][0]/sum(beta[key][name]) for name in ('global',family)}
                predictions={'frozen':.5,'global':priors['global'],'family':priors[family],'dendritic':p}
                phase='train' if t<train_end else 'validation' if t<holdout_start else 'holdout'
                f={'key':key,'at_ms':t,'phase':phase,'family':family,'x':x,'y':int(r['label']>0),
                   'predictions':predictions,'dendrite':[p,cache]}
                heapq.heappush(pending,(t+h*1000,serial,f));serial+=1
                forecasts.append({'key':key,'at_ms':t,'due_ms':t+h*1000,'phase':phase,
                                  'p_up':predictions,'event_types':types})
    mature(float('inf'))
    return {'groups':len(times),'train_end_ms':train_end,'holdout_start_ms':holdout_start,
            'last_training_label_maturity_ms':last_train_due,'scores':scores,'chosen_from_validation':chosen,
            'model_updates':{k:m.updates for k,m in models.items()},'forecasts':forecasts,
            'archived_training_model_states':{k:m.state() for k,m in models.items()},
            'archived_training_priors':{k:dict(v) for k,v in beta.items()},
            'historical_research_only':True,'real_orders':0,'execution_eligible':False,
            'calendar_vintage_and_consensus_complete':False,'profitability_proven':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='D:/CQWE_DATA/event_history_20261016')
    a=p.parse_args();root=Path(a.root)
    impact=checked(json.loads((root/'impact_report.json').read_text(encoding='utf-8')))
    if not impact.get('result_files'):raise ValueError('VERSIONED_RESULT_MANIFEST_REQUIRED')
    rows=[checked(json.loads(Path(path).read_text(encoding='utf-8'))) for path in impact['result_files']]
    result=evaluate(rows);result['input_report_sha256']=impact['sha256']
    result['input_files']=impact['result_files']
    out=root/'learning_runs'/f"{digest(result)}.json";out.parent.mkdir(exist_ok=True)
    if not out.exists():atomic(out,result)
    atomic(root/'learning_latest.json',{'path':str(out),'historical_only':True,'profitability_proven':False})
    print(json.dumps({'report':str(out),'groups':result['groups'],'model_updates':result['model_updates']}))
