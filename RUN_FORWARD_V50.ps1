$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA';$Py='C:\Python314\python.exe'
foreach($d in @('logs','l2_v47','l2_v49\reports','temp','pycache')){New-Item -ItemType Directory -Force -Path (Join-Path $Data $d)|Out-Null}
$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP
Set-Location $Repo
$Stamp=Get-Date -Format 'yyyyMMdd_HHmmss_fffffff'
$Stdout=Join-Path $Data "logs\v50_$Stamp.stdout.log"
$Stderr=Join-Path $Data "logs\v50_$Stamp.stderr.log"
Write-Host "CAPTURE_STDOUT=$Stdout"
Write-Host "CAPTURE_STDERR=$Stderr"
$Args=@('-m','cqwe.forward_supervisor_v49','--seconds','180','--root','D:\CQWE_DATA\l2_v47','--reports','D:\CQWE_DATA\l2_v49\reports')
$P=Start-Process -FilePath $Py -ArgumentList $Args -WorkingDirectory $Repo -PassThru -Wait -NoNewWindow -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr
$Code=$P.ExitCode
if(Test-Path $Stdout){Get-Content -LiteralPath $Stdout -Tail 15}
if(Test-Path $Stderr){Get-Content -LiteralPath $Stderr -Tail 35}
Write-Host "CAPTURE_EXIT=$Code"
if($Code -ne 0){throw "V50_CAPTURE_FAILED exit=$Code; review $Stdout and $Stderr"}
