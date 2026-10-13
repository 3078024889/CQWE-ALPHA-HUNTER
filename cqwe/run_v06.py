"""One-shot, read-only V06 commands, no background process."""
import argparse
import json
from .validation import study_file
from .history import download
from .market import historical_oi, discover, snapshot
from .core import save_json

def main():
    p=argparse.ArgumentParser(description='CQWE V06 consolidated RESEARCH ONLY (NO ORDER API)')
    sub=p.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('compare');a.add_argument('--input',required=True);a.add_argument('--out',default='reports/v06_comparison.json')
    a=sub.add_parser('fetch');a.add_argument('--days',type=int,default=7);a.add_argument('--symbols',nargs='+',default=['BTCUSDT','ETHUSDT'])
    a=sub.add_parser('oi');a.add_argument('--symbol',default='BTCUSDT');a.add_argument('--limit',type=int,default=100)
    a=sub.add_parser('scan');a.add_argument('--count',type=int,default=10)
    args=p.parse_args()
    if args.mode=='compare': result=study_file(args.input,args.out)
    elif args.mode=='fetch':result=download(args.symbols,args.days)
    elif args.mode=='oi':
        result=historical_oi(args.symbol,limit=args.limit);save_json(f'data/oi/{args.symbol}_v06.json',result)
    else:
        if not 1<=args.count<=20: p.error('count must be 1..20')
        result=[]
        for symbol in discover(limit=args.count):
            try:result.append(snapshot(symbol))
            except (RuntimeError,ValueError) as e:result.append({'symbol':symbol,'error':str(e)})
        save_json('data/snapshots/v06_latest.json',result)
    if args.mode=='compare':
        for period, strategies in result['outcomes'].items():
            for name,record in strategies.items():
                print(f"{period:15} {name:9} trades={len(record['trades']):3d} net={record['net_profit']:+.6f} maxDD={record['max_drawdown_pct']:.3f}%")
    else:print(json.dumps(result,ensure_ascii=False,indent=2))
    print('CQWE_V06_RESEARCH_PASS | NO ORDERS')

if __name__=='__main__':main()
