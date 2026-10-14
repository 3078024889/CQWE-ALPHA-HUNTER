# CQWE MASTER V3.7 — 盈利证据真值闸门 / 运行健康审计

## 研究结论边界
V3.6的 `FRESH` 和 `settled_steps=12` 仅证明研究数据可读、记录了12次成熟预测，**不能证明有盈利交易**。
V3.7专门读取和核验两套现存的独立证据：

1. V3.5/V3.6树突实验谱系及预测误差、跨谱系缺口、行情新鲜度。
2. V3.3共享$10现金账户的逐根SHA256账本，包括已记模拟买卖、账户权益、显式手续费与回撤。

始终保留两者各自独立的评价标准：预测误差不是成交收益；模拟权益不是实际到账。
如果不存在V3.3账户记录，则报告 `NO_ACCOUNT_FRAMES`，绝不声称赚钱。

## Windows installation
Extract the ZIP into `D:\CQWE_MASTER_V37` so the script lives at:
`D:\CQWE_MASTER_V37\CQWE_MASTER_V37\INSTALL_MASTER_V37.ps1`

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V37\CQWE_MASTER_V37\INSTALL_MASTER_V37.ps1"
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.operational_truth_v37
Get-Content reports\v37_operational_truth.json -Raw
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE\alpha-hunter\ENABLE_DENDRITES_V37.ps1"
```

Report `reports/v37_operational_truth.json` is a **mutable, derived** status view, never an immutable experiment artifact.
V3.7 never modifies old lineage journals, learned weights, trades or wallets. `PAPER_POSITIVE_NOT_REAL_PROFIT` means simulated positive equity only, not profitability proof.

## Known limitations
- V3.5 gap recovery still starts new epoch with reset learning weights. V3.7 audits gaps, but does not inherit unvalidated weights.
- A period of no trades, short observation horizon, or the absence of real fill evidence cannot justify live-trading promotion.
- No ability to access user's Windows state remotely. Windows verification is distinct from reference-environment tests.
- Existing order feasibility is a paper `$5` threshold; exchange filters are not verified.
- Execution price uses hypothetical future-bar observation, not actual executable bids/asks.
- No real orders, margin, leverage, automatic strategy promotion, exchange keys, or Git push.
