$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter'
$Task='CQWE_Rolling_Shadow_5m'
$Runner=Join-Path $Repo 'RUN_ROLLING_V31.ps1'
if (!(Test-Path -LiteralPath $Runner)) { throw 'V31_RUNNER_MISSING' }
# A separate read-only schedule; V30 hourly forward validation remains intact.
$cmd='powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+$Runner+'"'
& schtasks.exe /Create /SC MINUTE /MO 5 /TN $Task /TR $cmd /F
if ($LASTEXITCODE -ne 0) { throw 'ROLLING_SCHEDULE_FAILED' }
Write-Host 'CQWE_V31_SHADOW_SCHEDULE_CREATED: 5-minute cadence, NO ORDERS'
