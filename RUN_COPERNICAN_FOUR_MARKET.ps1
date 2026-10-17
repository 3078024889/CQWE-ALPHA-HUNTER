param(
    [int]$Rounds = 5,
    [int]$SecondsPerRound = 300,
    [string]$DataRoot = 'D:\CQWE_DATA\copernican_liquidity_v2'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$cqwePython = 'C:\Python314\python.exe'
if (-not (Test-Path -LiteralPath $cqwePython)) {
    throw 'Python executable missing. Install Python and update cqwePython in this launcher.'
}
& $cqwePython -u -m cqwe.four_market_supervisor --root $DataRoot --rounds $Rounds --seconds $SecondsPerRound --horizons '300,900' --attempts 3
exit $LASTEXITCODE
