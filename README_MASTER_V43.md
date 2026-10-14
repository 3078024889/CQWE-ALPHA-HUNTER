# CQWE V4.3 — D-drive public L2 + trade capture and conservative replay

Research-only. The collector uses Binance public combined diff-depth and raw trade streams, synchronizes the book from an official REST snapshot, then emits hashed append-only local events under **D:\CQWE_DATA\l2_v43**. The combined stream is observed, not a trading API. Local receive time is retained independently from trade exchange time. Trading is disabled.

## Scientific restrictions

* Binance public L2 reports quantities by PRICE, not order identity. A real queue position cannot be reconstructed. Conservative **queue depletion** counts only sell-aggressor trades at an observed bid after the decision (no presumed advancement from cancellations), and is a scenario bound, **never an actual fill**.
* Diff depth cannot be exactly decomposed into trades/cancellations because depth stream and trade stream have different sequencing. Report changes as unknown unless independent matching evidence; no maker identity or inferred illegal activity.
* A quote-crossing experiment requires quotes **after decision + assumed network delay** and a future quote after the chosen holding horizon. Even then both 'fills' are **hypothetical**, because the account never posted real orders; actual fees, RPI, partial fills, order flow market impact and bandwidth are unknown.
* Session interruption, sequence gap, queue overflow and cross-book fail closed; no stitching of pre/post reset streams. Incomplete capture records remain evidence and must not be used for profitability claims.
* Ten stress configurations: latency (250ms,500ms,1s,2s,1.5s,3s), fees (10/20/30/40bps per side), additional slippage (2/10/20/30bps). The cases are stress tests, NOT ten proof-of-profit rounds. Each five version updates should invoke at least ten different adversarial replay scenarios with sample-out audits; the exact cadence is a process standard not yet enforced across older versions.
* Actual fill evidence requires separately authorized private account trade reports, validated via order IDs, fee records and timestamps. This release intentionally does **not** connect private APIs or place an order.
* All CQWE V4.3 market data and new Python dependencies, pip cache, TEMP/TMP use D:\CQWE_DATA. The user's existing C:\Python314 interpreter remains unchanged. Legacy repo D:\CQWE\alpha-hunter remains as is.

## Usage

Extract ZIP to D:\CQWE_MASTER_V43\CQWE_MASTER_V43 then execute only:

`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V43\CQWE_MASTER_V43\RUN_ONCE_V43.ps1"`

One-shot creates a 75-second bounded real-market observation, ten scenario replay, and report. It does not create a permanent 24h task. Existing v38 paper, dendrite, and v41 REST minute tasks are untouched. Continuous 24/7 collector requires subsequent disk-bounded rotation, watchdog and 429/reconnect backoff; do not infer it exists here.

Sources: https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md and https://hft.readthedocs.io/en/latest/order_fill.html .
