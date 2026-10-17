param(
    [ValidateSet('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT')]
    [string]$Symbol = 'BTCUSDT',
    [ValidateRange(15,600)]
    [int]$Seconds = 90,
    [string]$Previous = '',
    [string]$Python = 'C:\Python314\python.exe'
)
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Set -Python to an installed Python 3.10+ interpreter.'
}
Push-Location -LiteralPath $PSScriptRoot
try {
    $TidalArgs = @('-X','utf8','-m','cqwe.tidal_hunter','--symbol',$Symbol,'--seconds',[string]$Seconds)
    if ($Previous) { $TidalArgs += @('--previous',$Previous) }
    & $Python @TidalArgs
    if ($LASTEXITCODE -ne 0) { throw 'TIDAL_RESEARCH_FAILED: inspect the preserved session report.' }
} finally {
    Pop-Location
}
