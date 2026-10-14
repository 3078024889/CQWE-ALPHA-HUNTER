$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe'
$Installer='D:\CQWE_MASTER_V45\CQWE_MASTER_V45\INSTALL_MASTER_V45.ps1';$Data='D:\CQWE_DATA'
function Checked([string]$step){if($LASTEXITCODE -ne 0){throw "${step}_FAILED exit=$LASTEXITCODE"}}
if(!(Test-Path $Installer)){throw 'V45_TWO_LEVEL_PACKAGE_NOT_FOUND'}
foreach($p in @($Data,(Join-Path $Data 'research_v45'),(Join-Path $Data 'temp'),(Join-Path $Data 'pip_cache'),(Join-Path $Data 'pycache'))){New-Item -ItemType Directory -Force -Path $p|Out-Null}
$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP;$env:TMPDIR=$env:TEMP;$env:PIP_CACHE_DIR=Join-Path $Data 'pip_cache';$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache'
Set-Location $Repo
if(!(Test-Path 'cqwe\evolution_cycle_v45.py')){
 Write-Host '=== INSTALL V45 / RUN FULL REGRESSION ===' -ForegroundColor Cyan
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer;Checked 'V45_INSTALL'
}else{
 & git ls-files --error-unmatch 'cqwe/evolution_cycle_v45.py'|Out-Null;Checked 'V45_TRACKING'
 Write-Host 'V45 already installed; refusing to overwrite existing files.' -ForegroundColor Yellow
}
Write-Host '=== V45 INDEPENDENT ADVERSARIAL TESTS (15 CASES) ===' -ForegroundColor Cyan
& $Py -m unittest discover -s tests -p test_v45.py -q;Checked 'V45_ADVERSARIAL'
Write-Host '=== V45 FOUR ASSET COPERNICAN + MARKET MAKER BENCHMARK ===' -ForegroundColor Cyan
& $Py -m cqwe.evolution_cycle_v45 --root (Join-Path $Data 'l2_v44') --output-dir (Join-Path $Data 'research_v45');Checked 'V45_COMPETITION'
Write-Host '=== D DRIVE SPACE GOVERNANCE (DRY RUN; ZERO DELETION) ===' -ForegroundColor Cyan
& $Py -m cqwe.storage_governor_v45 --root $Data;Checked 'V45_STORAGE'
Write-Host '=== EXISTING TASKS (READ ONLY) ===' -ForegroundColor Cyan
Get-ScheduledTask -TaskName 'CQWE_Cash_Paper_5m','CQWE_Dendrite_Forward_5m','CQWE_Microstructure_1m' -ErrorAction SilentlyContinue|Select-Object TaskName,State
Write-Host 'CQWE_V45_ONE_SHOT_COMPLETE: historical replay only; NO live edge or maker fill claim; NO deletion or task changes' -ForegroundColor Green
