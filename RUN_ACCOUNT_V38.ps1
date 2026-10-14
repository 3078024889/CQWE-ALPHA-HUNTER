$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter'
$Py='C:\Python314\python.exe'
$Logs=Join-Path $Repo 'reports\collection_logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
Set-Location $Repo
$Stamp=(Get-Date -Format 'yyyyMMdd_HHmmss_fffffff')
$Out=Join-Path $Logs ('account_v38_'+$Stamp+'.stdout.log')
$Err=Join-Path $Logs ('account_v38_'+$Stamp+'.stderr.log')
$Summary=Join-Path $Logs 'account_v38.log'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START stdout=$Out stderr=$Err" | Out-File $Summary -Append -Encoding utf8
$Exit=1
try {
    $Args=@('-m','cqwe.paper_recovery_v38','--store','reports\v21_evidence',
      '--registry','reports\v27_mutation_registry.json','--legacy','reports\v33_cash_account',
      '--root','reports\v38_cash_segments')
    $p=Start-Process -FilePath $Py -ArgumentList $Args -WorkingDirectory $Repo `
        -RedirectStandardOutput $Out -RedirectStandardError $Err -Wait -PassThru -NoNewWindow
    $Exit=$p.ExitCode
    if(Test-Path $Out){Get-Content $Out | Out-File $Summary -Append -Encoding utf8}
    if(Test-Path $Err){Get-Content $Err | Out-File $Summary -Append -Encoding utf8}
} catch {
    "RUNNER_ERROR: $($_.Exception.Message)" | Out-File $Summary -Append -Encoding utf8
} finally {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EXIT=$Exit" | Out-File $Summary -Append -Encoding utf8
}
exit $Exit
