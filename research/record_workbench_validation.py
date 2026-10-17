"""Record observed scoped test output and actual local UI-run artifacts."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from urllib.request import urlopen

from cqwe.local_autopilot import atomic


def main():
    with urlopen('http://127.0.0.1:8765/api/state',timeout=3) as stream:state=json.load(stream)
    archive=Path('D:/CQWE_DATA/workbench_ui_validation_20261016/paper.sqlite3')
    with sqlite3.connect(archive) as db:
        payload,sha=db.execute('SELECT payload,hash FROM state WHERE id=1').fetchone()
    if hashlib.sha256(payload.encode()).hexdigest()!=sha:raise ValueError('ARCHIVED_UI_ACCOUNT_HASH')
    test=json.loads(payload)
    assert len(test['trades'])==1 and not test['positions']
    assert not state['account']['positions']
    assert state['account']['cash']=='10' and state['real_orders']==0
    report={'observed_ms':time.time_ns()//1000000,
        'tests':{'count':115,'passed':True,'evidence':'Observed python -m unittest output, 2026-10-16, 115 tests in 3.823s, OK',
                 'scope':'workbench, paper_observer and nine existing event/liquidity/runner modules'},
        'browser':'Playwright CLI with installed Chrome, isolated cqwe-ui session',
        'ui_steps_verified':['manual mode selection','start','real public four-asset quote capture',
              'manual virtual long entry','manual virtual close','automatic start','pause',
              'desktop 1440x1100','mobile 390x844 without horizontal overflow'],
        'archived_ui_roundtrips':1,'archived_paper_net_pnl':str(float(test['cash'])-10),
        'archived_test_path':str(archive),'user_paper_cash':state['account']['cash'],
        'user_paper_positions':len(state['account']['positions']),'user_sampling_active':state['account']['running'],
        'launcher_test':'Hidden local service started and default browser opened successfully',
        'startup_registration_added':False,'real_orders':0,'profitability_proven':False,
        'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path('cqwe/workbench.py'),Path('cqwe/paper_observer.py'),Path('workbench/index.html'),
             Path('workbench/app.js'),Path('workbench/style.css'),Path('START_COPERNICAN_WORKBENCH.ps1')]}}
    atomic(Path('reports/workbench_validation_20261016.json'),report)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
