$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe'
$Installer='D:\CQWE_MASTER_V43\CQWE_MASTER_V43\INSTALL_MASTER_V43.ps1'
$Data='D:\CQWE_DATA';$Capture=Join-Path $Data 'l2_v43';$LogDir=Join-Path $Data 'logs'
function Checked([string]$step){if($LASTEXITCODE -ne 0){throw "${step}_FAILED exit=$LASTEXITCODE"}}
if(!(Test-Path $Installer)){throw 'V43_TWO_LEVEL_PACKAGE_NOT_FOUND'}
foreach($p in @($Data,$Capture,$LogDir,(Join-Path $Data 'temp'),(Join-Path $Data 'pip_cache'),(Join-Path $Data 'python_deps'))){New-Item -ItemType Directory -Force -Path $p|Out-Null}
$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP;$env:TMPDIR=$env:TEMP;$env:PIP_CACHE_DIR=Join-Path $Data 'pip_cache';$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache'
$env:PYTHONPATH=(Join-Path $Data 'python_deps') + [IO.Path]::PathSeparator + $Repo
Set-Location $Repo
if(!(Test-Path 'cqwe\market_replay_v43.py')){
 Write-Host '=== INSTALL V43 AND TEST ===' -ForegroundColor Cyan
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer;Checked 'V43_INSTALL'
}else{
 & git ls-files --error-unmatch 'cqwe/market_replay_v43.py'|Out-Null;Checked 'V43_TRACKING'
 Write-Host 'V43 already installed, skipping installer.' -ForegroundColor Yellow
}
Write-Host '=== RUN V43 SCIENTIFIC TESTS ===' -ForegroundColor Cyan
& $Py -m unittest discover -s tests -p test_v43.py -q;Checked 'V43_TESTS'
Write-Host '=== VERIFY WEBSOCKET CLIENT ===' -ForegroundColor Cyan
& $Py -c "import websocket;print('WEBSOCKET_CLIENT_READY')"
if($LASTEXITCODE -ne 0){
 Write-Host 'Installing missing websocket-client only to D drive' -ForegroundColor Yellow
 & $Py -m pip install --disable-pip-version-check --target (Join-Path $Data 'python_deps') 'websocket-client>=1.8,<2';Checked 'WS_CLIENT_INSTALL'
 & $Py -c "import websocket;print('WEBSOCKET_CLIENT_READY')";Checked 'WS_CLIENT_VERIFICATION'
}
Write-Host '=== CAPTURE PUBLIC REAL DEPTH AND RAW TRADE FOR 75 SECONDS ===' -ForegroundColor Cyan
$Out=Join-Path $LogDir ('v43_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.stdout.log')
$Err=Join-Path $LogDir ('v43_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.stderr.log')
$Proc=Start-Process -FilePath $Py -ArgumentList @('-m','cqwe.l2_trade_capture_v43','--symbol','BNBUSDT','--seconds','75','--root',$Capture) -WorkingDirectory $Repo -RedirectStandardOutput $Out -RedirectStandardError $Err -Wait -PassThru -NoNewWindow
if(Test-Path $Out){Get-Content $Out -Tail 6}
if(Test-Path $Err){Get-Content $Err -Tail 50}
if($Proc.ExitCode -ne 0){throw "V43_REAL_L2_CAPTURE_FAILED exit=$($Proc.ExitCode) | see $Err"}
Write-Host '=== CAPTURE FILES ON D DRIVE ===' -ForegroundColor Cyan
Get-ChildItem $Capture -File -Filter '*.jsonl'|Sort-Object LastWriteTime -Descending|Select-Object -First 3 FullName,Length,LastWriteTime
Write-Host 'CQWE_V43_ONE_SHOT_COMPLETE; OBSERVATIONS ONLY; NO REAL OR CLAIMED SIMULATED PROFITS' -ForegroundColor Green
