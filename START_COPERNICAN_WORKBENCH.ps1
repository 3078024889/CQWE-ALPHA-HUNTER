param([ValidateRange(1024,65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$cqwePython = 'C:\Python314\python.exe'
if (-not (Test-Path -LiteralPath $cqwePython)) { throw 'Python executable unavailable' }
try {
    $cqweExisting = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/state" -TimeoutSec 2
    if ($cqweExisting.mode -eq 'PUBLIC_DATA_PAPER_ONLY') {
        Start-Process "http://127.0.0.1:$Port"
        exit 0
    }
} catch { }
$cqweLogRoot = 'D:\CQWE_DATA\workbench_v1'
New-Item -ItemType Directory -Path $cqweLogRoot -Force | Out-Null
$cqweLaunchMethod = 'WMI-independent-process'
try {
    $cqweStartup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
    $cqweCommand = '"' + $cqwePython + '" -X utf8 -m cqwe.workbench --port ' + $Port + ' --background-log'
    $cqweCreated = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$cqweCommand;CurrentDirectory=$PSScriptRoot;ProcessStartupInformation=$cqweStartup}
    if ($cqweCreated.ReturnValue -ne 0) { throw "Process creation returned $($cqweCreated.ReturnValue)" }
    $cqweProcess = Get-Process -Id $cqweCreated.ProcessId
} catch {
    $cqweLaunchMethod = 'StartProcess-fallback'
    $cqweProcess = Start-Process -FilePath $cqwePython -ArgumentList @('-X','utf8','-m','cqwe.workbench','--port',"$Port",'--background-log') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
}
@{ pid = $cqweProcess.Id; started = $cqweProcess.StartTime.ToUniversalTime().ToString('o'); port = $Port; method = $cqweLaunchMethod } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $cqweLogRoot 'server_process.json') -Encoding utf8
for ($cqweAttempt = 0; $cqweAttempt -lt 20; $cqweAttempt++) {
    try {
        $cqweReady = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/state" -TimeoutSec 1
        if ($cqweReady.mode -eq 'PUBLIC_DATA_PAPER_ONLY') { Start-Process "http://127.0.0.1:$Port"; exit 0 }
    } catch { }
    Start-Sleep -Milliseconds 250
}
throw 'Workbench did not start; inspect D:\CQWE_DATA\workbench_v1\server_stderr.log'
