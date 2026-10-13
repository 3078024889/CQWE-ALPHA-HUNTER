"""V25 independent read-only audit of V24 simulated account ledgers.
No fitting, no trading, no changes to original evidence. Recompute dollars from unrounded fills.
"""
from __future__ import annotations
import argparse,hashlib,json,math,statistics
from collections import defaultdict
from pathlib import Path

def number(v,name):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
        raise ValueError('INVALID_'+name)
    return float(v)

def audit_one(payload):
    if not isinstance(payload,dict) or 'portfolio' not in payload:raise ValueError('MISSING_PORTFOLIO')
    p=payload['portfolio'];trades=p['trades'];curve=p['curve']
    if p.get('mode')!='V24_FROZEN_RESEARCH_PORTFOLIO' or not p.get('research_only') or not p.get('simulation_only') or p.get('realized_profit_usd') is not None or p.get('verified_executable_trades')!=0:
        raise ValueError('NOT_SIMULATION')
    start=number(p['initial_virtual_usd'],'INITIAL');cash=start;inv=defaultdict(float);open_buys={};roundtrips=[];cost=0.0;turnover=0.0;entries=0;exits=0;prev=-1
    for t in trades:
        side=t.get('side');sym=t.get('symbol');tm=t.get('time_ms')
        if side not in ('BUY','SELL') or not isinstance(sym,str) or not sym or type(tm)!=int or tm<prev:raise ValueError('BAD_TRADE')
        prev=tm;price=number(t['price'],'PRICE');qty=number(t['qty'],'QTY');fee=number(t['fee_and_extra_usd'],'COST')
        if price<=0 or qty<=0 or fee<0:raise ValueError('BAD_FILL')
        gross=price*qty;cost+=fee;turnover+=gross
        if side=='BUY':
            if open_buys:raise ValueError('MULTIPLE_POSITIONS')
            cash-=gross+fee;inv[sym]+=qty;entries+=1
            open_buys[sym]={'price':price,'qty':qty,'fee':fee,'time_ms':tm}
        else:
            if sym not in open_buys:raise ValueError('SELL_WITHOUT_BUY')
            b=open_buys.pop(sym)
            if not math.isclose(qty,b['qty'],rel_tol=1e-8,abs_tol=1e-8):raise ValueError('QTY_MISMATCH')
            cash+=gross-fee;inv[sym]-=qty;exits+=1
            profit=gross-fee-b['price']*b['qty']-b['fee']
            roundtrips.append({'symbol':sym,'buy_time_ms':b['time_ms'],'sell_time_ms':tm,'net_usd':round(profit,10),'gross_price_move_usd':round((price-b['price'])*qty,10),'explicit_fees_usd':round(b['fee']+fee,10),'net_return_on_buy_budget_pct':round(profit/(b['price']*b['qty']+b['fee'])*100,6)})
        if cash < -1e-7 or not math.isclose(cash,number(t['cash_after_usd'],'CASH_AFTER'),abs_tol=1e-7):raise ValueError('CASH_LEDGER_MISMATCH')
    if entries != p['entries'] or exits!=p['exits']:raise ValueError('TRADE_COUNTS_MISMATCH')
    op=p['open_position'];
    if (bool(op)!=bool(open_buys)):raise ValueError('POSITION_MISMATCH')
    if op:
        sym=op['symbol'];qty=number(op['qty'],'OPEN_QTY')
        if sym not in open_buys or not math.isclose(qty,open_buys[sym]['qty'],rel_tol=1e-8,abs_tol=1e-8):raise ValueError('OPEN_QTY_MISMATCH')
    if not math.isclose(cash,number(p['cash_usd'],'CASH'),abs_tol=1e-7):raise ValueError('FINAL_CASH_MISMATCH')
    if not curve:raise ValueError('EMPTY_CURVE')
    prev=-1;peak=start;drawdown=0.0
    for v in curve:
        tm=v.get('time_ms')
        if type(tm)!=int or tm<=prev:raise ValueError('BAD_EQUITY_CLOCK')
        prev=tm;equity=number(v['equity_usd'],'EQUITY')
        if equity<0:raise ValueError('NEGATIVE_EQUITY')
        peak=max(peak,equity);drawdown=min(drawdown,equity/peak-1)
    ending=number(curve[-1]['equity_usd'],'END_EQUITY')
    if not math.isclose(ending,number(p['final_virtual_equity_usd'],'REPORTED_EQUITY'),abs_tol=1.5e-7) or not math.isclose(ending-start,number(p['virtual_net_usd'],'REPORTED_NET'),abs_tol=1.5e-7):raise ValueError('END_EQUITY_MISMATCH')
    if not math.isclose(drawdown*100,number(p['max_drawdown_pct'],'DRAWDOWN'),abs_tol=1.5e-6):raise ValueError('DRAWDOWN_MISMATCH')
    realized=sum(r['net_usd'] for r in roundtrips)
    unrealized_or_mark=ending-cash
    unpaired=ending-start-realized
    return {'policy':p['policy'],'selected_rule':p.get('selected_rule'),'gate_pass':p['evidence_gate_pass'],'independent_holdout_claim':False,
            'initial_usd':start,'ending_equity_usd':round(ending,8),'virtual_net_usd':round(ending-start,8),
            'simulated_realized_pnl_usd':round(realized,8),'simulated_open_position_contribution_usd':round(unpaired,8),
            'ending_cash_usd':round(cash,8),'ending_position_mark_usd':round(unrealized_or_mark,8),
            'explicit_fill_fees_usd':round(cost,8),'filled_turnover_usd':round(turnover,8),
            'entries':entries,'exits':exits,'paired_trades':roundtrips,'max_drawdown_pct':round(drawdown*100,8),
            'account_ledger_verified':True,'warning':'Simulated event fills, not executable trades; price movement already contains modeled entry/exit slippage.'}

