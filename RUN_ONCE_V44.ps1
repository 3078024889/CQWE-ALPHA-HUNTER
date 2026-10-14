$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe'
$Installer='D:\CQWE_MASTER_V44\CQWE_MASTER_V44\INSTALL_MASTER_V44.ps1'
$Data='D:\CQWE_DATA';$Root=Join-Path $Data 'l2_v44';$LogDir=Join-Path $Data 'logs'
function Checked([string]$step){if($LASTEXITCODE -ne 0){throw "${step}_FAILED exit=$LASTEXITCODE"}}
if(!(Test-Path $Installer)){throw 'V44_TWO_LEVEL_PACKAGE_NOT_FOUND'}
foreach($p in @($Data,$Root,$LogDir,(Join-Path $Data 'temp'),(Join-Path $Data 'pip_cache'),(Join-Path $Data 'python_deps'))){New-Item -ItemType Directory -Force -Path $p|Out-Null}
$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP;$env:TMPDIR=$env:TEMP;$env:PIP_CACHE_DIR=Join-Path $Data 'pip_cache';$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache'
$env:PYTHONPATH=(Join-Path $Data 'python_deps') + [IO.Path]::PathSeparator + $Repo
Set-Location $Repo
if(!(Test-Path 'cqwe\four_asset_lab_v44.py')){
 Write-Host '=== INSTALL V44 AND RUN FULL REGRESSION ===' -ForegroundColor Cyan
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer;Checked 'V44_INSTALL'
}else{
 & git ls-files --error-unmatch 'cqwe/four_asset_lab_v44.py'|Out-Null;Checked 'V44_TRACKING'
 Write-Host 'V44 installed; not overwriting any existing files.' -ForegroundColor Yellow
}
Write-Host '=== TEST FOUR-ASSET LAB ===' -ForegroundColor Cyan
& $Py -m unittest discover -s tests -p test_v44.py -q;Checked 'V44_SPECIAL_TESTS'
Write-Host '=== VERIFY PUBLIC WEBSOCKET DEPENDENCY ===' -ForegroundColor Cyan
& $Py -c "import websocket;print('WEBSOCKET_CLIENT_READY')"
if($LASTEXITCODE -ne 0){
 & $Py -m pip install --disable-pip-version-check --target (Join-Path $Data 'python_deps') 'websocket-client>=1.8,<2';Checked 'WS_DEPENDENCY'
 & $Py -c "import websocket;print('WEBSOCKET_CLIENT_READY')";Checked 'WS_IMPORT'
}
Write-Host '=== REAL BINANCE SPOT FOUR-ASSET L2+TRADE PROBE (75 SECONDS) ===' -ForegroundColor Cyan
$Stamp=(Get-Date -Format 'yyyyMMdd_HHmmss')
$Stdout=Join-Path $LogDir "v44_$Stamp.stdout.log";$Stderr=Join-Path $LogDir "v44_$Stamp.stderr.log"
$Proc=Start-Process -FilePath $Py -ArgumentList @('-m','cqwe.four_asset_lab_v44','--seconds','75','--root',$Root) -WorkingDirectory $Repo -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr -Wait -PassThru -NoNewWindow
if(Test-Path $Stdout){Get-Content $Stdout -Tail 4}
if(Test-Path $Stderr){Get-Content $Stderr -Tail 50}
if($Proc.ExitCode -ne 0){throw "V44_FOUR_ASSET_PUBLIC_CAPTURE_FAILED exit=$($Proc.ExitCode) | see $Stderr"}
Write-Host '=== INDEPENDENT HASH AND SESSION AUDIT ===' -ForegroundColor Cyan
& $Py -m cqwe.four_asset_lab_v44 --root $Root --audit-only;Checked 'V44_AUDIT'
Write-Host '=== NO TASK/ACCOUNT MODIFICATION ===' -ForegroundColor Cyan
Get-ScheduledTask -TaskName 'CQWE_Cash_Paper_5m','CQWE_Dendrite_Forward_5m','CQWE_Microstructure_1m' -ErrorAction SilentlyContinue |Select-Object TaskName,State
Write-Host 'CQWE_V44_ONE_SHOT_COMPLETE: FOUR PUBLIC SPOT BOOKS VERIFIED; RESEARCH ONLY NO ORDERS NO PROFIT CLAIM' -ForegroundColor Green
