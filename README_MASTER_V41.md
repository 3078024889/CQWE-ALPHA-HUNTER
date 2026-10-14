# CQWE MASTER V4.1 — causal quote-forward research

## Purpose

Add a scheduled Binance public-REST, **observational-only** BTC/ETH/SOL/BNB-capable order-book monitor (initially BNBUSDT) and a reproducible **future quote outcome** analysis of original SHA256-protected V4.0 files.

The frozen pressure baseline uses microprice displacement and top-five depth imbalance, never claims to identify a specific market maker or to generate a trade. 60s and 300s forecast horizons accept the **first** later observed quote at or after the horizon and inside a strict tolerance; missing observations are unmatched. Report all coverage deficits.

Quote-cross proxies use buy at initial ask / sell at future bid, or initial bid / future ask for selling. These are nonexecuted, fee-exclusive examples; they are **NOT fills or realized profit**. Multiple outcomes overlap, and 100 outcomes alone do not provide statistically independent evidence. We deliberately DO NOT offer 30s results from 60s sampling, reconstruct cancellation events from REST, or alter old 240-bar benchmark artifacts.

## Install / run

Extract to `D:\CQWE_MASTER_V41\CQWE_MASTER_V41` (exactly two same-named directory levels), run `RUN_ONCE_V41.ps1` once. Installer requires clean main branch, V4.0 installed; it adds five files (module, tests, readme, runner, enable script), runs complete tests, commits to local git, no push. Then one-shot attempts public collection; offline audit can always be run without network. If public API fails, reports honest errors without assuming observation. Enable one-minute read-only task only if first collection succeeds. The current V3.8 paper and dendrite schedules are not touched.

## Sources/design comparisons

- Hummingbot market making: spread refresh/inventory skew; not directly suitable for $10 execution.
- hftbacktest: queue position and feed/order latency important to fill simulation.
- cryptofeed: event-driven trades and L2; a later *authenticated stream reconstruction* is needed to measure cancellations or order-flow imbalance properly.

This version is NOT a live trading or market-making bot. Future work: timestamp-qualified websocket book updates, server clock calibration, forward OOS holdout, executed price and min-notional gates. No automatic model promotion.
