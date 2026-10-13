# CQWE MASTER V1.2 — Multi-market evidence audit

Windows PowerShell + Python 3.14, standard library only. This is an incremental **single master delivery** with an automatic installer. It preserves existing V1.1 modules and local market data.

## Why V1.2 exists

V1.1 showed negative post-cost event returns for both BTC and ETH. `eligible_for_further_research` means only sufficient event coverage, **not profitable or statistically significant**. V1.2 introduces explicit data-history gates and a multi-market cost audit. A positive event mean cannot pass as proven alpha.

## Capabilities

- Collect 1–30 days of fully closed 5-minute bars for at most 6 symbols per invocation, via public Binance Futures GET API.
- Use `--auto-top 4` to select current-volume leaders (**survivorship/selection biased**; disclosed in manifest), or specify historical research symbols directly.
- Manifest includes number of bars, first/last timestamp and SHA-256 provenance digest. All raw data remains on D drive.
- Evaluate V1.1 walk-forward folds across multiple datasets and all predeclared transaction-cost scenarios.
- Explicit research-gate outcomes: INSUFFICIENT_HISTORY, INSUFFICIENT_FOLDS, INSUFFICIENT_EVENTS, NEGATIVE_AFTER_COSTS, CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION.
- All event summaries remain descriptive; no funding, latency, L2 orderbook, mark-price liquidation, compliance restrictions, or real market fills.

## Install

Expected path after extracting with Windows to same-name folder:

`D:\CQWE_MASTER_V12\CQWE_MASTER_V12\INSTALL_MASTER_V12.ps1`

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V12\CQWE_MASTER_V12\INSTALL_MASTER_V12.ps1"
```

## Offline quick check (uses existing BTC/ETH files)

```powershell
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.market_lab_v12 audit --inputs "data\klines\BTCUSDT_5m_7d.json" "data\klines\ETHUSDT_5m_7d.json" --output "reports\v12_audit.json"
```

## Bounded real-data expansion (may fail on regional connection or rate limits)

```powershell
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.market_lab_v12 fetch --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT --days 30
& "C:\Python314\python.exe" -m cqwe.market_lab_v12 audit --inputs "data\v12\BTCUSDT_5m_30d.json" "data\v12\ETHUSDT_5m_30d.json" "data\v12\SOLUSDT_5m_30d.json" "data\v12\BNBUSDT_5m_30d.json"
```

Note: `fetch` is bounded one-shot but can take time. Do not schedule it as a background service. Run only if authorized/available in local jurisdiction.

No order API is present, and no account keys are requested. The 10 USD budget is not deployed.
