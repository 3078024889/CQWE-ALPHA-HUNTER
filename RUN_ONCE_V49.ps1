$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe';$Data='D:\CQWE_DATA'
function Checked([string]$label){if($LASTEXITCODE -ne 0){throw "${label}_FAILED exit=$LASTEXITCODE"}}
foreach($p in @((Join-Path $Data 'logs'),(Join-Path $Data 'temp'),(Join-Path $Data 'pycache'),(Join-Path $Data 'pip_cache'))){New-Item -ItemType Directory -Force -Path $p|Out-Null}
$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP;$env:PIP_CACHE_DIR=Join-Path $Data 'pip_cache'
Set-Location $Repo
if(!(Test-Path 'tests\test_v49.py')){
 Write-Host '=== INSTALL V49 / COMPLETE REGRESSION ===' -ForegroundColor Cyan
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'INSTALL_MASTER_V49.ps1');Checked 'INSTALL'
}else{
 & git ls-files --error-unmatch 'tests/test_v49.py'|Out-Null;Checked 'TRACKED_V49'
 Write-Host 'V49 already installed.'
}
Write-Host '=== 7 V49 ADVERSARIAL TESTS ===' -ForegroundColor Cyan
& $Py -m unittest discover -s tests -p test_v49.py -q;Checked 'ADVERSARIAL'
Write-Host '=== FOUR-ASSET REAL FORWARD CAPTURE; MAX TWO INDEPENDENT ATTEMPTS ===' -ForegroundColor Cyan
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $Repo 'RUN_FORWARD_V49.ps1');Checked 'FORWARD'
Write-Host '=== READ-ONLY COMPLETED SESSION AUDIT ===' -ForegroundColor Cyan
& $Py -m cqwe.forward_supervisor_v49 --root 'D:\CQWE_DATA\l2_v47' --audit-only;Checked 'AUDIT'
Write-Host 'CQWE_V49_ONE_SHOT_COMPLETE: FOUR MARKETS, VERIFIED PRECOMMIT SETTLEMENT, NO TASK MODIFICATION' -ForegroundColor Green
