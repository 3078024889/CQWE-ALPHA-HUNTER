# CQWE MASTER V5.0 — Four-market causal settlement repair

One-shot Windows installation (extract as `D:\CQWE_MASTER_V50\CQWE_MASTER_V50`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V50\CQWE_MASTER_V50\RUN_ONCE_V50.ps1"
```

## Verified cause of V49 incident

The websocket callback saved the actual event reception time `t` in `SETTLED.settled_received_ns`, yet the V47 auditor compared this to the later on-disk `BOOK.received_ns` (append clock). In normal execution, the append clock is greater than `t`, so every settlement failed `SETTLEMENT_WITHOUT_FUTURE_BOOK`, identically for all symbols and both retries.

Fix: new `BOOK.payload.book_received_ns` records the WS event receive nanoseconds; `SETTLED` references the exact immediately preceding causal BOOK via `settlement_book_sha256` and `settlement_update_id`. Audit validates the identical event receipt timestamps, correct hash anchor and ordering, causal 60s maturity, unchanged no-fill accounting, STOP/sync and hash-chain integrity. Earlier sessions remain immutable; legacy audit remains strict without converting invalid old records to valid ones.

Installer checks SHA256 of the expected V49 originals, backs up both modified files under `D:\CQWE_DATA\source_backups`, runs whole regression and 12 new adversarial cases, and commits changes locally (no push). Only after tests does the one-shot runner launch 180-second four-market public L2 forward sampling via the V49 supervisor (at most two fresh sessions per failed asset). It does not create/edit tasks, place trades, or delete evidence. New data and logs remain on D drive.

Real Windows L2 verification is pending. Do not interpret precommitted price-move labels as order fills, MM identity, profit, or independent strategy edge. There is no autonomous cross-session dendrite selection in this fix.
