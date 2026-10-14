$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA';$Py='C:\Python314\python.exe'
foreach($d in @('logs','l2_v47','l2_v52\reports','memory_v52','temp','pycache')){New-Item -ItemType Directory -Force -Path (Join-Path $Data $d)|Out-Null}
$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP
Set-Location $Repo
$Stamp=Get-Date -Format 'yyyyMMdd_HHmmss_fffffff'
$Out=Join-Path $Data "logs\v52_$Stamp.stdout.log";$Err=Join-Path $Data "logs\v52_$Stamp.stderr.log"
$Params=@('-m','cqwe.forward_supervisor_v52','--seconds','180','--root','D:\CQWE_DATA\l2_v47','--memory','D:\CQWE_DATA\memory_v52','--reports','D:\CQWE_DATA\l2_v52\reports')
$P=Start-Process -FilePath $Py -ArgumentList $Params -WorkingDirectory $Repo -Wait -PassThru -NoNewWindow -RedirectStandardOutput $Out -RedirectStandardError $Err
$Code=$P.ExitCode
Write-Host "V52_STDOUT=$Out";Write-Host "V52_STDERR=$Err"
if(Test-Path $Out){Get-Content -LiteralPath $Out -Tail 12}
if(Test-Path $Err){Get-Content -LiteralPath $Err -Tail 25}
Write-Host "V52_CAPTURE_EXIT=$Code"
exit $Code
