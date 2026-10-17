"""Single-worker, cached event-window study; no trading or resident service."""
import argparse
import collections
import json
import math
import os
from pathlib import Path
import statistics
import time
import hashlib

from cqwe.historical_curriculum import public
from cqwe.four_market_core import SYMBOLS
from cqwe.local_autopilot import atomic
from cqwe.macro_events import responses
from cqwe.copernican_experiment_v81_v85 import digest


def daily_window(event,symbol,root):
    t=event['scheduled_ms'];path=root/'candles'/f'{symbol}_DAY_{t}.json'
    if path.exists():
        from cqwe.four_market_runner import checked
        raw=checked(json.loads(path.read_text(encoding='utf-8')))['raw']
    else:
        raw=public('klines',{'symbol':symbol,'interval':'1h','startTime':t,
                            'endTime':t+86400000-1,'limit':24})
        atomic(path,{'raw':raw,'symbol':symbol,'anchor_ms':t,'observed_ns':time.time_ns(),
                     'source':'BINANCE_USDM_PUBLIC_1H'});time.sleep(.15)
    if (len(raw)!=24 or [r[0] for r in raw]!=list(range(t,t+86400000,3600000))):
        raise ValueError('DATE_LEVEL_WINDOW_MISSING_HOURS')
    prices=[float(r[1]) for r in raw]+[float(r[4]) for r in raw]
    if not all(math.isfinite(p) and p>0 for p in prices):raise ValueError('DATE_LEVEL_PRICE')
    return {'event_id':event['event_id'],'event_type':event['event_type'],'symbol':symbol,
            'anchor_ms':t,'local_date':event['local_date'],'time_granularity':'DATE_ONLY',
            'local_midnight_24h_return_bps':(float(raw[-1][4])/float(raw[0][1])-1)*10000,
            'announcement_time_known':False,'causality_identified':False,'execution_eligible':False}


