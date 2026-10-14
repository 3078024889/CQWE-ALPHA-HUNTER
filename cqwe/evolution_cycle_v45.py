"""V45 deterministic causal four-market Copernican mutation research; no orders.

Replay sealed timestamped public L2 captures; do not confuse replay with live
precommit, fills or investable edge. Archived failure evidence is never pruned.
"""
from __future__ import annotations
import argparse, hashlib, json, math, statistics, time
from pathlib import Path
from .four_asset_lab_v44 import FOUR, inspect_capture
from .market_replay_v43 import read_chain
from .copernican_lab_v33 import specs, Dendrite
from .market_maker_competition_v45 import evaluate as mm_competition

ROOT=Path('D:/CQWE_DATA/l2_v44')
REPORT=Path('D:/CQWE_DATA/research_v45')
MIN_TEST=100

def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf8')).hexdigest()

def _features(history):
    # Latest and previous synchronised top-of-book data ONLY.
    a,b=history[-2:]
    pa,pb=a['payload'],b['payload']
    mid0=(float(pa['bid'])+float(pa['ask']))/2
    mid1=(float(pb['bid'])+float(pb['ask']))/2
    bid=float(pb['bid_qty']);ask=float(pb['ask_qty'])
    imb=(bid-ask)/max(bid+ask,1e-12)
    spread=1e4*(float(pb['ask'])-float(pb['bid']))/mid1
    drift=max(-1,min(1,1e4*(mid1/mid0-1)/15))
    return [max(-1,min(1,imb)), drift, max(-1,min(1,(imb+drift)/2)),max(-1,min(1,1-spread/10))]

def extract_events(file, horizon_ns=60_000_000_000, min_spacing_ns=60_000_000_000):
    """Nonoverlapping decisions and subsequent events from one intact capture.

    All features are computed before outcome, and outcomes use future quotes.
    Observational replay is explicitly NOT independently precommitted OOS.
    """
    rows=read_chain(file)
    starts=[r for r in rows if r['kind']=='START']
    if len(starts)!=1 or rows[-1]['kind']!='STOP':raise ValueError('UNSEALED_CAPTURE')
    if not starts[0]['payload'].get('synced') or not rows[-1]['payload'].get('synced'):
        raise ValueError('UNSYNCED_CAPTURE')
    books=[r for r in rows if r['kind']=='BOOK']
    if any(not x['payload'].get('synced') for x in books):raise ValueError('UNSYNCED_BOOK')
    out=[];last_exit=-1
    for i in range(1,len(books)-1):
        now=books[i]['received_ns']
        if now<=last_exit:continue
        outcome=next((x for x in books[i+1:] if x['received_ns']>=now+horizon_ns),None)
        if outcome is None:break
        if outcome['received_ns']-now>horizon_ns+15_000_000_000:continue
        x=_features(books[i-1:i+1]);p=books[i]['payload'];future=outcome['payload']
        ask=float(p['ask']);bid=float(p['bid'])
        exit_bid=float(future['bid']);exit_ask=float(future['ask'])
        if min(ask,bid,exit_bid,exit_ask)<=0 or ask<=bid or exit_ask<=exit_bid:
            raise ValueError('CORRUPT_QUOTE')
        mid=(ask+bid)/2;future_mid=(exit_ask+exit_bid)/2
        move=(future_mid/mid-1)*1e4
        # 10bps fee and 2bps slippage per side: illustrative, NOT actual account costs.
        long_proxy=(exit_bid/ask-1)*1e4-24
        out.append({'decision_ns':now,'outcome_ns':outcome['received_ns'],'features':x,
                    'label':1 if move>0 else -1 if move<0 else 0,
                    'move_bps':move,'long_cross_proxy_bps':long_proxy})
        last_exit=outcome['received_ns']+min_spacing_ns-horizon_ns
    return out

