"""Fixed public official feeds. Text is stored as data, never executed or traded."""
import argparse
import datetime
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen
import xml.etree.ElementTree as ET

from .local_autopilot import atomic,exclusive

FEEDS={
    'FED':'https://www.federalreserve.gov/feeds/press_all.xml',
    'BLS_CPI':'https://www.bls.gov/feed/cpi.rss',
    'SEC':'https://www.sec.gov/news/pressreleases.rss',
}


def parse(raw,source,observed_ms):
    if source not in FEEDS or len(raw)>500000:
        raise ValueError('NEWS_SOURCE_OR_SIZE')
    root=ET.fromstring(raw)
    rows=[];source_hash=hashlib.sha256(raw).hexdigest()
    for item in root.findall('.//item')[:100]:
        title=(item.findtext('title') or '')[:4000]
        link=(item.findtext('link') or '')[:2000]
        date=item.findtext('pubDate')
        published=None
        if date:
            try:
                dt=parsedate_to_datetime(date)
                if dt.tzinfo is not None:
                    published=int(dt.timestamp()*1000)
            except (ValueError,TypeError,OverflowError):
                pass
        ident=hashlib.sha256((source+'\0'+link+'\0'+title+'\0'+str(date)).encode()).hexdigest()
        rows.append({'id':ident,'source':source,'title':title,'link':link,
                     'published_ms':published,'first_seen_ms':observed_ms,
                     'available_ms':max(published,observed_ms) if published is not None else observed_ms,
                     'source_sha256':source_hash,'untrusted_text':True,
                     'event_cluster_resolved':False,'directional_signal':None})
    return rows


def collect(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    status={};now=time.time_ns()//1_000_000
    for source,url in FEEDS.items():
        try:
            with urlopen(Request(url,headers={'User-Agent':'CQWE-public-research/1.0'}),timeout=6) as stream:
                raw=stream.read(500001)
            rows=parse(raw,source,now)
            if not rows:
                raise ValueError('NEWS_FEED_EMPTY_OR_UNSUPPORTED')
            sha=hashlib.sha256(raw).hexdigest()
            snapshot=root/f'{source}_{sha}.json'
            if not snapshot.exists():
                atomic(snapshot,{'source':source,'url':url,'raw_xml':raw.decode('utf-8','replace'),
                                  'observed_ms':now,'items':rows})
            status[source]={'status':'CAPTURED','items':len(rows),'snapshot':str(snapshot)}
        except Exception as exc:
            status[source]={'status':'UNAVAILABLE','error':type(exc).__name__+': '+str(exc)}
    report={'observed_ms':now,'sources':status,'automatic_classification_trained':False,
            'real_orders':0,'scope':'OFFICIAL_FEED_SNAPSHOTS_NOT_ALL_GLOBAL_NEWS'}
    atomic(root/'status.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True)
    p.add_argument('--once',action='store_true');a=p.parse_args()
    root=Path(a.root);root.mkdir(parents=True,exist_ok=True)
    with exclusive(root):
        while True:
            if sum(f.stat().st_size for f in root.glob('*.json'))>100_000_000:
                atomic(root/'status.json',{'status':'PAUSED_NEWS_DISK_BUDGET'});return
            result=collect(root)
            if a.once:
                print(json.dumps(result));return
            time.sleep(300)


if __name__=='__main__':main()
