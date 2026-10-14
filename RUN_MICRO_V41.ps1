$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe'
Set-Location $Repo
$Logs='reports\collection_logs';New-Item -ItemType Directory -Force -Path $Logs|Out-Null
$Log=Join-Path $Logs 'micro_v41.log'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START" | Out-File -FilePath $Log -Append -Encoding utf8
$Stamp=Get-Date -Format 'yyyyMMdd_HHmmss_fffffff'
$Stdout=Join-Path $Logs "micro_v41_$Stamp.stdout.log"
$Stderr=Join-Path $Logs "micro_v41_$Stamp.stderr.log"
try{
 $P=Start-Process -FilePath $Py -ArgumentList @('-m','cqwe.micro_forward_v41','--symbol','BNBUSDT') -WorkingDirectory $Repo -NoNewWindow -PassThru -Wait -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr
 $Code=$P.ExitCode
 if(Test-Path $Stdout){Get-Content $Stdout |Out-File $Log -Append -Encoding utf8}
 if(Test-Path $Stderr){Get-Content $Stderr |Out-File $Log -Append -Encoding utf8}
 "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EXIT=$Code" |Out-File $Log -Append -Encoding utf8
 if($Code -ne 0){exit $Code}
}catch{
 "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] WRAPPER_ERROR=$($_.Exception.Message) EXIT=1"|Out-File $Log -Append -Encoding utf8
 exit 1
}
