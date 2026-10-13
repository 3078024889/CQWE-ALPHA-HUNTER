CQWE Alpha Hunter - read-only research radar v0.1

Requirements: Windows, Python 3.10+ (standard library only), Binance public futures data reachable from your network.

PowerShell:
  py -3 --version
  py -3 -m unittest -v test_radar.py
  py -3 cqwe_radar.py --scan 25 --top 10

Outputs: cqwe_output/radar_<UTC timestamp>.json and .csv

This version does not create orders, connect to accounts, require API keys, or run autonomously in the background.
The scanner ranks 24h USDT turnover (liquidity) then examines 5m bars. It does NOT yet detect emerging illiquid coins, test historical profitability, or measure OI changes (only current OI).
The anomaly score is a heuristic observation measure, not a trading signal.
Binance blocks futures API in some regions. If network or jurisdiction restricts access, do not bypass restrictions; use locally permitted data providers instead.

Safety: Never send API keys, Secret Key, Binance login, 2FA, QR logins or recovery codes to ChatGPT.
