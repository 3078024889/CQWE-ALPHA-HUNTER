# CQWE Master V3.8 — Flat-only paper segment recovery

- Resolves the confirmed `MISSED_BARS_FAIL_CLOSED_NO_RETROSPECTIVE_FILLS` without retrospective fills.
- **Only** opens a new, independent $10 research paper segment when the previous ledger is independently validated, flat, has no pending intentions, zero fills/fees and exactly $10 cash/equity. Otherwise stops and requires manual review.
- Previous V33 frames remain untouched, segmented ledgers are independent with immutable linked SHA256 manifests.
- Does **not** aggregate segment balances as one profit curve or claim real revenue. V37 remains an audit of original V33 ledger; new segments are in `reports/v38_cash_segments`.
- The writer lock refuses concurrent researchers, including stale locks. No automatic deletion of lock or audit records.
- `RUN_ACCOUNT_V38.ps1` writes full separate stderr and stdout files, appends completion exit code to account_v38.log.
- The existing paper Windows task is only replaced **after** initial manual validation; the dendrite task is unaffected.
- Not implemented: automatic recovery of a virtual open position, matching historical execution across missed bars, full account equity inheritance, or independently verified profitable strategy.
- No live trading, API credentials, leverage or simulated-to-real profit conversion.

After clean V37 checkout and extraction of the two-level archive:

```
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V38\CQWE_MASTER_V38\INSTALL_MASTER_V38.ps1"
```

Runner manual validation via `RUN_ACCOUNT_V38.ps1`. When its latest execution exits zero, `ENABLE_ACCOUNT_V38.ps1` replaces the one existing 5-minute paper task. No automatic enable on install.
