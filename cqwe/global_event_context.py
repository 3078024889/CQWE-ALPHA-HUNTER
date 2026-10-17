"""Bounded public-news context. Headlines are unconfirmed data, not directions."""
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from urllib.request import Request,urlopen
import xml.etree.ElementTree as ET

from .copernican_experiment_v81_v85 import digest
from .local_autopilot import atomic

FEEDS={
 'FED':('https://www.federalreserve.gov/feeds/press_all.xml','PRIMARY'),
 'SEC':('https://www.sec.gov/news/pressreleases.rss','PRIMARY'),
 'BLS':('https://www.bls.gov/feed/cpi.rss','PRIMARY'),
 'ECB':('https://www.ecb.europa.eu/rss/press.html','PRIMARY'),
 'BOE':('https://www.bankofengland.co.uk/rss/news','PRIMARY'),
 'BBC_WORLD':('https://feeds.bbci.co.uk/news/world/rss.xml','SECONDARY'),
 'COINTELEGRAPH':('https://cointelegraph.com/rss','SECONDARY'),
 'EIA':('https://www.eia.gov/rss/press_releases.xml','PRIMARY'),
}
PATTERNS={
 'INFLATION':r'\b(cpi|ppi|pce|inflation)\b',
 'EMPLOYMENT_GROWTH':r'\b(payrolls?|unemployment|jolts|retail sales|gdp|pmi)\b',
 'MONETARY_POLICY':r'\b(federal reserve|interest rate|rate cut|rate hike|central bank|quantitative)\b',
 'WAR_GEOPOLITICS':r'\b(missiles?|invasion|ceasefire|airstrikes?|war erupts)\b',
 'SANCTIONS_TRADE':r'\b(sanctions?|tariffs?|export controls?)\b',
 'POLITICAL_STATEMENT':r'\b(president|white house|executive order|trump)\b',
 'ETF_FLOWS':r'\b(etf|exchange.traded fund|inflows?|outflows?)\b',
 'REGULATION_LEGAL':r'\b(sec|regulat\w*|lawsuit|approval|securities)\b',
 'HACK_EXPLOIT':r'\b(hacked|exploit(?:ed)?|stolen|breach)\b',
 'EXCHANGE_CUSTODY':r'\b(withdrawal\w*|insolvency|bankruptcy|exchange outage)\b',
 'STABLECOIN_CREDIT':r'\b(depeg|redemption|stablecoin reserves)\b',
 'CHAIN_TOKEN':r'\b(token unlock|chain outage|network upgrade)\b',
}
ACUTE={'WAR_GEOPOLITICS','SANCTIONS_TRADE','HACK_EXPLOIT','EXCHANGE_CUSTODY','STABLECOIN_CREDIT'}


def classify(title):
    return [family for family,pattern in PATTERNS.items() if re.search(pattern,title,re.I)]


def parse(raw,source,now):
    if source not in FEEDS or len(raw)>400000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('NEWS_SOURCE_SIZE_OR_XML')
    root=ET.fromstring(raw);items=root.findall('.//item')
    if not items:items=root.findall('.//{http://www.w3.org/2005/Atom}entry')
    rows=[]
    for node in items[:60]:
        fields={c.tag.split('}')[-1]:c for c in node}
        def value(name):
            e=fields.get(name);return ''.join(e.itertext()).strip() if e is not None else ''
        title=value('title')[:1000];link=value('link')[:2000]
        if not link and fields.get('link') is not None:link=fields['link'].get('href','')[:2000]
        date=value('pubDate') or value('published') or value('updated');published=None
        try:
            from datetime import datetime
            dt=parsedate_to_datetime(date) if ',' in date else datetime.fromisoformat(date.replace('Z','+00:00'))
            if dt.tzinfo is not None:published=int(dt.timestamp()*1000)
        except (ValueError,TypeError,OverflowError):pass
        if not title:continue
        normalized=re.sub(r'\W+',' ',title.lower()).strip()
        rows.append({'id':digest({'source':source,'title':title,'link':link,'date':date}),
            'cluster':digest(normalized),'source':source,'source_kind':FEEDS[source][1],
            'title':title,'url':link,'published_ms':published,'first_seen_ms':now,
            'available_ms':max(now,published) if published is not None else now,
            'families':classify(title),'fact_confirmed':False,'direction':None,
            'raw_source_sha256':hashlib.sha256(raw).hexdigest()})
    if not rows:raise ValueError('NEWS_EMPTY_OR_HTML_NOT_RSS')
    return rows


