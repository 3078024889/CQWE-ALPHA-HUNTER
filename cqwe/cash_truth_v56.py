"""V56 evidence-gated cash accounting. No account or network access."""
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import hashlib, json

def money(value):
    if isinstance(value,(bool,float)): raise ValueError('NON_DECIMAL_MONEY')
    try: d=Decimal(str(value))
    except (InvalidOperation,ValueError): raise ValueError('INVALID_MONEY')
    if not d.is_finite() or d.as_tuple().exponent < -2: raise ValueError('INVALID_MONEY')
    return d

def ledger(events, starting='10.00'):
    start=money(starting)
    if start != Decimal('10'): raise ValueError('STARTING_CAPITAL_MUST_BE_10')
    balance=start; revenues=Decimal('0'); costs=Decimal('0'); ids=set(); previous='0'*64
    entries=[]
    for e in events:
        if not isinstance(e,dict) or set(e)!={'id','timestamp','type','amount','evidence_sha256','verified'}: raise ValueError('BAD_EVENT')
        if not isinstance(e['id'],str) or not e['id'] or e['id'] in ids: raise ValueError('DUPLICATE_EVENT')
        ids.add(e['id'])
        if e['type'] not in ('receipt','expense'): raise ValueError('UNSUPPORTED_TYPE')
        amt=money(e['amount'])
        if amt <= 0: raise ValueError('NON_POSITIVE_AMOUNT')
        if e['verified'] is not True: raise ValueError('UNVERIFIED_EVIDENCE')
        proof=e['evidence_sha256']
        if not isinstance(proof,str) or len(proof)!=64 or any(c not in '0123456789abcdef' for c in proof): raise ValueError('MISSING_EVIDENCE')
        try:
            dt=datetime.fromisoformat(e['timestamp'])
            if dt.tzinfo is None: raise ValueError()
        except (TypeError,ValueError): raise ValueError('INVALID_TIMESTAMP')
        if e['type']=='receipt': balance+=amt; revenues+=amt
        else:
            if amt>balance: raise ValueError('INSUFFICIENT_CASH')
            balance-=amt; costs+=amt
        encoded=json.dumps(e,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        previous=hashlib.sha256((previous+encoded).encode()).hexdigest()
        entries.append({'event_id':e['id'],'chain_sha256':previous})
    profit=revenues-costs
    return {'initial_usd':'10.00','revenue_usd':str(revenues.quantize(Decimal('.01'))),'cost_usd':str(costs.quantize(Decimal('.01'))),'cash_usd':str(balance.quantize(Decimal('.01'))),'net_profit_usd':str(profit.quantize(Decimal('.01'))),'goal_remaining_usd':str(max(Decimal(0),Decimal(1000)-profit).quantize(Decimal('.01'))),'verified_events':len(entries),'audit_chain':previous,'entries':entries}
