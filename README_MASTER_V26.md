# CQWE MASTER V2.6 | Dendritic causal loss diagnostics

**Purpose:** Isolate root causes of the V2.4 historically simulated $10 account failure, turn them into testable node-local repair hypotheses. **NO ORDERS. NO VERIFIED PROFIT.**

## Actual user-side observations (provided log, not rerun in this package)
- V2.5 locally installed at e67e7a6; user-side 230 tests passed.
- Gate $10.00000000, shadow $9.69929590, +10bp stress $9.66456703.
- Shadow explicit fills fees $0.03514475, stress $0.07015014. Fees alone do not account for shadow loss; model fills embed slippage.

## What was actually extracted, and the limits
- *Copernicus* novel: dendritic linked nodes + weighted local learning (PDF page 67), self-modifying algorithms (pages 166-167), novel or edge-case inputs (page 744). This is a fictional conceptual source, NOT a reproducible neural-network recipe, sentience proof, or investment model.
- Freqtrade `lookahead-analysis` and `recursive-analysis`: test timestamp contamination and startup-candle sensitivity before accepting a candidate (https://github.com/freqtrade/freqtrade/blob/develop/docs/lookahead-analysis.md ; https://github.com/freqtrade/freqtrade/blob/develop/docs/recursive-analysis.md).
- NautilusTrader: event-driven execution and explicit backtest/live semantic differences (https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/concepts/backtesting/execution-flow.md).
- Hummingbot: paper-trade connector to test without actual assets (https://github.com/hummingbot/hummingbot-site/blob/main/docs/client/global-configs/paper-trade.md).
- CCXT: venue precision, minimum notional, quantity steps and tick sizes are independent constraints; never infer them from a five-minute candle (https://github.com/ccxt/ccxt/wiki/Manual).

These projects are research references, not vendored code. No repo or license claims from copied sources; all V26 code newly written. GitHub samples and developer docs do **not** prove realized profitable trades or verified tx hashes.

## Features
- Read-only diagnosis of V25 forensics report and user supplied optional **UNVERIFIED** venue metadata.
- Decompose closed paired trades into gross price movement, explicit fees, and net PnL; non-closed component labeled separately.
- Identify direction loss, execution cost, too-small sample, concentration, and minimum-notional blockers.
- Map findings into hypotheses for later **independent** forward tests. No self-editing source, no live orders, no promotion.
- Reject contradictory trade totals or inconsistent reported account net; hash exact source bytes; atomic output.

## Windows installation
Unzip under `D:\CQWE_MASTER_V26\CQWE_MASTER_V26`, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V26\CQWE_MASTER_V26\INSTALL_MASTER_V26.ps1"
```

Then:

```powershell
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.dendritic_diagnostics_v26 `
  --forensics "reports\v25_forensics.json" `
  --output "reports\v26_dendritic_postmortem.json"
```

Test venue metadata only after obtaining **real venue data**; any supplied metadata is still marked unverified. Optional file fields: `min_notional_usd`, `min_qty`, `qty_step`, `price_tick`. This simulator does NOT claim a particular exchange's live market accepts the trade.

## What V26 does NOT establish
No new unseen data, genuine execution, validated fill price, executable liquidity, proof of learning improvement, or profits. The current history has already been examined repeatedly. V26 diagnoses failure and proposes falsifiable future experiments only.
