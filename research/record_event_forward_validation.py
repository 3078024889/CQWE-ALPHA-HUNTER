"""Reproducible final evidence: source hashes, manifests, model archive and scoped tests."""
import hashlib
import json
from pathlib import Path
import time
import unittest

from cqwe.event_forward_loop import ForwardLoop
from cqwe.four_market_runner import checked
from cqwe.local_autopilot import atomic
from cqwe.liquidity_research import Branch16


def main():
    root=Path('D:/CQWE_DATA/event_history_supplement_20261016')
    impact=checked(json.loads((root/'combined_impact_report.json').read_text(encoding='utf-8')))
    learning=checked(json.loads((root/'combined_learning_report.json').read_text(encoding='utf-8')))
    catalog=json.loads(Path('reports/event_history_expanded_catalog_20261016.json').read_text(encoding='utf-8'))
    hashes={}
    for event in catalog['events']:
        path=event['source_path'];actual=hashes.setdefault(path,hashlib.sha256(Path(path).read_bytes()).hexdigest())
        if actual!=event['source_sha256']:raise ValueError('CALENDAR_SOURCE_HASH')
    for path in impact['result_files']:checked(json.loads(Path(path).read_text(encoding='utf-8')))
    if learning['last_training_label_maturity_ms']>=learning['train_end_ms']:raise ValueError('TRAINING_LEAKAGE')
    if not learning['archived_training_model_states']:raise ValueError('MISSING_ARCHIVED_WEIGHTS')
    for key,state in learning['archived_training_model_states'].items():
        if Branch16(state).updates!=learning['model_updates'][key]:raise ValueError('MODEL_ARCHIVE')
    forward=ForwardLoop('D:/CQWE_DATA/event_forward_probe_v3_20261016/forward.sqlite3')
    try:replay=forward.verify()
    finally:forward.close()
    names=['tests.test_event_forward_loop','tests.test_event_council_bridge','tests.test_event_policy_validation',
           'tests.test_event_history','tests.test_local_autopilot','tests.test_news_watch',
           'tests.test_four_market','tests.test_four_market_supervisor','tests.test_liquidity_research']
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    report={'observed_ms':time.time_ns()//1000000,'tests':result.testsRun,'passed':result.wasSuccessful(),
            'failures':len(result.failures),'errors':len(result.errors),'test_modules':names,
            'calendar_entries':len(catalog['events']),'event_types':len(catalog['counts']),
            'asset_windows':impact['complete_market_windows'],'source_files_verified':len(hashes),
            'historical_groups':learning['groups'],'model_archives':len(learning['archived_training_model_states']),
            'forward_probe_replay':replay,'real_event_outcomes_in_probe':0,
            'cost_policy_report':'reports/event_policy_validation_20261016.json',
            'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  [Path('cqwe/event_forward_loop.py'),Path('cqwe/event_council_bridge.py'),
                   Path('research/learn_event_history.py'),Path('research/event_supplement_pipeline.py')]},
            'real_orders':0,'profitability_proven':False,'resident_started':False}
    atomic(Path('reports/event_forward_validation_20261016.json'),report)
    if not result.wasSuccessful():raise SystemExit(1)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
