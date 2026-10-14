# CTI Copernicus V5.2 — Durable forward memory

One command after extracting the ZIP as `D:\CQWE_MASTER_V52\CQWE_MASTER_V52`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V52\CQWE_MASTER_V52\RUN_ONCE_V52.ps1"
```

## Research constraints

Four public Binance **spot** markets, 180 seconds per concurrent cycle, once per 30 minutes when the initial real capture is verified. The run does **not** place orders, access keys or enable live trading. First run can take >3 minutes; installation runs the full regression first.

For each symbol, the process loads the immutable checkpoint lineage and validates its digest and the latest underlying raw capture; it acquires an OS process lock. It then makes prospective predictions from the inherited six-genotype state, waits for future market events and verifies the whole append-only source session. Only after at least one verified settlement will it write the next immutable `checkpoint_XXXXXXXX.json` plus `.sha256` sidecar in `D:\CQWE_DATA\memory_v52\SYMBOL`. Missing or altered evidence stops succession. The capture keeps one pending decision at a time; discarded/pending events are not counted as completed.

Data and logs are on D: (`l2_v47`, `memory_v52`, `l2_v52/reports`, `logs`). Stops new sessions when disk free space is below 2GiB. No automatic deletion of audit evidence. Logs and historic raw files need a separate archive/retention phase after an archive and restore test; no automatic deletions here.

After a failed capture, the source is preserved; no learning checkpoint is committed for that session. Successful independent symbols may still get their own checkpoints. A later capture won't rewrite a failed session or fill missing outcomes. Do not interpret prediction directional labels as fills or realized profits. The scheduled task `CQWE_CTI_Durable_Forward_30m` is created only after all four symbols succeed in the first real session, and uses a no-window launcher. Existing tasks are not changed.

## Limitations

Cross-market observations share regimes and are statistically correlated; no independent OOS profitability inference is justified from a few sessions. Memory checkpoints have hashes and chain links, not cryptographic authentication against a user with write access to every file. A crash between the model session and the checkpoint may leave unpromoted evidence. A crash between checkpoint creation and digest sidecar leaves a fail-closed incomplete generation that requires manual review. Tests are offline unless run on user's Windows.
