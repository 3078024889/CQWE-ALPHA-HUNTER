# CQWE MASTER V1.5 — public-market observation & replay

Scope: research only. Not a Polymarket trading bot. Only Gamma `/markets` and CLOB `/book` public GET endpoints. No account API, credentials, private keys, orders, or background service.

## Installation
Run `INSTALL_MASTER_V15.ps1` from anywhere. Uses `D:\CQWE\alpha-hunter` and `C:\Python314\python.exe`. Requires clean tracked worktree; earlier untracked version files unrelated to V15 are untouched. Checks and never silently overwrites divergent V15 files. Creates local Git commit; remote push is **not** automatic.

## Commands

```powershell
cd D:\CQWE\alpha-hunter
& 'C:\Python314\python.exe' -m cqwe.live_books_v15 capture --limit 3 --shares 10 --out data/polymarket/v15_snapshot.json
& 'C:\Python314\python.exe' -m cqwe.live_books_v15 replay --inputs data/polymarket/v15_snapshot.json --out reports/v15_replay.json
```

## Epistemic limits
- Gamma identifies YES/NO token pairs using a single condition ID. It cannot prove settlement certainty or simultaneous execution.
- CLOB book asks are point-in-time, non-atomic across tokens. Request timing is NOT quote freshness; the code deliberately treats quote age as unverified and **never labels any result executable**.
- `positive_indicative_not_executable` is NOT alpha, fill, settled arbitrage or realized profit.
- The fee buffer is a research assumption, not a fetched market-specific fee schedule.
- The same event repeatedly observed is serially correlated; snapshots are not independent return samples.
- No direct per-order archival historical replay. Replay is of snapshots captured by this project only.
- Check Polymarket terms, access restrictions and jurisdictional rules before any future account use.

## Source research
- Official Gamma API: https://gamma-api.polymarket.com/docs
- Polymarket CLOB GET book: https://docs.polymarket.com/developers/CLOB/prices-books/get-order-book
- Open source reference architecture: https://github.com/pascal-labs/polymarket-sdk
