$ErrorActionPreference = 'Stop'
Set-Location 'D:\CQWE\alpha-hunter'
$Py = 'C:\Python314\python.exe'
$LogDir = 'reports\collection_logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'rolling_v31.log'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START" | Out-File $Log -Append -Encoding utf8
& $Py -m cqwe.rolling_signal_v31 --store reports\v21_evidence --registry reports\v27_mutation_registry.json --output-dir reports\v31_rolling_signals 2>&1 | Out-File $Log -Append -Encoding utf8
$Code = $LASTEXITCODE
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EXIT=$Code" | Out-File $Log -Append -Encoding utf8
if ($Code -ne 0) { exit $Code }
