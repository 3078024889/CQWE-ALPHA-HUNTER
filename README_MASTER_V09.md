# CQWE ALPHA HUNTER V0.9 — conservative strategy research master

**Research only. No API key, live trading, leverage, withdrawal capability, scheduled tasks, or background services.**

## Based on existing local repository

`D:\CQWE\alpha-hunter` and `C:\Python314\python.exe`.  Installer adds three files and does not overwrite existing code, local K-line data, OI datasets, logs, models or reports. `snapshot/` is an uninstalled **reference copy** of known V0.8-era sources, not a license to overwrite the live repository.

## Research references (ideas, not code copying)

- Freqtrade lookahead-analysis and recursive-analysis: https://docs.freqtrade.io/en/2026.5/lookahead-analysis/ ; https://www.freqtrade.io/en/2026.7/recursive-analysis/
- Microsoft Qlib modular forecasting / research workflow: https://github.com/microsoft/qlib
- Hummingbot connector and execution architecture: https://hummingbot.org/docs/
- Bysik and Ślepaczuk, 2026, transaction-cost aware Bitcoin ML walkforward paper: https://arxiv.org/abs/2606.00060

## V09 additions

- Four **predeclared research cohorts**: high-volume breakout, taker-buy-confirmed breakout, OI-rising subset, and OI-nonrising control. The OI groups cannot form when OI observations are missing; no fake filling.
- Split at 70% of **time**, with outcomes finishing within their partition. Non-overlapping event windows within each cohort.
- Four fee/slippage stress levels, reported on separate descriptive event metrics (not simulated account cash PnL).
- Coverage gate requiring OI observations and both OI cohorts to reach at least the configured minimum count **on each partition**. This does not imply statistical significance.
- Fails on invalid OHLC, K-line timing gaps, duplicate/invalid OI and negative assumptions; does not infer future signals from label data.

## How to run after installation

```powershell
cd D:\CQWE\alpha-hunter
& 'C:\Python314\python.exe' -B -m unittest discover -v
& 'C:\Python314\python.exe' -B -m cqwe.strategy_lab_v09 --klines 'data\klines\BTCUSDT_5m_7d.json' --output 'reports\v09_BTC_study.json'
& 'C:\Python314\python.exe' -B -m cqwe.strategy_lab_v09 --klines 'data\klines\ETHUSDT_5m_7d.json' --output 'reports\v09_ETH_study.json'
# Only if authentic historical OI records are already present:
& 'C:\Python314\python.exe' -B -m cqwe.strategy_lab_v09 --klines 'data\klines\BTCUSDT_5m_7d.json' --oi-file 'data\oi\BTCUSDT_v08_history.json' --output 'reports\v09_BTC_OI_study.json'
```

If OI results contain zero rows, V09 **refuses to assert** an OI-backed edge. The exchange's limited historical availability cannot be reconstructed from prices. V09 does not attempt internet calls itself; fetch and validate genuine historical OI separately.

## What is not done

No deployed AI model, statistically validated edge, live order executor, order-book replay, minute-level real liquidation test, or profitable real account. The provided V09 tests are synthetic. Seven days of data cannot establish reliable returns. The OI endpoints may restrict available history.

## Git

Installer commits new V09 sources **locally only** after tests pass and Git workspace is clean. It does not push, modify Git TLS configuration or weaken SSL verification. Use `git push origin main` manually and verify remote SHA before claiming sync.
