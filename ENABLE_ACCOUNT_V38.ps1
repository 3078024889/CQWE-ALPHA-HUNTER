$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Runner=Join-Path $Repo 'RUN_ACCOUNT_V38.ps1'
$TaskName='CQWE_Cash_Paper_5m'
if(!(Test-Path $Runner)){throw 'V38_RUNNER_MISSING'}
$Existing=Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if($Existing -and $Existing.State -eq 'Running'){throw 'EXISTING_PAPER_TASK_RUNNING_REFUSE_REPLACE'}
# Only the research paper task; never touch trading keys, V32/V33 journals, or dendrite task.
$Action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File "'+$Runner+'"')
$Now=Get-Date;$Bucket=[int]([Math]::Floor($Now.Minute/5)*5)
$At=Get-Date -Year $Now.Year -Month $Now.Month -Day $Now.Day -Hour $Now.Hour -Minute $Bucket -Second 25
if($At -le $Now){$At=$At.AddMinutes(5)}
$Trigger=New-ScheduledTaskTrigger -Once -At $At -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host 'CQWE_V38_ACCOUNT_TASK_UPDATED: only paper simulated account; no real orders'
Write-Host "NEXT_SCHEDULE_FROM=$At"
