"""CQWE V3.3 cash-only, deterministic, append-only observational account.

Every intended action is recorded before the chosen *future* paper execution bar
opens. It is only priced when that bar has closed, so NO intrabar/real fills.
The frozen V31 expert is advisory; no autonomous model promotion or live API.
"""
from __future__ import annotations
import argparse, json, math, time
from pathlib import Path
from .public_data_v29 import SYMBOLS, PERIOD, _digest
from .rolling_signal_v31 import market_snapshot, _load_checked, _score, _read, _write_new, _verify

VERSION='CQWE_V33_CASH_ONLY_FULL_EXIT'
CASH0=10.0
MIN_NOTIONAL=5.0
FEE_BPS=5.0
SLIPPAGE_BPS=2.0
MAX_ALLOC=0.60
MAX_RISK_FRACTION=0.02
STOP_PCT=0.008
TARGET_PCT=0.016
TRAIL_ACTIVATE_PCT=0.010
TRAIL_DISTANCE_PCT=0.005
MAX_HOLD_BARS=12
MAX_ADDS=1


def _safe(v):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
        raise ValueError('NONFINITE_ACCOUNT_VALUE')
    return float(v)


def _hashrec(rec):return _digest({k:v for k,v in rec.items() if k!='record_sha256'})

def _verify_frame(rec):
    if rec.get('record_sha256')!=_hashrec(rec):raise ValueError('FRAME_HASH_MISMATCH')
    if rec.get('version')!=VERSION or not rec.get('no_real_orders'):raise ValueError('BAD_FRAME_VERSION')
    state=rec['state']; cash=_safe(state['cash']);qty=_safe(state['qty']);equity=_safe(state['equity']);peak=_safe(state['peak_equity'])
    if cash< -1e-8 or qty< -1e-10 or equity< -1e-8 or peak< -1e-8:raise ValueError('INVALID_ACCOUNT_BALANCE')
    if (qty>1e-10)!=bool(state['symbol']):raise ValueError('BAD_INVENTORY')
    if state['adds']>MAX_ADDS or state['adds']<0:raise ValueError('BAD_ADD_COUNT')
    p=rec.get('pending')
    if p and (p['action'] not in ('BUY','SELL','ADD') or p['execution_open_ms'] not in (rec['last_open_ms']+PERIOD,rec['last_open_ms']+2*PERIOD)):
        raise ValueError('INVALID_PENDING_ORDER')
    if abs(equity-(cash+qty*rec['market_close_for_position']))>1e-7:raise ValueError('EQUITY_NOT_BALANCED')


def _check_existing(root, last_open, context):
    files=sorted(root.glob('frame_*.json'),key=lambda p:int(p.stem.split('_')[1]))
    previous=None
    for file in files:
        rec=_read(file);_verify_frame(rec)
        if file.name!=f"frame_{rec['last_open_ms']}.json":raise ValueError('FRAME_FILENAME_MISMATCH')
        if rec['context_sha256']!=context:raise ValueError('FROZEN_CONTEXT_CHANGED')
        if previous:
            if rec['last_open_ms']!=previous['last_open_ms']+PERIOD:raise ValueError('GAP_IN_JOURNAL')
            if rec['previous_sha256']!=previous['record_sha256']:raise ValueError('JOURNAL_CHAIN_BROKEN')
        elif rec['previous_sha256'] is not None:raise ValueError('JOURNAL_GENESIS_INVALID')
        previous=rec
    if previous and previous['last_open_ms']>last_open:raise ValueError('CLOCK_ROLLBACK')
    return previous


def _starting_state():
    return dict(cash=CASH0,symbol=None,qty=0.0,avg_entry=0.0,entry_bar=None,peak_price=0.0,
                stop_price=0.0,adds=0,realized=0.0,fees=0.0,
                equity=CASH0,peak_equity=CASH0,max_drawdown_pct=0.0,closed_positions=0,
                skipped_actions=0,loss_memory=[])


def _cost(action, qty, open_price):
    px=open_price*(1+SLIPPAGE_BPS/10000 if action in ('BUY','ADD') else 1-SLIPPAGE_BPS/10000)
    nominal=qty*px;fee=nominal*FEE_BPS/10000
    return px,nominal,fee


