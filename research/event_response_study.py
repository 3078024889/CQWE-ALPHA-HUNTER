"""Join explicitly supplied release records to public minute candles. No orders."""
import argparse
import json
from pathlib import Path

from cqwe.historical_curriculum import public
from cqwe.local_autopilot import atomic
from cqwe.macro_events import responses
from cqwe.four_market_core import SYMBOLS
from cqwe.event_catalog import identity


def collect(events,target):
    if not isinstance(events,list) or not 1<=len(events)<=100:
        raise ValueError('EVENT_STUDY_BUDGET')
    target=Path(target);target.mkdir(parents=True,exist_ok=False)
    now=public('time')['serverTime'];results=[]
    for index,e in enumerate(events):
        start=((e['scheduled_ms']+59999)//60000)*60000
        if start+3600000>now:
            raise ValueError('EVENT_RESPONSE_NOT_MATURE')
        for symbol in SYMBOLS:
            raw=public('klines',{'symbol':symbol,'interval':'1m','startTime':start,
                                'endTime':start+3600000-1,'limit':60})
            atomic(target/f'raw_{index:03d}_{symbol}.json',{'symbol':symbol,'raw':raw,
                   'source':'BINANCE_USDM_PUBLIC_KLINES','observed_ms':now})
            bars=[{'time':r[0],'open':float(r[1]),'close':float(r[4])} for r in raw
                  if isinstance(r,list) and len(r)==12 and r[6]<now]
            results.append(responses(e,symbol,bars))
    report={'schema':'CQWE_EVENT_RESPONSE_STUDY_V1','events':events,'results':results,
            'distinct_event_clusters':len({identity(e) for e in events}),
            'observed_ms':now,'real_orders':0,'profitability_proven':False,
            'automatic_narrative_feed_connected':False}
    atomic(target/'report.json',report)
    print(json.dumps({'target':str(target),'event_clusters':report['distinct_event_clusters'],
                      'responses':[{k:r[k] for k in ('symbol','responses')} for r in results]},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--events',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();collect(json.loads(Path(a.events).read_text(encoding='utf-8')),a.output)
