# CQWE MASTER V3.0 — one-shot frozen forward research automation

## Provenance and limitations

Extends V2.9 public read-only collector and V2.8 frozen-weight experiment.
Every hourly cycle checks the verified V2.1 checkpoint and only collects *closed* Binance spot 5-minute bars.
Below 240 aligned bars, reports WAIT; at 240 or more, snapshots **exactly the first 240** after checkpoint, runs two pre-registered V2.8 thresholds, and writes a receipt with SHA256 fingerprints.
Later hourly cycles validate frozen evidence, never re-run an expanding window and never automatically promote or issue orders.
No trades in an exchange account; hypothetical fills have no orderbook liquidity model. Future bars were not independently audited as unselected data; this is limited forward research, not proof of profits.

## Windows installation

Extract the archive into `D:\CQWE_MASTER_V30`, so the installer is at `D:\CQWE_MASTER_V30\CQWE_MASTER_V30\INSTALL_MASTER_V30.ps1`. Run that installer first. Then separately authorize swapping the existing hourly task to the new wrapper:

`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE\alpha-hunter\ENABLE_AUTOMATION_V30.ps1"`

The existing `CQWE_Public_Market_Collector` hourly schedule stays at the same time and its action changes to `RUN_RESEARCH_V30.ps1` (collector + conditional test). No second duplicate task is created.

Manually check: `Get-Content D:\CQWE\alpha-hunter\reports\collection_logs\market_research_v30.log -Tail 20`.

## Fail closed

Each cycle uses a lock directory; stale locks require manual examination. Interrupted evaluation outputs remain in the evidence directory and block automatic overwrite. Never remove a partial run without review; store contains valuable forensic records.

This version adds **one** orchestrator, not a new learning engine. No historical components are removed without proven migration safety. No deployment, live order, auto push or real profit claim.