class GlobalContext:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.stop=threading.Event();self.thread=None
        self.state={'sources':{},'items':{},'cursor':0}
        file=self.root/'state.json'
        if file.exists():
            from .four_market_runner import checked
            self.state=checked(json.loads(file.read_text(encoding='utf-8')))
            self.state.pop('sha256',None)

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.thread=threading.Thread(target=self.run,name='CQWE-global-news',daemon=True);self.thread.start()

    def run(self):
        while not self.stop.is_set():
            self.poll_one();self.stop.wait(30)

    def poll_one(self):
        with self.lock:
            source=list(FEEDS)[self.state['cursor']%len(FEEDS)];self.state['cursor']+=1
        now=time.time_ns()//1000000;url,_=FEEDS[source]
        try:
            with urlopen(Request(url,headers={'User-Agent':'CQWE-public-research/1.0'}),timeout=4) as r:raw=r.read(400001)
            rows=parse(raw,source,now)
            sha=hashlib.sha256(raw).hexdigest();snapshot=self.root/('source_'+source+'_'+sha+'.json')
            if not snapshot.exists():
                if sum(p.stat().st_size for p in self.root.glob('source_*.json'))>20000000:raise ValueError('NEWS_DISK_BUDGET')
                atomic(snapshot,{'source':source,'url':url,'observed_ms':now,'raw_xml':raw.decode('utf-8','replace'),'raw_sha256':sha})
            status={'status':'CAPTURED','observed_ms':now,'items':len(rows),'url':url}
            with self.lock:
                for row in rows:
                    previous=self.state['items'].get(row['id'])
                    if previous:row['first_seen_ms']=previous['first_seen_ms'];row['available_ms']=previous['available_ms']
                    self.state['items'][row['id']]=row
                self.state['items']={k:v for k,v in self.state['items'].items() if now-v['first_seen_ms']<=172800000}
                self.state['items']=dict(sorted(self.state['items'].items(),key=lambda kv:kv[1]['first_seen_ms'])[-1000:])
        except Exception as exc:status={'status':'UNAVAILABLE','observed_ms':now,'url':url,'error':str(exc)}
        with self.lock:
            self.state['sources'][source]=status
            atomic(self.root/'state.json',self.state)
        return status

    def snapshot(self,now):
        with self.lock:
            fresh=[k for k,v in self.state['sources'].items() if v['status']=='CAPTURED' and 0<=now-v['observed_ms']<=1800000]
            # No backdating: only reports actually first seen and published recently can veto entries.
            recent={}
            for row in self.state['items'].values():
                p=row['published_ms']
                if (p is not None and 0<=now-p<=1800000 and 0<=now-row['first_seen_ms']<=900000
                    and row['available_ms']<=now and set(row['families']) & ACUTE):
                    recent[row['cluster']]=row
            alerts=list(recent.values())[-12:]
            return {'at_ms':now,'fresh_sources':fresh,'source_count':len(FEEDS),
                'sources':dict(self.state['sources']),'potential_acute_events':alerts,
                'entry_veto':bool(alerts),'reason':'UNCONFIRMED_ACUTE_REPORT' if alerts else None,
                'directional_weight':0.,'all_global_events_complete':False,
                'missing':['ETF numeric flows','point-in-time consensus','complete political/war/hack coverage'],
                'headlines_are_not_confirmed_facts':True,'orders_enabled':False}
