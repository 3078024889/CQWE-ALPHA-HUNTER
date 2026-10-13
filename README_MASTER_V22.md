# CQWE V2.2 | verified continual-learning evidence audit

Installs **three** research-only files onto the already-verified V2.1 repository. No network, API keys or live orders.

- `cqwe/evidence_audit_v22.py` uses V2.1's ledger/checkpoint/report hash consistency verification before examining V2.0's matured-event rule diagnostics.
- Builds a per-episode audit of every learning-rule candidate: events, mean net event fraction, the **reported** lower bound, and an evidence gate.
- **Does not** promote rules merely because one adaptive segment has a positive event metric, nor sum events into portfolio PnL.
- Writes a separate report OUTSIDE the immutable evidence store.
- `tests/test_v22.py` tests tampering, semantics, no evidence mutation, positive/negative/low-N results.

## Install (fixed two-level path)

`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V22\CQWE_MASTER_V22\INSTALL_MASTER_V22.ps1"`

## Research run after existing V2.1 replay

`& "C:\Python314\python.exe" -m cqwe.evidence_audit_v22 --store "reports\v21_evidence" --output "reports\v22_diagnostic.json"`

This analysis is adaptive/historical, not independent live validation, not portfolio-accounting, and does not establish real profit. V2.1's SHA chain checks internal consistency, NOT signatures or tamper-proof external provenance.
