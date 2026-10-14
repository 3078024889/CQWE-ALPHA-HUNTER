# CQWE MASTER V3.9 — ten-gate profit falsification (research only)

V3.8 stays the active **paper-only** account task. V3.9 does not change its execution,
threshold, saved weights, records, task configuration or trading API (there is no live order API).

This module evaluates ten independent evidence checks against the **actual** local V3.8
segments, legacy V3.3 journal and precommitted V3.1 signals. It intentionally reports
`profitability_proven=false` until independent, executable, cost-adjusted out-of-sample
account evidence is independently verified. The cost study is a non-executable
close-to-close signal proxy, not a tradable backtest or advice.

The V3.1 outcome filename is keyed on the original signal candle's opening timestamp.
Predictions recorded **at or after** the target candle's open cannot be credited with a
pre-open fill. Such observations are counted as late and excluded from the pre-open study.

Ten gates: hashed segments; independent legacy audit; no live orders; prohibit segment PnL
compounding; account freshness; paper executions; causally pre-open signals; 100 forward
observations; hypothetical 40bps two-sided friction stress; independent executable OOS evidence.
Passing a few checks does **not** establish profitability. No automatic promotion.

Installation: extract to `D:\CQWE_MASTER_V39\CQWE_MASTER_V39`, then run:

`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V39\CQWE_MASTER_V39\RUN_ONCE_V39.ps1"`

The sole output report is `reports\v39_profitability_audit.json` and contains source
limitations, signals excluded, stress assumptions and all gate results. Existing V3.8
account schedule and journal are not modified. Installer commits only three new files.
