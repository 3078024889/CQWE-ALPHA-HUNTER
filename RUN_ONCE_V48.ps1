$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe';$Data='D:\CQWE_DATA'
function Checked([string]$step){if($LASTEXITCODE -ne 0){throw "${step}_FAILED exit=$LASTEXITCODE"}}
New-Item -ItemType Directory -Force -Path (Join-Path $Data 'logs'),(Join-Path $Data 'temp'),(Join-Path $Data 'pycache'),(Join-Path $Data 'pip_cache')|Out-Null
$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP
$env:PIP_CACHE_DIR=Join-Path $Data 'pip_cache'
Set-Location $Repo
if(!(Test-Path 'tests\test_v48.py')){
 Write-Host '=== INSTALL V48 AND ALL TESTS ===' -ForegroundColor Cyan
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'INSTALL_MASTER_V48.ps1');Checked 'INSTALL'
}else{
 & git ls-files --error-unmatch 'tests/test_v48.py'|Out-Null;Checked 'V48_TRACKED'
 Write-Host 'V48 already installed; no reinstall.'
}
Write-Host '=== V48 FALSIFICATION TESTS ===' -ForegroundColor Cyan
& $Py -m unittest discover -s tests -p test_v48.py -q;Checked 'TESTS'
Write-Host '=== PUBLIC SPOT ONE-SHOT LIVE CHECK (BNBUSDT, NO ORDERS) ===' -ForegroundColor Cyan
# Existing V41 wrapper writes stdout/stderr to existing collection_logs.
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $Repo 'RUN_MICRO_V41.ps1');$LiveExit=$LASTEXITCODE
$Main=Join-Path $Repo 'reports\collection_logs\micro_v41.log'
if(Test-Path $Main){Get-Content -LiteralPath $Main -Tail 8}
if($LiveExit -ne 0){throw "LIVE_MICRO_V41_FAILED exit=$LiveExit; inspect reports\collection_logs\micro_v41.log"}
Write-Host 'CQWE_V48_ONE_SHOT_COMPLETE: STALE_TRADE_ROOT_CAUSE_FIXED; REAL PUBLIC CAPTURE RETURNED 0' -ForegroundColor Green
Write-Host 'NOTE: only V41 BNB one-shot verified; V47 forward multi-asset is separate.'
