"""Extract source-backed historical schedules; never invent an announcement time."""
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ROOT=Path('reports/event_sources_20261016')
START=dt.datetime(2024,10,16,tzinfo=dt.timezone.utc)
END=dt.datetime(2026,10,16,tzinfo=dt.timezone.utc)
events={}


def plain(s):
    return html.unescape(re.sub('<[^>]+>',' ',s))


def add(kind,family,date,clock,tz,source,path,title='',granularity='MINUTE',status='OFFICIAL_SCHEDULE_RETROSPECTIVE'):
    d=dt.datetime.strptime(date,'%Y-%m-%d')
    if clock:
        h,m=map(int,clock.split(':'));d=d.replace(hour=h,minute=m)
    d=d.replace(tzinfo=ZoneInfo(tz)).astimezone(dt.timezone.utc)
    if not START<=d<END:return
    ms=int(d.timestamp()*1000);ident=f'{kind}_{date}'
    events[ident]={'event_id':ident,'family':family,'event_type':kind,'scheduled_ms':ms,
        'local_date':date,'local_time':clock,'timezone':tz,'time_granularity':granularity,
        'timing_status':status,'source_url':source,'source_path':str(path),
        'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'title':title,'consensus_missing':True,'first_release_values_missing':True,
        'recorded_retrospectively':True}


