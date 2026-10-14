$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Task='CQWE_L2_Forward_30m';$Run=Join-Path $Repo 'RUN_FORWARD_V47.ps1'
if(!(Test-Path $Run)){throw 'V47_TASK_SCRIPT_MISSING'}
$existing=Get-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue
if($null -ne $existing){
 $action=($existing.Actions|ForEach-Object {"$($_.Execute) $($_.Arguments)"}) -join ' '
 if($action -notlike '*RUN_FORWARD_V47.ps1*'){throw 'REFUSE_REPLACE_UNKNOWN_TASK'}
 if($existing.State -eq 'Running'){throw 'REFUSE_REPLACE_RUNNING_TASK'}
}
& schtasks.exe /Create /TN $Task /SC MINUTE /MO 30 /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Run" /F
if($LASTEXITCODE -ne 0){throw 'TASK_CREATE_FAILED'}
Write-Host 'CQWE_V47_TASK_CONFIGURED: FOUR SPOT MARKETS 180s per 30m; NO ORDERS' -ForegroundColor Green
