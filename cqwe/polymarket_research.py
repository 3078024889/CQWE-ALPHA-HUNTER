"""Public Polymarket discovery/books + pending forecasts, never wallet management.

Quotes are reference probabilities, not independent event information. Final
binary labels require a separate closed-market winner response after forecast.
"""
import argparse
import datetime
import json
import math
import re
import time
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal as D, ROUND_UP
from pathlib import Path

from .copernican_experiment_v81_v85 import digest
from .event_learning import EventJournal
from .tidal_hunter import write_new

HEX = re.compile(r'0x[0-9a-fA-F]{64}')


def public_get(kind, identifier=None):
    if kind == 'discovery':
        url = 'https://gamma-api.polymarket.com/markets/keyset?closed=false&limit=20'
    elif kind == 'book' and isinstance(identifier,str) and identifier.isdigit() and len(identifier)<=100:
        url = 'https://clob.polymarket.com/book?'+urllib.parse.urlencode({'token_id':identifier})
    elif kind == 'resolution' and isinstance(identifier,str) and HEX.fullmatch(identifier):
        url = 'https://clob.polymarket.com/markets/'+identifier
    else:
        raise ValueError('PUBLIC_ENDPOINT_NOT_ALLOWED')
    request = urllib.request.Request(url,headers={'User-Agent':'CQWE-research/1.0','Accept':'application/json'},method='GET')
    with urllib.request.urlopen(request,timeout=12) as r:
        raw = r.read(3_000_001)
    if len(raw)>3_000_000:
        raise ValueError('PUBLIC_RESPONSE_BUDGET')
    return json.loads(raw)


def decimal(value, lo=D(0), hi=None):
    if isinstance(value,bool):
        raise ValueError('INVALID_DECIMAL')
    v = D(str(value))
    if not v.is_finite() or v<lo or (hi is not None and v>hi):
        raise ValueError('INVALID_DECIMAL')
    return v


def binary_market(raw):
    if raw.get('active') is not True or raw.get('closed') is not False or raw.get('enableOrderBook') is not True:
        raise ValueError('MARKET_NOT_ACTIVE')
    if raw.get('negRisk') is not False:
        raise ValueError('NEG_RISK_NOT_SUPPORTED')
    if not HEX.fullmatch(str(raw.get('conditionId',''))):
        raise ValueError('INVALID_CONDITION_ID')
    def seq(v):
        return json.loads(v) if isinstance(v,str) else v
    outcomes,tokens = seq(raw['outcomes']),seq(raw['clobTokenIds'])
    if not isinstance(outcomes,list) or not isinstance(tokens,list) or len(outcomes)!=2 or len(tokens)!=2:
        raise ValueError('BINARY_MARKET_REQUIRED')
    names = [str(x).lower() for x in outcomes]
    if set(names)!={'yes','no'} or any(not isinstance(t,str) or not t.isdigit() or int(t)<=0 for t in tokens) or tokens[0]==tokens[1]:
        raise ValueError('INVALID_BINARY_TOKENS')
    return {'condition_id':raw['conditionId'],'yes':tokens[names.index('yes')],
            'no':tokens[names.index('no')],'category':str(raw.get('feeType') or 'unclassified')[:100],
            'question':str(raw.get('question','')),'description':str(raw.get('description','')),
            'resolution_source':raw.get('resolutionSource'),'end_date':raw.get('endDate')}


def parse_book(raw, *, token, condition):
    if str(raw.get('asset_id'))!=token or raw.get('market')!=condition:
        raise ValueError('BOOK_IDENTITY_MISMATCH')
    sides = {}
    for side in ('bids','asks'):
        if not isinstance(raw.get(side),list) or not raw[side]:
            raise ValueError('EMPTY_BOOK_SIDE')
        values = []
        for row in raw[side]:
            p,q = decimal(row['price'],hi=D(1)),decimal(row['size'])
            if not 0<p<1 or q<=0:
                raise ValueError('INVALID_BOOK_LEVEL')
            values.append((p,q))
        sides[side] = sorted(values,reverse=side=='bids')
    if sides['bids'][0][0]>=sides['asks'][0][0]:
        raise ValueError('CROSSED_BOOK')
    return sides


