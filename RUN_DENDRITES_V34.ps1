$ErrorActionPreference='Stop'
Set-Location 'D:\CQWE\alpha-hunter'
$log='reports\collection_logs\dendrites_v34.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log -Parent) | Out-Null
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START" | Out-File $log -Append -Encoding utf8
& 'C:\Python314\python.exe' -m cqwe.forward_dendrites_v34 2>&1 | Out-File $log -Append -Encoding utf8
$code=$LASTEXITCODE
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EXIT=$code" | Out-File $log -Append -Encoding utf8
if($code -ne 0) {exit $code}
