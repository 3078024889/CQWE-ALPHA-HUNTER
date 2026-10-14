$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA';$Py='C:\Python314\python.exe'
function Checked([string]$label){if($LASTEXITCODE -ne 0){throw "${label}_FAILED exit=$LASTEXITCODE"}}
foreach($d in @('logs','temp','pycache','pip_cache','l2_v47','l2_v49\reports')){New-Item -ItemType Directory -Force -Path (Join-Path $Data $d)|Out-Null}
$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP;$env:PIP_CACHE_DIR=Join-Path $Data 'pip_cache'
Set-Location $Repo
if(!(Test-Path 'tests\test_v51.py')){
 Write-Host '=== INSTALL V51 / FULL REGRESSION ===' -ForegroundColor Cyan
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'INSTALL_MASTER_V51.ps1');Checked 'INSTALL'
}else{
 & git ls-files --error-unmatch 'tests/test_v51.py'|Out-Null;Checked 'TRACKED_V51'
 Write-Host 'V51 already installed.'
}
Write-Host '=== TEN ADVERSARIAL CAUSAL ORDERING TESTS ===' -ForegroundColor Cyan
& $Py -m unittest discover -s tests -p test_v51.py -q;Checked 'ADVERSARIAL'
Write-Host '=== REAL FOUR-ASSET 180s FORWARD CAPTURE ===' -ForegroundColor Cyan
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $Repo 'RUN_FORWARD_V50.ps1');Checked 'FORWARD'
Write-Host '=== POST-CAPTURE AUDIT ===' -ForegroundColor Cyan
& $Py -m cqwe.forward_supervisor_v49 --root 'D:\CQWE_DATA\l2_v47' --audit-only;Checked 'AUDIT'
Write-Host 'CQWE_V51_ONE_SHOT_COMPLETE: FOUR NEW CAUSAL SESSIONS VERIFIED; NO LIVE TRADES' -ForegroundColor Green
