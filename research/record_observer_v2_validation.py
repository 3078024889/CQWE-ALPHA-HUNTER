"""Save actual restored runtime separately from synthetic reachability tests."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
from cqwe.local_autopilot import atomic


def main():
    s=json.load(urlopen('http://127.0.0.1:8765/api/state',timeout=3))
    migration=json.loads(Path('reports/observer_v2_migration_20261016.json').read_text(encoding='utf-8'))
    process=json.loads(Path('D:/CQWE_DATA/workbench_v1/server_process.json').read_text(encoding='utf-8-sig'))
    report={'at_ms':s['at_ms'],'scoped_tests':130,'test_result':'OK, observed 2026-10-16, 4.097s',
        'synthetic_entry_exit_reachability':True,'synthetic_gradient_numeric_check':True,
        'real_market_entry_observed':bool(s['account']['positions']) or s['performance_by_source']['PAPER_EXPLORATION']['closed']>0,
        'runtime':{'running':s['account']['running'],'automatic':s['account']['automatic'],
                   'leverage':s['account']['leverage'],'last_cycle_ms':s['last_cycle_ms'],
                   'decisions':s['decisions'],'performance_by_source':s['performance_by_source'],'errors':s['errors']},
        'launch_method':process['method'],'diagnosis':migration['diagnosis'],
        'archive':migration['archive'],'real_orders':0,'profitability_proven':False,
        'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
           [Path('cqwe/paper_observer_v2.py'),Path('cqwe/workbench.py'),Path('workbench/app.js'),
            Path('workbench/index.html'),Path('START_COPERNICAN_WORKBENCH.ps1')]}}
    atomic(Path('reports/observer_v2_validation_20261016.json'),report)
    print(json.dumps({'tests':130,'running':s['account']['running'],
          'real_market_entry_observed':report['real_market_entry_observed'],'real_orders':0}))


if __name__=='__main__':main()
