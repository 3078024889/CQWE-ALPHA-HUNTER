# CQWE V3.1: rolling read-only prospective research

- V3.0 frozen forward account evidence is **preserved**. No alteration to `data/future`, V30 receipt or trained model state.
- Every run fetches 400 *past, fully closed* 5-minute public Binance candles across four symbols; 400 is a pragmatic warmup, **not an optimum**.
- Emits a SHA256-identified, immutable next-bar shadow research signal for the next 5-minute candle. If no signal passes, it records `HOLD_CASH`.
- Future runs match previously recorded signals with subsequent close prices. One-bar close-to-close return is **not** executable trading PnL, and no future outcomes are consulted when making the prediction.
- No model updates, self-modification, buy/sell orders, exchange API keys, or claims of stable profit. The existing V28 fixed-horizon $10 account test remains separate.
- Time alignment: A run before the candle closes should use the last **fully closed** candle. An hourly schedule is too sparse for next-candle observations; use the optional 5-minute schedule. On a missed interval, do not manufacture settlement data.
- Requires existing V21 checkpoint and V27 registry. No synthetic data substitutions if public API is unavailable.
- Log: `reports/collection_logs/rolling_v31.log`; evidence: `reports/v31_rolling_signals/`.
- First run: `& 'C:\Python314\python.exe' -m cqwe.rolling_signal_v31`.
- Enable only after one successful manual trial: `powershell -NoProfile -ExecutionPolicy Bypass -File 'D:\CQWE\alpha-hunter\ENABLE_ROLLING_V31.ps1'`.
- To check task: `schtasks /Query /TN CQWE_Rolling_Shadow_5m /V /FO LIST`.
- Accuracy limitations: Binance REST polling delay, public data timestamps, trigger and model state selection bias, and non-independent contiguous market bars. Do not assume exchange fill, depth, or tradability on $10.
