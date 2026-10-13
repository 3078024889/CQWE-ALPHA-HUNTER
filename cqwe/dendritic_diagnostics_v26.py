"""CQWE V26: Read-only causal accounting diagnostics and evidence-gated mutation proposals.

Ideas adapted, not copied: novel dendritic locality and edge cases; Freqtrade
lookahead analysis; Nautilus sequencing; Hummingbot dry-run; CCXT venue filters.
No profitability claims, actual venue order authority, or execution API.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from collections import defaultdict
from pathlib import Path
from .account_forensics_v25 import audit_one

EXPERIMENTS={
 'PRICE_DIRECTION': {'node':'direction_signal', 'mutation':'test alternative closed-bar trend/regime feature; never fit on sealed evaluation period'},
 'EXECUTION_FRICTION': {'node':'execution_cost', 'mutation':'evaluate passive versus taker hypothetical fills with non-fill and latency assumptions'},
 'ORDER_FEASIBILITY_UNKNOWN': {'node':'venue_constraints', 'mutation':'obtain fresh actual venue lot size, tick size and minimum notional before any executable claim'},
 'ORDER_FEASIBILITY_REJECTED': {'node':'venue_constraints', 'mutation':'reject sub-minimum order; research a zero-cost alternative venue only with independently verified metadata'},
 'SMALL_SAMPLE': {'node':'evidence_confidence', 'mutation':'wait for new forward data; preserve fixed thresholds and baseline'},
 'LOSS_CONCENTRATION': {'node':'regime_exception', 'mutation':'log loss regime and test change-point monitoring only on subsequent unseen periods'},
 'NO_TRADES': {'node':'opportunity_detection', 'mutation':'keep no-trade baseline and request new independent observations'}
}

def _number(v):
 if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError('NONFINITE_VALUE')
 return float(v)

def evaluate(forensics,venue=None):
 if not isinstance(forensics,dict) or forensics.get('decision')!='NO_LIVE_PROMOTION' or not forensics.get('research_only') or 'reports' not in forensics:raise ValueError('INVALID_FORENSICS')
 report=forensics['reports']['shadow']; stress=forensics['reports']['shadow_stress']
 if not report.get('account_ledger_verified') or not stress.get('account_ledger_verified'):raise ValueError('UNVERIFIED_LEDGER')
 pairs=report['paired_trades'];entries=report['entries'];end=_number(report['ending_equity_usd']);start=_number(report['initial_usd'])
 cost=_number(report['explicit_fill_fees_usd']);sim_net=_number(report['virtual_net_usd']);gross=sum(_number(x['gross_price_move_usd']) for x in pairs)
 closed_net=sum(_number(x['net_usd']) for x in pairs)
 closed_fees=sum(_number(x['explicit_fees_usd']) for x in pairs)
 if not math.isclose(closed_net,gross-closed_fees,abs_tol=1e-6):raise ValueError('TRADE_ATTRIBUTION_INVALID')
 if not math.isclose(sim_net,end-start,abs_tol=1e-6):raise ValueError('NET_RECONCILIATION_FAILED')
 if _number(stress['explicit_fill_fees_usd'])<=cost:raise ValueError('INVALID_COST_STRESS')
 losses=sorted(({'symbol':x['symbol'],'buy_time_ms':x['buy_time_ms'],'loss_usd':round(-_number(x['net_usd']),9)} for x in pairs if _number(x['net_usd'])<0),key=lambda t:t['loss_usd'],reverse=True)
 loss_total=sum(x['loss_usd'] for x in losses)
 concentration=(losses[0]['loss_usd']/loss_total if loss_total else 0.0)
 breakdown=defaultdict(lambda:{'n':0,'net':0.0})
 for x in pairs:
  k=x['symbol'];breakdown[k]['n']+=1;breakdown[k]['net']+=_number(x['net_usd'])
 for v in breakdown.values():v['net']=round(v['net'],9)
 findings=[]
 if entries==0:findings.append('NO_TRADES')
 else:
  if closed_net < -1e-8:findings.append('PRICE_DIRECTION')
  if cost>0:findings.append('EXECUTION_FRICTION')
  if len(pairs)<30:findings.append('SMALL_SAMPLE')
  if concentration>.5 and len(losses)>1:findings.append('LOSS_CONCENTRATION')
 venue_data=venue or {}
 # Venue metadata is explicitly optional: unknown != feasible. Never synthesize venue rules.
 if not venue_data:findings.append('ORDER_FEASIBILITY_UNKNOWN')
 else:
  if not isinstance(venue_data,dict):raise ValueError('INVALID_VENUE')
  needed=('min_notional_usd','min_qty','qty_step','price_tick')
  if any(k not in venue_data for k in needed):findings.append('ORDER_FEASIBILITY_UNKNOWN')
  else:
   vals={k:_number(venue_data[k]) for k in needed}
   if any(v<=0 for v in vals.values()):raise ValueError('INVALID_VENUE_FILTER')
   max_possible=start*.6
   if max_possible < vals['min_notional_usd']:findings.append('ORDER_FEASIBILITY_REJECTED')
 # Proposed experiments are hypotheses, not verified mutations.
 actions=[{'finding':k,**EXPERIMENTS[k],'status':'PROPOSAL_ONLY_NOT_PROMOTED'} for k in dict.fromkeys(findings)]
 return {'version':'CQWE_V26_DENDRITIC_POSTMORTEM','research_only':True,'no_orders':True,'profit_claim':False,
  'historical_reuse_contaminated':True,'initial_virtual_usd':start,'ending_virtual_usd':end,'simulated_net_usd':sim_net,
  'completed_pair_count':len(pairs),'entry_count':entries,'closed_trade_gross_price_move_usd':round(gross,9),
  'closed_trade_explicit_fees_usd':round(closed_fees,9),'closed_trade_net_usd':round(closed_net,9),
  'all_fills_explicit_fees_usd':round(cost,9),'unpaired_or_mark_to_market_net_contribution_usd':round(sim_net-closed_net,9),
  'max_drawdown_pct':report['max_drawdown_pct'],'loss_share_largest_loser':round(concentration,8),
  'by_symbol':dict(sorted(breakdown.items())),'venue_status':('PROVIDED_UNVERIFIED_METADATA' if venue_data else 'UNKNOWN'),
  'proposals':actions,'decision':'RESEARCH_ONLY_NO_PROMOTION',
  'limitations':['Gross move already includes modeled entry/exit slippage. Fees do not explain all losses.',
                 'Venue metadata not verified against live exchange: no claim of feasibility.',
                 'No re-fitting on the same reviewed 30-day evaluation sample.',
                 'Candlestick open assumptions cannot establish actual spread, maker fills, queue position or order-book depth.']}

def run(forensics_path,output,venue_path=None):
 inp=Path(forensics_path).read_bytes();report=json.loads(inp.decode('utf-8-sig'))
 venue_raw=Path(venue_path).read_bytes() if venue_path else None
 outcome=evaluate(report,json.loads(venue_raw.decode('utf-8-sig')) if venue_raw else None)
 outcome['source_sha256']=hashlib.sha256(inp).hexdigest()
 if venue_raw:outcome['venue_file_sha256']=hashlib.sha256(venue_raw).hexdigest()
 outcome['audit_sha256']=hashlib.sha256(json.dumps(outcome,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
 dst=Path(output);dst.parent.mkdir(parents=True,exist_ok=True);tmp=dst.with_name(dst.name+'.tmp')
 tmp.write_text(json.dumps(outcome,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');tmp.replace(dst)
 return outcome

def main():
 a=argparse.ArgumentParser(description='V26 evidence-based simulated-trade postmortem; no orders')
 a.add_argument('--forensics',required=True);a.add_argument('--output',default='reports/v26_dendritic_postmortem.json');a.add_argument('--venue-file')
 args=a.parse_args();x=run(args.forensics,args.output,args.venue_file)
 print('V26 pairs=',x['completed_pair_count'],'net=',x['simulated_net_usd'],'findings=',[p['finding'] for p in x['proposals']]);print('CQWE_V26_POSTMORTEM_PASS | READ ONLY | NO PROFIT CLAIM')
if __name__=='__main__':main()
