"""Pause paper entries and preserve an online SQLite backup before router change."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from urllib.request import Request,urlopen


def main():
    base='http://127.0.0.1:8765'
    token=json.loads(urlopen(base+'/bootstrap.js',timeout=3).read().decode().split('=',1)[1].rstrip(';'))
    request=json.dumps({'action':'pause','request_id':'portfolio-stage-'+str(time.time_ns())}).encode()
    json.load(urlopen(Request(base+'/api/action',data=request,headers={'Content-Type':'application/json','X-CQWE-Token':token}),timeout=3))
    state=json.load(urlopen(base+'/api/state',timeout=3))
    root=Path('D:/CQWE_DATA/workbench_v1');archive=root/'stage_archives'/('before_portfolio_router_'+str(time.time_ns()))
    archive.mkdir(parents=True)
    with sqlite3.connect(root/'paper.sqlite3') as db:
        with sqlite3.connect(archive/'paper.sqlite3') as backup:db.backup(backup)
    trades=state['account']['trades']
    result={'at_ms':time.time_ns()//1000000,'archive':str(archive),'cash':state['account']['cash'],
        'fees':state['account']['fees'],'position_symbols':list(state['account']['positions']),
        'trade_count':len(trades),'trades_sha256':hashlib.sha256(json.dumps(trades,sort_keys=True).encode()).hexdigest(),
        'trades':[{k:t.get(k) for k in ('symbol','direction','source','opened_ms','closed_ms','reason','net_pnl','entry_fee','exit_fee')} for t in trades],
        'restart_entries':False,'real_orders':0}
    Path('reports/portfolio_router_transition_20261016.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('archive','cash','fees','trade_count','position_symbols')}))


if __name__=='__main__':main()
