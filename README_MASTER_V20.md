# CQWE V2.0 | Evidence-gated Local Self-Evolution

**Research-only Python 3.14 compatible. The code neither reads private keys nor places orders.**

## Why this release
V1.9 on user-provided BTC/ETH/SOL/BNB 30-day 5m inputs: 5,829 training events, **6 holdout events, mean net event return -0.86142714%**. This is a failed/insufficient signal, not profit. V1.8 unified virtual account: **$10 → $7.70073146** (-22.99% historical simulation). Both are fixed external baselines; they do not prove live performance.

## What actually runs
1. Align each market's closed 5m candles; reject gaps or bad OHLC.
2. Build event observations from the three V1.9 deterministic triggers and regime nodes.
3. Partition chronologically: first 60% learning; next 20% adaptive validation; last 20% *sealed* verification. Purge events straddling boundaries.
4. Test four **predeclared** weight-update variants, not executable source-code mutations. Each uses outcome data only after position maturity. Admit a variant only when cost-adjusted validation event mean has a positive conservative lower bound and enough events; multiple-testing bias still exists.
5. If none passes, return HOLD, save failed variants and report no portfolio profit (not a fictitious zero PnL from phantom orders). The sealed test never selects the variant.
6. Save check-point with per-node weights, candidate states, event statistics, time boundaries and SHA256 identity.
7. New *strictly contiguous future* batches can resume candidate updates via `--mode continue`. Entries are hash-chained. This is **prequential adaptive research**, not a new independent holdout and not cash-account trading.

## Install (Windows)
Unzip so path is `D:\CQWE_MASTER_V20\CQWE_MASTER_V20`, then:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V20\CQWE_MASTER_V20\INSTALL_MASTER_V20.ps1"
```

## First research (uses existing 30-day bars)
```powershell
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.self_evolution_v20 `
  --inputs data\v12\BTCUSDT_5m_30d.json data\v12\ETHUSDT_5m_30d.json data\v12\SOLUSDT_5m_30d.json data\v12\BNBUSDT_5m_30d.json `
  --output reports\v20_evolution.json `
  --checkpoint reports\v20_evolution_state.json
```

Do **not** rerun against the same checkpoint. The system intentionally rejects replay. Keep the original report and checkpoint; new data must begin at precisely the next 5m candle and include at least 240 new bars per symbol (e.g. ~1 day).

```powershell
& "C:\Python314\python.exe" -m cqwe.self_evolution_v20 `
  --mode continue `
  --inputs data\future\BTCUSDT_5m_next.json data\future\ETHUSDT_5m_next.json data\future\SOLUSDT_5m_next.json data\future\BNBUSDT_5m_next.json `
  --output reports\v20_continuation_01.json `
  --checkpoint reports\v20_evolution_state.json
```

**Future data filenames above are examples only, not files created by installer**. They must contain properly aligned real candles. There is no automatic future data collector or service in V2.0. There is no claim that the module has demonstrated a profitable strategy, and no live production deployment.

## Strict limitations
- Candidate updates are predefined parameter mutations; no dynamically generated source code or neural self-modification.
- Training/validation outcomes are event returns, **not** a real multiasset account PnL. Future validation may show a negative result even if mutation selected a candidate.
- No automatic strategy promotion during future continuations. Each future continuation is a time-ordered learning journal; promotion requires a **fresh separately sealed evaluation**.
- A naive statistical lower bound ignores serial dependence and four-way multiple comparisons. It is a *research screen*, not proof of profitable alpha.
- All output is offline and simulated. Risk constraints, minimum viable order, spread, funding, dynamic gas and actual execution remain outside this research module.
