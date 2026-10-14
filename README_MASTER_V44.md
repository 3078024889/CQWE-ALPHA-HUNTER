# CQWE V4.4 — Four Major Assets, Public L2 Forward Research

**Scope:** BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, Binance **spot** only. Symbol availability is not equivalent to $10 order feasibility. Perpetual contracts and other exchanges are **not** silently mixed into this experiment. No order/API key access, no real fills or profit assertions.

## Design

- Reuse the validated V4.3 REST-snapshot + sequenced Binance WebSocket `depth@100ms` and `trade` collector, one isolated session per asset; **do not retroactively reconstruct missing sequence updates**.
- Capture all four concurrently for a **bounded 75-second** study (configurable 65–180 seconds), not a permanent four-way high-frequency service.
- Locally verify every V4.3 hash-chained session, START/STOP, BBO spread, post-sync trade count, symbol identity and complete session. Mark failed/incomplete individual markets; fail the one-shot runner unless all four passed.
- Record files under `D:\CQWE_DATA\l2_v44\<SYMBOL>`, reports under `D:\CQWE_DATA\l2_v44\reports`. Require at least 300 MiB available before starting. Legacy datasets and journals are untouched.
- Findings are *capture quality observations*, not a model trained on these samples. Four markets aren't ranked by one 75-second movement or by assumed profits. Broker minimum notional, live latency, partial fills, maker queue and actual account fees remain unverified.
- Binance public endpoints may still rate-limit requests by IP. Four synchronized initial snapshot calls mean slightly more request weight, albeit within a short bounded probe. **Never run this package repeatedly in a tight loop.**
- Every five released construction iterations perform ten *independent* falsification drills; V4.4 includes ten new module tests and inherits regression tests. Stress scenarios do not prove profitability. V4.5 should include the first explicit periodic cross-release review if V4.1–V4.5 are counted as a cycle.

## Run

After extracting `D:\CQWE_MASTER_V44\CQWE_MASTER_V44`, run exactly:

`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V44\CQWE_MASTER_V44\RUN_ONCE_V44.ps1"`

The script fails closed on unavailable public data; it does not modify existing Windows tasks, nor does it push Git.

## Future limits

Proper trade-book atomic synchronization, actual exchange queue priority, maker attribution, real broker execution reports, and **independently verified cost-after-execution OOS edge** are not established. Real trading requires separate authorization; paper profitability never automatically licenses it.
