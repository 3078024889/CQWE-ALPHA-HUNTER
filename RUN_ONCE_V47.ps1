$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA';$Py='C:\Python314\python.exe';$Package='D:\CQWE_MASTER_V47\CQWE_MASTER_V47';$Task='CQWE_L2_Forward_30m'
function Checked([string]$step){if($LASTEXITCODE -ne 0){throw "${step}_FAILED exit=$LASTEXITCODE"}}
foreach($p in @($Data,(Join-Path $Data 'logs'),(Join-Path $Data 'l2_v47'),(Join-Path $Data 'temp'),(Join-Path $Data 'pycache'),(Join-Path $Data 'pip_cache'))){New-Item -ItemType Directory -Force -Path $p|Out-Null}
$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP;$env:PIP_CACHE_DIR=Join-Path $Data 'pip_cache'
Set-Location $Repo
if(!(Test-Path (Join-Path $Package 'INSTALL_MASTER_V47.ps1'))){throw 'TWO_LEVEL_V47_PACKAGE_MISSING'}
if(!(Test-Path 'cqwe\forward_lab_v47.py')){
 Write-Host '=== INSTALL V47 ===' -ForegroundColor Cyan
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Package 'INSTALL_MASTER_V47.ps1');Checked 'INSTALL'
}else{
 & git ls-files --error-unmatch 'cqwe/forward_lab_v47.py'|Out-Null;Checked 'V47_TRACKED'
 Write-Host 'V47 already installed; no reinstall.'
}
Write-Host '=== V47 ADVERSARIAL TESTS ===' -ForegroundColor Cyan
& $Py -m unittest discover -s tests -p test_v47.py -q;Checked 'TESTS'
Write-Host '=== FIRST REAL FOUR-ASSET 180 SECOND FORWARD EXPERIMENT ===' -ForegroundColor Cyan
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repo 'RUN_FORWARD_V47.ps1');Checked 'FORWARD'
Write-Host '=== HASH CHAIN AND PROSPECTIVE AUDIT ===' -ForegroundColor Cyan
& $Py -m cqwe.forward_lab_v47 --root (Join-Path $Data 'l2_v47') --audit-only;Checked 'AUDIT'
Write-Host '=== ENABLE SINGLE BOUNDED 30-MIN TASK ===' -ForegroundColor Cyan
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repo 'ENABLE_FORWARD_V47.ps1');Checked 'SCHEDULE'
Get-ScheduledTask -TaskName $Task | Select-Object TaskName,State
Write-Host 'CQWE_V47_ONE_SHOT_COMPLETE: VERIFIED PROSPECTIVE SAMPLER; NO ORDERS OR PROFIT CLAIM' -ForegroundColor Green
