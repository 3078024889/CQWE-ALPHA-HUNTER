# CQWE MASTER V2.5 — Independent Cash-Ledger Forensics

**Research only. Zero real orders, not evidence of trading profits.**

V24 user-side: strict gate $10 unchanged; shadow $9.69929590 (6 entries); shadow extra 10bps $9.66456703 (6 entries). V25 verifies rather than assumes ledger consistency. It independently recomputes cash balances, position pairing, simulated closed-trade return and drawdown; compares cost scenarios and identifies changed schedules. It cannot recreate genuine liquidity/quotes from OHLCV nor declare independent holdout after repeated study of this 30-day sample. Ledger's entry slippage is already embedded in fill prices; explicit fill fees must not be conflated with entire cost drag.

Install after V24 on Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V25\CQWE_MASTER_V25\INSTALL_MASTER_V25.ps1"`.

Then:

```powershell
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.account_forensics_v25 `
 --gate "reports\v24_gate.json" `
 --shadow "reports\v24_shadow.json" `
 --stress "reports\v24_shadow_stress10.json" `
 --output "reports\v25_forensics.json"
```

Do not make any new trading decision from these old observations. A new unseen market sample with executable quote/lot/min-notional evidence is required for genuine positive-edge validation.
