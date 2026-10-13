$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter'
$Runner=Join-Path $Repo 'RUN_ACCOUNT_V32.ps1'
if (!(Test-Path $Runner)) { throw 'V32_RUNNER_NOT_FOUND' }
$Task='CQWE_Cash_Paper_5m'
$cmd='powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+$Runner+'"'
& schtasks.exe /Create /SC MINUTE /MO 5 /TN $Task /TR $cmd /F
if ($LASTEXITCODE -ne 0) {throw 'V32_SCHEDULE_FAILED'}
Write-Host 'CQWE_V32_PAPER_SCHEDULE_CONFIGURED: no real orders'
