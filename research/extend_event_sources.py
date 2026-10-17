"""Turn retained primary-source retrievals into auditable structured records."""
import datetime as dt
import json
from pathlib import Path
import re

ROOT=Path('reports/event_sources_20261016')


if __name__=='__main__':
    text='\n'.join(p.read_text(encoding='utf-8') for p in ROOT.glob('*web.txt'))
    rows=[]
    def add(kind,date,clock,tz,url,title='',granularity='MINUTE',status='OFFICIAL_DECISION_DATE_STANDARD_RELEASE_TIME'):
        rows.append({'event_type':kind,'family':'MONETARY_POLICY' if kind.endswith('_RATE') else 'OTHER_RELEVANT',
            'date':date,'clock':clock,'timezone':tz,'source_url':url,'title':title,
            'time_granularity':granularity,'timing_status':status})
    for url,date in set(re.findall(r'(https://www.ecb.europa.eu/press/pr/date/202[456]/html/ecb.mp(\d{6})[^\s)]+?\.en.html)',text)):
        day=dt.datetime.strptime(date,'%y%m%d').strftime('%Y-%m-%d')
        add('ECB_RATE',day,'14:15','Europe/Berlin',url)
    for day in ('2026-02-05','2026-03-19','2026-04-30','2026-06-11','2026-07-23','2026-09-10'):
        add('ECB_RATE',day,'14:15','Europe/Berlin','https://www.ecb.europa.eu/press/govcdec/mopo/html/index.en.html')
    for date in set(re.findall(r'Published on (\d{2} [A-Za-z]+ 2025)',text)):
        d=dt.datetime.strptime(date,'%d %B %Y')
        url=f'https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2025/{d.strftime("%B").lower()}-2025'
        add('BOE_RATE',d.strftime('%Y-%m-%d'),'12:00','Europe/London',url)
    bank=(ROOT/'bank_schedules_web.txt').read_text(encoding='utf-8')
    first=bank.split('## 2027 confirmed dates')[0]
    for day,month in re.findall(r'Thursday (\d{1,2}) ([A-Za-z]+)',first):
        d=dt.datetime.strptime(f'{day} {month} 2026','%d %B %Y')
        add('BOE_RATE',d.strftime('%Y-%m-%d'),'12:00','Europe/London',
            'https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates')
    rbnzurl='https://www.rbnz.govt.nz/news-and-events/news/2024/06/monetary-policy-announcement-and-financial-stability-report-dates-for-late-2025-and-2026'
    begin=bank.index('L14: 2024')
    section=bank[begin:bank.index('L37:',begin)]
    section=re.sub(r'cite\d+†([^]+)',r'\1',section)
    year=None
    for line in section.splitlines():
        m=re.search(r'L\d+: (202[456])\s*$',line)
        if m:year=int(m[1])
        m=re.search(r'(\d{1,2}) (February|April|May|July|August|October|November)',line)
        if m and year:
            d=dt.datetime.strptime(f'{m[1]} {m[2]} {year}','%d %B %Y')
            add('RBNZ_RATE',d.strftime('%Y-%m-%d'),'14:00','Pacific/Auckland',rbnzurl,
                status='OFFICIAL_SCHEDULE_RETROSPECTIVE')
    for date in set(re.findall(r'Monetary policy assessment of (\d{1,2} [A-Za-z]+ 202[456])',bank)):
        d=dt.datetime.strptime(date,'%d %B %Y')
        add('SNB_RATE',d.strftime('%Y-%m-%d'),None,'Europe/Zurich',
            'https://www.snb.ch/en/the-snb/mandates-goals/monetary-policy/decisions',granularity='DATE_ONLY')
    for kind,day,tz,url,title in (
      ('CONFERENCE_BITCOIN','2025-05-27','America/Los_Angeles','https://2025.b.tc/faqs','Bitcoin 2025; opening day, multi-day event'),
      ('CONFERENCE_TOKEN2049_DUBAI','2025-04-30','Asia/Dubai','https://token2049.nyc3.cdn.digitaloceanspaces.com/Dubai/Event%20Report/TOKEN2049%20Dubai%20Report.pdf','TOKEN2049 Dubai 2025; opening day'),
      ('CONFERENCE_TOKEN2049_SG','2025-10-01','Asia/Singapore','https://www.asia.token2049.com/tickets','TOKEN2049 Singapore 2025; opening day')):
        add(kind,day,None,tz,url,title,'DATE_ONLY','OFFICIAL_EVENT_DATE_ONLY')
    target=ROOT/'verified_events.json';target.write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print(json.dumps({'records':len(rows),'target':str(target)}))
