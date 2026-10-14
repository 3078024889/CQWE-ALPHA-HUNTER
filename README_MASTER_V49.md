# CQWE Master V4.9 — bounded four-asset precommit supervisor

Run from extracted double-level directory `D:\CQWE_MASTER_V49\CQWE_MASTER_V49`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V49\CQWE_MASTER_V49\RUN_ONCE_V49.ps1"
```

Adds an isolated fault-reporting supervisor to V4.7's forward capture. Each of BTCUSDT, ETHUSDT, BNBUSDT, and SOLUSDT receives at most two **fresh, separate 180-second capture sessions**. Failure of any symbol returns code 2, retaining previous partial session evidence without joining books. Both successful and failing batches write immutable JSON audit reports under `D:\CQWE_DATA\l2_v49\reports`; stdout/stderr are preserved under `D:\CQWE_DATA\logs`. Success requires **at least one authenticated precommit and one causal settlement per symbol**, full hash-chain integrity and a STOP-synchronized session.

No real orders, no profitability claim, no account/task changes, and no automatic task enablement. In particular this version **does not establish that the V4.7 exit=2 was caused by any specific network error**: it makes the next real failure diagnosable and tolerates one transient fresh-session retry. Do not interpret 4 sessions as enough for robust out-of-sample profitability claims.
