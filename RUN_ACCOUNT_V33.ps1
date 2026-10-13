$ErrorActionPreference='Stop'
Set-Location 'D:\CQWE\alpha-hunter'
$Py='C:\Python314\python.exe'
$Logs='reports\collection_logs';New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Log=Join-Path $Logs 'account_v33.log'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START" | Out-File $Log -Append -Encoding utf8
& $Py -m cqwe.live_paper_v33 --store reports\v21_evidence --registry reports\v27_mutation_registry.json --output-dir reports\v33_cash_account 2>&1 | Out-File $Log -Append -Encoding utf8
$Code=$LASTEXITCODE
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EXIT=$Code" | Out-File $Log -Append -Encoding utf8
if ($Code -ne 0) {exit $Code}
