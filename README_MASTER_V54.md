# CQWE V5.4 complete master (cumulative from verified V5.2)

Unzip so the Windows script path is `D:\CQWE_MASTER_V54\CQWE_MASTER_V54\RUN_ONCE_V54.ps1`.
Run: `powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V54\CQWE_MASTER_V54\RUN_ONCE_V54.ps1"`.

V5.3 originally failed `git diff --cached --check` because `tests/test_v53.py` had trailing whitespace. V5.4 packages the corrected V5.3 lineage modules together with the V5.4 competition audit, and installs directly on an unmodified, clean V5.2 repository. No need to separately install V5.3.

Existing V5.2 30-minute research task remains unchanged. V5.4 is read-only on existing memory lineage and public capture evidence, but writes an append-only research report under `D:\CQWE_DATA\research_v54`. No market orders. No automatic model promotion. The experiment compares precommitted six-genotype predictions and public-quote baselines; markout proxies are not fill or PnL. Gate floors are research criteria, not proof of tradable profits. Archived failed sessions are not rewritten.
