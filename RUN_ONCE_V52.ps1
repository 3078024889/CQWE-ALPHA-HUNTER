$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA';$Py='C:\Python314\python.exe'
function Checked([string]$label){if($LASTEXITCODE -ne 0){throw "${label}_FAILED exit=$LASTEXITCODE"}}
foreach($d in @('logs','temp','pycache','pip_cache','l2_v47','l2_v52\reports','memory_v52')){New-Item -ItemType Directory -Force -Path (Join-Path $Data $d)|Out-Null}
$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP;$env:PIP_CACHE_DIR=Join-Path $Data 'pip_cache'
Set-Location $Repo
if(!(Test-Path 'tests\test_v52.py')){
 Write-Host '=== INSTALL V52 / FULL REGRESSION ===' -ForegroundColor Cyan
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'INSTALL_MASTER_V52.ps1');Checked 'INSTALL'
}else{
 & git ls-files --error-unmatch 'tests/test_v52.py'|Out-Null;Checked 'TRACKED_V52'
 Write-Host 'V52 already installed.'
}
Write-Host '=== V52 ADVERSARIAL MEMORY TESTS ===' -ForegroundColor Cyan
& $Py -m unittest discover -s tests -p test_v52.py -q;Checked 'MEMORY_TESTS'
Write-Host '=== REAL FOUR-ASSET 180s DURABLE FORWARD ===' -ForegroundColor Cyan
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $Repo 'RUN_FORWARD_V52.ps1');Checked 'CAPTURE'
Write-Host '=== ENABLE RESEARCH-ONLY SILENT FORWARD 30m ===' -ForegroundColor Cyan
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repo 'ENABLE_FORWARD_V52.ps1');Checked 'SCHEDULE'
Write-Host 'CQWE_V52_ONE_SHOT_COMPLETE: FOUR VERIFIED MEMORY CHECKPOINTS; SILENT RESEARCH SCHEDULE; NO ORDERS' -ForegroundColor Green
