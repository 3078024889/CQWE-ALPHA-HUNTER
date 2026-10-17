"""Frozen multi-leg screen reusing existing checksummed history; all folds reported."""
import hashlib
import json
import math
from pathlib import Path
import time
from cqwe.strategy_candidates import candidates,SPEC

HOUR=3600000


def replay(data,funding,targets,start,end,slip=.0002):
    times=[b['time'] for b in data['BTCUSDT']];cash=10.;peak=10.;dd=0.;fees=0.;funding_total=0.
    held={};weights={};trades=[];entry_at=None;entry_cash=None
    fs={s:{int(f['fundingTime']):f for f in ff} for s,ff in funding.items()}
    # Bucket actual settlements into the matching hour, retaining original times.
    buckets={s:{} for s in data}
    for s,items in fs.items():
        for t,f in items.items():buckets[s].setdefault(t//HOUR*HOUR,[]).append(f)
    def close(i,at,price_key):
        nonlocal cash,fees,held,weights
        for s,(q,entry) in held.items():
            px=data[s][i][price_key]*(1-math.copysign(slip,q));fee=abs(q)*px*.0005
            cash+=q*(px-entry)-fee;fees+=fee
        trades.append({'opened_ms':entry_at,'closed_ms':at,'net':cash-entry_cash})
        held={};weights={}
    for i,t in enumerate(times):
        if not start<=t<end:continue
        desired=targets[i]
        if desired!=weights:
            if held:close(i,t,'open')
            if desired:
                if abs(sum(abs(w) for w in desired.values())-1)>1e-8:raise ValueError('GROSS_WEIGHT_MUST_BE_ONE')
                entry_cash=cash;entry_at=t;gross=cash*.5
                for s,w in desired.items():
                    px=data[s][i]['open']*(1+math.copysign(slip,w));q=gross*w/px;fee=abs(q)*px*.0005
                    held[s]=(q,px);cash-=fee;fees+=fee
                weights=desired.copy()
        for s,(q,entry) in held.items():
            for f in buckets[s].get(t,[]):
                delta=-q*float(f['markPrice'])*float(f['fundingRate']);cash+=delta;funding_total+=delta
        worst=cash+sum(q*(data[s][i]['low' if q>0 else 'high']-entry) for s,(q,entry) in held.items())
        dd=max(dd,1-worst/peak)
        equity=cash+sum(q*(data[s][i]['close']-entry) for s,(q,entry) in held.items());peak=max(peak,equity)
        if equity<=0:raise ValueError('SIMULATED_BANKRUPTCY')
    if held:
        i=max(i for i,t in enumerate(times) if start<=t<end);close(i,times[i]+HOUR-1,'close')
    dd=max(dd,1-cash/peak)
    assert math.isclose(cash-10,sum(t['net'] for t in trades),abs_tol=1e-8)
    return {'net':cash-10,'return_pct':(cash/10-1)*100,'max_drawdown_pct':dd*100,
            'trades':len(trades),'fees':fees,'funding_cashflow':funding_total,'ledger':trades}


def main():
    root=Path('D:/CQWE_DATA/expanded_strategy_20261016');root.mkdir(exist_ok=True,parents=True)
    source=Path('cqwe/strategy_candidates.py');engine=Path(__file__)
    plan={'created_ms':time.time_ns()//1000000,'rules':SPEC,'code_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'engine_sha256':hashlib.sha256(engine.read_bytes()).hexdigest(),'fold_days':[0,182,365,547,730],
          'slippage_bps':[2,5],'fee_bps_each_side':5,'gross_notional_equity_fraction':.5,
          'previous_history_already_inspected':True,'blind_holdout_claimed':False,'parameter_search':False}
    planfile=root/'locked_plan.json'
    if planfile.exists():
        old=json.loads(planfile.read_text(encoding='utf-8'))
        if any(old[k]!=plan[k] for k in ('code_sha256','engine_sha256','rules')):raise ValueError('PLAN_CHANGED_USE_NEW_ROOT')
        plan=old
    else:planfile.write_text(json.dumps(plan,indent=2),encoding='utf-8')
    data={};funding={};coverage={}
    for symbol in ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT'):
        path=Path('D:/CQWE_DATA/strategy_lab_20261016')/(symbol+'.json');raw=json.loads(path.read_text(encoding='utf-8'));d=raw['data']
        if raw['sha256']!=hashlib.sha256(json.dumps(d,separators=(',',':')).encode()).hexdigest():raise ValueError('DATA_HASH_MISMATCH')
        data[symbol]=d['bars'];funding[symbol]=d['funding'];coverage[symbol]=raw['sha256']
    generated=candidates(data);rows=[];start=data['BTCUSDT'][0]['time']
    for name,targets in generated.items():
        for slip in (.0002,.0005):
            for fold,(left,right) in enumerate(zip(plan['fold_days'],plan['fold_days'][1:])):
                r=replay(data,funding,targets,start+left*86400000,start+right*86400000,slip)
                ledger=r.pop('ledger');p=root/(name.replace(':','_')+f'_{slip}_{fold}.json');p.write_text(json.dumps(ledger),encoding='utf-8')
                rows.append({'candidate':name,'fold':fold,'slippage_bps':slip*10000,'ledger':str(p),**r})
        print(json.dumps({'candidate':name,'folds_done':8}),flush=True)
    summary=[]
    for name in generated:
        trials=[r for r in rows if r['candidate']==name];stress=[r for r in trials if r['slippage_bps']==5]
        reasons=[]
        if any(r['net']<=0 for r in trials):reasons.append('NONPOSITIVE_FOLD')
        if any(r['trades']<20 for r in trials):reasons.append('INSUFFICIENT_TRADES_IN_FOLD')
        if any(r['max_drawdown_pct']>10 for r in trials):reasons.append('DRAWDOWN_ABOVE_RESEARCH_BUDGET')
        summary.append({'id':name,'historical_gate_pass':not reasons,'historical_reasons':reasons,
            'stress_positive_folds':sum(r['net']>0 for r in stress),'folds':4,
            'stage':'SHADOW_ONLY','execution_weight':0,'profitability_proven':False,
            'deployment_blockers':['UNSEEN_FORWARD_EVIDENCE_REQUIRED','SMALL_ACCOUNT_ORDER_FILTERS',
                'PARTIAL_FILLS_AND_EXECUTION_UNMODELLED','MULTIPLE_COMPARISONS_NOT_CORRECTED']})
    out={'plan':plan,'data_sha256':coverage,'results':rows,'candidates':summary,'real_orders':0,'profitability_proven':False,
         'limits':['Independent research variants, not exact third-party implementations','Hourly signals cannot reproduce microstructure or events',
                   'Four folds share market regimes, not independent experiments','Multi-leg adverse-bar drawdown is conservative; extrema need not be simultaneous',
                   'No order minimums, impact, exact margin/liquidation, or partial fills','Each configuration has separate 10 USD; not one combined account']}
    Path('reports/expanded_strategy_screen_20261016.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps({'configurations':len(rows),'candidates':len(summary),'historical_pass':sum(s['historical_gate_pass'] for s in summary)}))


if __name__=='__main__':main()