def _fill(state,pending,bar,events):
    action=pending['action'];symbol=pending['symbol'];o=_safe(bar[1]);
    if o<=0:raise ValueError('BAD_OPEN_PRICE')
    if action in ('BUY','ADD'):
        if state['symbol'] is not None and (action!='ADD' or state['symbol']!=symbol):raise ValueError('BUY_WHILE_OCCUPIED')
        # No real orders. Nominal cash, min-order checks and paper fills only.
        budget=min(_safe(pending['budget_usd']),state['cash'])
        px=o*(1+SLIPPAGE_BPS/10000)
        gross=budget/(1+FEE_BPS/10000)
        if gross<MIN_NOTIONAL:
            state['skipped_actions']+=1;events.append({'action':'REJECT_MIN_NOTIONAL','symbol':symbol,'amount':gross});return
        qty=gross/px;fee=gross*FEE_BPS/10000
        if state['symbol'] is None:
            state.update(symbol=symbol,qty=qty,avg_entry=px,entry_bar=int(bar[0]),peak_price=o,
                         stop_price=px*(1-STOP_PCT),adds=0)
        else:
            previous=state['qty'];state['avg_entry']=(previous*state['avg_entry']+gross)/(previous+qty)
            state['qty']+=qty;state['adds']+=1
            state['stop_price']=max(state['stop_price'],state['avg_entry']*(1-STOP_PCT))
        state['cash']-=gross+fee;state['fees']+=fee
        events.append({'action':action,'symbol':symbol,'time_ms':int(bar[0]),'qty':qty,'price':px,
                       'gross_usd':gross,'fee_usd':fee,'cash_after':state['cash'],'hypothetical':True})
    else:
        if action!='SELL':raise ValueError('UNKNOWN_OR_PARTIAL_ACTION_DISABLED')
        if state['symbol']!=symbol or state['qty']<=0:raise ValueError('SELL_WITHOUT_POSITION')
        px=o*(1-SLIPPAGE_BPS/10000)
        qty=state['qty']
        gross=qty*px
        fee=gross*FEE_BPS/10000
        pnl=gross-fee-qty*state['avg_entry']
        state['cash']+=gross-fee;state['qty']-=qty;state['fees']+=fee;state['realized']+=pnl
        events.append({'action':action,'symbol':symbol,'time_ms':int(bar[0]),'qty':qty,'price':px,
                       'gross_usd':gross,'fee_usd':fee,'realized_basis_pnl_usd':pnl,
                       'cash_after':state['cash'],'hypothetical':True})
        state['closed_positions']+=1
        state['loss_memory'].append({'exit_ms':int(bar[0]),'cause':pending['reason'],
                                     'exit_basis_pnl_usd':pnl,'negative':pnl<0})
        state.update(symbol=None,qty=0.0,avg_entry=0.0,entry_bar=None,peak_price=0.0,
                     stop_price=0.0,adds=0)


def _intent(state,decision,last_open,markets):
    if state['symbol']:
        s=state['symbol'];bar=markets[s][-1];close=_safe(bar[4]);state['peak_price']=max(state['peak_price'],_safe(bar[2]))
        if state['peak_price']>=state['avg_entry']*(1+TRAIL_ACTIVATE_PCT):
            state['stop_price']=max(state['stop_price'],state['peak_price']*(1-TRAIL_DISTANCE_PCT))
        duration=(last_open-state['entry_bar'])//PERIOD
        reason=None
        if close<=state['stop_price']:reason='STOP_OR_TRAIL_CLOSE_CONFIRMED'
        elif close>=state['avg_entry']*(1+TARGET_PCT):reason='TARGET_CLOSE_CONFIRMED'
        elif duration>=MAX_HOLD_BARS:reason='TIME_LIMIT'
        elif decision.get('symbol')!=s:reason='FROZEN_SIGNAL_INVALIDATED'
        if reason:
            return {'action':'SELL','symbol':s,'execution_open_ms':last_open+2*PERIOD,'reason':reason}
        if (decision.get('symbol')==s and decision.get('expert') in ('trend_volume','breakout') and state['adds']<MAX_ADDS
            and close>=state['avg_entry']*(1+STOP_PCT) and state['cash']>=MIN_NOTIONAL*1.001):
            budget=min(state['cash']*.60,state['cash'])
            if budget/(1+FEE_BPS/10000)>=MIN_NOTIONAL:
                return {'action':'ADD','symbol':s,'budget_usd':budget,
                        'execution_open_ms':last_open+2*PERIOD,'reason':'TREND_CONFIRMED_RISK_BOUNDED'}
        return None
    if decision.get('intent')!='PAPER_BUY_CANDIDATE_NOT_ORDER':return None
    # Max planned dollar risk on fixed stop, no borrowing.
    budget=min(state['cash']*MAX_ALLOC, state['equity']*MAX_RISK_FRACTION/STOP_PCT)
    if budget/(1+FEE_BPS/10000)<MIN_NOTIONAL:return None
    return {'action':'BUY','symbol':decision['symbol'],'budget_usd':budget,
            'execution_open_ms':last_open+2*PERIOD,'reason':'FROZEN_EXPERT_ENTRY'}


