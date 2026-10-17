"""Observable-flow reversal exits with independent hard risk protection."""
from decimal import Decimal as D

POLICY='COPERNICAN_FLOW_EVENT_EXIT_V1'


def evaluate(position,bid,ask,at,decision=None):
    direction=D(position['direction']);px=bid if direction==1 else ask
    move=direction*(px/D(position['entry'])-1)*10000
    tracking=position.setdefault('exit_tracking',{})
    best=max(D(tracking.get('best_move_bps','0')),move)
    tracking.update(best_move_bps=str(best),current_move_bps=str(move),trailing_armed=best>=40)
    position['exit_policy']=POLICY
    if move<=-30:return 'STOP_LOSS'
    if best>=40 and best-move>=20:return 'TRAILING_PROFIT_EXIT'
    tracking['mechanism_status']='WAIT_FOR_FRESH_ORDERFLOW'
    if not decision or not 0<=at-decision.get('at_ms',0)<=10000:return None
    tracking['mechanism_status']=decision.get('reason','UNKNOWN')
    tracking['mechanism_hypotheses']=decision.get('mechanism_hypotheses',[])
    tracking['global_event_risk']=bool(decision.get('global_event_context',{}).get('entry_veto'))
    evidence=decision.get('market_evidence',{})
    opposite=any(h.get('direction')==-position['direction'] and h.get('confirmations',0)>=2
                 and h.get('strength',0)>=.45 for h in decision.get('mechanism_hypotheses',[]))
    if (decision.get('action')=='CLOSE' and decision.get('exit_basis')=='FLOW_LIQUIDITY_REVERSAL'
        and decision.get('mechanism_confirmations',0)>=2 and evidence.get('ready') and opposite
        and 0<=at-evidence.get('at_ms',-100000)<=15000):
        return 'FLOW_LIQUIDITY_REVERSAL'
    return None
