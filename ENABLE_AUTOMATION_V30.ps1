$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter'
$Task='CQWE_Public_Market_Collector'
$Script=Join-Path $Repo 'RUN_RESEARCH_V30.ps1'
if (!(Test-Path -LiteralPath $Script)) { throw 'V30_WORKFLOW_NOT_INSTALLED' }
if (!(Test-Path -LiteralPath (Join-Path $Repo 'cqwe\auto_research_v30.py'))) { throw 'V30_MODULE_MISSING' }
$Old=schtasks.exe /Query /TN $Task 2>&1
if ($LASTEXITCODE -ne 0) { throw 'PREVIOUS_HOURLY_TASK_MISSING: do not create an unknown schedule' }
$Command='powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE\alpha-hunter\RUN_RESEARCH_V30.ps1"'
schtasks.exe /Change /TN $Task /TR $Command
if ($LASTEXITCODE -ne 0) { throw 'V30_TASK_UPDATE_FAILED' }
Write-Host 'CQWE_V30_HOURLY_TASK_UPDATED: collects and evaluates only when ready'
Write-Host 'Existing hourly trigger retained; no real orders, no leverage, no auto model promotion.'
schtasks.exe /Query /TN $Task /V /FO LIST
