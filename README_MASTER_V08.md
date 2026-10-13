# CQWE V0.8 Research MASTER — no live orders

This archive contains a read-only V08 OI module plus a reference snapshot of V06/V07 source. The installer adds ONLY V08 files, never overwrites existing V07 or any local data.

Evidence patterns: Freqtrade lookahead checks, Qlib separation of data/models, vectorbt cost stress tests. None guarantees profitability.

CLI:
`C:\Python314\python.exe -m cqwe.oi_lab --klines data/klines/BTCUSDT_5m_7d.json --symbol BTCUSDT --fetch-oi`

Binance historical OI has limited rolling retention; missing data is not reconstructed. OI samples use timestamps <= signal close and may still face publication latency. No live fills or liquidation modeling.

Archive snapshot is for audit/reference, not automatically merged.
