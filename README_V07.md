# CQWE V0.7 Offline Microstructure Research

- Adds: `cqwe/microstructure.py`, `cqwe/run_v07.py`, `tests/test_v07.py`.
- Conservative OI synchronization; no missing-OI imputation.
- 70/30 chronological cohort description with label embargo at split.
- No API credentials, exchange orders, leverage execution, or background tasks.
- Signals can overlap and must NOT be interpreted as independent trading profit.

From `D:\CQWE\alpha-hunter`:

`& "C:\Python314\python.exe" -m cqwe.run_v07 --input "data\klines\BTCUSDT_5m_7d.json" --out "reports\v07_BTC.json"`

Optional `--oi data\oi\BTCUSDT_v06.json` when a real historical OI file is present.

Offline Kline-based study cannot prove AI profitability. No weights/training are provided.
