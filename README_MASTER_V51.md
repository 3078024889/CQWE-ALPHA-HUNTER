# CQWE V5.1 — Copernicus Tidal Intelligence

Root cause observed on actual Windows V5.0: `PRECOMMIT_WITHOUT_PRIOR_BOOK` for all four symbols. When a pending decision settles, the valid record sequence is `BOOK -> SETTLED -> PRECOMMIT`. The old auditor incorrectly demanded an immediately adjacent BOOK before each PRECOMMIT.

V5.1 records `decision_book_sha256` and `decision_book_received_ns` on each *new* prediction, matching the most recently appended preceding BOOK. It verifies the hash, exchange update id, receive time vs append time, causal order, and settlement separately. Legacy records are not modified; legacy unanchored predictions that have an intervening settlement remain rejected rather than retrospectively promoted.

## Windows

Extract to `D:\CQWE_MASTER_V51\CQWE_MASTER_V51`; run:

`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V51\CQWE_MASTER_V51\RUN_ONCE_V51.ps1"`

Requires V5.0 installed in a clean Git `main` worktree and `C:\Python314\python.exe`. Exact SHA256 checks and D-drive source backups protect local changes. Tests run before Git commit; no GitHub push. V5.1 runs one bounded four-symbol forward capture after install, using the existing V5.0 wrapper. A failed symbol remains failed and no session is stitched. No task modification, no real orders, no demonstrated profitability. Data only on `D:\CQWE_DATA`.
