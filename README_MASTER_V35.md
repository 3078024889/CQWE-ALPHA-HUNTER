# CQWE MASTER V3.5 — evidence-governed continuous research

* Recover after missing a complete 5-minute bar by **starting a new epoch**, never by filling missed predictions. The old SHA-chained V3.4 journal stays untouched. V3.5 begins a new experiment under `reports/v35_lineages`. This is NOT continuous unbroken learning through gaps.
* Six V3.3 genotypes continue as competing **research-only** response functions, each with its own forward-updated state and an immutable chain per epoch. A new epoch resets each candidate's state, explicitly recording lost continuity.
* The derived audit reports observation count and squared-error comparison against a zero forecast. It cannot automatically promote nodes or prove executable profit. Statistical evidence is correlated and insufficient for independence claims.
* Exclusive file lock prevents overlapping processes; stale lock requires manual inspection rather than automatic deletion.
* Optional `ENABLE_DENDRITES_V35.ps1` replaces only the existing V3.4 research task with one V3.5 research task. Other task names remain untouched.
* V3.5 does not alter the V3.3 $10 cash-paper task, does not access trade APIs, cannot place exchange orders.
* Existing V3.4 history stays available for forensic audit; it is not silently spliced into the V3.5 lineage.

## Installation

Extract as `D:\CQWE_MASTER_V35\CQWE_MASTER_V35` and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V35\CQWE_MASTER_V35\INSTALL_MASTER_V35.ps1"
```

## First test then schedule

```powershell
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.evolution_supervisor_v35
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE\alpha-hunter\ENABLE_DENDRITES_V35.ps1"
Get-Content "reports\collection_logs\dendrites_v35.log" -Tail 30
```

**Limitations:** abrupt crash during new-epoch creation can leave an incomplete epoch, requiring manual review; a restart is never allowed to silently rewrite it. No real orders. No validated profit or automated investment decision.
