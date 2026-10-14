# CQWE V4.2 — Binance Spot sequence-verified L2 research

Data: `wss://stream.binance.com:9443/ws/bnbusdt@depth@100ms` and Binance public REST `api/v3/depth`. No API key and **no trading**.

Independent reference: Binance official spot WebSocket local order book algorithm. Buffer depth diffs BEFORE REST snapshot; validate `[U,u]` against lastUpdateId; refuse gaps, crossed books and tampered files. Reader continues receiving while HTTP snapshot downloads. Disconnects fail closed; new session starts from a fresh snapshot, never invents missing data. Bound each research capture to a 65-second session to control memory and API load; this is NOT a 24/7 continuously synchronized book yet.

The source `cqwe/l2_replay_v42.py` also creates 60-second future *quote-crossing proxy* outcomes with two-sided fees/slippage; they are neither real nor independently executable fills. Never auto-enable real trading based on this metric. Source is original code informed by Binance official protocol, not vendor code copied verbatim. The book is limited to 1000 levels and is NOT full market depth.

Default dependency: optional freely available `websocket-client` (Python package). RUN_ONCE explicitly reports the dependency and attempts `pip install websocket-client` from PyPI if absent. This network action is shown in the console and costs no CQWE trading capital. If live collection fails, scripts do not schedule it or call it success. V4.1 scheduled one-minute REST observer remains unchanged; to avoid rate accumulation V4.2 does not add automatic continuous runs.

**Limits**: No cancellation vs trade causal attribution without matched trade events; no own queue position, no fill, no maker identity, no verified profit; the L2 book is only as accurate as synchronization and exchange updates. Multiple independent sessions MUST NOT be joined as a continuous market history. `STOP` and `GAP` delimit sessions. Probe `BNBUSDT` only; no multi-symbol multiplexor enabled in this version.

The installer ONLY adds files into a clean Git main checkout and commits locally; no push; does not delete existing evidence, no overwrite. Older models retained for audit.
