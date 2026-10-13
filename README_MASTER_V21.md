# CQWE MASTER V2.1 – verified continuous research replay

V2.1 adds **offline multi-episode chronology, immutable per-episode checkpoint files, file-level SHA256 and cross-episode evidence chains** to V2.0. Run on existing verified Binance 5-minute data; no private API or trades. The 60/20/20 initial V2.0 protocol is *within the initial prefix only*. Later days are sequential adaptive/prequential feedback, **not independent holdout**. V2.1 does not assert profits or auto-discover alpha.

Install: `powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V21\CQWE_MASTER_V21\INSTALL_MASTER_V21.ps1"`.

From `D:\CQWE\alpha-hunter` run:

```powershell
& "C:\Python314\python.exe" -m cqwe.continuous_lab_v21 replay --inputs data\v12\BTCUSDT_5m_30d.json data\v12\ETHUSDT_5m_30d.json data\v12\SOLUSDT_5m_30d.json data\v12\BNBUSDT_5m_30d.json --store reports\v21_evidence
& "C:\Python314\python.exe" -m cqwe.continuous_lab_v21 verify --store reports\v21_evidence
```

Same-source same-config reruns resume idempotently. The evidence store maintains append-only-by-name checkpoints and per-episode SHA hashes; these protect against *accidental corruption*, **not a malicious actor who can rewrite all local files and hashes**. Never edit state files. Simulated event metrics are not executable portfolio profits. No account connection, authenticated signatures, network polling, persistent live daemon, real orders, leverage, betting, or earnings.

## Windows V19 direct upgrade (fixed installer)
This package contains the entire required V20 source, V20 tests, sample data, and its installer. `INSTALL_MASTER_V21.ps1` automatically invokes the bundled V20 installer when `cqwe/self_evolution_v20.py` does not exist, validates the V20 commit, then installs V21. No separately extracted V20 folder is required. Run only this single command from any Windows PowerShell working directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V21\CQWE_MASTER_V21\INSTALL_MASTER_V21.ps1"
```

The final success marker must be emitted by the installer itself, and `git log -1 --oneline` must show the V21 commit. Manually printed messages are not evidence. `V19_REQUIRED` still applies if the actual V19 files are missing. The Windows PowerShell installer itself must be verified on the user's machine.
