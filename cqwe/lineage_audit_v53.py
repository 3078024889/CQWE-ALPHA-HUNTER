"""Read-only all-generation evidence and disk inventory. No repair or deletion."""
import argparse, json, shutil, time
from pathlib import Path
from .memory_v52 import load, ROOT

SYMBOLS=('BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT')

def audit(root=ROOT):
    root=Path(root)
    symbols={}; failures={}
    for symbol in SYMBOLS:
        begin=time.monotonic_ns()
        try:
            last,sha=load(root,symbol)
            count=last['generation'] if last else 0
            symbols[symbol]={'generations':count,'latest_sha256':sha,
                'verified_historical_sources':count,'last_settled':last['settled_events'] if last else 0,
                'audit_duration_ms':round((time.monotonic_ns()-begin)/1e6,2)}
        except Exception as ex:
            failures[symbol]={'type':type(ex).__name__,'error':str(ex)}
    total=0
    if root.is_dir():
        total=sum(f.stat().st_size for f in root.rglob('*') if f.is_file())
    return {'schema':'CTI_V53_LINEAGE_AUDIT','symbols':symbols,'failures':failures,
        'all_valid':not failures and len(symbols)==4,
        'memory_bytes':total,'real_orders':0,'real_profit_usd':0,
        'research_only':True,'evidence_deleted':False}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(ROOT));args=ap.parse_args()
    result=audit(args.root)
    print('CQWE_V53_LINEAGE '+json.dumps(result,sort_keys=True,ensure_ascii=False),flush=True)
    if not result['all_valid']:raise SystemExit(2)

if __name__=='__main__':main()
