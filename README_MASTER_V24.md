# CQWE V2.4 — Frozen research account, single $10 cash ledger

Two experimental modes: **gate** only executes a V20 validation-promoted rule. If none is admitted, cash is left idle; **shadow** replays predeclared `(0.12, 0.0)` rule for hypothesis generation only. This rule was observed in the same 30-day history, so **shadow is NOT independent out-of-sample evidence**. Both modes use the last 20% of synchronized candles as a historical hypothetical trade exercise; next-open fills, 5bps fee each side and 2bps slippage each side. No real liquidity, minimum lot filters, order book, tax or gas estimate. Extra-cost param is round-trip bps divided between buy and sell.

No unrealized exposure is force-sold on the final historical candle. Every entry/exits shares one $10 cash account, ledger replay, open position and marked equity. V20 validation admitted rule is only selected using first 80%; 20% is never used for selection in gate.

Typical run (from repo root):

```powershell
& 'C:\Python314\python.exe' -m cqwe.frozen_portfolio_v24 --inputs data\v12\BTCUSDT_5m_30d.json data\v12\ETHUSDT_5m_30d.json data\v12\SOLUSDT_5m_30d.json data\v12\BNBUSDT_5m_30d.json --mode gate --output reports\v24_gate.json
```

Run shadow separately with `--mode shadow --output reports\v24_shadow.json`; and cost pressure via `--extra-cost-bps 10`, changing output filename. Shadow findings cannot justify automatic promotion. Unverified returns never count toward realized income.
