$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Name='CQWE_Microstructure_1m'
$Script=Join-Path $Repo 'RUN_MICRO_V41.ps1'
if(!(Test-Path $Script)){throw 'V41_SCRIPT_NOT_FOUND'}
$Action='powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+$Script+'"'
# Windows schtasks with /SC MINUTE /MO 1 is a one-minute observation cadence.
# This task is intentionally separate from the existing cash-paper and dendrite tasks.
& schtasks.exe /Create /TN $Name /TR $Action /SC MINUTE /MO 1 /F | Out-Host
if($LASTEXITCODE -ne 0){throw 'V41_TASK_CREATE_FAILED'}
$Task=Get-ScheduledTask -TaskName $Name -ErrorAction Stop
$Text=($Task.Actions | ForEach-Object {"$($_.Execute) $($_.Arguments)"}) -join ' '
if($Text -notlike '*RUN_MICRO_V41.ps1*'){throw 'V41_TASK_ACTION_MISMATCH'}
if($Task.State -eq 'Disabled'){throw 'V41_TASK_DISABLED'}
Write-Host 'CQWE_V41_MINUTE_OBSERVER_SCHEDULED: read-only public market data, NO ORDERS' -ForegroundColor Green
