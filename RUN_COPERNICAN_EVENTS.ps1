param(
    [ValidateRange(1,3600)][int]$Seconds = 60,
    [string]$Root = 'D:\CQWE_DATA\event_forward_v1',
    [string]$Calendar = '',
    [string]$BookState = ''
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $Calendar) { $Calendar = Join-Path $PSScriptRoot 'reports\macro_watch_plan_expanded_20261016.json' }
$cqwePython = 'C:\Python314\python.exe'
if (-not (Test-Path -LiteralPath $cqwePython)) { throw 'Python executable unavailable' }
$cqweArgs = @('-m', 'cqwe.event_forward_loop', '--root', $Root, '--calendar', $Calendar, '--seconds', "$Seconds")
if ($BookState) { $cqweArgs += @('--book-state', $BookState) }
& $cqwePython @cqweArgs
if ($LASTEXITCODE -ne 0) { throw "Bounded event research failed, exit $LASTEXITCODE" }
