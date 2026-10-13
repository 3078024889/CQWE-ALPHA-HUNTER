# CQWE MASTER V1.8 — Web3 open-source research + one-account cash-only paper simulation

2026-10-13. Research-only. No keys, no wallets, no orders, no leveraged finance, no real-money profit claims.

## Research source comparison (public, independent implementations; no third-party trading code copied)

| Source | Evidence | Extracted principle | Limitations |
|---|---|---|---|
| https://github.com/flashbots/simple-arbitrage | Official Flashbots example of bundle arbitration | Competing searchers, fees/miner payment and execution gating | README explicitly says the example is very unlikely profitable. No verified transaction receipts or P&L established by this package. |
| https://github.com/flashbots/simple-blind-arbitrage | Flashbots MEV-Share demo / atomic backrun | Atomicity matters; execution attempts are not realized returns | No proof of profitable trades from source alone; gas/bids consume edge. |
| https://github.com/hummingbot/hummingbot + https://github.com/hummingbot/gateway | Production-grade public DEX/CEX connector architecture | Separate observation, quotes, risk, portfolio and execution | Connector existence is not evidence the strategy makes money. |
| https://github.com/jup-ag/docs | Jupiter V2 quote/order documentation | Route competition, quote expiry, confirmation, net fees | Quotes are not fills; route endpoints require access; not added as live connector. |
| Uniswap V2 constant-product swap mathematics | Widely used open-source AMM contract design | Price impact, reserve size and pool fee before declaring edge | AMM model is analytical, not a chain-specific current state or a fill. |
| https://github.com/DFXswiss/rangekeeper | Open-source Uniswap V3 liquidity manager | Polling recovery, inventory/rebalance costs | Complex concentrated liquidity strategies cannot be assumed profitable or fit $10. |
| https://github.com/zostaff/poly-trading-bot | Prediction-market research bot source | Market ID and telemetry discipline | Repository itself warns no guaranteed profit; onchain profitability not independently verified. |

A repository containing trading code does NOT prove that its authors executed profitable onchain trades. To verify performance independently, require chain ID, transaction hash, successful receipt, token transfers, gas/priority fees, LP fees, positions, inventory, and settlement/cost basis. This release deliberately makes no claim that any reviewed bot has verified positive net P&L.

## Actual improvements

- `cqwe/unified_paper_v18.py`: ONE shared $10 cash wallet across BTC/ETH/SOL/BNB, aligned UTC 5-minute history and nonlookahead next-open hypothetical fills; market ranking deterministic, ledger replay, stop/time exits, end-of-data simulated liquidation, virtual fee and gas costs, minimum notional rejection. Does not pretend these are 4 independent accounts.
- `cqwe/web3_lab_v18.py`: offline constant-product AMM pricing, trade-size price impact, hypothetical route comparison, stale-quote rejection and file SHA256.
- `tests/test_v18.py`: 17 adversarial tests including minimum order, gas effect, no negative cash, no future leakage, file hashing and reproducibility.
- `reference_source/`: full known v17 snapshot from supplied reference; **not installed or overwritten**.

## Install on Windows (two named directory levels maximum)

```
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V18\CQWE_MASTER_V18\INSTALL_MASTER_V18.ps1"
```

Previous V17 must be installed; Git worktree must be clean. Installer only stages three V18 files and then runs all project tests plus offline smoke. It never pushes to GitHub.

## Run the unified-account research on the already downloaded 30-day datasets

```
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.unified_paper_v18 --inputs `
 "data\v12\BTCUSDT_5m_30d.json" `
 "data\v12\ETHUSDT_5m_30d.json" `
 "data\v12\SOLUSDT_5m_30d.json" `
 "data\v12\BNBUSDT_5m_30d.json" `
 --output "reports\v18_unified_30d.json" `
 --min-notional-usd 1
```

**Important**: `--min-notional-usd 1` is for testing logic only. The default is `$5` and with `$10` equity and 20% allocation, a `$2` signal will be rejected. Real exchange tick/lot sizes and minimum notional may differ. This simulation does not access the trade endpoints or make actual fills. V17's per-symbol virtual returns were all negative; new results are not yet validated on the user's actual historical data.

## Web3 offline experiments

```
& "C:\Python314\python.exe" -m cqwe.web3_lab_v18 --input "D:\CQWE_MASTER_V18\CQWE_MASTER_V18\examples\synthetic_cpmm.json" --output "reports\v18_cpmm.json"
& "C:\Python314\python.exe" -m cqwe.web3_lab_v18 --input "D:\CQWE_MASTER_V18\CQWE_MASTER_V18\examples\synthetic_routes.json" --output "reports\v18_routes.json"
```

Gas is an **assumed** USD amount, not retrieved from a chain. For $10 capital, gas is often decisive; Flashbots examples and DEX routes should not be used blindly. No bot is set to trade.
