# CQWE MASTER V3.6 — Audited long-term memory and heartbeat

**Research-only, cash-only paper experiments. No orders, no automatic model promotion.**

## What changed

- `cqwe/evidence_health_v36.py` independently verifies all V3.5 lineage manifest and V3.4 frame hashes using existing verification routines; tampered, missing, and overlapping epochs fail closed.
- Computes paired incremental squared-error improvement over the zero-forecast research baseline for each of the six *existing* candidates, without interpolating missed bars. Adds a conservative, multiple-candidate-corrected descriptive bound. Sequentially adapted market observations **are not independent statistical evidence** and this is **not a trading-profit test**.
- Explicitly labels market freshness based on the most recent validated observed candle; `STALE_OR_TASK_DELAY` is diagnostic, not an automatic guarantee of data availability. A healthy Windows task with the same closed candle does not mean market data is current.
- Archives lineage identity, tip hashes, observed gaps, and candidate scores; **no automatic predictive weight carryover across gaps**. This is truthful long-term *evidence* memory; state inheritance still needs separate causal validation.
- `RUN_DENDRITES_V36.ps1` runs V3.5 supervisor and V3.6 evidence health sequentially with error and exit logging. `ENABLE_DENDRITES_V36.ps1` updates only the existing `CQWE_Dendrite_Forward_5m` task; it does not create a parallel learning engine or interfere with the V3.3 $10 account.
- Existing V3.5 lineage journals and older learning models are intentionally preserved. **Old source removals: 0**; no safe-deletion proof yet.

## Windows installation (fixed TWO-level extraction)

Extract ZIP to `D:\CQWE_MASTER_V36` so installer exists at:
`D:\CQWE_MASTER_V36\CQWE_MASTER_V36\INSTALL_MASTER_V36.ps1`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V36\CQWE_MASTER_V36\INSTALL_MASTER_V36.ps1"
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.evidence_health_v36
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE\alpha-hunter\ENABLE_DENDRITES_V36.ps1"
schtasks.exe /Run /TN "CQWE_Dendrite_Forward_5m"
Start-Sleep -Seconds 15
Get-Content "reports\collection_logs\dendrites_v36.log" -Tail 25
```

The first invocation uses existing `reports/v35_lineages`. If data is not available or evidence is corrupted, it fails closed without deleting records. The task may require a logged-in Windows session. Machine sleep/offline periods are not guaranteed to execute.

## Research limitations

The 120-observation gate is a floor, not proof of profitable performance. No amount of error-bound calculation on adaptive observations can validate executable returns, actual order fill prices, fees, slippage, or live revenue. Genuine held-out new dates, an executable paper cash account, and multiple-testing safeguards are necessary before any evidence-gated promotion can be considered.
