"""Check retained real evidence, source hashes, forecast chronology and coverage."""
import hashlib
import json
from pathlib import Path

from cqwe.four_market_runner import checked
from cqwe.local_autopilot import atomic


if __name__=='__main__':
    root=Path('D:/CQWE_DATA/event_history_20261016')
    impact=checked(json.loads((root/'impact_report.json').read_text(encoding='utf-8')))
    snapshot=Path(impact['catalog_snapshot']);catalog=json.loads(snapshot.read_text(encoding='utf-8'))
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==impact['catalog_sha256']
    assert hashlib.sha256(Path('research/event_history_impact.py').read_bytes()).hexdigest()==impact['study_sha256']
    assert impact['all_intraday_windows_complete'] and not impact['failures']
    seen=set();source_paths={}
    for p in impact['result_files']+impact['day_result_files']:
        r=checked(json.loads(Path(p).read_text(encoding='utf-8')))
        key=(r['event_id'],r['symbol']);assert key not in seen;seen.add(key)
        assert r['study_sha256']==impact['study_sha256']
        e=r['event_input'];path=Path(e['source_path']);source_paths[path]=e['source_sha256']
        if r.get('time_granularity')!='DATE_ONLY':
            assert len(r['responses'])==3 and all(x['status']=='OBSERVED' for x in r['responses'])
    for p,expected in source_paths.items():assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
    pointer=checked(json.loads((root/'learning_latest.json').read_text(encoding='utf-8')))
    learned=checked(json.loads(Path(pointer['path']).read_text(encoding='utf-8')))
    assert learned['input_report_sha256']==impact['sha256']
    assert learned['last_training_label_maturity_ms']<learned['train_end_ms']<learned['holdout_start_ms']
    assert learned['real_orders']==0 and not learned['execution_eligible']
    nums=json.loads(Path('reports/archived_release_values_20261016.json').read_text(encoding='utf-8'))
    tests=json.loads(Path('reports/event_history_tests_20261016.json').read_text(encoding='utf-8'))
    assert tests['success']
    spike=checked(json.loads((root/'spike_casebook.json').read_text(encoding='utf-8')))
    result={'schema':'CQWE_HISTORICAL_EVENT_VALIDATION','range_utc':[catalog['start_utc'],catalog['end_utc']],
        'catalog_events':len(catalog['events']),'event_types':catalog['counts'],'catalog_sha256':impact['catalog_sha256'],
        'impact_report_sha256':impact['sha256'],'intraday_windows':impact['complete_market_windows'],
        'price_response_labels':impact['complete_market_windows']*3,'date_only_windows':impact['daily_responses_count'],
        'distinct_event_times_for_learning':learned['groups'],'statistical_independence_assumed':False,
        'learning_report':pointer['path'],
        'archived_numeric_records':nums['extracted'],'numeric_requests':nums['attempted'],
        'consensus_available':nums['consensus_available'],'first_vintages_authenticated':False,
        'spike_cases':spike['count'],'source_hashes_verified':len(source_paths),'tests':tests,
        'real_orders':0,'profitability_proven':False,'all_global_events_covered':False,
        'resident_research_restarted':False,'code_source':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path('research').glob('*event*.py')}}
    result['resource_pause_report']='reports/resource_pause_20261016.json'
    result['future_watch_plan']='reports/macro_watch_plan_20261016.json'
    atomic(Path('reports/event_history_validation_20261016.json'),result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('event_types','code_source')}))