def score(events):
    results=[]
    for ix,spec in enumerate(specs()):
        model=Dendrite(spec);historical=[];tests=[];wins=0;decisions=0
        # Fixed predeclared burn-in; no model revision during evaluation tail.
        training_cut=int(len(events)*.60)
        for i,e in enumerate(events):
            x=e['features'];prediction, response=model.forward(x)
            if i>=training_cut:
                # Shadow long-only entry considered only above fixed threshold.
                tradesignal=prediction>.08
                if tradesignal:
                    decisions+=1;tests.append(e['long_cross_proxy_bps']);wins+=e['long_cross_proxy_bps']>0
            else:
                model.update(response,e['label'],prediction,x)
            historical.append({'decision_ns':e['decision_ns'],'outcome_ns':e['outcome_ns'],
                               'pred':round(prediction,9),'label':e['label'],'training':i<training_cut})
        n=len(events)-training_cut
        results.append({'candidate':ix,'genotype':spec,'train_observations':training_cut,
                        'heldout_observations':n,'heldout_long_signals':decisions,
                        'mean_cost_proxy_bps':round(statistics.mean(tests),8) if tests else None,
                        'positive_proxy_signals':wins,'weights_after_training':[round(z,8) for z in model.w],
                        'outcome_stream_sha256':digest(historical),
                        'promotion':'INELIGIBLE_REPLAY_NOT_LIVE_OOS'})
    return results

def audit(root=ROOT, outdir=REPORT):
    root=Path(root); outdir=Path(outdir)
    markets={};bad={};total=0
    for symbol in FOUR:
        events=[];digests=[]
        for file in sorted((root/symbol).glob('*.jsonl')):
            try:
                inspect_capture(file,symbol)
                extracted=extract_events(file)
                digests.append(hashlib.sha256(file.read_bytes()).hexdigest())
                events+=extracted
            except (ValueError,KeyError,TypeError,UnicodeError,json.JSONDecodeError) as e:
                bad[file.name]=str(e)[:120]
        # Do NOT add 'event streams' across sessions as if they were continuous.
        total+=len(events)
        markets[symbol]={'sessions':len(digests),'decisions':len(events),
                          'source_sha256':digests,'candidates':score(events),
                          'market_maker_competition':mm_competition(events),
                          'independent_live_oos':False,'real_fills':0}
    body={'schema':'CQWE_V45_COPERNICAN_REPLAY','assets':list(FOUR),'markets':markets,
          'rejected_sessions':bad,'nonoverlap_event_count':total,
          'promotion':'BLOCKED_NO_INDEPENDENT_PRECOMMITTED_LIVE_OOS',
          'no_orders':True,'real_profit_usd':0,'profitable_edge_proven':False,
          'read_only_existing_evidence':True,
          'limitations':'Historical capture replay; no live prediction precommit, no real fills, no queue identity; same sessions may have been seen by researcher.'}
    body['sha256']=digest(body)
    outdir.mkdir(parents=True,exist_ok=True)
    target=outdir/('research_'+body['sha256']+'.json')
    if not target.exists():target.write_text(json.dumps(body,ensure_ascii=False,indent=2),encoding='utf8')
    elif json.loads(target.read_text(encoding='utf8'))!=body:raise ValueError('EVIDENCE_CONFLICT')
    return body

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(ROOT));p.add_argument('--output-dir',default=str(REPORT));a=p.parse_args()
    r=audit(a.root,a.output_dir)
    print('CQWE_V45_EVOLUTION_AUDIT',json.dumps({'events':r['nonoverlap_event_count'],
      'by_symbol':{k:v['decisions'] for k,v in r['markets'].items()},'rejected':len(r['rejected_sessions']),
      'promotion':r['promotion'],'sha256':r['sha256']},sort_keys=True))
    print('COPERNICAN SIX GENOTYPES | NO LIVE OOS CLAIM | NO REAL FILLS | NO ORDERS')
if __name__=='__main__':main()
