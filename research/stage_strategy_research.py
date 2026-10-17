"""Preserve the current paper ledger before enabling an independent shadow bench."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from urllib.request import Request,urlopen


def main():
    base='http://127.0.0.1:8765'
    token=json.loads(urlopen(base+'/bootstrap.js',timeout=3).read().decode().split('=',1)[1].rstrip(';'))
    data=json.dumps({'action':'pause','request_id':'strategy-research-stage-'+str(time.time_ns())}).encode()
    json.load(urlopen(Request(base+'/api/action',data=data,headers={'Content-Type':'application/json','X-CQWE-Token':token}),timeout=3))
    s=json.load(urlopen(base+'/api/state',timeout=3));root=Path('D:/CQWE_DATA/workbench_v1')
    archive=root/'stage_archives'/('before_strategy_shadow_'+str(time.time_ns()));archive.mkdir()
    with sqlite3.connect(root/'paper.sqlite3') as db:
        with sqlite3.connect(archive/'paper.sqlite3') as target:db.backup(target)
    r={'at_ms':time.time_ns()//1000000,'archive':str(archive),'cash':s['account']['cash'],'fees':s['account']['fees'],
       'positions':s['account']['positions'],'trade_count':len(s['account']['trades']),
       'trades_sha256':hashlib.sha256(json.dumps(s['account']['trades'],sort_keys=True).encode()).hexdigest(),
       'new_entries_paused':True,'observation_enabled':s['account'].get('observation_enabled'),'real_orders':0}
    Path('reports/strategy_research_transition_20261016.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
    print(json.dumps({k:r[k] for k in ('archive','cash','trade_count','new_entries_paused')}))


if __name__=='__main__':main()
