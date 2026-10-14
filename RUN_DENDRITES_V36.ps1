$ErrorActionPreference = 'Stop'
$Repo = 'D:\CQWE\alpha-hunter'
$Python = 'C:\Python314\python.exe'
$Log = Join-Path $Repo 'reports\collection_logs\dendrites_v36.log'
New-Item -ItemType Directory -Force -Path (Split-Path $Log -Parent) | Out-Null
Set-Location $Repo
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START" | Out-File $Log -Append -Encoding utf8
$ExitCode = 1
try {
    & $Python -m cqwe.evolution_supervisor_v35 2>&1 | Out-File $Log -Append -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "V35_SUPERVISOR_EXIT_$LASTEXITCODE" }
    & $Python -m cqwe.evidence_health_v36 2>&1 | Out-File $Log -Append -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "V36_HEALTH_EXIT_$LASTEXITCODE" }
    $ExitCode = 0
} catch {
    "ERROR: $($_.Exception.Message)" | Out-File $Log -Append -Encoding utf8
} finally {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EXIT=$ExitCode" | Out-File $Log -Append -Encoding utf8
}
exit $ExitCode
