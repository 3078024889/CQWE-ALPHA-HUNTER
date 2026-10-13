$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter'; $Python='C:\Python314\python.exe'
Set-Location $Repo
$Log='reports\collection_logs\dendrites_v35.log'
New-Item -ItemType Directory -Force -Path (Split-Path $Log -Parent) | Out-Null
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START" | Out-File $Log -Append -Encoding utf8
& $Python -m cqwe.evolution_supervisor_v35 2>&1 | Out-File $Log -Append -Encoding utf8
$Result=$LASTEXITCODE
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EXIT=$Result" | Out-File $Log -Append -Encoding utf8
if($Result -ne 0){ exit $Result }
