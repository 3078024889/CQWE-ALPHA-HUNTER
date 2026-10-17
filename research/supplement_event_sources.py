"""Extend calendars without replacing the previously published historical study."""
import datetime as dt
import json
import re
import time
from pathlib import Path

from research.history_sources import fetch, ROOT
from research import build_event_history as builder


def ism_rows(text):
    # Explicit official table only: no inferred business-day schedules.
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', text, re.S | re.I):
        cells=[builder.plain(c).strip() for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>',row,re.S|re.I)]
        if len(cells)!=3:continue
        try:month=dt.datetime.strptime(cells[0],'%B %Y')
        except ValueError:continue
        for name,cell in zip(('US_ISM_MANUFACTURING','US_ISM_SERVICES'),cells[1:]):
            day=re.match(r'^(\d{1,2})\b',cell)
            if day:
                yield name,month.replace(day=int(day[1])).strftime('%Y-%m-%d')


def run():
    status=[]
    for rid in (13,27,97,95):
        for year in (2024,2025,2026):
            status.append(fetch((f'fred_{rid}_{year}',f'https://fred.stlouisfed.org/releases/calendar?rid={rid}&y={year}')))
            time.sleep(.15)
    url='https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/'
    status.append(fetch(('ism_calendar',url)))
    target=Path('reports/event_history_expanded_catalog_20261016.json')
    data=builder.build(target)
    path=ROOT/'ism_calendar.html'
    if path.exists():
        for kind,day in ism_rows(path.read_text(encoding='utf-8')):
            builder.add(kind,'EMPLOYMENT_GROWTH',day,'10:00','America/New_York',url,path,
                        status='OFFICIAL_CALENDAR_EASTERN_WALL_TIME_NOT_ACTUAL_RELEASE_CONFIRMATION')
    else:
        path=ROOT/'ism_calendar_verified.json'
        if path.exists():
            table=json.loads(path.read_text(encoding='utf-8'))
            for month,mfg,svc in table['rows']:
                for kind,day in (('US_ISM_MANUFACTURING',mfg),('US_ISM_SERVICES',svc)):
                    builder.add(kind,'EMPLOYMENT_GROWTH',f"{table['year']}-{month:02d}-{day:02d}",
                                '10:00','America/New_York',url,path,
                                status='WEB_EXTRACTED_OFFICIAL_CALENDAR_EASTERN_TIME_ASSUMPTION')
    data['events']=sorted(builder.events.values(),key=lambda e:(e['scheduled_ms'],e['event_id']))
    for e in data['events']:e['cluster_id']='TIME_'+str(e['scheduled_ms'])
    for e in data['events']:
        if e['event_type'] in ('US_RESIDENTIAL_CONSTRUCTION','US_M3_ORDERS'):
            e['release_stage']='UNRESOLVED_INITIAL_OR_REVISION'
            e['title']+='; calendar release family may include advance/final/revision releases'
    data['counts']={k:sum(e['event_type']==k for e in data['events']) for k in sorted({e['event_type'] for e in data['events']})}
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    old=json.loads(Path('reports/event_history_catalog_20261016.json').read_text(encoding='utf-8'))
    ids={e['event_id'] for e in old['events']}
    extra={**data,'events':[e for e in data['events'] if e['event_id'] not in ids]}
    extra['counts']={k:sum(e['event_type']==k for e in extra['events']) for k in sorted({e['event_type'] for e in extra['events']})}
    Path('reports/event_history_supplement_catalog_20261016.json').write_text(json.dumps(extra,ensure_ascii=False,indent=2),encoding='utf-8')
    Path('reports/event_sources_20261016/supplement_fetch_status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    print(json.dumps({'total':len(data['events']),'added':len(extra['events']),'counts':data['counts'],'fetch_status':status}),flush=True)


if __name__=='__main__':run()
