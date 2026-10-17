"""Gather finished V3 tests, public event samples and restart evidence."""
import json
import hashlib
from pathlib import Path
import time

from cqwe.four_market_runner import checked,sources
from cqwe.local_autopilot import atomic,accepted


if __name__=='__main__':
    repo=Path(__file__).resolve().parents[1]
    smoke=Path('D:/CQWE_DATA/local_v3_smoke_20261015')
    rows=[]
    for p in smoke.glob('sessions/*/round_*/report.json'):
        report=checked(json.loads(p.read_text(encoding='utf-8')))
        state=checked(json.loads((p.parent/'state.json').read_text(encoding='utf-8')))
        if (state['source_sha256']!=sources() or report['state_sha256']!=state['sha256']
                or len(report['checks'])!=10 or not all(report['checks'].values())):
            raise ValueError('SMOKE_NOT_VERIFIED')
        rows.append({'path':str(p),'state_sha256':state['sha256'],'previous':state['previous'],
                     'round':state['engine']['rounds'],'checks':report['checks'],'summary':report['summary']})
    rows.sort(key=lambda r:r['round'])
    if len(rows)!=2 or rows[1]['previous']!=rows[0]['state_sha256']:
        raise ValueError('RESTART_LINEAGE_NOT_VERIFIED')
    tests=json.loads((repo/'reports/local_v3_test_results_20261015.json').read_text())
    targeted=json.loads((repo/'reports/local_v3_targeted_results_20261015.json').read_text())
    if not tests['success'] or not targeted['success']:
        raise ValueError('REGRESSION_FAILED')
    prod=Path('D:/CQWE_DATA/copernican_local_v3')
    status=checked(json.loads((prod/'status.json').read_text(encoding='utf-8')))
    if status['status']!='OBSERVING' or time.time_ns()-status['observed_ns']>120_000_000_000:
        raise ValueError('SERVICE_NOT_RECENTLY_OBSERVING')
    history=checked(json.loads((prod/'history_state.json').read_text(encoding='utf-8')))
    startup=Path.home()/'AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/CQWE Copernican Research.lnk'
    event=checked(json.loads(Path('D:/CQWE_DATA/cpi_20261014_event_study/report.json').read_text(encoding='utf-8')))
    news=checked(json.loads((prod/'official_news/status.json').read_text(encoding='utf-8')))
    result={'schema':'CQWE_LOCAL_V3_VALIDATION','source_sha256':sources(),'tests':tests,
            'targeted_after_event_expansion':targeted,
            'additional_source_sha256':{n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in
                ('cqwe/local_autopilot.py','cqwe/historical_curriculum.py','cqwe/macro_events.py',
                 'cqwe/event_catalog.py','cqwe/news_watch.py','START_COPERNICAN_LOCAL.ps1')},
            'restart_rounds':rows,'local_service_status_snapshot':status,
            'history_labels':{s:d['labels'] for s,d in history['symbols'].items()},
            'history_labels_are_retrospective':True,'history_weights_transferred_to_live':False,
            'event_study':event,'official_news_status':news,'startup_shortcut_exists':startup.exists(),
            'startup_trigger':'WINDOWS_USER_LOGON','restart_after_actual_reboot_tested':False,
            'cloud_accessed':False,'live_orders':0,'profitability_proven':False,
            'automatic_arbitrary_code_rewriting':False,'automatic_macro_training_connected':False,
            'observed_ns':time.time_ns()}
    target=repo/'reports/local_v3_validation_20261015.json';atomic(target,result)
    print(json.dumps({'report':str(target),'tests':tests,'restart_rounds':len(rows),
                      'history_labels':result['history_labels'],'startup':startup.exists(),
                      'service_status':status['status'],'event_clusters':event['distinct_event_clusters']}))
