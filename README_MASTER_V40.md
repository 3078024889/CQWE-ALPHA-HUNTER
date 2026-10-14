# CQWE MASTER V4.0 — Market Microstructure Research

## Research basis (independent implementation, no copied external source)
- Hummingbot Avellaneda–Stoikov: inventory-aware reservation price, bid-ask quote constraints, risk aversion. https://hummingbot.org/strategies/v1-strategies/avellaneda-market-making/
- hftbacktest: market-data/feed/order latency, queue position and fill uncertainty. https://github.com/nkaz001/hftbacktest
- NautilusTrader: order-book imbalance research and preconfigured trigger controls. https://nautilustrader.io/docs/latest/tutorials/orderbook_imbalance/
- cryptofeed: normalized L1/L2/trades, multi-exchange observation. https://github.com/bmoscon/cryptofeed
- Binance public API: depth, aggregate trades, exchangeInfo; REST snapshots are not atomic and must not be described as full order flow. https://github.com/binance/binance-spot-api-docs

## What V40 does
- Auth-free public **spot** REST depth + aggTrades (one independent instrument BNBUSDT by default), no orders, no leverage, no API keys.
- Timestamped top and 5-level book imbalance, microprice, spread bps, aggressor buy/sell notional inferred using `m` (buyer-is-maker flag), signed observed-aggressor imbalance and descriptive regimes.
- Hash-protected append-only observations, validation for crossed/unsorted book, invalid sizes, stale or out-of-window trade timestamps. Immutable V38 paper segments untouched.
- Offline dry audit works without network; optional live snapshot can fail due to provider restrictions. No scheduled tasks or privileges changed.
- Does **not** claim to know individual market maker positions, fake order detection, queue priority, true OFI, future prices, executable spread capture, or profit.

## Next separate independent experiments
- Capture incremental depth stream with snapshot reconciliation and sequence IDs; capture all timestamped aggressor trades, and verify feed gaps.
- Preregister future midquote horizons (at least 30/60/300s), separate strictly later market data and external latency measurements; compare to zero, momentum and microprice benchmarks with OOS holdout.
- Build fee/spread/queue/latency-aware shadow fills only when full event data can support them. Do not change trading decision engine based on snapshot scores alone.

## Usage
From the user project folder after installing: `C:\Python314\python.exe -m cqwe.microstructure_v40 --offline-audit`.
One-shot package launch: `D:\CQWE_MASTER_V40\CQWE_MASTER_V40\RUN_ONCE_V40.ps1`.
No remote git push, no production tasks changed. Real $10 budget untouched; real profit 0 without verified receipts.
