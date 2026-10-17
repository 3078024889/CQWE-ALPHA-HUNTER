"""Conservative extraction from retained BLS archive retrievals, no consensus invention."""
import collections
import hashlib
import json
from pathlib import Path
import re

ROOT=Path('reports/event_sources_20261016')


def extract(kind,text):
    s=re.sub(r'L\d+:\s*',' ',text)
    s=' '.join(s.split())
    if kind in ('US_CPI','US_PPI'):
        head=r'Consumer Price Index for All Urban Consumers \(CPI-U\)' if kind=='US_CPI' else r'Producer Price Index for final demand'
        m=re.search(head+r'\s+(increased|rose|advanced|declined|decreased|fell|edged up|edged down|inched up|inched down|moved up|moved down)\s+(\d+(?:\.\d+)?)\s+percent',s,re.I)
        if m:
            value=float(m[2])*(-1 if m[1].lower() in ('declined','decreased','fell','edged down','inched down','moved down') else 1)
            return {'value':value,'unit':'percent','metric':'headline_mom'}
        if re.search(head+r'\s+(?:was |remained )?unchanged',s,re.I):
            return {'value':0.,'unit':'percent','metric':'headline_mom'}
    elif kind=='US_NFP':
        m=re.search(r'Total nonfarm payroll employment\s+(increased|rose|advanced|declined|decreased|fell|edged up|edged down)(?:\s+by)?\s+([\d,]+)',s,re.I)
        if m:return {'value':int(m[2].replace(',',''))*(-1 if m[1].lower() in ('declined','decreased','fell','edged down') else 1),'unit':'jobs','metric':'monthly_change'}
        m=re.search(r'Total nonfarm payroll employment.{0,120}?\(([+-]?[\d,]+)\)',s,re.I)
        if m:return {'value':int(m[1].replace(',','')),'unit':'jobs','metric':'monthly_change'}
    elif kind=='US_JOLTS':
        m=re.search(r'(?:The )?number of job openings.{0,160}?\b(?:at|to)\s+(\d+(?:\.\d+)?)\s+million',s,re.I)
        if m:return {'value':float(m[1]),'unit':'million_jobs','metric':'openings_level'}
    return None


if __name__=='__main__':
    rows=[]
    for path in sorted(ROOT.glob('releases_*.json')):
        obj=json.loads(path.read_text(encoding='utf-8'));text=obj['retrieval']
        for e in obj['entries']:
            position=text.find(e['url'])
            section=text[position:].split('\n--------------------------------------------------------------------------------',1)[0] if position>=0 else ''
            value=extract(e['event_type'],section)
            rows.append({**e,'archived_value':value,'parser_status':'EXTRACTED' if value else 'UNEXTRACTED',
                'retrieval_snapshot':str(path),'snapshot_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'first_vintage_authenticated':False,'consensus':None,
                'safe_for_historical_pre_release_features':False})
    unique={}
    for row in rows:
        if row['event_id'] not in unique or row['archived_value'] is not None:unique[row['event_id']]=row
    rows=list(unique.values())
    report={'rows':rows,'counts':dict(collections.Counter(r['event_type'] for r in rows if r['archived_value'] is not None)),
            'attempted':len(rows),'extracted':sum(r['archived_value'] is not None for r in rows),
            'consensus_available':0,'archived_values_not_certified_initial_vintages':True}
    target=Path('reports/archived_release_values_20261016.json')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
