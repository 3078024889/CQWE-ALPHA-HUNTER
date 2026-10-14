$ErrorActionPreference='Stop'
$Name='CQWE_CTI_Durable_Forward_30m';$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA'
$File=Join-Path $Repo 'RUN_FORWARD_V52.ps1';$Folder=Join-Path $Data 'hidden_task_launchers'
if(!(Test-Path $File)){throw 'V52_RUNTIME_SCRIPT_MISSING'}
New-Item -ItemType Directory -Force -Path $Folder|Out-Null
if(Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue){
 $existing=Get-ScheduledTask -TaskName $Name
 if($existing.Actions[0].Execute -notmatch '(?i)wscript\.exe$'){throw 'EXISTING_TASK_UNEXPECTED_REFUSE_MODIFY'}
 Write-Host 'V52_SCHEDULE_ALREADY_PRESENT';exit 0
}
$Launcher=Join-Path $Folder ($Name+'.vbs')
# WScript.Run does not open a visible PowerShell console and propagates exit status.
$Command='"'+$env:WINDIR+'\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$File+'"'
$Escaped=$Command.Replace('"','""')
@('Set shell = CreateObject("WScript.Shell")',('result = shell.Run("'+$Escaped+'", 0, True)'),'WScript.Quit result') | Set-Content -LiteralPath $Launcher -Encoding ASCII
$Action=New-ScheduledTaskAction -Execute (Join-Path $env:WINDIR 'System32\wscript.exe') -Argument ('//B //Nologo "'+$Launcher+'"')
$Trigger=New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(30)) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 365)
$Settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -StartWhenAvailable
$Principal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description 'CTI four-asset public market forward memory; research only; no orders' -ErrorAction Stop|Out-Null
$Task=Get-ScheduledTask -TaskName $Name
if($Task.Actions[0].Execute -notmatch '(?i)wscript\.exe$'){throw 'TASK_INSTALL_VERIFY_FAILED'}
Write-Host "V52_SILENT_SCHEDULE_ENABLED: $Name" -ForegroundColor Green
