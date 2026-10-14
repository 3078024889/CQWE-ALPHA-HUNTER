$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA';$Py='C:\Python314\python.exe'
foreach($p in @($Data,(Join-Path $Data 'l2_v47'),(Join-Path $Data 'logs'),(Join-Path $Data 'temp'),(Join-Path $Data 'pycache'))){New-Item -ItemType Directory -Force -Path $p|Out-Null}
$env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP
Set-Location $Repo
$Log=Join-Path $Data 'logs\v47_forward.log'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START"|Out-File $Log -Append -Encoding utf8
$stdout=Join-Path $Data 'logs\v47_last_stdout.log';$stderr=Join-Path $Data 'logs\v47_last_stderr.log'
try{
 $proc=Start-Process -FilePath $Py -ArgumentList @('-m','cqwe.forward_lab_v47','--root','D:\CQWE_DATA\l2_v47','--seconds','180') -WorkingDirectory $Repo -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -Wait -NoNewWindow
 $code=$proc.ExitCode
 if(Test-Path $stdout){Get-Content $stdout -Tail 12|Out-File $Log -Append -Encoding utf8}
 if(Test-Path $stderr){Get-Content $stderr -Tail 30|Out-File $Log -Append -Encoding utf8}
 "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EXIT=$code"|Out-File $Log -Append -Encoding utf8
 if($code -ne 0){exit $code}
}catch{($_|Out-String)|Out-File $Log -Append -Encoding utf8;throw}
