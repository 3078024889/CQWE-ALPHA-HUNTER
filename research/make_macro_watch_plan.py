"""Plan observations from known future calendars, not forecast unpublished releases."""
import datetime as dt
import json
from pathlib import Path

from cqwe.four_market_runner import checked
from cqwe.local_autopilot import atomic
from research import build_event_history as calendars


if __name__=='__main__':
    root=Path('D:/CQWE_DATA/event_history_20261016')
    impact=checked(json.loads((root/'impact_report.json').read_text(encoding='utf-8')))
    asof=dt.datetime.now(dt.timezone.utc)
    calendars.START=asof;calendars.END=asof+dt.timedelta(days=60)
    future=calendars.build('reports/upcoming_event_catalog_20261016.json')
    risk={}
    for s in impact['statistics']:
        if s['symbol']=='BTCUSDT' and s['horizon']==900:
            risk[s['event_type']]=s
    plans=[]
    for e in future['events']:
        s=risk.get(e['event_type']);high=s is not None and s['events']>=8 and s['median_abs_return_bps']>=30
        plans.append({'event_id':e['event_id'],'event_type':e['event_type'],'scheduled_ms':e['scheduled_ms'],
            'source_url':e['source_url'],'priority':'HIGH_VOLATILITY_WATCH' if high else 'WATCH_OR_INSUFFICIENT_HISTORY',
            'observation_start_ms':e['scheduled_ms']-1800000,'observation_end_ms':e['scheduled_ms']+3600000,
            'before_release':'REVIEW_SPREAD_DEPTH_AND_EXISTING_RISK',
            'after_release':'CAPTURE_ACTUAL_VALUE_AND_CHECK_ORDER_FLOW',
            'direction':'UNDECIDED','automated_orders':False,'risk_rule_is_advisory_only':True})
    out=Path('reports/macro_watch_plan_20261016.json')
    atomic(out,{'asof_ms':int(asof.timestamp()*1000),'window_days':60,'plans':plans,
        'risk_history_report_sha256':impact['sha256'],'calendar_coverage_complete':False,
        'live_strategy_connected':False,'real_orders':0})
    print(json.dumps({'plan':str(out),'events':len(plans),'next':plans[:3]}))
