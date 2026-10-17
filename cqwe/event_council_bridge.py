"""Combine existing shadow council output and a forward-event research snapshot.

No unqualified event node can add directional weight. Calendar risk can veto a
proposed opening; exits stay controlled by the existing position exit rules.
"""
import argparse
import copy
import json
import math
from pathlib import Path

from .four_market_runner import checked
from .local_autopilot import atomic


def combine(book,event_state,now):
    result=copy.deepcopy(book)
    if result.get('execution_enabled') is not False:raise ValueError('SHADOW_COUNCIL_REQUIRED')
    if result.get('symbol') not in ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT'):raise ValueError('SYMBOL')
    at=result.get('at_ms')
    if type(at) is not int or not 0<=now-at<=10000:raise ValueError('STALE_ORDERBOOK_COUNCIL')
    nodes=result.setdefault('nodes',[])
    if any(n.get('id','').startswith('event:') for n in nodes):raise ValueError('ALREADY_COMBINED')
    fresh=(event_state and type(event_state.get('at_ms')) is int and 0<=now-event_state['at_ms']<=15000)
    if event_state and event_state.get('execution_enabled') is not False:raise ValueError('SHADOW_EVENT_REQUIRED')
    key=f"{result['symbol']}:{result['horizon']}"
    score=event_state.get('scores',{}).get(key,{}) if fresh else {}
    forecast=event_state.get('node_forecasts',{}).get(key,{}) if fresh else {}
    p=forecast.get('p_up') if forecast.get('at_ms',now+1)<=now<forecast.get('due_ms',0) else None
    n=score.get('n',0)
    nodes.append({'id':'event:forward','eligible':False,'weight':0.,'labels':n,
                  'p_up':p,'status':'FORWARD_COST_VALIDATION_REQUIRED' if fresh else 'MISSING_OR_STALE',
                  'brier':score.get('brier_sum',0)/n if n else None})
    result['event_context_fresh']=bool(fresh)
    result['event_weight']=0.
    result['event_risk_veto']=False
    opens=result.get('action') in ('OPEN_LONG','OPEN_SHORT')
    if opens and not fresh:
        result.update(action='WAIT',reason='EVENT_CONTEXT_MISSING_OR_STALE',event_risk_veto=True)
    if fresh:
        upcoming=[e for e in event_state.get('upcoming_30min',[]) if now<e['scheduled_ms']<=now+1800000]
        result['scheduled_events_next_30min']=upcoming
        if opens and upcoming:
            result.update(action='WAIT',reason='SCHEDULED_EVENT_WITHIN_30MIN',event_risk_veto=True)
    result.update(event_calendar_complete=False,paper_advisory_only=True,execution_enabled=False,
                  profitability_proven=False,real_orders=0)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--book-decision',required=True);p.add_argument('--event-state',required=True)
    p.add_argument('--output',required=True);p.add_argument('--now-ms',required=True,type=int)
    a=p.parse_args()
    book=json.loads(Path(a.book_decision).read_text(encoding='utf-8'))
    event=checked(json.loads(Path(a.event_state).read_text(encoding='utf-8')))
    result=combine(book,event,a.now_ms);atomic(Path(a.output),result)
    print(json.dumps(result))
