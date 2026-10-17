"""Point-in-time event features and grouped retrospective response labels.

No inferred market consensus, no revised values silently substituted for first
releases, and no claim that a candle response was executable at its opening price.
"""
import math
from .four_market_core import SYMBOLS
from .event_catalog import identity


def finite(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('EVENT_FINITE_NUMBER')
    return float(value)


def features(event,decision_ms):
    identity(event)
    if type(decision_ms) is not int or type(event['scheduled_ms']) is not int:
        raise ValueError('EVENT_TIME_REQUIRED')
    out={'event_id':event['event_id'],'family':event['family'],
         'minutes_to_release':(event['scheduled_ms']-decision_ms)/60000,
         'actual':None,'consensus':None,'surprise':None,'narratives':[],
         'directional_trade_authorized':False}
    def available(item):
        return (type(item.get('available_ms')) is int and type(item.get('first_seen_ms')) is int
                and 0<=item['available_ms']<=decision_ms and 0<=item['first_seen_ms']<=decision_ms
                and isinstance(item.get('source_sha256'),str) and len(item['source_sha256'])==64)
    actual=event.get('actual',{})
    consensus=event.get('consensus',{})
    if (decision_ms>=event['scheduled_ms'] and available(actual)
            and actual['available_ms']>=event['scheduled_ms'] and actual.get('first_release') is True):
        out['actual']=finite(actual['value'])
    if available(consensus) and consensus['available_ms']<event['scheduled_ms'] and consensus['first_seen_ms']<event['scheduled_ms']:
        out['consensus']=finite(consensus['value'])
    if out['actual'] is not None and out['consensus'] is not None:
        if actual.get('unit')==consensus.get('unit') and actual.get('series')==consensus.get('series'):
            out['surprise']=out['actual']-out['consensus']
    for item in event.get('narratives',[])[:100]:
        if available(item):
            out['narratives'].append({'text':str(item.get('text',''))[:4000],
                                     'source_sha256':item['source_sha256'],
                                     'untrusted_text':True})
    return out


def responses(event,symbol,minute_bars,horizons=(300,900,3600)):
    """Aligned announcement response labels, not simulated fills or independent trades."""
    if symbol not in SYMBOLS or any(h not in (300,900,3600) for h in horizons):
        raise ValueError('EVENT_RESPONSE_SCOPE')
    start=((event['scheduled_ms']+59999)//60000)*60000
    by_time={}
    for b in minute_bars:
        t=b['time'];o=finite(b['open']);c=finite(b['close'])
        if type(t) is not int or t%60000 or o<=0 or c<=0 or t in by_time:
            raise ValueError('EVENT_RESPONSE_BARS')
        by_time[t]=b
    rows=[]
    for h in horizons:
        times=range(start,start+h*1000,60000)
        if any(t not in by_time for t in times):
            rows.append({'horizon':h,'status':'MISSING_CANDLES'});continue
        first=by_time[start];last=by_time[start+h*1000-60000]
        move=(float(last['close'])/float(first['open'])-1)*10000
        rows.append({'horizon':h,'status':'OBSERVED','return_bps':move,
                     'label':1 if move>0 else -1 if move<0 else 0})
    return {'event_id':event['event_id'],'cluster_id':identity(event),'symbol':symbol,
            'anchor_ms':start,'responses':rows,'retrospective_event_study_only':True,
            'execution_costs_included':False,'independent_events':1,
            'pre_release_features':features(event,event['scheduled_ms']-1),
            'profitability_proven':False}