def window(event,symbol,root):
    t=((event['scheduled_ms']+59999)//60000)*60000
    path=root/'candles'/f'{symbol}_{t}.json'
    if path.exists():
        payload=json.loads(path.read_text(encoding='utf-8'))
        from cqwe.four_market_runner import checked
        checked(payload)
        raw=payload['raw']
    else:
        raw=public('klines',{'symbol':symbol,'interval':'1m','startTime':t-3600000,
                             'endTime':t+3600000-1,'limit':120})
        if not isinstance(raw,list):raise ValueError('CANDLE_RESPONSE_SCHEMA')
        atomic(path,{'raw':raw,'symbol':symbol,'anchor_ms':t,'observed_ns':time.time_ns(),
                     'source':'BINANCE_USDM_PUBLIC_1M'})
        time.sleep(.15)
    bars=[]
    for row in raw:
        if not isinstance(row,list) or len(row)!=12 or row[6]!=row[0]+59999:
            raise ValueError('CANDLE_SCHEMA')
        nums=list(map(float,row[1:6]))
        if not all(math.isfinite(n) for n in nums) or min(nums[:4])<=0 or nums[4]<0:
            raise ValueError('CANDLE_VALUES')
        bars.append({'time':row[0],'open':nums[0],'high':nums[1],'low':nums[2],
                     'close':nums[3],'volume':nums[4]})
    result=responses(event,symbol,bars)
    result['event_type']=event['event_type'];result['timing_status']=event['timing_status']
    by={b['time']:b for b in bars}
    for r in result['responses']:
        h=r['horizon'];pre=[by.get(i) for i in range(t-h*1000,t,60000)]
        r['pre_return_bps']=(pre[-1]['close']/pre[0]['open']-1)*10000 if all(pre) else None
        after=[by.get(i) for i in range(t,t+h*1000,60000)]
        if all(after):
            r['range_bps']=(max(b['high'] for b in after)-min(b['low'] for b in after))/after[0]['open']*10000
            r['max_upper_wick_bps']=max((b['high']-max(b['open'],b['close']))/b['open']*10000 for b in after)
            r['max_lower_wick_bps']=max((min(b['open'],b['close'])-b['low'])/b['open']*10000 for b in after)
            r['volume_ratio_to_pre_window']=sum(b['volume'] for b in after)/(sum(b['volume'] for b in pre)+1e-12) if all(pre) else None
    return result


def summarize(events,results):
    by=collections.defaultdict(list)
    for row in results:
        for r in row['responses']:
            if r['status']=='OBSERVED':by[(row['event_type'],row['symbol'],r['horizon'])].append((row,r))
    stats=[]
    for (kind,symbol,h),rows in sorted(by.items()):
        post=[r['return_bps'] for _,r in rows]
        diffs=[abs(r['return_bps'])-abs(r['pre_return_bps']) for _,r in rows if r['pre_return_bps'] is not None]
        stats.append({'event_type':kind,'symbol':symbol,'horizon':h,'events':len({a['cluster_id'] for a,_ in rows}),
                      'up_fraction':sum(v>0 for v in post)/len(post),'mean_return_bps':statistics.mean(post),
                      'median_abs_return_bps':statistics.median(map(abs,post)),
                      'median_abs_change_vs_pre_bps':statistics.median(diffs) if diffs else None,
                      'median_range_bps':statistics.median(r['range_bps'] for _,r in rows),
                      'max_wick_bps':max(max(r['max_lower_wick_bps'],r['max_upper_wick_bps']) for _,r in rows),
                      'selection_corrected':False,'causality_identified':False})
    return {'statistics':stats,'complete_market_windows':len(results),
            'requested_events':len(events),'real_orders':0,'profitability_proven':False,
            'interpretation':'Scheduled/standard-time windows, not all independently verified actual announcements; pre-window is not an independent counterfactual.',
            'calendar_rows_are_not_surprise_features':True}


def run(catalog,root,max_windows=None):
    if os.name=='nt':
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
    root=Path(root);(root/'candles').mkdir(parents=True,exist_ok=True)
    catalog_bytes=Path(catalog).read_bytes();data=json.loads(catalog_bytes);events=data['events']
    catalog_sha=hashlib.sha256(catalog_bytes).hexdigest()
    study_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    snapshot=root/f'catalog_{catalog_sha}.json'
    if not snapshot.exists():snapshot.write_bytes(catalog_bytes)
    coevents=collections.defaultdict(list)
    for e in events:
        if e['time_granularity']=='MINUTE':coevents[e['scheduled_ms']].append(e['event_type'])
    results=[];failed=[];date_only=[];windows=0;files=[];daily_files=[]
    target_count=4*sum(e['time_granularity']=='MINUTE' for e in events)
    for e in events:
        e={**e,'simultaneous_types':sorted(set(coevents[e['scheduled_ms']]))}
        day_only=e['time_granularity']!='MINUTE'
        if day_only:date_only.append(e['event_id'])
        version=digest({'event':e,'study_sha256':study_sha})[:16]
        for symbol in SYMBOLS:
            target=root/'results'/f"{e['event_id']}_{version}_{symbol}.json";target.parent.mkdir(exist_ok=True)
            if target.exists():
                from cqwe.four_market_runner import checked
                result=checked(json.loads(target.read_text(encoding='utf-8')))
            else:
                if max_windows is not None and windows>=max_windows:break
                try:
                    result=daily_window(e,symbol,root) if day_only else window(e,symbol,root)
                    result.update(event_input=e,study_sha256=study_sha)
                    atomic(target,result);windows+=1
                except Exception as exc:
                    failed.append({'event':e['event_id'],'symbol':symbol,'error':str(exc)});continue
            if day_only:
                daily_files.append(str(target));continue
            results.append(result);files.append(str(target))
            if len(results)%20==0:
                atomic(root/'progress.json',{'completed':len(results),'target':target_count,
                    'last_event':e['event_id'],'observed_ns':time.time_ns(),'failures':failed})
                print(json.dumps({'completed':len(results),'last_event':e['event_id']}),flush=True)
        if max_windows is not None and windows>=max_windows:break
    report=summarize(events,results);report.update(failures=failed,date_only_excluded=date_only,
        catalog_snapshot=str(snapshot),catalog_sha256=catalog_sha,study_sha256=study_sha,
        newly_generated_windows=windows,observed_ns=time.time_ns(),result_files=files,
        day_result_files=daily_files,daily_responses_count=len(daily_files),
        intraday_target=target_count,all_intraday_windows_complete=len(results)==target_count)
    atomic(root/'impact_report.json',report)
    print(json.dumps({'report':str(root/'impact_report.json'),'complete':len(results),'failures':len(failed)}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--catalog',default='reports/event_history_catalog_20261016.json')
    p.add_argument('--root',default='D:/CQWE_DATA/event_history_20261016');p.add_argument('--max-windows',type=int)
    a=p.parse_args();run(a.catalog,a.root,a.max_windows)
