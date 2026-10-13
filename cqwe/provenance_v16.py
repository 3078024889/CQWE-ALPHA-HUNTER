"""CQWE V1.6: offline provenance checks for V1.5 public book snapshots.
No external API, keys, positions or orders. File hash != observation hash.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from .edge_lab_v14 import complete_set_no_yes
from .live_books_v15 import decode_binary_market, book_levels


def canonical_hash(obj):
    data=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def read_snapshot(path, max_bytes=3_000_000):
    raw=Path(path).read_bytes()
    if len(raw)>max_bytes:raise ValueError('oversized snapshot')
    payload=json.loads(raw)
    if not isinstance(payload,dict) or payload.get('research_only') is not True or payload.get('schema_version')!=1:
        raise ValueError('invalid V15 snapshot schema')
    if not isinstance(payload.get('snapshots'),list) or len(payload['snapshots'])>10:
        raise ValueError('invalid market count')
    return payload,hashlib.sha256(raw).hexdigest()


def observation(item, shares, buffer):
    if not isinstance(item,dict):raise ValueError('invalid observation')
    market=item.get('market')
    if not isinstance(market,dict):raise ValueError('missing market identity')
    condition=market.get('condition_id')
    if not isinstance(condition,str) or len(condition)!=66 or not condition.startswith('0x'):
        raise ValueError('invalid condition id')
    try:int(condition[2:],16)
    except ValueError as e:raise ValueError('invalid condition hex') from e
    ids=market.get('tokens')
    if not isinstance(ids,list) or len(ids)!=2 or ids[0]==ids[1] or not all(str(t).isdigit() and int(t)>0 for t in ids):
        raise ValueError('unverified token mapping')
    base={'condition_id':condition,'observation_sha256':canonical_hash(item),
          'quote_age_verified':False,'executable':False,'realized_profit_usd':None}
    if 'error' in item:
        base.update(decision='REJECT_INVALID_BOOK',net_after_buffer_usd=None)
        return base
    start=item.get('observation_start_ms');end=item.get('observation_end_ms')
    if not all(isinstance(x,int) and not isinstance(x,bool) for x in (start,end)) or end<start:
        raise ValueError('bad observation timestamps')
    yes=book_levels({'asks':item['yes_asks']});no=book_levels({'asks':item['no_asks']})
    estimate=complete_set_no_yes(yes,no,shares,fee_usd=buffer,market_age_ms=None,verified_complementary=True)
    # Recompute rather than trust serialized estimates.
    reported=item.get('estimate') or {}
    value=estimate.get('indicative_net_after_buffers_usd')
    old=reported.get('indicative_net_after_buffers_usd')
    if value is not None:
        if not isinstance(old,(int,float)) or isinstance(old,bool) or not math.isfinite(old) or abs(old-value)>1e-6:
            raise ValueError('saved indicative result mismatch')
    elif old is not None:
        raise ValueError('saved depth result mismatch')
    base.update(decision='REJECT_DEPTH' if not estimate['book_fillable'] else 'OBSERVATION_ONLY_NOT_EXECUTABLE',
                gross_spread_usd=estimate.get('gross_spread_usd'),net_after_buffer_usd=value,
                pair_capture_duration_ms=end-start)
    return base


def audit(paths):
    if not 1<=len(paths)<=100:raise ValueError('snapshot files must be 1..100')
    records=[]; seen=set();file_records=[];duplicate_observations=0
    for path in paths:
        payload,file_hash=read_snapshot(path)
        shares=payload.get('requested_shares'); buffer=payload.get('fee_buffer_usd')
        if not isinstance(shares,(int,float)) or isinstance(shares,bool) or not math.isfinite(shares) or shares<=0:
            raise ValueError('invalid requested shares')
        if not isinstance(buffer,(int,float)) or isinstance(buffer,bool) or not math.isfinite(buffer) or buffer<0:
            raise ValueError('invalid fee buffer')
        file_records.append({'path':str(path),'file_sha256':file_hash,'observations':len(payload['snapshots'])})
        for item in payload['snapshots']:
            row=observation(item,shares,buffer)
            key=(row['condition_id'],row['observation_sha256'])
            if key in seen:
                duplicate_observations+=1
                continue
            seen.add(key)
            row['source_file_sha256']=file_hash
            records.append(row)
    return {'research_only':True,'schema_version':2,'files':file_records,'unique_observations':len(records),
            'duplicate_observations_removed':duplicate_observations,
            'positive_indicative_observations':sum((r.get('net_after_buffer_usd') or 0)>0 for r in records),
            'verified_executable_trades':0,'realized_profit_usd':None,
            'warning':'File hash identifies full snapshot; observation hash identifies individual market record. Non-atomic order books cannot prove executable profits. No verified quote age, live fill, custody or settlement.',
            'records':records}


def main():
    p=argparse.ArgumentParser(description='CQWE offline V15 evidence audit. No network/orders.')
    p.add_argument('--inputs',nargs='+',required=True)
    p.add_argument('--output',default='reports/v16_provenance.json')
    args=p.parse_args()
    result=audit(args.inputs)
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2,ensure_ascii=False))
    print('CQWE_V16_OFFLINE_PROVENANCE_PASS | NO ORDERS')

if __name__=='__main__':main()
