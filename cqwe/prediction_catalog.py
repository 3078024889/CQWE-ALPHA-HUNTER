"""Read-only venue catalogs. No order, transfer, wallet or signing-tx endpoint.

Binance signed GETs use only explicitly named optional read-data credentials.
Polymarket Up/Down discovery never guesses the settlement reference or TWAP.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .copernican_experiment_v81_v85 import digest
from .four_market_core import SYMBOLS
from .polymarket_research import parse_book

BINANCE_PATHS = ('market/list','market/detail','order-book')


def request_json(url, headers=None):
    req = urllib.request.Request(url,headers={'User-Agent':'CQWE-research/1.0','Accept':'application/json',**(headers or {})},method='GET')
    with urllib.request.urlopen(req,timeout=10) as response:
        raw = response.read(3_000_001)
    if len(raw) > 3_000_000:
        raise ValueError('CATALOG_RESPONSE_BUDGET')
    return json.loads(raw)


def binance_read(path, params=None):
    if path not in BINANCE_PATHS:
        raise ValueError('SIGNED_READ_ENDPOINT_NOT_ALLOWED')
    key = os.environ.get('CQWE_PREDICTION_READ_API_KEY')
    secret = os.environ.get('CQWE_PREDICTION_READ_API_SECRET')
    if not key or not secret:
        raise ValueError('BINANCE_READ_CREDENTIALS_NOT_CONFIGURED')
    params = dict(params or {})
    params['timestamp'] = time.time_ns()//1_000_000
    query = urllib.parse.urlencode(params)
    signature = hmac.new(secret.encode(),query.encode(),hashlib.sha256).hexdigest()
    url = 'https://api.binance.com/sapi/v1/w3w/wallet/prediction/'+path+'?'+query+'&signature='+signature
    return request_json(url, {'X-MBX-APIKEY':key})


def polymarket_window(symbol, horizon, epoch):
    slug = f'{symbol[:-4].lower()}-updown-{horizon//60}m-{epoch}'
    raw = request_json('https://gamma-api.polymarket.com/markets?'+urllib.parse.urlencode({'slug':slug}))
    if not isinstance(raw,list) or len(raw) != 1 or raw[0].get('slug') != slug:
        return {'symbol':symbol,'horizon_seconds':horizon,'slug':slug,'status':'NO_EXACT_WINDOW_MARKET'}
    m = raw[0]
    result = {'symbol':symbol,'horizon_seconds':horizon,'slug':slug,'metadata':m,
              'status':'METADATA_ONLY','automatic_event_forecast':False,
              'blocking_reason':'EXACT_ORACLE_REFERENCE_AND_RULE_ADAPTER_REQUIRED'}
    if m.get('active') is not True or m.get('closed') is not False or m.get('enableOrderBook') is not True:
        result['status'] = 'WINDOW_NOT_OPEN'
        return result
    names = m['outcomes']
    tokens = m['clobTokenIds']
    names = json.loads(names) if isinstance(names,str) else names
    tokens = json.loads(tokens) if isinstance(tokens,str) else tokens
    if len(names)!=2 or len(tokens)!=2 or {str(n).lower() for n in names} != {'up','down'}:
        raise ValueError('UP_DOWN_LAYOUT_REQUIRED')
    books = {}
    for side in ('up','down'):
        token = tokens[[str(n).lower() for n in names].index(side)]
        if not isinstance(token,str) or not token.isdigit() or len(token)>100:
            raise ValueError('TOKEN_ID_REQUIRED')
        book = request_json('https://clob.polymarket.com/book?'+urllib.parse.urlencode({'token_id':token}))
        parse_book(book,token=token,condition=m['conditionId'])
        books[side] = book
    result.update(status='REAL_ORDERBOOKS_CAPTURED',books=books,rules_sha256=digest(m.get('description','')))
    return result


def collect(root, *, horizons=(300,900)):
    root = Path(root)
    root.mkdir(parents=True,exist_ok=True)
    now = int(time.time())
    result = {'captured_at_ms':time.time_ns()//1_000_000,'mode':'READ_ONLY_CATALOG',
              'polymarket':[],'binance':{},'real_orders':0}
    for symbol in SYMBOLS:
        for horizon in horizons:
            try:
                entry = polymarket_window(symbol,horizon,now//horizon*horizon)
            except Exception as exc:
                # Do not log exceptions containing signed URLs or credential material.
                entry = {'symbol':symbol,'horizon_seconds':horizon,'status':'FETCH_FAILED','error_type':type(exc).__name__}
            result['polymarket'].append(entry)
    try:
        raw = binance_read('market/list',{'l1Category':'crypto','l2Category':'up-down','limit':100})
        result['binance'] = {'status':'SIGNED_READ_SUCCEEDED','raw':raw,
                             'automatic_event_forecast':False,'blocking_reason':'EXACT_ORACLE_REFERENCE_AND_RULE_ADAPTER_REQUIRED'}
    except Exception as exc:
        result['binance'] = {'status':'NOT_CONNECTED','error_type':type(exc).__name__,
                             'reason':'READ_CREDENTIALS_REQUIRED' if not os.environ.get('CQWE_PREDICTION_READ_API_KEY') else 'SIGNED_READ_FAILED'}
    result['sha256'] = digest(result)
    target = root/f'catalog_{time.time_ns()}.json'
    with target.open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    return {'path':str(target),'polymarket_statuses':[r['status'] for r in result['polymarket']],
            'binance_status':result['binance']['status'],'sha256':result['sha256'],'real_orders':0}
