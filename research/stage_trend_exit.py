"""Archive the paper stage, preserving any held position before exit-rule migration."""
import json
from pathlib import Path
import sqlite3
import time
from urllib.request import urlopen,Request
from cqwe.local_autopilot import atomic


def main():
    base='http://127.0.0.1:8765';before=json.load(urlopen(base+'/api/state',timeout=3))
    token=json.loads(urlopen(base+'/bootstrap.js',timeout=3).read().decode().split('=',1)[1].rstrip(';'))
    data=json.dumps({'action':'pause','request_id':'trend-stage-'+str(time.time_ns())}).encode()
    json.load(urlopen(Request(base+'/api/action',data=data,headers={'Content-Type':'application/json','X-CQWE-Token':token}),timeout=3))
    root=Path('D:/CQWE_DATA/workbench_v1');archive=root/'stage_archives'/('before_trend_exit_'+str(time.time_ns()));archive.mkdir(parents=True)
    with sqlite3.connect(root/'paper.sqlite3') as db:
        with sqlite3.connect(archive/'paper.sqlite3') as backup:db.backup(backup)
    report={'before':before,'archive':str(archive),'resume_automatic':before['account']['automatic'] and before['account']['running'],
            'at_ms':time.time_ns()//1000000,'real_orders':0}
    atomic(Path('reports/trend_exit_transition_20261016.json'),report)
    print(json.dumps({'archive':str(archive),'held':list(before['account']['positions']),'resume_automatic':report['resume_automatic']}))


if __name__=='__main__':main()
