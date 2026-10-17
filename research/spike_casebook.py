"""Preserve abnormal candle evidence without inferring hidden maker intentions."""
import datetime as dt
import json
from pathlib import Path

from cqwe.four_market_runner import checked
from cqwe.local_autopilot import atomic


def build(root):
    root=Path(root)
    report=checked(json.loads((root/'impact_report.json').read_text(encoding='utf-8')))
    cases={}
    for path in report['result_files']:
        r=checked(json.loads(Path(path).read_text(encoding='utf-8')))
        t=r['anchor_ms'];symbol=r['symbol']
        candles=checked(json.loads((root/'candles'/f'{symbol}_{t}.json').read_text(encoding='utf-8')))
        for b in candles['raw']:
            o,h,l,c=map(float,b[1:5])
            if not (0<l<=min(o,c)<=max(o,c)<=h):raise ValueError('SPIKE_OHLC_INCONSISTENT')
            upper=(h-max(o,c))/o*10000;lower=(min(o,c)-l)/o*10000
            if max(upper,lower)<20:continue
            key=f'{symbol}:{b[0]}'
            if key not in cases:
                cases[key]={'symbol':symbol,'at_ms':b[0],
                    'utc':dt.datetime.fromtimestamp(b[0]/1000,dt.timezone.utc).isoformat(),
                    'upper_wick_bps':upper,'lower_wick_bps':lower,'volume':b[5],
                    'trades':b[8],'calendar_matches':[],
                    'causal_status':'UNRESOLVED','maker_identity_known':False,
                    'missing_evidence':['historical_orderbook','complete_liquidation_stream',
                                        'cross_venue_price_comparison','timestamped_news_confirmation']}
            match={'event_id':r['event_id'],'event_type':r['event_type'],
                   'seconds_from_scheduled_time':(b[0]-t)/1000,'timing_status':r['timing_status']}
            cases[key]['calendar_matches'].append(match)
    ordered=sorted(cases.values(),key=lambda c:max(c['upper_wick_bps'],c['lower_wick_bps']),reverse=True)
    atomic(root/'spike_casebook.json',{'scope':'ONLY_CANDLES_INSIDE_COLLECTED_EVENT_WINDOWS',
        'threshold_bps':20,'cases':ordered,'count':len(ordered),
        'same_time_is_not_causation':True,'profitability_proven':False})
    print(json.dumps({'cases':len(ordered),'report':str(root/'spike_casebook.json')}))


if __name__=='__main__':build('D:/CQWE_DATA/event_history_20261016')
