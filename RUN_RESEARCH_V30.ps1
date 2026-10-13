$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'D:\CQWE\alpha-hunter'
$Py='C:\Python314\python.exe'
$LogDir='D:\CQWE\alpha-hunter\reports\collection_logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log=Join-Path $LogDir 'market_research_v30.log'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START" | Out-File $Log -Append -Encoding utf8
try {
    & $Py -m cqwe.auto_research_v30 2>&1 | Out-File $Log -Append -Encoding utf8
    $Code=$LASTEXITCODE
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EXIT=$Code" | Out-File $Log -Append -Encoding utf8
    if ($Code -ne 0) { exit $Code }
} catch {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR=$($_.Exception.Message)" | Out-File $Log -Append -Encoding utf8
    exit 1
}
