$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA';$Py='C:\Python314\python.exe'
function CheckExit([string]$label){if($LASTEXITCODE -ne 0){throw "${label}_FAILED exit=$LASTEXITCODE"}}
foreach($dir in @('logs','temp','pycache','research_v54','memory_v52')){New-Item -ItemType Directory -Force -Path (Join-Path $Data $dir)|Out-Null}
$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP
Set-Location $Repo
if(!(Test-Path 'tests\test_v54.py')){
 Write-Host '=== INSTALL CUMULATIVE V54 (V52 BASE + V53 FIX) ==='
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'INSTALL_MASTER_V54.ps1');CheckExit 'INSTALL'
}else{
 & git ls-files --error-unmatch 'tests/test_v54.py'|Out-Null;CheckExit 'TRACKED_V54'
 Write-Host 'V54_ALREADY_INSTALLED'
}
Write-Host '=== V54 TEN INDEPENDENT RESEARCH VALIDATION CASES ==='
& $Py -m unittest discover -s tests -p test_v54.py -q;CheckExit 'V54_TESTS'
Write-Host '=== FULL-LINEAGE FOUR-SYMBOL VALIDATION ==='
& $Py -m cqwe.lineage_audit_v53 --root 'D:\CQWE_DATA\memory_v52';CheckExit 'LINEAGE_AUDIT'
Write-Host '=== AUDITED PRECOMMITTED COMPETITION REPORT ==='
& $Py -m cqwe.forward_competition_v54 --memory 'D:\CQWE_DATA\memory_v52' --output 'D:\CQWE_DATA\research_v54';CheckExit 'COMPETITION'
Write-Host '=== EXISTING DURABLE TASK STATUS (READ ONLY) ==='
$Task=Get-ScheduledTask -TaskName 'CQWE_CTI_Durable_Forward_30m' -ErrorAction SilentlyContinue
if($null -eq $Task){Write-Host 'TASK_MISSING'}else{
 $Info=$Task|Get-ScheduledTaskInfo
 Write-Host "TASK=$($Task.TaskName) STATE=$($Task.State) LAST_EXIT=$($Info.LastTaskResult) LAST_RUN=$($Info.LastRunTime) NEXT=$($Info.NextRunTime)"
}
Write-Host 'CQWE_V54_ONE_SHOT_COMPLETE: CAUSAL COMPETITION REPORT VERIFIED; NO ORDERS NO DELETION' -ForegroundColor Green
