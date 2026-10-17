"""Pause and snapshot the existing paper-only stage before changing leverage."""
import json
from pathlib import Path
import sqlite3
import time
from urllib.request import urlopen,Request
from cqwe.local_autopilot import atomic


def main():
    base='http://127.0.0.1:8765'
    before=json.load(urlopen(base+'/api/state',timeout=3))
    if before['account']['positions']:raise ValueError('Existing positions require unchanged exit monitoring before migration')
    token=json.loads(urlopen(base+'/bootstrap.js',timeout=3).read().decode().split('=',1)[1].rstrip(';'))
    data=json.dumps({'action':'pause','request_id':'leverage-stage-'+str(time.time_ns())}).encode()
    json.load(urlopen(Request(base+'/api/action',data=data,headers={'Content-Type':'application/json','X-CQWE-Token':token}),timeout=3))
    target=Path('D:/CQWE_DATA/workbench_v1/stage_archives')/str(time.time_ns());target.mkdir(parents=True)
    for name in ('paper.sqlite3','events.sqlite3'):
        src=Path('D:/CQWE_DATA/workbench_v1')/name
        if src.exists():
            with sqlite3.connect('file:'+src.as_posix()+'?mode=ro',uri=True) as original:
                with sqlite3.connect(target/name) as backup:original.backup(backup)
    report={'at_ms':time.time_ns()//1000000,'previous_leverage':1,'target_leverage':10,
            'before':before,'archive':str(target),'resume_automatic':before['account']['running'] and before['account']['automatic'],
            'real_orders':0}
    atomic(Path('reports/leverage_stage_transition_20261016.json'),report)
    print(json.dumps({'archive':str(target),'resume_automatic':report['resume_automatic'],'labels':before['book_labels']}))


if __name__=='__main__':main()
