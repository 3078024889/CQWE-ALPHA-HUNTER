"""V57 commercial funnel: demand and conversion evidence, no invented orders."""
from .cash_truth_v56 import money

def funnel(leads, orders):
    if not isinstance(leads,list) or not isinstance(orders,list): raise ValueError('BAD_FUNNEL')
    lid=set(); oid=set(); qualified=0
    for l in leads:
        if not isinstance(l,dict) or set(l)!={'id','segment','pain','source_url','observed_at'}: raise ValueError('BAD_LEAD')
        if not all(isinstance(l[k],str) and l[k].strip() for k in l): raise ValueError('EMPTY_LEAD_EVIDENCE')
        if l['id'] in lid: raise ValueError('DUPLICATE_LEAD')
        lid.add(l['id']); qualified+=1
    paid=0
    for o in orders:
        if not isinstance(o,dict) or set(o)!={'id','lead_id','price_usd','payment_event_id'}: raise ValueError('BAD_ORDER')
        if o['id'] in oid or o['lead_id'] not in lid: raise ValueError('UNTRACEABLE_ORDER')
        oid.add(o['id'])
        if money(o['price_usd'])<=0: raise ValueError('BAD_PRICE')
        if not isinstance(o['payment_event_id'],str) or not o['payment_event_id']: raise ValueError('ORDER_MISSING_PAYMENT_PROOF')
        paid+=1
    return {'qualified_leads':qualified,'claimed_paid_orders':paid,'cash_confirmation':'REQUIRES_SEPARATE_VERIFIED_LEDGER','conversion_rate_observed':(paid/qualified if qualified else None)}
