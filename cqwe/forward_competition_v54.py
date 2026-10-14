"""Audited precommitted four-market competitions, research only.

Uses recorded PRECOMMIT predictions and later SETTLED results, never retrains on
future data. Cost proxies are illustrative and never represent actual fills.
"""
from __future__ import annotations
import argparse, hashlib, json, math, statistics
from pathlib import Path
from .forward_lab_v47 import audit_file
from .market_replay_v43 import read_chain
from .memory_v52 import load, ROOT
from .copernican_lab_v33 import specs

SYMBOLS=('BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT')
ROOT_OUT=Path('D:/CQWE_DATA/research_v54')


def _digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')).hexdigest()


def events_from_capture(file):
    verified=audit_file(file)  # mandatory full causal chain audit
    rows=read_chain(file)
    pending={}; events=[]
    for r in rows:
        p=r['payload'];kind=r['kind']
        if kind=='PRECOMMIT':
            key=p['decision_ns']
            if key in pending:raise ValueError('DUPLICATE_PRECOMMIT')
            preds=p.get('genotype_predictions')
            directions=p.get('baseline_directions')
            if not isinstance(preds,list) or len(preds)!=6 or not all(type(x) in (int,float) and math.isfinite(x) and -1<=x<=1 for x in preds):
                raise ValueError('INVALID_PRECOMMIT_PREDICTIONS')
            if not isinstance(directions,dict) or set(directions)!={'cash','cross_long','book_imbalance','trend_agreement'} or any(type(x) is not int or x not in (0,1) for x in directions.values()):
                raise ValueError('INVALID_BASELINE_DIRECTIONS')
            pending[key]=p
        if kind in ('SETTLED','EXPIRED'):
            key=p['decision_ns']
            if key not in pending:raise ValueError('UNPAIRED_OUTCOME')
            prior=pending.pop(key)
            if kind=='EXPIRED':continue
            move=p.get('move_bps');cross=p.get('long_cross_proxy_bps')
            if not all(type(v) in (int,float) and math.isfinite(v) for v in (move,cross)):
                raise ValueError('INVALID_OUTCOME_VALUE')
            # Causal audit checks book anchors; here we check prediction quality only.
            label=p['label']
            if type(label) is not int or label not in (-1,0,1):raise ValueError('INVALID_LABEL')
            events.append({'decision_ns':key,'settled_received_ns':p['settled_received_ns'],
                'label':label,'move_bps':move,'long_cross_proxy_bps':cross,
                'predictions':prior['genotype_predictions'],'baselines':prior['baseline_directions']})
    if len(events)!=verified['settled']:raise ValueError('SETTLED_EVENT_MISMATCH')
    return events


def evaluate(memory=ROOT,output=ROOT_OUT,minimum_sessions=30,minimum_events=100):
    if minimum_sessions<2 or minimum_events<2:raise ValueError('INSUFFICIENT_GATE_SETTINGS')
    output=Path(output); report={'schema':'CTI_V54_FORWARD_COMPETITION','symbols':{},
      'profitability_proven':False,'promotion_allowed':False,'real_orders':0,'actual_fills':0,
      'real_profit_usd':0,'warning':'Shared market regimes, correlated non-overlapping per-symbol windows; no execution evidence or calibrated PnL.'}
    for symbol in SYMBOLS:
        last,sha=load(memory,symbol) # verifies every ancestor source and memory lineage
        count=0;items=[];intervals=[];files=[]
        folder=Path(memory)/symbol
        for i in range(1,1+(last['generation'] if last else 0)):
            c=json.loads((folder/f'checkpoint_{i:08d}.json').read_bytes())
            file=Path(c['source_file']);capture=events_from_capture(file)
            count+=1;files.append(c['source_sha256'])
            # Only compare within chronologically validated, non-overlapping decisions.
            for e in capture:
                if intervals and e['decision_ns']<=intervals[-1][1]:raise ValueError('OVERLAPPING_FORWARD_WINDOWS')
                intervals.append((e['decision_ns'],e['settled_received_ns']))
                items.append(e)
        genotypes=[]
        for i,spec in enumerate(specs()):
            errors=[(e['predictions'][i]-e['label'])**2 for e in items]
            # A fixed long-only threshold; still a non-executable proxy.
            selected=[e['long_cross_proxy_bps'] for e in items if e['predictions'][i]>.2]
            genotypes.append({'index':i,'spec':spec,'scored_events':len(errors),
                 'mean_squared_direction_error':round(statistics.mean(errors),8) if errors else None,
                 'long_proxy_signals':len(selected),'mean_cross_proxy_bps':round(statistics.mean(selected),8) if selected else None})
        names=('cash','cross_long','book_imbalance','trend_agreement')
        baselines={k:{'signals':sum(e['baselines'][k] for e in items),
              'mean_cross_proxy_bps':round(statistics.mean([e['long_cross_proxy_bps'] for e in items if e['baselines'][k]]),8)
                  if any(e['baselines'][k] for e in items) else None} for k in names}
        report['symbols'][symbol]={'generations':count,'settled_events':len(items),'evidence_sha256':files,
            'checkpoint_sha256':sha,'candidate_scores':genotypes,'baseline_proxies':baselines,
            'sample_gate_pass':count>=minimum_sessions and len(items)>=minimum_events,
            'winner':None,'trade_permission':False}
    report['all_symbol_gates_pass']=all(v['sample_gate_pass'] for v in report['symbols'].values())
    report['sha256']=_digest(report)
    output.mkdir(parents=True,exist_ok=True)
    target=output/f'competition_{report["sha256"]}.json'
    if target.exists():
        if json.loads(target.read_text(encoding='utf8'))!=report:raise ValueError('REPORT_CONFLICT')
    else:
        with target.open('x',encoding='utf8') as f:json.dump(report,f,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)
    report['report_file']=str(target)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--memory',default=str(ROOT));p.add_argument('--output',default=str(ROOT_OUT));a=p.parse_args()
    result=evaluate(a.memory,a.output)
    print('CTI_V54_COMPETITION '+json.dumps({'events':{k:v['settled_events'] for k,v in result['symbols'].items()},
      'generations':{k:v['generations'] for k,v in result['symbols'].items()},
      'all_gates_pass':result['all_symbol_gates_pass'],'promotion_allowed':False,'report':result['report_file']},sort_keys=True),flush=True)
if __name__=='__main__':main()
