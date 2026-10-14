$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe'
$Installer='D:\CQWE_MASTER_V42\CQWE_MASTER_V42\INSTALL_MASTER_V42.ps1'
if(!(Test-Path $Installer)){throw 'V42_TWO_LEVEL_PACKAGE_NOT_FOUND'}
Set-Location $Repo
if(!(Test-Path 'cqwe\l2_replay_v42.py')){
 Write-Host '=== INSTALL AND TEST V42 ===' -ForegroundColor Cyan
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer
 if($LASTEXITCODE -ne 0){throw 'V42_INSTALL_FAILED'}
}else{
 & git ls-files --error-unmatch 'cqwe/l2_replay_v42.py' | Out-Null
 if($LASTEXITCODE -ne 0){throw 'V42_SOURCE_NOT_TRACKED'}
 Write-Host 'V42 already installed. Running read-only checks.' -ForegroundColor Yellow
}
Write-Host '=== VERIFY EXISTING AUDIT ===' -ForegroundColor Cyan
& $Py -m cqwe.l2_replay_v42 --audit
if($LASTEXITCODE -ne 0){throw 'V42_AUDIT_FAILED'}
Write-Host '=== VERIFY WEBSOCKET DEPENDENCY ===' -ForegroundColor Cyan
& $Py -c "import websocket; print('WEBSOCKET_CLIENT_READY')"
if($LASTEXITCODE -ne 0){
 Write-Host 'Missing free websocket-client; installing from PyPI (no paid API key).' -ForegroundColor Yellow
 & $Py -m pip install --disable-pip-version-check 'websocket-client>=1.8,<2'
 if($LASTEXITCODE -ne 0){throw 'WEBSOCKET_DEPENDENCY_INSTALL_FAILED'}
 & $Py -c "import websocket; print('WEBSOCKET_CLIENT_READY')"
 if($LASTEXITCODE -ne 0){throw 'WEBSOCKET_DEPENDENCY_VERIFY_FAILED'}
}
Write-Host '=== PUBLIC LIVE L2 65-SECOND PROBE ===' -ForegroundColor Cyan
& $Py -m cqwe.l2_replay_v42 --symbol BNBUSDT --seconds 65
if($LASTEXITCODE -ne 0){throw 'V42_L2_LIVE_NOT_VERIFIED_NO_TASK_CREATED'}
Write-Host '=== EXISTING TASKS (READ ONLY) ===' -ForegroundColor Cyan
foreach($Name in @('CQWE_Cash_Paper_5m','CQWE_Dendrite_Forward_5m','CQWE_Microstructure_1m')){
 $T=Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
 if($null -ne $T){$T|Select-Object TaskName,State;Get-ScheduledTaskInfo -TaskName $Name|Select-Object LastRunTime,LastTaskResult,NextRunTime}
}
Write-Host 'CQWE_V42_ONE_SHOT_COMPLETE: VERIFIED L2 PROBE; NO ORDERS NO AUTO TRADING' -ForegroundColor Green
