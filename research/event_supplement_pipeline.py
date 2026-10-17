"""Bounded single-worker extension; retain original reports and reuse immutable candles."""
import hashlib
import json
from pathlib import Path
import time

from cqwe.four_market_runner import checked
from cqwe.local_autopilot import atomic
from research.event_history_impact import run,summarize
from research.learn_event_history import evaluate


def main():
    old=Path('D:/CQWE_DATA/event_history_20261016')
    root=Path('D:/CQWE_DATA/event_history_supplement_20261016')
    (root/'candles').mkdir(parents=True,exist_ok=True)
    catalog=Path('reports/event_history_supplement_catalog_20261016.json')
    events=json.loads(catalog.read_text(encoding='utf-8'))['events']
    # Read-only cached inputs are hardlinked on this drive, saving disk and downloads.
    for e in events:
        t=((e['scheduled_ms']+59999)//60000)*60000
        for symbol in ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT'):
            name=f'{symbol}_{t}.json';src=old/'candles'/name;dst=root/'candles'/name
            if src.exists() and not dst.exists():dst.hardlink_to(src)
    run(catalog,root)
    previous=checked(json.loads((old/'impact_report.json').read_text(encoding='utf-8')))
    current=checked(json.loads((root/'impact_report.json').read_text(encoding='utf-8')))
    files=previous['result_files']+current['result_files']
    rows=[checked(json.loads(Path(p).read_text(encoding='utf-8'))) for p in files]
    learning=evaluate(rows)
    combined=json.loads(Path('reports/event_history_expanded_catalog_20261016.json').read_text(encoding='utf-8'))
    report=summarize(combined['events'],rows)
    report.update(parent_reports=[str(old/'impact_report.json'),str(root/'impact_report.json')],
                  parent_sha256=[previous['sha256'],current['sha256']],result_files=files,
                  added_windows=current['complete_market_windows'],failures=current['failures'],
                  observed_ns=time.time_ns(),calendar_complete=False)
    atomic(root/'combined_impact_report.json',report)
    atomic(root/'combined_learning_report.json',learning)
    public={'total_calendar_entries':len(combined['events']),'event_types':len(combined['counts']),
            'added_calendar_entries':len(events),'added_asset_windows':current['complete_market_windows'],
            'total_asset_windows':len(rows),'learning_groups':learning['groups'],
            'holdout':{k:{'selected':kind,**learning['scores'][k]['holdout'][kind]}
                       for k,kind in learning['chosen_from_validation'].items()},
            'failures':current['failures'],'real_orders':0,'profitability_proven':False,
            'report':str(root/'combined_impact_report.json'),'learning_report':str(root/'combined_learning_report.json')}
    atomic(Path('reports/event_supplement_result_20261016.json'),public)
    print(json.dumps(public),flush=True)


if __name__=='__main__':main()
