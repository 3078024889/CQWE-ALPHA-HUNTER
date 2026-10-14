# CQWE MASTER V4.8 — Timestamp-window root-cause correction

## Confirmed root cause
`microstructure_v40.analyze()` rejected entire public aggTrades responses if **any** trade was older than `ended_ms - 300000`. The endpoint returns up to N recent trades and does not guarantee all prints fall in the latest five-minute window. This repeatedly made `CQWE_Microstructure_1m` exit 1.

## Safety-preserving repair
`collect_once()` excludes ONLY syntactically valid stale trades, counts them in `excluded_stale_trades`, sets `trade_payload_count`, and flags `trade_window_completeness`; stale trades never contribute aggressor volume. Malformed trades and future timestamps still fail closed. `analyze()` retains strict standalone time-window validation, so older tests remain valid. When no current prints exist, aggressor imbalance is null, not fabricated. Historical files and hashes are not touched.

## Scope / installation
This archive includes complete V47 source and V48 updates. Unzip to `D:\CQWE_MASTER_V48\CQWE_MASTER_V48`. Run:

`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V48\CQWE_MASTER_V48\RUN_ONCE_V48.ps1"`

Requires clean git main repo `D:\CQWElpha-hunter`, Windows Python `C:\Python314\python.exe`; installer accepts only exact known V47 V40 source SHA256. Source backup under `D:\CQWE_DATA\source_backups`. Runs all unit tests; does a single public BNB spot REST capture, no real orders, no GitHub push, no task modifications, no automatic deletions. V47 forward exit=2 is a distinct unresolved incident; V48 does not pretend to fix it.
