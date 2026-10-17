# CQWE Copernican V32

V32 replaces independent per-coin voting with a unified market-state decision process.

## Core research contract

1. **Public market data only**. The live adapter uses Bybit V5 public endpoints; no API key, account endpoint, order endpoint, or real order path exists.
2. **BTC anchor for crypto**. BTC defines the primary crypto regime. ETH/SOL/BNB may show residual strength/weakness, but a single altcoin expert cannot create an opposing basket direction by itself.
3. **Multi-timeframe dendrite**. 5m is the base clock. The decision state contains 5m, 15m, 30m, 1h, 4h, 6h and 24h. Three consecutive 5m bars are therefore part of the 15m state rather than three unrelated signals.
4. **Macro over micro**. Higher frames constrain lower-frame entries. A short 5m pullback inside a strong 24h/6h/4h up-regime is treated as a pullback state, not an automatic short.
5. **Structure levels**. The engine derives S1/S2/S3 and R1/R2/R3 from repeated local pivots. They are candidates, not guaranteed support/resistance.
6. **Liquidity-aware exits**. The first opposing order-book liquidity cluster and structural level are used as dynamic exit references. Order-book liquidity is not called a liquidation price and is not treated as guaranteed.
7. **Stop discipline**. A paper position may tighten its invalidation level but never widen it after entry. Targets may migrate only in the favorable direction.
8. **Event veto**. A supplied event-context file can veto new entries around high-risk events. The engine never invents event data.
9. **Evidence hash**. Every live decision is hashed so a later audit can prove which evidence snapshot produced it.
10. **Unified portfolio state**. The paper loop never holds LONG and SHORT simultaneously inside the same crypto basket.

## Live run

```powershell
python -m cqwe.copernican_paper_v32 --cycles 1000 --interval 300
```

This runs paper simulation against fresh public Bybit data every five minutes. It writes:

- `reports/copernican_v32_live.json`
- `reports/copernican_v32_paper_state.json`

`real_orders` is hard-coded to `0` in the research path.

## Validation

```powershell
python -m unittest tests/test_copernican_v32.py -v
```

V32 is a research/paper system, not a profitability certification. A profitable-looking short sample does not authorize live trading. Independent walk-forward validation, execution-cost replay, event out-of-sample testing and long enough forward paper evidence remain required.
