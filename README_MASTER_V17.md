# CQWE MASTER V1.7 — CLOSED HISTORICAL PAPER LOOP

Research-only software. This is *cash-only long-only historical simulation*, not real-time trading and not Polymarket trade simulation. Does not call a network, broker, wallet or trading endpoint.

## Installation
Extract to `D:\CQWE_MASTER_V17\CQWE_MASTER_V17` and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V17\CQWE_MASTER_V17\INSTALL_MASTER_V17.ps1"
```

Existing repository: `D:\CQWE\alpha-hunter`; Python: `C:\Python314\python.exe`. Installer installs the 3 versioned deliverables, verifies entire test suite, runs an offline closed-loop smoke test and makes a scoped local Git commit (re-running identical installer is safe). Repository must be clean apart from matching package files. No automatic push.

## Run on already-downloaded **closed** Binance klines

```powershell
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.paper_loop_v17 --inputs `
  "data\v12\BTCUSDT_5m_30d.json" `
  "data\v12\ETHUSDT_5m_30d.json" `
  "data\v12\SOLUSDT_5m_30d.json" `
  "data\v12\BNBUSDT_5m_30d.json" `
  --output "reports\v17_paper_30d.json"
```

**Important**: `$10` virtual balance is **separate in each market run**, not a single shared 4-asset portfolio. Hence never add virtual account results to real revenue. Each signal is a strictly historical breakout on the completed bar close and paper-buy is on next open. Fixed 20% of available virtual cash, 5 bps fees/side, 2 bps slip/side, hold 12 5-minute bars unless stop trigger. Long-only cash, no leverage. Final open position closed at last historical close with an **explicit synthetic end-of-sample liquidation assumption**; not a real available executable fill. Real brokerage minimum notional, spread, full live order-book depth, maker/taker fee variability, exchange outages and settlement are not modeled.

The entry strategy is an *unoptimized fixed baseline*, not a proposed profitable method. To avoid in-sample selection, choose parameters before testing additional future unseen history. The tests are software correctness tests, **not evidence of statistically profitable trading**.

## Strict limits
- No real trade routes, futures, borrowed funds or API keys.
- No verified live execution or PnL.
- Polymarket snapshots remain read-only market observations and must never be converted to actual paper fills without a documented non-atomic exposure model.
- Reports include cash, transactions, fees, end-of-sample flattening, drawdown, timestamps, per-dataset SHA-256.
