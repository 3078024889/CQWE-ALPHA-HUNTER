"""Separate future calendar snapshot: retain historical studies byte-for-byte."""
import datetime as dt
import json
from pathlib import Path

from cqwe.local_autopilot import atomic
from research import build_event_history as builder


def main():
    start,end=builder.START,builder.END
    now=dt.datetime.now(dt.timezone.utc)
    try:
        builder.START=now;builder.END=now+dt.timedelta(days=60)
        builder.build(Path('reports/upcoming_expanded_calendar_20261016.json'))
        path=builder.ROOT/'ism_calendar_verified.json'
        table=json.loads(path.read_text(encoding='utf-8'))
        for month,mfg,svc in table['rows']:
            for kind,day in (('US_ISM_MANUFACTURING',mfg),('US_ISM_SERVICES',svc)):
                builder.add(kind,'EMPLOYMENT_GROWTH',f"{table['year']}-{month:02d}-{day:02d}",
                    '10:00','America/New_York',table['source_url'],path,
                    status='WEB_EXTRACTED_OFFICIAL_CALENDAR_EASTERN_TIME_NOT_CONFIRMED_ACTUAL')
        rows=sorted(builder.events.values(),key=lambda e:(e['scheduled_ms'],e['event_id']))
        for e in rows:e['cluster_id']='TIME_'+str(e['scheduled_ms'])
        report={'asof_ms':int(now.timestamp()*1000),'window_days':60,'events':rows,
                'calendar_complete':False,'actual_consensus_complete':False,'real_orders':0,
                'unknown_release_stage':'FRED construction and M3 calendars can include revisions/updates',
                'source_status':'SAVED_CALENDARS_NOT_CONTINUOUSLY_REFRESHED'}
        atomic(Path('reports/macro_watch_plan_expanded_20261016.json'),report)
        print(json.dumps({'future_events':len(rows),'types':sorted({e['event_type'] for e in rows})}))
    finally:builder.START=start;builder.END=end


if __name__=='__main__':main()
