$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Runner=Join-Path $Repo 'RUN_DENDRITES_V35.ps1'
if(!(Test-Path $Runner)){throw 'V35_RUNNER_MISSING'}
# Only replace the existing V34 research task after explicit user invocation.
# Do not touch collection, rolling signals, or the separate cash-paper account.
$Name='CQWE_Dendrite_Forward_5m'
$Action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File "'+$Runner+'"')
$Trigger=New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
# Maintain current user's interactive logon, no password collection.
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host 'CQWE_V35_TASK_UPDATED: five-minute single-instance dendrite supervisor; NO ORDERS' -ForegroundColor Green
