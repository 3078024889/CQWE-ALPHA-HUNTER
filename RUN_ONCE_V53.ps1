$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA';$Py='C:\Python314\python.exe'
function CheckExit([string]$label){if($LASTEXITCODE -ne 0){throw "${label}_FAILED exit=$LASTEXITCODE"}}
foreach($dir in @('logs','temp','pycache','pip_cache','memory_v52')){New-Item -ItemType Directory -Force -Path (Join-Path $Data $dir)|Out-Null}
$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP
Set-Location $Repo
if(!(Test-Path 'tests\test_v53.py')){
 Write-Host '=== INSTALL V53 ==='
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'INSTALL_MASTER_V53.ps1');CheckExit 'INSTALL'
}else{
 & git ls-files --error-unmatch 'tests/test_v53.py'|Out-Null;CheckExit 'TRACKED_V53'
 Write-Host 'V53_ALREADY_INSTALLED'
}
Write-Host '=== V53 ADVERSARIAL LINEAGE TESTS ==='
& $Py -m unittest discover -s tests -p test_v53.py -q;CheckExit 'V53_TESTS'
Write-Host '=== READ-ONLY ALL-GENERATION LIVE MEMORY AUDIT ==='
& $Py -m cqwe.lineage_audit_v53 --root 'D:\CQWE_DATA\memory_v52';CheckExit 'LINEAGE_AUDIT'
Write-Host '=== FORWARD TASK STATUS READ-ONLY ==='
$Task=Get-ScheduledTask -TaskName 'CQWE_CTI_Durable_Forward_30m' -ErrorAction SilentlyContinue
if($null -eq $Task){Write-Host 'FORWARD_TASK_MISSING'}else{
 $Info=$Task|Get-ScheduledTaskInfo
 Write-Host "TASK=$($Task.TaskName) STATE=$($Task.State) LAST_EXIT=$($Info.LastTaskResult) LAST_RUN=$($Info.LastRunTime) NEXT=$($Info.NextRunTime)"
}
Write-Host 'CQWE_V53_ONE_SHOT_COMPLETE: ALL GENERATIONS VERIFIED; NO ORDER NO DELETE NO TASK CHANGE' -ForegroundColor Green
