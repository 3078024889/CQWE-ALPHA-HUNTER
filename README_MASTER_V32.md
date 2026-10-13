# CQWE V3.2 — persistent cash-only lifecycle research

Requires V3.1 already installed in `D:\CQWE\alpha-hunter`.

**Scope.** Independent observational $10 simulated portfolio. Uses existing frozen V2.1 weights and V2.7 registry; fetches public Binance 5m historical candles as V3.1 does. No real orders, private keys, exchange account access, leverage, or automatic promotion. Do not equate historical-next-open **assumptions** with achievable execution.

**Causal execution clock:** At candle B close (typically a few seconds after B+5m), produce a decision for *B+2 candle open* (not B+1 open, which already passed). Stage the pending instruction immutably, only value it after B+2 has completed. Never fill on signal-generation bar. Runs every 5m, refuses unexplained gaps (no retrospective fake trading). Initial cash $10, at most one symbol, no borrowing, 60% opening cash allocation subject to nominal 2% initial stop risk cap. Paper orders require >=$5 quote value; actual exchange lot-size and min-notional rules are unknown and do not get represented as verified.

**Lifecycle:** close-confirmed protective exit at -0.8%, target +1.6%, max 12 bars, trailing threshold +1% with 0.5% trail. Profit partial reduction after +1% only if both resulting portions meet the $5 simulated minimum; limited trend-node add once per position when cash and nominal budget permit. A threshold or stop is **not** a guaranteed fill. Trigger after the candle closes, fill in a later candle at hypothetical open subject to 2 bp adverse slippage and 5 bp side fee. No borrowed positions. Min-notional feasibility means at $10 partial sells / adds may be rare or impossible. Closed-position error causes are recorded in loss memory; memory is audit data, not unverified weights mutation.

**Install:** extract to `D:\CQWE_MASTER_V32\CQWE_MASTER_V32`, run `INSTALL_MASTER_V32.ps1`. Installer refuses unrelated Git changes; local runtime logs, data, and ignore-listed scripts are preserved. Runs tests before committing five new source files.

**Immediate observation:** `C:\Python314\python.exe -m cqwe.live_paper_v32`; **enable** `powershell -NoProfile -ExecutionPolicy Bypass -File D:\CQWE\alpha-hunter\ENABLE_ACCOUNT_V32.ps1` after immediate observation succeeds. Adds separate `CQWE_Cash_Paper_5m` 5-minute task, keeping V3.0 hourly and V3.1 observations intact. Requires Windows to be awake and account execution permissions valid.

**Research integrity:** immutable SHA256-chained per-bar frames. The first bar creates only a staged intent; no fabricated fill. A late scheduler run, missing 5m candle or earlier journal alteration stops the paper engine rather than retrospectively pretending it traded. Reports are simulated, not independent validation of profitability. No auto cleanup of dependent modules. Real exchange order implementation deliberately omitted until separate explicit authorization, broker/account specification, and audited sandbox safety gate.