def fee_rate(raw):
    if raw.get('feesEnabled') is False:
        return D(0)
    schedule = raw.get('feeSchedule')
    if (raw.get('feesEnabled') is not True or not isinstance(schedule,dict)
            or type(schedule.get('exponent')) not in (float,int) or schedule['exponent']!=1
            or schedule.get('takerOnly') is not True):
        raise ValueError('UNKNOWN_FEE_SCHEDULE')
    return decimal(schedule['rate'],hi=D(1))


def ask_cost(book, shares, rate):
    left,gross,fee = shares,D(0),D(0)
    for p,q in book['asks']:
        amount = min(q,left)
        gross += amount*p
        fee += amount*rate*p*(1-p)
        left -= amount
        if not left:
            # Conservative fee rounding; actual match-time deductions unverified.
            return gross,fee.quantize(D('.00001'),rounding=ROUND_UP)
    raise ValueError('INSUFFICIENT_ASK_DEPTH')


def final_binary_outcome(raw, condition):
    if raw.get('condition_id')!=condition or raw.get('closed') is not True:
        return None
    tokens = raw.get('tokens')
    if not isinstance(tokens,list) or len(tokens)!=2:
        return None
    if {str(t.get('outcome','')).lower() for t in tokens}!={'yes','no'} or any(type(t.get('winner')) is not bool for t in tokens):
        return None
    winners = [t for t in tokens if t['winner']]
    if len(winners)!=1:
        return None
    return int(str(winners[0]['outcome']).lower()=='yes')


