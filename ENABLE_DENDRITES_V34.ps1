$ErrorActionPreference='Stop'
$repo='D:\CQWE\alpha-hunter';$runner=Join-Path $repo 'RUN_DENDRITES_V34.ps1'
if (!(Test-Path $runner)) {throw 'V34_RUNNER_MISSING'}
$task='CQWE_Dendrite_Forward_5m'
$cmd='powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+$runner+'"'
& schtasks.exe /Create /SC MINUTE /MO 5 /TN $task /TR $cmd /F
if ($LASTEXITCODE -ne 0) {throw 'V34_SCHEDULE_FAILED'}
Write-Host 'CQWE_V34_RESEARCH_TASK_CREATED: no orders, independent from V33 account'
