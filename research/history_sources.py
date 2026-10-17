"""Fetch public primary calendar pages; keep failures and original source bytes."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import hashlib
import time
from urllib.request import urlopen

ROOT=Path('reports/event_sources_20261016')
URLS={
 'fed':'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',
 'census24':'https://www.census.gov/economic-indicators/calendar-listview-2024.html',
 'census25':'https://www.census.gov/economic-indicators/calendar-listview-2025.html',
 'census26':'https://www.census.gov/economic-indicators/calendar-listview-2026.html',
 'bea':'https://www.bea.gov/news/schedule/full',
 'bea25':'https://www.bea.gov/news/schedule/2025',
 'ecb':'https://www.ecb.europa.eu/press/govcdec/mopo/html/index.en.html',
 'adp':'https://mediacenter.adp.com/press-releases',
 'boe':'https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates',
 'boc':'https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/',
 'rba':'https://www.rba.gov.au/monetary-policy/int-rate-decisions/',
 'boj':'https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm',
 'rbnz':'https://www.rbnz.govt.nz/monetary-policy/monetary-policy-decisions',
 'snb':'https://www.snb.ch/en/the-snb/mandates-goals/monetary-policy/monetary-policy-decisions',
}


def fetch(item):
    key,url=item;path=ROOT/(key+'.html')
    try:
        if path.exists():
            body=path.read_bytes()
        else:
            with urlopen(url,timeout=12) as stream:body=stream.read(4000001)
            if len(body)>4000000:raise ValueError('SOURCE_BUDGET')
            path.write_bytes(body)
        return {'key':key,'url':url,'status':'CAPTURED','path':str(path),
                'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}
    except Exception as exc:
        return {'key':key,'url':url,'status':'UNAVAILABLE','error':str(exc)}


if __name__=='__main__':
    ROOT.mkdir(parents=True,exist_ok=True)
    rows=list(ThreadPoolExecutor(4).map(fetch,URLS.items()))
    (ROOT/'fetch_status.json').write_text(json.dumps({'observed_ns':time.time_ns(),'sources':rows},indent=2))
    print(json.dumps(rows))
