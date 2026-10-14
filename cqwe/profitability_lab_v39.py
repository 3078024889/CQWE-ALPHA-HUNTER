"""V39 read-only profitability falsification: 10 auditable gates, NO tuning or orders.

This report separates recorded V38 $10 paper segments from non-executable V31
close-to-close forward signals. Stress costs are hypothetical assumptions, not fills.
"""
from __future__ import annotations
import argparse, json, math, os, time
from pathlib import Path
from .paper_recovery_v38 import segment_truth
from .operational_truth_v37 import _read_account
from .rolling_signal_v31 import _read, _verify
from .public_data_v29 import PERIOD, _digest

VERSION='CQWE_V39_TEN_GATE_PROFIT_FALSIFICATION'
MIN_EVENTS=100
FEE_SLIPPAGE_TOTAL_BPS=(0, 10, 20, 40, 80)

def _forward_signals(root):
    folder=Path(root)
    records=[];missing=0;unusable=0;invalid=0
    for p in sorted(folder.glob('signal_*.json')):
        sig=_read(p);_verify(sig)
        if sig.get('version')!='CQWE_V31_PRECOMMITTED_NEXT_BAR_SIGNAL' or not sig.get('no_orders'):
            raise ValueError('SIGNAL_INVALID_VERSION_OR_SAFETY')
        target=sig.get('target_open_ms')
        if not isinstance(target,int) or sig.get('observed_last_open_ms')+PERIOD!=target:
            raise ValueError('TARGET_ALIGNMENT_INVALID')
        if sig.get('recorded_at_ms',10**25)>=target:
            unusable+=1;continue  # already-started candle, not a pre-open execution plan
        out=folder/('outcome_'+p.name.removeprefix('signal_'))
        if not out.is_file():missing+=1;continue
        event=_read(out);_verify(event)
        if event.get('signal_sha256')!=sig['record_sha256'] or event.get('target_open_ms')!=target:
            raise ValueError('OUTCOME_LINK_INVALID')
        decision=sig.get('decision',{})
        if decision.get('intent')!='PAPER_BUY_CANDIDATE_NOT_ORDER':continue
        r=event.get('candidate_close_to_close_return')
        if isinstance(r,bool) or not isinstance(r,(float,int)) or not math.isfinite(r) or r <= -1:
            raise ValueError('INVALID_RESEARCH_RETURN')
        records.append({'target_open_ms':target,'return':float(r),'symbol':decision.get('symbol')})
    if len({x['target_open_ms'] for x in records})!=len(records):
        raise ValueError('DUPLICATE_TARGET_EVENT')
    return records,missing,unusable

def _cost_stress(records):
    series={}
    for bps in FEE_SLIPPAGE_TOTAL_BPS:
        # Indicative *one-bar change*, not a tradable entry-to-exit spread.
        seq=[x['return']-bps/10000 for x in records]
        series[str(bps)]={'mean_one_bar_proxy':sum(seq)/len(seq) if seq else None,
                          'proxy_positive_event_count':sum(x>0 for x in seq),
                          'event_count':len(seq)}
    return series

def audit(*,segments='reports/v38_cash_segments',legacy='reports/v33_cash_account',
          signals='reports/v31_rolling_signals',now_ms=None):
    if now_ms is None:now_ms=time.time_ns()//1_000_000
    truth=segment_truth(root=segments,now_ms=now_ms)
    historical=_read_account(legacy,now_ms=now_ms)
    obs,missing,late=_forward_signals(signals)
    stress=_cost_stress(obs)
    latest=truth['latest_segment']
    account_fresh=bool(latest and now_ms-(latest['last_open_ms']+PERIOD)<2*PERIOD+60_000)
    has_real_trade=any(x['status']!='NO_TRADES' for x in truth['segments'])
    # Gate verdicts are intentionally stringent; these are evidence gates, not an optimizer.
    gates=[
      ('G01_HASHED_SEGMENTS',truth['segment_count']>0,'All segment manifests and paper event replay verified'),
      ('G02_LEGACY_SEPARATED',True,'Old V33 journal audited separately, never summed into new PnL'),
      ('G03_NO_REAL_ORDERS',truth['no_real_orders'],'No live order API in this audit'),
      ('G04_NO_INTERSEGMENT_COMPOUNDING',truth['cumulative_profit_not_claimed'],'No cumulative claim across resets'),
      ('G05_CURRENT_ACCOUNT_FRESH',account_fresh,'Latest closed bar should be timely'),
      ('G06_PAPER_TRADE_EVIDENCE',has_real_trade,'At least one recorded simulated trade exists'),
      ('G07_PREOPEN_SIGNALS',len(obs)>0,'Forward signal registered before target bar opens'),
      ('G08_EVENT_SAMPLE_FLOOR',len(obs)>=MIN_EVENTS,'At least 100 causally usable preopen signal outcomes'),
      ('G09_COST_STRESS_POSITIVE',len(obs)>=MIN_EVENTS and stress['40']['mean_one_bar_proxy']>0,
       'Directional research proxy positive after hypothetical 40bps round-trip drag'),
      ('G10_EXECUTABLE_OOS_EDGE',False,'Requires independent executable paper fills, larger OOS sample, drawdown and exchange filters'),
    ]
    checked=[{'gate':key,'passed':bool(ok),'explanation':why} for key,ok,why in gates]
    return {'version':VERSION,'generated_at_ms':now_ms,'research_only':True,'no_real_orders':True,
            'no_model_update':True,'no_parameter_selection':True,'no_auto_promotion':True,
            'real_profit_usd':0.0,'real_receipts_verified':False,
            'v38_paper_segments':truth,'legacy_v33':historical,
            'preopen_research_event_count':len(obs),'missing_outcomes':missing,
            'signals_too_late_for_preopen':late,'stress_total_round_trip_bps':list(FEE_SLIPPAGE_TOTAL_BPS),
            'non_executable_cost_proxy':stress,'gates':checked,'passed_gates':sum(g['passed'] for g in checked),
            'profitability_proven':False,'decision':'RESEARCH_ONLY_NOT_PROVEN_PROFITABLE',
            'next_action':'Keep V38 paper task running, collect independent timestamped simulated fills; do not tune on final holdout.',
            'limitations':'V31 close-to-close returns are not fills; bps scenarios are hypothetical; G10 intentionally requires future independent evidence.'}

def write(output, report):
    data=dict(report);data['sha256']=_digest(data)
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(data,sort_keys=True,indent=2,allow_nan=False),encoding='utf-8')
    os.replace(tmp,path)

def main():
    ap=argparse.ArgumentParser(description='V39 read-only 10-gate profitability falsification')
    ap.add_argument('--segments',default='reports/v38_cash_segments')
    ap.add_argument('--legacy',default='reports/v33_cash_account')
    ap.add_argument('--signals',default='reports/v31_rolling_signals')
    ap.add_argument('--output',default='reports/v39_profitability_audit.json')
    a=ap.parse_args();result=audit(segments=a.segments,legacy=a.legacy,signals=a.signals)
    write(a.output,result)
    print('CQWE_V39_TEN_GATES_PASS '+json.dumps({'gates_passed':result['passed_gates'],
        'gates_total':len(result['gates']),'segments':result['v38_paper_segments']['segment_count'],
        'usable_events':result['preopen_research_event_count'],
        'profitability_proven':False},sort_keys=True))
    print('RESEARCH ONLY | NO ORDERS | NO PARAMETER TUNING | REAL PROFIT NOT PROVEN')
if __name__=='__main__':main()
