# CTI / CQWE V5.3 — all-generation memory provenance

This release preserves the V5.2 live forward learning and scheduled capture and **does not change or launch the scheduled task**.

## Change

The prior V5.2 loader only re-audited the most recent market evidence file. V5.3 now checks **every historical checkpoint** and its original market session: raw bytes, capture hash chain, causal settlement, source symbol, inherited checkpoint SHA, and exact six-genotype update increments.

Five independent adversarial tests cover two successive generations, deleted/modified older evidence, altered historical update counts, and an altered session lineage. Failure is fail-closed, never silently repaired.

`cqwe.lineage_audit_v53` prints a read-only four-asset status, per-symbol generation count, measured audit milliseconds, checkpoint storage bytes, and failures. It never deletes data, places orders, or declares profit.

## Installation

Unzip to `D:\CQWE_MASTER_V53\CQWE_MASTER_V53` and run:

`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V53\CQWE_MASTER_V53\RUN_ONCE_V53.ps1"`

Requires clean `main` checkout with V5.2 installed. Safeguarded by SHA256 exact base-file check, source backup on D drive, full offline regression, and local Git commit. No push.

## Long-run limitations

Re-reading all ancestors is cumulative and becomes increasingly expensive; monitoring runtime before optimizing with securely indexed immutable archival proofs is necessary. Capture data remains on D drive; automatic deletion is intentionally disabled. This release does **not** implement automatic mutation or validated profitable trading.
