param([string]$Python = 'C:\Python314\python.exe')
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Set -Python to the full path of an installed Python 3.10+ interpreter.'
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $Python -X utf8 -m unittest tests.test_v81_v85 -v
    if ($LASTEXITCODE -ne 0) { throw 'V85_TESTS_FAILED' }
    $V85RunDir = Join-Path $PSScriptRoot ('output\v85_' + [DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss_fff'))
    New-Item -ItemType Directory -Path $V85RunDir -ErrorAction Stop | Out-Null
    $V85First = Join-Path $V85RunDir 'round1.json'
    $V85Second = Join-Path $V85RunDir 'round2.json'
    & $Python -X utf8 -m cqwe.copernican_experiment_v81_v85 --input 'reports\v85_public_20261015\BTCUSDT.batch1.data.json' --output $V85First
    if ($LASTEXITCODE -ne 0) { throw 'V85_FIRST_BATCH_FAILED' }
    & $Python -X utf8 -m cqwe.copernican_experiment_v81_v85 --input 'reports\v85_public_20261015\BTCUSDT.batch2.data.json' --previous $V85First --output $V85Second
    if ($LASTEXITCODE -ne 0) { throw 'V85_SECOND_BATCH_FAILED' }
    Write-Output ('RESEARCH_OUTPUT=' + $V85RunDir)
    Write-Output 'REAL_ORDERS=0; REALIZED_PROFIT=UNVERIFIED; RESEARCH_ONLY'
} finally {
    Pop-Location
}
