$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe';$Data='D:\CQWE_DATA'
$Installer='D:\CQWE_MASTER_V46\CQWE_MASTER_V46\INSTALL_MASTER_V46.ps1'
function Checked([string]$step){if($LASTEXITCODE -ne 0){throw "${step}_FAILED exit=$LASTEXITCODE"}}
if(!(Test-Path $Installer)){throw 'V46_TWO_LEVEL_PACKAGE_NOT_FOUND'}
foreach($p in @($Data,(Join-Path $Data 'research_v46'),(Join-Path $Data 'temp'),(Join-Path $Data 'pip_cache'),(Join-Path $Data 'pycache'))){New-Item -ItemType Directory -Force -Path $p|Out-Null}
$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP;$env:TMPDIR=$env:TEMP;$env:PIP_CACHE_DIR=Join-Path $Data 'pip_cache';$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache'
Set-Location $Repo
if(!(Test-Path 'cqwe\readiness_gate_v46.py')){
 Write-Host '=== INSTALL V46 / FULL TESTS ===' -ForegroundColor Cyan
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer;Checked 'V46_INSTALL'
}else{
 & git ls-files --error-unmatch 'cqwe/readiness_gate_v46.py'|Out-Null;Checked 'V46_TRACKING'
 Write-Host 'V46 already tracked; no reinstall.' -ForegroundColor Yellow
}
Write-Host '=== V46 FALSIFICATION TESTS ===' -ForegroundColor Cyan
& $Py -m unittest discover -s tests -p test_v46.py -q;Checked 'V46_FALSIFICATION'
Write-Host '=== V46 REAL HISTORICAL FOUR-MARKET READINESS ===' -ForegroundColor Cyan
& $Py -m cqwe.readiness_gate_v46 --root (Join-Path $Data 'l2_v44') --output-dir (Join-Path $Data 'research_v46');Checked 'V46_AUDIT'
Write-Host '=== SAFE SPACE PLAN; ZERO DELETION ===' -ForegroundColor Cyan
& $Py -m cqwe.storage_governor_v45 --root $Data;Checked 'SAFE_SPACE'
Write-Host '=== EXISTING TASKS (READ ONLY) ===' -ForegroundColor Cyan
Get-ScheduledTask -TaskName 'CQWE_Cash_Paper_5m','CQWE_Dendrite_Forward_5m','CQWE_Microstructure_1m' -ErrorAction SilentlyContinue|Select-Object TaskName,State
Write-Host 'CQWE_V46_ONE_SHOT_COMPLETE: NO ORDERS, NO PROMOTION, NO DELETION, NO TASK CHANGES' -ForegroundColor Green
