$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Runner=Join-Path $Repo 'RUN_ACCOUNT_V33.ps1'
if (!(Test-Path $Runner)) {throw 'V33_RUNNER_NOT_FOUND'}
# Do NOT silently abandon an open V32 paper position or queued intent.
$OldJournal=Join-Path $Repo 'reports\v32_cash_account'
if (Test-Path $OldJournal) {
 $Frames=@(Get-ChildItem $OldJournal -Filter 'frame_*.json' -File | Sort-Object { [int64]($_.BaseName -replace '^frame_','') })
 if ($Frames.Count -gt 0) {
  $Last=Get-Content $Frames[-1].FullName -Raw | ConvertFrom-Json
  if ($Last.state.symbol -or $Last.pending) {throw 'OLD_PAPER_HAS_OPEN_POSITION_OR_PENDING: refuse migration'}
 }
}
$Task='CQWE_Cash_Paper_5m'
$Cmd='powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+$Runner+'"'
& schtasks.exe /Create /SC MINUTE /MO 5 /TN $Task /TR $Cmd /F
if ($LASTEXITCODE -ne 0) {throw 'V33_SCHEDULE_FAILED'}
Write-Host 'CQWE_V33_FULL_EXIT_PAPER_SCHEDULE_CONFIGURED: V32 journal untouched; no real orders'
