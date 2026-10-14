$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA';$Py='C:\Python314\python.exe'
foreach($p in @((Join-Path $Data 'logs'),(Join-Path $Data 'l2_v47'),(Join-Path $Data 'l2_v49\reports'),(Join-Path $Data 'temp'),(Join-Path $Data 'pycache'))){New-Item -ItemType Directory -Force -Path $p|Out-Null}
$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP
Set-Location $Repo
$Stamp=Get-Date -Format 'yyyyMMdd_HHmmss_fffffff'
$Stdout=Join-Path $Data "logs\v49_$Stamp.stdout.log"
$Stderr=Join-Path $Data "logs\v49_$Stamp.stderr.log"
Write-Host '=== FOUR-ASSET PRECOMMITTED FORWARD CAPTURE ===' -ForegroundColor Cyan
Write-Host "CAPTURE_STDOUT=$Stdout"
Write-Host "CAPTURE_STDERR=$Stderr"
$Args=@('-m','cqwe.forward_supervisor_v49','--seconds','180','--root','D:\CQWE_DATA\l2_v47','--reports','D:\CQWE_DATA\l2_v49\reports')
try {
 $P=Start-Process -FilePath $Py -ArgumentList $Args -WorkingDirectory $Repo -PassThru -Wait -NoNewWindow -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr
 $Code=$P.ExitCode
 if(Test-Path $Stdout){Get-Content -LiteralPath $Stdout -Tail 16}
 if(Test-Path $Stderr){Get-Content -LiteralPath $Stderr -Tail 50}
 Write-Host "CAPTURE_EXIT=$Code"
 if($Code -ne 0){throw "V49_CAPTURE_FAILED exit=$Code; inspect per-symbol failures above and $Stdout"}
}catch{
 Write-Host "CAPTURE_WRAPPER_ERROR=$($_.Exception.Message)" -ForegroundColor Red
 throw
}
