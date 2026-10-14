"""CQWE V43: conservative MARKET-BY-PRICE paper execution only.

The anonymous spot L2 book cannot reveal individual queue priority or exact cancel
attribution. Scenarios are research assumptions, never fills/real PnL.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from decimal import Decimal
from pathlib import Path

D = lambda x: Decimal(str(x))

def hash_record(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def read_chain(file):
    """Verify sequential append-only hash chain, disallow mixed capture sessions."""
    prev='0'*64; records=[];last_seq=0;last_clock=0;session=None
    with Path(file).open(encoding='utf8') as stream:
      for lineno,line in enumerate(stream,1):
          if not line.strip():continue
          rec=json.loads(line)
          if rec.get('schema')!='CQWE_V43_CAPTURE' or rec.get('prev_sha256')!=prev or rec.get('sequence')!=last_seq+1:
              raise ValueError(f'BROKEN_CAPTURE_CHAIN_LINE_{lineno}')
          signed={k:v for k,v in rec.items() if k!='sha256'}
          if rec.get('sha256')!=hash_record(signed):raise ValueError(f'CAPTURE_HASH_MISMATCH_LINE_{lineno}')
          if not isinstance(rec.get('received_ns'),int) or rec['received_ns']<last_clock:
              raise ValueError('NONMONOTONIC_LOCAL_CLOCK')
          if session is None:session=rec.get('session_id')
          elif session!=rec.get('session_id'):raise ValueError('MIXED_SESSION')
          prev=rec['sha256'];last_seq=rec['sequence'];last_clock=rec['received_ns'];records.append(rec)
    return records

def evaluate(records, latency_ms=250, fee_bps=10, slippage_bps=2, target_usd=5, horizon_ms=60000):
    """Non-executable, conservative causal decision and queue proxy.

    Decision at first fully synchronized BOOK record, order arrival AFTER simulated
    latency. Marketable entry uses future ASK; exits future BID. No fills at past
    quotes; no fill if future bid/ask absent or displayed size too small.
    A passive alternative is quantified but never granted a fill for depth decrease.
    """
    if any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in
           (latency_ms,fee_bps,slippage_bps,target_usd,horizon_ms)):
        raise ValueError('BAD_SIMULATION_PARAMS')
    if fee_bps>100 or slippage_bps>100 or target_usd<5 or horizon_ms<1000:raise ValueError('BAD_SIMULATION_PARAMS')
    books=[r for r in records if r.get('kind')=='BOOK' and r['payload'].get('synced') is True]
    trades=[r for r in records if r.get('kind')=='TRADE']
    if not books:return {'status':'NO_SYNCED_BOOK','hypothetical_fills':0,'executable_profit_proven':False}
    entry_ref=books[0];t0=entry_ref['received_ns'];arrival=t0+int(latency_ms*1e6)
    eligible=[r for r in books[1:] if r['received_ns']>=arrival]
    if not eligible:return {'status':'NO_POST_LATENCY_BOOK','hypothetical_fills':0,'executable_profit_proven':False}
    entry=eligible[0]
    target_close=entry['received_ns']+int(horizon_ms*1e6)
    exits=[r for r in books if r['received_ns']>=target_close]
    if not exits:return {'status':'NO_FUTURE_EXIT_BOOK','hypothetical_fills':0,'executable_profit_proven':False}
    exit_=exits[0]
    buy=D(entry['payload']['ask']);sell=D(exit_['payload']['bid']);buy_size=D(entry['payload']['ask_qty']);sell_size=D(exit_['payload']['bid_qty'])
    if min(buy,sell,buy_size,sell_size)<=0 or buy<=D(entry['payload']['bid']) or sell>=D(exit_['payload']['ask']):raise ValueError('UNTRUSTED_BOOK')
    qty=D(target_usd)/buy
    if buy_size<qty or sell_size<qty:
        return {'status':'INSUFFICIENT_DISPLAYED_LIQUIDITY','hypothetical_fills':0,'executable_profit_proven':False}
    # Even if public displayed quantity suffices, actual fills and fees are unknown.
    net=(sell/buy-1)*10000-D(2)*(D(fee_bps)+D(slippage_bps))
    maker_bid=D(entry_ref['payload']['bid']);ahead=D(entry_ref['payload']['bid_qty'])
    # Only seller-initiated prints AT bid can count as possible depletion of
    # displayed queue; cancels are not assumed to move our order.
    sells=sum((D(r['payload']['qty']) for r in trades if
         entry['received_ns']<=r['received_ns']<=exit_['received_ns'] and
         r['payload'].get('buyer_is_maker') is True and D(r['payload']['price'])==maker_bid),D(0))
    passive_possible=sells>=ahead+qty
    return {'status':'HYPOTHETICAL_QUOTE_CROSS','hypothetical_fills':2,'entry_received_ns':entry['received_ns'],
        'exit_received_ns':exit_['received_ns'],'entry_ask':str(buy),'exit_bid':str(sell),
        'quote_cross_net_bps':float(net),'fee_bps_per_side':fee_bps,'slippage_bps_per_side':slippage_bps,
        'queue_ahead_estimate':str(ahead),'seller_initiated_at_bid_qty':str(sells),
        'passive_queue_depletion_condition_met':passive_possible,
        'passive_actual_fill_known':False,'market_actual_fill_known':False,
        'executable_profit_proven':False,'real_profit_usd':0.0,
        'limitations':'Latency assumed; posted quantities may vanish; no maker queue position, actual fill, market impact or per-account fee.'}

def ten_stresses(records):
    cases=[('baseline',250,10,2),('network_500ms',500,10,2),('network_1000ms',1000,10,2),
      ('network_2000ms',2000,10,2),('fee_20bps',250,20,2),('fee_40bps',250,40,2),
      ('slippage_10bps',250,10,10),('slippage_20bps',250,10,20),
      ('combined_stress',1500,30,20),('severe_stress',3000,40,30)]
    out=[{'scenario':name,**evaluate(records,delay,fee,slip)} for name,delay,fee,slip in cases]
    return {'stress_count':10,'scenario_results':out,'all_positive_and_executable':False,'real_profit_usd':0.0}

def main():
    p=argparse.ArgumentParser();p.add_argument('--file',required=True);args=p.parse_args()
    records=read_chain(args.file)
    print('CQWE_V43_REPLAY '+json.dumps({'records':len(records),'result':ten_stresses(records)},sort_keys=True))
    print('HYPOTHETICAL ONLY | NO REAL ORDERS | NO FILL CLAIM | NO PROFIT PROMOTION')
if __name__=='__main__':main()