def cycle(store,registry,output_dir,*,fetch=None,now_ms=None,threshold=0.12):
    from .rolling_signal_v31 import fetch_public
    if threshold not in (0.10,0.12,0.20):raise ValueError('UNREGISTERED_THRESHOLD')
    _,registry_sha,checkpoint,weights,_=_load_checked(registry,store)
    if now_ms is None:now_ms=time.time_ns()//1_000_000
    last_open,markets=market_snapshot(fetch=fetch or fetch_public,now_ms=now_ms)
    if last_open<=checkpoint['last_seen_ms']:raise ValueError('HISTORICAL_REPLAY_REFUSED')
    context=_digest({'tip':checkpoint['tip_sha256'],'registry':registry_sha,'threshold':threshold,'v':'33'})
    root=Path(output_dir);root.mkdir(parents=True,exist_ok=True)
    previous=_check_existing(root,last_open,context)
    if previous and previous['last_open_ms']==last_open:
        return {'status':'ALREADY_RECORDED','last_open_ms':last_open,'equity_usd':previous['state']['equity'],
                'pending':previous['pending'],'no_orders':True}
    if previous and last_open!=previous['last_open_ms']+PERIOD:
        raise ValueError('MISSED_BARS_FAIL_CLOSED_NO_RETROSPECTIVE_FILLS')
    state=json.loads(json.dumps(previous['state'])) if previous else _starting_state()
    events=[];pending=None
    if previous and previous.get('pending'):
        old=previous['pending'];target=old['execution_open_ms']
        if target==last_open:
            _fill(state,old,markets[old['symbol']][-1],events)
        elif target>last_open:pending=old
        else:raise ValueError('MISSED_PENDING_EXECUTION')
    # Existing inventory marked at current close; no fabricated liquidation.
    posclose=_safe(markets[state['symbol']][-1][4]) if state['symbol'] else 0.0
    state['equity']=state['cash']+state['qty']*posclose
    state['peak_equity']=max(state['peak_equity'],state['equity'])
    state['max_drawdown_pct']=min(state['max_drawdown_pct'],100*(state['equity']/state['peak_equity']-1))
    decision=_score(markets,weights,threshold)
    # Do not stage new intent while a future execution is already pending.
    if pending is None:pending=_intent(state,decision,last_open,markets)
    recorded_at_ms=now_ms
    # Fail closed if the current bar has not finished; captured snapshot enforces it.
    if recorded_at_ms < last_open+PERIOD:raise ValueError('BAR_NOT_CLOSED')
    # Must register intent before target candle opens (one full bar of lead time).
    if recorded_at_ms>=last_open+2*PERIOD:raise ValueError('INTENT_REGISTRATION_TOO_LATE')
    record={'version':VERSION,'research_only':True,'no_real_orders':True,'no_autopromotion':True,
            'real_exchange_order_api':False,'model_weights_frozen':True,'last_open_ms':last_open,
            'recorded_at_ms':recorded_at_ms,'context_sha256':context,'previous_sha256':previous['record_sha256'] if previous else None,
            'pending':pending,'decision':decision,'state':state,'events':events,
            'market_close_for_position':posclose,'market_sources_sha256':_digest(markets),
            'execution_assumptions':{'fill':'future-bar-open-observed-after-close; NOT an actual execution',
              'fee_bps_per_side':FEE_BPS,'slippage_bps_per_side':SLIPPAGE_BPS,
              'research_min_notional_usd':MIN_NOTIONAL,'partial_exits_disabled':True,'exchange_filters_unverified':True,
              'stop_fill':'close-triggered; future bar open; gap/slippage possible'}}
    record['record_sha256']=_hashrec(record)
    _verify_frame(record)
    _write_new(root/f'frame_{last_open}.json',record)
    return {'status':'FRAME_RECORDED','last_open_ms':last_open,'equity_usd':round(state['equity'],8),
            'cash_usd':round(state['cash'],8),'position':state['symbol'],'events':events,'pending':pending,
            'max_drawdown_pct':round(state['max_drawdown_pct'],6),'no_orders':True}


def main():
    p=argparse.ArgumentParser(description='V3.3 non-trading 5-minute persistent $10 shadow account')
    p.add_argument('--store',default='reports/v21_evidence')
    p.add_argument('--registry',default='reports/v27_mutation_registry.json')
    p.add_argument('--output-dir',default='reports/v32_cash_account')
    a=p.parse_args();r=cycle(a.store,a.registry,a.output_dir)
    print('CQWE_V33_ACCOUNT_PASS '+json.dumps(r,sort_keys=True))
    print('CASH ONLY | PAPER INTENTS | NO EXCHANGE ORDERS | NO PROFIT CLAIM')
if __name__=='__main__':main()
