$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Python = "C:\Python314\python.exe"

if (-not (Test-Path $Python)) { throw "PYTHON_NOT_FOUND: $Python" }

Set-Location $Repo

Write-Host "=== COPERNICAN V32 VALIDATION ===" -ForegroundColor Cyan
& $Python -m unittest tests/test_copernican_v32.py -v
if ($LASTEXITCODE -ne 0) { throw "V32_TESTS_FAILED" }

Write-Host "`n=== START PAPER SIMULATION ===" -ForegroundColor Green
Write-Host "PUBLIC_DATA=BYBIT"
Write-Host "REAL_ORDERS=0"
Write-Host "INTERVAL=300s"

& $Python -m cqwe.copernican_paper_v32 --cycles 10000 --interval 300
