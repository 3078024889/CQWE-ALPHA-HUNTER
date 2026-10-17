"""V44 fixed four-asset, public-data-only L2 collection and evidence review.

Parallel bounded probes; no orders, no auto choice of winners, no trade access.
All new records reside on D:, each symbol in its own append-only V43 session.
"""
from __future__ import annotations
import argparse, concurrent.futures, json, os, shutil, time
from pathlib import Path
from .l2_replay_v42 import SYMBOLS
from .l2_trade_capture_v43 import live
from .market_replay_v43 import read_chain

FOUR = ('BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT')
ROOT = Path('D:/CQWE_DATA/l2_v44')
MIN_DISK_FREE = 300 * 1024 * 1024
MAX_OBS_FILE = 128 * 1024 * 1024


def ensure_d_root(root=ROOT, *, free_bytes=None):
    path=Path(root).resolve()
    if os.name == 'nt' and path.drive.upper() != 'D:' and not (os.environ.get("CQWE_ALLOW_NON_D_MEMORY_TESTS") == "1" and os.path.normcase(os.path.abspath(os.fspath(path))).startswith(os.path.normcase(os.path.abspath(os.environ.get("TEMP", os.path.join(os.environ.get("SystemDrive", "C:"), "Windows", "Temp")))) + os.sep)):
        raise ValueError('V44_D_DRIVE_REQUIRED')
    # Windows D: is not a POSIX drive; for tests on Unix accept only explicit
    # test paths passed in, while the actual default is always D:.
    if root == ROOT and not str(ROOT).upper().startswith('D:'):
        raise ValueError('V44_INVALID_DEFAULT_ROOT')
    path.mkdir(parents=True, exist_ok=True)
    available = shutil.disk_usage(path).free if free_bytes is None else free_bytes
    if available < MIN_DISK_FREE:
        raise RuntimeError('V44_LOW_DISK_SPACE_FAIL_CLOSED')
    return path


def inspect_capture(file, symbol):
    path=Path(file)
    if not path.is_file() or path.stat().st_size > MAX_OBS_FILE:
        raise ValueError('V44_MISSING_OR_OVERSIZED_CAPTURE')
    rows=read_chain(path)
    starts=[r for r in rows if r['kind']=='START']
    stops=[r for r in rows if r['kind']=='STOP']
    if len(starts)!=1 or len(stops)!=1 or rows[-1]['kind']!='STOP':
        raise ValueError('V44_INCOMPLETE_SESSION')
    if starts[0]['payload'].get('symbol')!=symbol:
        raise ValueError('V44_WRONG_SYMBOL')
    if not starts[0]['payload'].get('synced') or not stops[0]['payload'].get('synced'):
        raise ValueError('V44_UNSYNCHRONIZED_SESSION')
    books=[r for r in rows if r['kind']=='BOOK']
    trades=[r for r in rows if r['kind']=='TRADE' and not r['payload'].get('pre_sync')]
    spreads=[]
    for r in books:
        p=r['payload']; b=float(p['bid']); a=float(p['ask'])
        if b<=0 or a<=b or p.get('synced') is not True:
            raise ValueError('V44_INVALID_BOOK')
        spreads.append(20000*(a-b)/(a+b))
    if not books or not trades:
        raise ValueError('V44_NO_FULL_MARKET_OBSERVATIONS')
    return {'symbol':symbol,'file':str(path),'bytes':path.stat().st_size,
            'book_samples':len(books),'post_sync_trades':len(trades),
            'median_spread_bps':sorted(spreads)[len(spreads)//2],
            'session_verified':True,'profitability_proven':False,
            'real_fills_known':False,'order_queue_position_known':False}


def collect_four(seconds=75, root=ROOT, *, collector=live, free_bytes=None):
    if not isinstance(seconds,int) or not 65<=seconds<=180:
        raise ValueError('V44_CAPTURE_SECONDS_OUT_OF_BOUNDS')
    base=ensure_d_root(root,free_bytes=free_bytes)
    # Never assert a complete four-market observation when one venue fails.
    successes={}; failures={}; started=time.time_ns()
    def one(symbol):
        sub=base/symbol;sub.mkdir(exist_ok=True)
        out=collector(symbol=symbol,seconds=seconds,root=sub)
        return inspect_capture(out['file'],symbol)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4,thread_name_prefix='cqwe-v44') as pool:
        pending={pool.submit(one,s):s for s in FOUR}
        for future in concurrent.futures.as_completed(pending):
            symbol=pending[future]
            try: successes[symbol]=future.result()
            except Exception as exc:failures[symbol]=f'{type(exc).__name__}:{str(exc)[:180]}'
    report={'version':'CQWE_V44_FOUR_ASSET_L2','symbols':list(FOUR),
            'started_ns':started,'completed_ns':time.time_ns(),
            'data_root':str(base),'markets':{s:successes[s] for s in FOUR if s in successes},
            'failures':{s:failures[s] for s in FOUR if s in failures},
            'all_four_valid':len(successes)==4 and not failures,
            'costs_realized_usd':0,'real_orders':0,'real_profit_usd':0,
            'winner_selected':False,'profitable_edge_proven':False,
            'interpretation':'Capture quality and spreads only; no independent executable OOS fills.'}
    reports=base/'reports';reports.mkdir(exist_ok=True)
    report_path=reports/f'four_asset_{started}.json'
    with report_path.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    report['report_file']=str(report_path)
    return report


def audit(root=ROOT):
    base=Path(root)
    results={}
    for symbol in FOUR:
        folder=base/symbol
        valid=0;invalid=0;latest=None
        if folder.exists():
            for file in sorted(folder.glob('*.jsonl')):
                try: info=inspect_capture(file,symbol)
                except (ValueError,KeyError,TypeError,UnicodeError,json.JSONDecodeError):invalid+=1
                else:valid+=1;latest=info
        results[symbol]={'valid_sessions':valid,'invalid_sessions':invalid,'latest':latest}
    return {'version':'CQWE_V44_FOUR_ASSET_AUDIT','symbols':results,
            'profitability_proven':False,'real_profit_usd':0,'no_orders':True}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=int,default=75)
    parser.add_argument('--root',default=str(ROOT))
    parser.add_argument('--audit-only',action='store_true')
    a=parser.parse_args()
    result=audit(a.root) if a.audit_only else collect_four(a.seconds,a.root)
    print('CQWE_V44_FOUR_ASSET '+json.dumps(result,sort_keys=True))
    print('PUBLIC REAL L2+TRADES | D DRIVE ONLY | NO ORDERS | NO PROFIT CLAIM')
    if not a.audit_only and not result['all_four_valid']:
        raise SystemExit(2)
if __name__=='__main__':main()
