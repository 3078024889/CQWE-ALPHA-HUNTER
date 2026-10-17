"""Bounded public-source probe; no account actions or strategy promotion."""
from pathlib import Path
import json
import time
from cqwe.global_event_context import GlobalContext,FEEDS
from cqwe.market_evidence import MarketEvidence
from cqwe.liquidation_watch import LiquidationWatch
from cqwe.event_forward_loop import capture
from cqwe.local_autopilot import atomic


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--market-only',action='store_true');args=parser.parse_args()
    news=GlobalContext('D:/CQWE_DATA/workbench_v1/global_news')
    statuses=[]
    for _ in (() if args.market_only else FEEDS):
        statuses.append(news.poll_one());print(json.dumps(statuses[-1]),flush=True)
    watch=LiquidationWatch();watch.start();evidence=MarketEvidence();samples={};errors={}
    try:
        for symbol in ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT'):
            try:
                q=capture(symbol);at=time.time_ns()//1000000
                batch=evidence.capture(symbol,q,watch.snapshot(symbol,at))
                samples[symbol]=evidence.frame(symbol,q,batch,time.time_ns()//1000000)
            except Exception as exc:errors[symbol]=str(exc)
        at=time.time_ns()//1000000
        report={'at_ms':at,'news':news.snapshot(at),'market_samples':samples,'errors':errors,
                'stream':watch.snapshot('BTCUSDT',at),'real_orders':0,'profitability_proven':False}
        atomic(Path('reports/market_event_source_probe_20261016.json'),report)
        print(json.dumps({'market':samples,'errors':errors,'fresh_news':report['news']['fresh_sources'],
                          'stream_connected':report['stream']['connected']}),flush=True)
    finally:watch.close()


if __name__=='__main__':main()
