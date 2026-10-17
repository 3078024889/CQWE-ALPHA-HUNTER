param([string]$DataRoot = 'D:\CQWE_DATA\copernican_local_v3', [switch]$InstallAutostart, [switch]$Stop)
$ErrorActionPreference = 'Stop'
$repoPath = $PSScriptRoot
$pythonPath = 'C:\Python314\python.exe'
$startupPath = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupPath 'CQWE Copernican Research.lnk'
if ($InstallAutostart) {
    $shellObject = New-Object -ComObject WScript.Shell
    $shortcutObject = $shellObject.CreateShortcut($shortcutPath)
    $shortcutObject.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $shortcutObject.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $PSCommandPath + '" -DataRoot "' + $DataRoot + '"'
    $shortcutObject.WorkingDirectory = $repoPath
    $shortcutObject.WindowStyle = 7
    $shortcutObject.Save()
    Write-Output "Autostart installed for Windows user logon: $shortcutPath"
}
New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
$pidPath = Join-Path $DataRoot 'launcher_pid.json'
$newsPidPath = Join-Path $DataRoot 'news_pid.json'
if ($Stop) {
    if (Test-Path -LiteralPath $pidPath) {
        $record = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
        $existingProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)" -ErrorAction SilentlyContinue
        if ($existingProcess -and $existingProcess.CreationDate.ToUniversalTime().ToString('o') -eq $record.started -and $existingProcess.CommandLine -like '*cqwe.local_autopilot*') {
            & taskkill.exe /PID $record.pid /T /F
        }
    }
    if (Test-Path -LiteralPath $newsPidPath) {
        $newsRecord = Get-Content -LiteralPath $newsPidPath -Raw | ConvertFrom-Json
        $newsProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($newsRecord.pid)" -ErrorAction SilentlyContinue
        if ($newsProcess -and $newsProcess.CreationDate.ToUniversalTime().ToString('o') -eq $newsRecord.started -and $newsProcess.CommandLine -like '*cqwe.news_watch*') {
            & taskkill.exe /PID $newsRecord.pid /T /F
        }
    }
    exit
}
if (-not (Test-Path -LiteralPath $pythonPath)) { throw "Python missing: $pythonPath" }
$newsAlreadyRunning = $false
if (Test-Path -LiteralPath $newsPidPath) {
    $newsRecord = Get-Content -LiteralPath $newsPidPath -Raw | ConvertFrom-Json
    $newsProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($newsRecord.pid)" -ErrorAction SilentlyContinue
    $newsAlreadyRunning = $newsProcess -and $newsProcess.CreationDate.ToUniversalTime().ToString('o') -eq $newsRecord.started -and $newsProcess.CommandLine -like '*cqwe.news_watch*'
}
if (-not $newsAlreadyRunning) {
    $newsArguments = @('-u', '-m', 'cqwe.news_watch', '--root', ('"' + (Join-Path $DataRoot 'official_news') + '"'))
    $newsStarted = Start-Process -FilePath $pythonPath -ArgumentList $newsArguments -WorkingDirectory $repoPath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $DataRoot 'news.out.log') -RedirectStandardError (Join-Path $DataRoot 'news.err.log')
    $newsInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($newsStarted.Id)"
    @{pid=$newsStarted.Id;started=$newsInfo.CreationDate.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $newsPidPath
    Write-Output "Official public-feed observer started: PID $($newsStarted.Id)"
}
if (Test-Path -LiteralPath $pidPath) {
    $record = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
    $existingProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)" -ErrorAction SilentlyContinue
    if ($existingProcess -and $existingProcess.CreationDate.ToUniversalTime().ToString('o') -eq $record.started -and $existingProcess.CommandLine -like '*cqwe.local_autopilot*') {
        Write-Output "Local research is already running: PID $($record.pid)"
        exit
    }
}
$arguments = @('-u', '-m', 'cqwe.local_autopilot', '--root', ('"' + $DataRoot + '"'))
$processObject = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $repoPath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $DataRoot 'launcher.out.log') -RedirectStandardError (Join-Path $DataRoot 'launcher.err.log')
$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($processObject.Id)"
@{pid=$processObject.Id;started=$processInfo.CreationDate.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $pidPath
Write-Output "Local public-data research started: PID $($processObject.Id), $DataRoot"