def collect(root, *, limit=3, fetch=public_get):
    if type(limit) is not int or not 1<=limit<=10:
        raise ValueError('EVENT_COLLECTION_BUDGET')
    root = Path(root)
    root.mkdir(parents=True,exist_ok=True)
    folder = root/('capture_'+str(time.time_ns())+'_'+uuid.uuid4().hex[:6])
    folder.mkdir()
    ledger = EventJournal(root/'event_forecasts.jsonl')
    raw = fetch('discovery')
    write_new(folder/'discovery.json',raw)
    markets = raw['markets'] if isinstance(raw,dict) else raw
    if not isinstance(markets,list):
        raise ValueError('INVALID_DISCOVERY_RESPONSE')
    results = []
    for item in markets:
        if len(results)>=limit:
            break
        try:
            m = binary_market(item)
        except (ValueError,KeyError,TypeError):
            continue
        prefix = str(len(results)+1)
        write_new(folder/(prefix+'.metadata.json'),item)
        result = {'condition_id':m['condition_id'],'question':m['question'],
                  'decision':'OBSERVE_ONLY','real_orders':0}
        try:
            yes,no = fetch('book',m['yes']),fetch('book',m['no'])
            write_new(folder/(prefix+'.yes_book.json'),yes)
            write_new(folder/(prefix+'.no_book.json'),no)
            yb,nb = parse_book(yes,token=m['yes'],condition=m['condition_id']),parse_book(no,token=m['no'],condition=m['condition_id'])
            now = time.time_ns()//1_000_000
            bid,ask = yb['bids'][0][0],yb['asks'][0][0]
            p0 = float((bid+ask)/2)
            bv,av = sum(q for _,q in yb['bids'][:5]),sum(q for _,q in yb['asks'][:5])
            end = datetime.datetime.fromisoformat(m['end_date'].replace('Z','+00:00'))
            if end.tzinfo is None:
                raise ValueError('END_DATE_TIMEZONE_REQUIRED')
            days = max(0.,(end.timestamp()*1000-now)/86400000)
            x = [1.,2*p0-1,float((bv-av)/(bv+av)),math.tanh(days/30)]
            evidence = digest({'metadata':item,'yes_book':yes,'no_book':no})
            learned,_,_ = ledger.load()
            if m['condition_id'] not in learned.forecasts:
                prediction = ledger.append('FORECAST',event_id=m['condition_id'],category=m['category'],
                         market_probability=p0,features=x,source_sha256=evidence,at_ms=now)
                result['forecast_recorded_now'] = True
            else:
                prediction = learned.forecasts[m['condition_id']]
                result['forecast_recorded_now'] = False
            result.update({'reference_probability':p0,'committed_forecast':prediction,
                           'independent_probability_edge_established':False,
                           'rule_sha256':digest(m['description']),'quote_times_ms':[yes.get('timestamp'),no.get('timestamp')],
                           'atomic_quotes_or_fills_verified':False})
            try:
                rate = fee_rate(item)
                shares = max(decimal(yes['min_order_size']),decimal(no['min_order_size']))
                yc,yf = ask_cost(yb,shares,rate)
                nc,nf = ask_cost(nb,shares,rate)
                result['complete_set_quote'] = {'shares':str(shares),'quoted_cost_with_estimated_fees':str(yc+yf+nc+nf),
                    'hypothetical_redemption_minus_cost':str(shares-yc-yf-nc-nf),
                    'fits_10_quote_units':yc+yf+nc+nf<=10,
                    'collateral_currency_verified':False,'executable_arbitrage_proven':False}
            except (ValueError,KeyError) as exc:
                result['cost_analysis_rejected'] = str(exc)
        except Exception as exc:
            result['error'] = type(exc).__name__+': '+str(exc)
            result['decision'] = 'REJECT_INCOMPLETE_DATA'
        results.append(result)
    learner,tip,_ = ledger.load()
    report = {'schema':'CQWE_POLYMARKET_RESEARCH_V1','markets':results,'event_learning':learner.summary(),
              'journal_tip_sha256':tip,'captured_ms':time.time_ns()//1_000_000,
              'real_orders':0,'realized_account_profit':None,'profitability_proven':False,
              'limitations':['Market-reference residuals are not an independent external-information model.',
                  'No resolution label is inferred from a market quote or end date.',
                  'Book snapshots are non-atomic; quote freshness and actual fees/fills unverified.',
                  'No wallet, signing key, redemption or order operation is implemented.']}
    report['sha256'] = digest(report)
    write_new(folder/'report.json',report)
    return folder,report


def settle(root, *, fetch=public_get):
    root = Path(root)
    ledger = EventJournal(root/'event_forecasts.jsonl')
    learner,_,_ = ledger.load()
    results = []
    for condition in [k for k in learner.forecasts if k not in learner.resolved][:20]:
        raw = fetch('resolution',condition)
        at_ms = time.time_ns()//1_000_000
        evidence = {'observed_at_ms':at_ms,'condition_id':condition,'public_response':raw}
        write_new(root/f'resolution_{condition}_{at_ms}.json',evidence)
        label = final_binary_outcome(raw,condition)
        if label is None:
            results.append({'condition_id':condition,'status':'PENDING_NO_FINAL_BINARY_LABEL'})
        else:
            row = ledger.append('RESOLVED',event_id=condition,outcome=label,source_sha256=digest(evidence),at_ms=at_ms)
            results.append({'condition_id':condition,'status':'RESOLVED_PUBLIC_API_LABEL','score':row['score']})
    current,_,_ = ledger.load()
    return {'results':results,'event_learning':current.summary(),'real_orders':0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='D:/CQWE_DATA/polymarket_research')
    p.add_argument('--limit',type=int,default=3)
    p.add_argument('--settle',action='store_true')
    a = p.parse_args()
    if a.settle:
        result = settle(a.root)
    else:
        folder,report = collect(a.root,limit=a.limit)
        result = {'folder':str(folder),'markets':len(report['markets']),
                  'event_learning':report['event_learning'],'real_orders':0}
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
