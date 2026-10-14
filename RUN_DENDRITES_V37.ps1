$ErrorActionPreference = 'Stop'
$Repo = 'D:\CQWE\alpha-hunter'
$Py = 'C:\Python314\python.exe'
$Log = Join-Path $Repo 'reports\collection_logs\dendrites_v37.log'
New-Item -ItemType Directory -Force -Path (Split-Path $Log -Parent) | Out-Null
Set-Location $Repo
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START" | Out-File $Log -Append -Encoding utf8
$Code = 1
try {
    & $Py -m cqwe.evolution_supervisor_v35 2>&1 | Out-File $Log -Append -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "SUPERVISOR_EXIT_$LASTEXITCODE" }
    & $Py -m cqwe.evidence_health_v36 2>&1 | Out-File $Log -Append -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "EVIDENCE_HEALTH_EXIT_$LASTEXITCODE" }
    & $Py -m cqwe.operational_truth_v37 2>&1 | Out-File $Log -Append -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "OPERATIONAL_TRUTH_EXIT_$LASTEXITCODE" }
    $Code = 0
} catch {
    "ERROR: $($_.Exception.Message)" | Out-File $Log -Append -Encoding utf8
} finally {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EXIT=$Code" | Out-File $Log -Append -Encoding utf8
}
exit $Code