def build(target=Path('reports/event_history_catalog_20261016.json')):
    global events
    events={}
    for path in ROOT.glob('bls*.txt'):
        text=path.read_text(encoding='utf-8')
        for match in re.finditer(r'(?:Monday|Tuesday|Wednesday|Thursday|Friday), ([A-Z][a-z]+ \d{1,2}, (202[456])) (\d{2}:\d{2} [AP]M) ([^\n]+)',text):
            date,year,clock,title=match.groups()
            types=(('Consumer Price Index','US_CPI','US_CPI'),('Producer Price Index','US_PPI','INFLATION_OTHER'),
                   ('Employment Situation for','US_NFP','EMPLOYMENT_GROWTH'),
                   ('Job Openings and Labor Turnover Survey','US_JOLTS','EMPLOYMENT_GROWTH'),
                   ('Employment Cost Index','US_ECI','INFLATION_OTHER'),
                   ('U.S. Import and Export Price Indexes','US_IMPORT_EXPORT','INFLATION_OTHER'),
                   ('Productivity and Costs','US_PRODUCTIVITY','EMPLOYMENT_GROWTH'))
            for prefix,kind,family in types:
                if title.startswith(prefix):
                    # Known 2025 shutdown schedules cannot stand in for actual releases.
                    parsed=dt.datetime.strptime(date,'%B %d, %Y')
                    if dt.datetime(2025,10,1)<=parsed<dt.datetime(2025,11,17):continue
                    add(kind,family,parsed.strftime('%Y-%m-%d'),dt.datetime.strptime(clock,'%I:%M %p').strftime('%H:%M'),
                        'America/New_York',f'https://www.bls.gov/schedule/{year}/home.htm',path,title)
    for path in (ROOT/'fed_census_web.txt',ROOT/'supplement_web.txt'):
      if path.exists():
        text=path.read_text(encoding='utf-8')
        for year,section in re.findall(r'#### (202[456]) FOMC Meetings(.*?)(?=#### \d{4} FOMC Meetings|\Z)',text,re.S):
            for month,day in re.findall(r'L\d+: (January|March|April|May|June|July|September|October|November|December|Apr/May)\s*\nL\d+:\s*\nL\d+: \d{1,2}-(\d{1,2})',section):
                month='May' if month=='Apr/May' else month
                date=dt.datetime.strptime(f'{month} {day} {year}','%B %d %Y').strftime('%Y-%m-%d')
                add('FED_RATE','MONETARY_POLICY',date,'14:00','America/New_York',
                    'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',path)
    for path in (ROOT/'bea.html',ROOT/'bea25full.html'):
        if not path.exists():continue
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>',path.read_text(encoding='utf-8'),re.S):
            title=re.search(r'<td[^>]*class="release-title[^>]*>(.*?)</td>',row,re.S)
            date=re.search(r'<div class="release-date">([^<]+)</div>.*?<small[^>]*>([^<]+)</small>',row,re.S)
            year=re.search(r'href="/news/(202[456])/',row)
            if not (title and date and year):continue
            name=plain(title[1]).strip()
            kind='US_PCE' if name.startswith('Personal Income and Outlays') else 'US_GDP' if (name.startswith('GDP (') or name.startswith('Gross Domestic Product,')) else None
            if kind:
                day=dt.datetime.strptime(date[1]+' '+year[1],'%B %d %Y').strftime('%Y-%m-%d')
                clock=dt.datetime.strptime(date[2],'%I:%M %p').strftime('%H:%M')
                add(kind,'INFLATION_OTHER' if kind=='US_PCE' else 'EMPLOYMENT_GROWTH',day,clock,'America/New_York',
                    'https://www.bea.gov/news/schedule/full',path,name)
    path=ROOT/'boc.html'
    if path.exists():
        for date in re.findall(r'<th data-date="(202[456]-\d\d-\d\d)"',path.read_text(encoding='utf-8')):
            add('BOC_RATE','MONETARY_POLICY',date,'09:45','America/Toronto',
                'https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/',path,status='OFFICIAL_DECISION_DATE_STANDARD_RELEASE_TIME')
    for path in (ROOT/'rba.html',ROOT/'rba25.html',ROOT/'rba24.html'):
        if not path.exists():continue
        for url,date in re.findall(r'<a href="(/media-releases/202[456]/[^"]+)">(\d{1,2} [A-Za-z]+ 202[456])</a>',path.read_text(encoding='utf-8')):
            day=dt.datetime.strptime(date,'%d %B %Y').strftime('%Y-%m-%d')
            add('RBA_RATE','MONETARY_POLICY',day,'14:30','Australia/Sydney','https://www.rba.gov.au'+url,path,status='OFFICIAL_DECISION_DATE_STANDARD_RELEASE_TIME')
    for path in (ROOT/'boj.html',ROOT/'bojpast.html'):
      if path.exists():
        for y,m,d in re.findall(r'/mopo/mpmdeci/mpr_202[456]/k(2[456])(\d\d)(\d\d)[a-z]\.pdf',path.read_text(encoding='utf-8')):
            add('BOJ_RATE','MONETARY_POLICY',f'20{y}-{m}-{d}',None,'Asia/Tokyo',
                'https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm',path,granularity='DATE_ONLY')
    from research.fred_event_sources import RELEASES
    for path in ROOT.glob('fred_*_*.html'):
        text=path.read_text(encoding='utf-8')
        if 'All times are US Central Time' not in text:continue
        for date,clock,rid,title in re.findall(r'<span style="font-weight: bold;">([^<]+)</span>.*?<td nowrap[^>]*>\s*(\d{1,2}:\d{2} [ap]m)\s*</td>.*?<a href="/release\?rid=(\d+)">([^<]+)</a>',text,re.S):
            if int(rid) not in RELEASES:continue
            kind=RELEASES[int(rid)]
            day=dt.datetime.strptime(date,'%A %B %d, %Y').strftime('%Y-%m-%d')
            clock=dt.datetime.strptime(clock,'%I:%M %p').strftime('%H:%M')
            family='US_CPI' if kind=='US_CPI' else 'INFLATION_OTHER' if kind in ('US_PCE','US_PPI') else 'EMPLOYMENT_GROWTH'
            add(kind,family,day,clock,
                'America/Chicago',f'https://fred.stlouisfed.org/releases/calendar?rid={rid}&y={day[:4]}',
                path,title,status='OFFICIAL_AGGREGATOR_CALENDAR_NOT_FIRST_VINTAGE')
    # Sources added as structured, individually checked records (conferences etc.).
    manual=ROOT/'verified_events.json'
    if manual.exists():
        for e in json.loads(manual.read_text(encoding='utf-8')):
            add(e['event_type'],e['family'],e['date'],e.get('clock'),e['timezone'],e['source_url'],
                manual,e.get('title',''),e.get('time_granularity','MINUTE'),e.get('timing_status','OFFICIAL_SCHEDULE_RETROSPECTIVE'))
    rows=sorted(events.values(),key=lambda e:(e['scheduled_ms'],e['event_id']))
    for e in rows:e['cluster_id']='TIME_'+str(e['scheduled_ms'])
    out={'start_utc':START.isoformat(),'end_utc':END.isoformat(),'events':rows,
         'counts':{kind:sum(e['event_type']==kind for e in rows) for kind in sorted({e['event_type'] for e in rows})},
         'all_requested_sources_complete':False,'actual_consensus_complete':False}
    target=Path(target)
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'events':len(rows),'counts':out['counts'],'target':str(target)}))
    return out


if __name__=='__main__':build()