def analyze(gate,shadow,stress):
    reports=[audit_one(x) for x in (gate,shadow,stress)]
    for a,b in ((reports[0],reports[1]),(reports[1],reports[2])):
        if not math.isclose(a['initial_usd'],b['initial_usd']):raise ValueError('DIFFERENT_INITIAL_CAPITAL')
    if [r['policy'] for r in reports]!=['gate','shadow','shadow']:raise ValueError('WRONG_REPORT_MODES')
    s0=shadow['portfolio']['cost_assumptions'];s1=stress['portfolio']['cost_assumptions']
    if number(s1['extra_roundtrip_bps'],'STRESS_COST')<=number(s0['extra_roundtrip_bps'],'BASE_COST'):raise ValueError('STRESS_NOT_HIGHER')
    if s0['fee_bps_per_side']!=s1['fee_bps_per_side'] or s0['slippage_bps_per_side']!=s1['slippage_bps_per_side']:raise ValueError('BASE_COSTS_CHANGED')
    if shadow.get('sources_sha256')!=stress.get('sources_sha256') or gate.get('sources_sha256')!=shadow.get('sources_sha256'):raise ValueError('DATA_SOURCE_MISMATCH')
    comparisons={'base_to_stress_virtual_equity_change_usd':round(reports[2]['ending_equity_usd']-reports[1]['ending_equity_usd'],8),
      'base_to_stress_simulated_explicit_fees_change_usd':round(reports[2]['explicit_fill_fees_usd']-reports[1]['explicit_fill_fees_usd'],8),
      'same_entry_count':reports[1]['entries']==reports[2]['entries'],
      'same_fill_schedule':[(t['side'],t['symbol'],t['time_ms']) for t in shadow['portfolio']['trades']]==[(t['side'],t['symbol'],t['time_ms']) for t in stress['portfolio']['trades']],
      'warning':'Equity difference includes cash path, compounding, and possible schedule effects. It must not be described as fees alone.'}
    return {'version':'CQWE_V25_ACCOUNT_FORENSICS','research_only':True,'no_orders':True,'independent_holdout_claim':False,
      'reports':dict(zip(('gate','shadow','shadow_stress'),reports)),'comparison':comparisons,
      'decision':'NO_LIVE_PROMOTION','why':'Historic candidate failed unified cash account; research replay is not a new independent holdout.'}

def run(gate_path,shadow_path,stress_path,output):
    paths=[Path(x) for x in (gate_path,shadow_path,stress_path)]
    raws=[x.read_bytes() for x in paths]
    result=analyze(*[json.loads(r.decode('utf-8-sig')) for r in raws])
    result['input_sha256']=dict(zip(('gate','shadow','shadow_stress'),[hashlib.sha256(r).hexdigest() for r in raws]))
    result['audit_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True);tmp=out.with_name(out.name+'.tmp')
    tmp.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(out)
    return result

def main():
    a=argparse.ArgumentParser(description='V25 verification of V24 historical simulated-account evidence')
    a.add_argument('--gate',required=True);a.add_argument('--shadow',required=True);a.add_argument('--stress',required=True)
    a.add_argument('--output',default='reports/v25_forensics.json');args=a.parse_args()
    x=run(args.gate,args.shadow,args.stress,args.output)
    for key,p in x['reports'].items():print(key,'entries=',p['entries'],'net=',p['virtual_net_usd'],'fees=',p['explicit_fill_fees_usd'],'maxDD=',p['max_drawdown_pct'])
    print('CQWE_V25_ACCOUNT_AUDIT_PASS | RESEARCH ONLY | NO ORDERS | NO PROFIT CLAIM')
if __name__=='__main__':main()
