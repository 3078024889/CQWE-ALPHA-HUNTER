"""CQWE V15: bounded public Polymarket book snapshots and conservative replay.
Only public HTTP GET. No credentials, order endpoints, wallets, or trading.
Snapshots are NOT historical fills; indicative observations only.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from .edge_lab_v14 import complete_set_no_yes

GAMMA='https://gamma-api.polymarket.com'
CLOB='https://clob.polymarket.com'
HEADERS={'User-Agent':'CQWE-Research-Only/1.5','Accept':'application/json'}


def public_get(base, endpoint, params=None, timeout=9):
    if (base,endpoint) not in ((GAMMA,'/markets'),(CLOB,'/book')):
        raise ValueError('read-only endpoint not allowed')
    url=base+endpoint+'?'+urllib.parse.urlencode(params or {})
    req=urllib.request.Request(url,headers=HEADERS,method='GET')
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError('response too large')
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'public endpoint HTTP {e.code}') from e


def unpack_list(value):
    if isinstance(value,str):value=json.loads(value)
    if not isinstance(value,list):raise ValueError('invalid encoded list')
    return value


def decode_binary_market(m):
    """Only native binary YES/NO pair from ONE Gamma market, not two unrelated events."""
    if m.get('closed') is True or m.get('active') is False or m.get('enableOrderBook') is False:
        return None
    try:
        outcomes=unpack_list(m['outcomes']); tokens=unpack_list(m['clobTokenIds'])
    except (KeyError,TypeError,ValueError,json.JSONDecodeError):
        return None
    if [str(x).strip().lower() for x in outcomes] != ['yes','no'] or len(tokens)!=2:
        return None
    if any(not str(t).isdigit() or int(str(t))<=0 for t in tokens) or tokens[0]==tokens[1]:
        return None
    condition=str(m.get('conditionId') or '')
    if not condition.startswith('0x') or len(condition)!=66:
        return None
    try:int(condition[2:],16)
    except ValueError:return None
    return {'condition_id':condition,'market_id':str(m.get('id','')),
            'question':str(m.get('question',''))[:250], 'tokens':[str(t) for t in tokens],
            'order_min_size':m.get('orderMinSize')}


def book_levels(raw):
    if not isinstance(raw,dict) or not isinstance(raw.get('asks'),list):
        raise ValueError('book has no asks')
    out=[]
    for row in raw['asks']:
        if not isinstance(row,dict):raise ValueError('bad book level')
        price=float(row['price']); size=float(row['size'])
        if not (math.isfinite(price) and math.isfinite(size) and 0<price<1 and size>0):
            raise ValueError('invalid price or size')
        out.append({'price':price,'size':size})
    return out


def capture(limit=5, shares=10, fee_buffer_usd=0.10, delay=.25, fetcher=public_get, clock=None):
    if not 1<=limit<=10 or not 0<shares<=100 or fee_buffer_usd<0 or not 0<=delay<=2:
        raise ValueError('resource bounds invalid')
    clock=clock or (lambda:int(time.time()*1000))
    markets=fetcher(GAMMA,'/markets',{'active':'true','closed':'false','limit':min(50,limit*10)})
    if not isinstance(markets,list):raise ValueError('unexpected Gamma response')
    snapshots=[]; seen=set()
    for raw in markets:
        m=decode_binary_market(raw)
        if m is None or m['condition_id'] in seen:continue
        seen.add(m['condition_id'])
        capture_start=clock()
        try:
            yes_raw=fetcher(CLOB,'/book',{'token_id':m['tokens'][0]})
            no_raw=fetcher(CLOB,'/book',{'token_id':m['tokens'][1]})
            capture_end=clock()
            if not isinstance(yes_raw,dict) or not isinstance(no_raw,dict):
                raise ValueError('book response must be object')
            if str(yes_raw.get('asset_id',''))!=m['tokens'][0] or str(no_raw.get('asset_id',''))!=m['tokens'][1]:
                raise ValueError('book asset identity mismatch')
            yes=book_levels(yes_raw); no=book_levels(no_raw)
            elapsed=capture_end-capture_start
            # Age here is observation-pair capture duration, NOT actual quote age.
            estimate=complete_set_no_yes(yes,no,shares,fee_usd=fee_buffer_usd,
                     market_age_ms=None,verified_complementary=True)
            # Never identify as fresh using request duration or unverified timestamps.
            estimate['decision']='OBSERVATION_ONLY_NOT_EXECUTABLE' if estimate['book_fillable'] else 'REJECT_DEPTH'
            estimate['fresh']=False
            snapshots.append({'market':m,'observation_start_ms':capture_start,
                'observation_end_ms':capture_end,'pair_capture_duration_ms':elapsed,
                'quote_age_verified':False,'yes_asks':yes,'no_asks':no,'estimate':estimate})
        except (RuntimeError,ValueError,KeyError,TypeError) as e:
            snapshots.append({'market':m,'error':str(e),'decision':'REJECT_INVALID_BOOK'})
        if len(snapshots)>=limit:break
        if delay:time.sleep(delay)
    return {'schema_version':1,'research_only':True,'source':'Polymarket Gamma + CLOB public GET',
        'captured_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'requested_shares':shares,'fee_buffer_usd':fee_buffer_usd,
        'limitations':'Non-atomic book snapshots; quote age and simultaneous fills not verified; never guaranteed or executable.',
        'snapshots':snapshots}


def save_snapshot(payload,path):
    if not payload.get('research_only'):raise ValueError('not research payload')
    dest=Path(path);dest.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2).encode('utf-8')
    digest=hashlib.sha256(content).hexdigest()
    tmp=dest.with_suffix(dest.suffix+'.tmp');tmp.write_bytes(content);tmp.replace(dest)
    return {'file':str(dest),'sha256':digest,'markets':len(payload['snapshots'])}


def replay(paths):
    if not paths or len(paths)>100:raise ValueError('bounded file count 1..100')
    observations=[]; seen=set()
    for path in paths:
        raw=Path(path).read_bytes()
        if len(raw)>3_000_000:raise ValueError('snapshot too large')
        payload=json.loads(raw)
        if payload.get('schema_version')!=1 or payload.get('research_only') is not True:
            raise ValueError('invalid snapshot schema')
        sha=hashlib.sha256(raw).hexdigest()
        if sha in seen:continue
        seen.add(sha)
        for item in payload['snapshots']:
            estimate=item.get('estimate') or {}
            observations.append({'condition_id':item['market']['condition_id'],
               'snapshot_sha256':sha,
               'gross_spread_usd':estimate.get('gross_spread_usd'),
               'net_after_buffer_usd':estimate.get('indicative_net_after_buffers_usd'),
               'decision':item.get('decision',estimate.get('decision','UNKNOWN')),
               'quote_age_verified':item.get('quote_age_verified',False)})
    return {'research_only':True,'observations':len(observations),
            'positive_indicative_not_executable':sum((x['net_after_buffer_usd'] or 0)>0 for x in observations),
            'verified_executable_trades':0,'realized_profit_usd':None,
            'warning':'Repeated snapshots are correlated; no fills, order queue, fees schedule, settlement or executable profit.',
            'records':observations}


def main():
    parser=argparse.ArgumentParser(description='CQWE V15 public-book evidence only; NO ORDERS')
    sp=parser.add_subparsers(dest='action',required=True)
    p=sp.add_parser('capture');p.add_argument('--limit',type=int,default=5);p.add_argument('--shares',type=float,default=10)
    p.add_argument('--out',default='data/polymarket/v15_snapshot.json')
    p=sp.add_parser('replay');p.add_argument('--inputs',nargs='+',required=True)
    p.add_argument('--out',default='reports/v15_replay.json')
    args=parser.parse_args()
    if args.action=='capture':
        result=save_snapshot(capture(limit=args.limit,shares=args.shares),args.out)
    else:
        result=replay(args.inputs)
        dest=Path(args.out);dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('CQWE_V15_RESEARCH_PASS | NO ORDERS | NO PROFIT CLAIM')

if __name__=='__main__':main()
