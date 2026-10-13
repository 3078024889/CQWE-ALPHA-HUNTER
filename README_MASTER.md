# CQWE Alpha Hunter — Master V0.5

Standalone additions to the existing V0.1–V0.4 research repository. Python 3.14 stdlib only. No API key, no order endpoint, no live trading, no daemon, no SQLite interactions. Existing v01–v04 source files are not changed or deleted. No files are written to C: aside from Python's normal runtime caches; no dependencies installed. Market data and reports remain under the D: project tree.

## Install

Extract to `D:\CQWE_MASTER_V05\cqwe_master_v05` (if Windows extraction uses the ZIP name as outer folder), then:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V05\cqwe_master_v05\INSTALL_MASTER.ps1"
```

Installer does not automatically push to GitHub. After verifying:

```powershell
cd D:\CQWE\alpha-hunter
git push origin main
```

## Research CLI

```powershell
cd D:\CQWE\alpha-hunter
$P='C:\Python314\python.exe'
& $P -m cqwe demo
& $P -m cqwe study --input data\klines\BTCUSDT_5m_7d.json
& $P -m cqwe fetch --symbols BTCUSDT ETHUSDT --days 7
& $P -m cqwe scan --count 10
& $P -m cqwe oi --symbol BTCUSDT --limit 100
```

All network commands are **manual, single-shot, read-only**. No API credentials required. Exchange restrictions and rate limits apply. `scan` makes multiple requests, so use sparingly. Use `study` against existing offline data to avoid network usage entirely.

## Interpretation limits

- V0.5 event study: completed 5-minute candle signals only; entry next-bar open; non-overlapping per asset; 70/30 chronological split. This is descriptive, not a fully executable order-level backtest.
- Flat each-side fee and slippage proxies do not model spread variations, market impact, funding, stop order queues, or liquidation. Intrabar stop model is optimistic in some gaps/rapid moves; never use as execution guarantee.
- OI history reflects **contract open interest value**, not authenticated net capital inflows. OI historical API may have limited lookback; absence or gaps must not be fabricated.
- Market scanner uses current OI and funding snapshots, not historical pre-event features. Never align snapshots to earlier historical candles.
- 10 USD paper ledger has no leverage and no exchange order connection. Its printed balance is hypothetical, not account revenue.
- Historical winners and overlapping labels, survivorship bias, data-snooping, and limited market regimes can invalidate performance claims. Do not claim AI prediction until independent validation.
- No financial return is promised, and V0.5 is not authorized for trading client funds.

## Architecture

`cqwe/core.py`: public REST and strict data checks

`cqwe/history.py`: paginated 5-minute fully-closed Kline fetch

`cqwe/market.py`: USDT perpetual snapshots + bounded historic OI

`cqwe/research.py`: conservative forward event comparison with separate train/test

`cqwe/paper.py`: cash-only capped paper ledger, basic drawdown stop

`cqwe/cli.py`: bounded command-line interface

`tests/test_master.py`: isolated unit tests with mocked history API

## Known work remaining

Historical funding-rate alignment, historical taker buy/sell (available in Klines), delisting-aware universe, regime segmentation, interval uncertainty under dependence, order book replay, liquidation model, and forward paper tracking. None is claimed complete in this release.

## Safety/operations

CQWE does not access `D:\二十瓦特`, port 28720, Oracle services or any `*.sqlite` databases. No services are installed or started. Secrets must stay out of Git. If the PC remains unstable following BSODs, postpone large downloads and continuous market scans until the OS is healthy.
