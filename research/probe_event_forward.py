"""Small real-public-data integration probe; no invented macro events or outcomes."""
from pathlib import Path
import time

from cqwe.event_forward_loop import capture,run
from cqwe.four_market_core import SYMBOLS
from cqwe.local_autopilot import atomic


def main():
    captures={};errors={}
    for s in SYMBOLS:
        try:captures[s]=capture(s)
        except Exception as exc:errors[s]=str(exc)
    report={'observed_ms':time.time_ns()//1000000,'quotes':captures,'errors':errors,
            'macro_event_occurred_during_probe':False,'real_orders':0,'profitability_proven':False}
    atomic(Path('reports/event_forward_public_probe_20261016.json'),report)
    run('D:/CQWE_DATA/event_forward_probe_v3_20261016',
        'reports/macro_watch_plan_expanded_20261016.json',10)


if __name__=='__main__':main()
