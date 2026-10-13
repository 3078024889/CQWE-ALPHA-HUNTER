"""Unified bounded CLI; public GET-only or offline; never places trades."""
import argparse
import datetime as dt
import json
from pathlib import Path
from .core import save_json
from .history import download
from .market import discover,snapshot,historical_oi
from .research import walkforward


def main():
    ap=argparse.ArgumentParser(prog='cqwe',description='CQWE V0.5 research only. NO ORDER API.')
    sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('fetch');p.add_argument('--symbols',nargs='+',default=['BTCUSDT','ETHUSDT']);p.add_argument('--days',type=int,default=7)
    p=sub.add_parser('scan');p.add_argument('--count',type=int,default=10)
    p=sub.add_parser('oi');p.add_argument('--symbol',default='BTCUSDT');p.add_argument('--limit',type=int,default=100)
    p=sub.add_parser('study');p.add_argument('--input',required=True);p.add_argument('--out',default='reports/v05_study.json')
    p.add_argument('--fee-bps',type=float,default=5);p.add_argument('--slippage-bps',type=float,default=2)
    p=sub.add_parser('demo')
    args=ap.parse_args()
    if args.command=='fetch':result=download(args.symbols,args.days)
    elif args.command=='scan':
        if not 1<=args.count<=30: ap.error('--count must be 1..30')
        result=[]
        for symbol in discover(args.count):
            try: result.append(snapshot(symbol))
            except (RuntimeError,ValueError) as e:result.append({'symbol':symbol,'error':str(e)})
        save_json('data/snapshots/latest.json',result)
    elif args.command=='oi':
        series=historical_oi(args.symbol,limit=args.limit)
        result={'symbol':args.symbol,'series':series,'disclaimer':'OI historical value not equivalent to net capital inflow'}
        save_json(f'data/oi/{args.symbol}_latest.json',result)
    elif args.command=='study':
        candles=json.loads(Path(args.input).read_text(encoding='utf-8'))
        result=walkforward(candles,fee_bps=args.fee_bps,slippage_bps=args.slippage_bps)
        save_json(args.out,result)
    else:
        from .paper import Ledger
        l=Ledger(); l.buy(100);l.sell(101)
        result={'cash':round(l.cash,6),'fees':round(l.fees,6),'trades':l.trades,'simulation_only':True}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('CQWE_V05_RESEARCH_PASS | NO API KEY | NO ORDERS')

if __name__=='__main__':main()
