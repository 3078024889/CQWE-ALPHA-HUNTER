$ErrorActionPreference = 'Stop'
$Repo = 'D:\CQWE\alpha-hunter'
$Runner = Join-Path $Repo 'RUN_DENDRITES_V37.ps1'
$Python = 'C:\Python314\python.exe'
if (!(Test-Path $Runner) -or !(Test-Path $Python)) { throw 'V37_DEPENDENCY_MISSING' }
$Name = 'CQWE_Dendrite_Forward_5m'
# Replaces the existing dendrite research task only; other tasks remain untouched.
$now = Get-Date
$block = [int]([Math]::Floor($now.Minute / 5) * 5)
$at = Get-Date -Year $now.Year -Month $now.Month -Day $now.Day -Hour $now.Hour -Minute $block -Second 20
if ($at -le $now) { $at = $at.AddMinutes(5) }
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + $Runner + '"')
$Trigger = New-ScheduledTaskTrigger -Once -At $at -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host 'CQWE_V37_TASK_UPDATED: single 5m supervisor + evidence + paper account truth. NO ORDERS.' -ForegroundColor Green
Write-Host "NEXT_SCHEDULE_FROM=$at"
