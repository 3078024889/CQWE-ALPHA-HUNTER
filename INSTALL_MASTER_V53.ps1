$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA';$Py='C:\Python314\python.exe'
function CheckExit([string]$name){if($LASTEXITCODE -ne 0){throw "${name}_FAILED exit=$LASTEXITCODE"}}
$Modified=@{'cqwe/memory_v52.py'='c50c2ff3e2b3ba1eb2e9d8ed1f7485fc8142d0a19fe134d78c630ee88101b06d'}
$New=@('cqwe/lineage_audit_v53.py','tests/test_v53.py','RUN_ONCE_V53.ps1','INSTALL_MASTER_V53.ps1','README_MASTER_V53.md')
if(!(Test-Path (Join-Path $Repo '.git')) -or !(Test-Path $Py)){throw 'REPO_OR_PYTHON_MISSING'}
Set-Location $Repo
if((git branch --show-current).Trim() -ne 'main'){throw 'MAIN_BRANCH_REQUIRED'};CheckExit 'BRANCH'
if(@(git status --porcelain --untracked-files=all).Count -gt 0){throw 'DIRTY_WORKTREE_REFUSED'};CheckExit 'STATUS'
if(!(Test-Path 'tests\test_v52.py')){throw 'V52_BASE_REQUIRED'}
$Backup=Join-Path $Data ('source_backups\v53_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Force -Path $Backup|Out-Null
$Copied=New-Object System.Collections.Generic.List[string]
$Backed=New-Object System.Collections.Generic.List[string]
try {
 foreach($f in $Modified.Keys){
  $src=Join-Path $PSScriptRoot ($f.Replace('/','\'));$dst=Join-Path $Repo ($f.Replace('/','\'))
  if(!(Test-Path $src) -or !(Test-Path $dst)){throw "MISSING_SOURCE: $f"}
  $got=(Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLowerInvariant()
  if($got -ne $Modified[$f]){throw "MODIFIED_BASE_REFUSED: $f actual=$got"}
 }
 foreach($f in $New){
  $src=Join-Path $PSScriptRoot ($f.Replace('/','\'));$dst=Join-Path $Repo ($f.Replace('/','\'))
  if(!(Test-Path $src)){throw "PACKAGE_MISSING: $f"};if(Test-Path $dst){throw "REFUSE_OVERWRITE: $f"}
 }
 foreach($f in $Modified.Keys){
  $dst=Join-Path $Repo ($f.Replace('/','\'));$src=Join-Path $PSScriptRoot ($f.Replace('/','\'))
  $back=Join-Path $Backup ($f.Replace('/','\'))
  New-Item -ItemType Directory -Force -Path (Split-Path $back -Parent)|Out-Null
  Copy-Item -LiteralPath $dst -Destination $back -ErrorAction Stop;$Backed.Add($f)
  Copy-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop
 }
 foreach($f in $New){
  $dst=Join-Path $Repo ($f.Replace('/','\'));$src=Join-Path $PSScriptRoot ($f.Replace('/','\'))
  New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent)|Out-Null
  Copy-Item -LiteralPath $src -Destination $dst -ErrorAction Stop;$Copied.Add($f)
 }
 $env:PYTHONPYCACHEPREFIX=Join-Path $Data 'pycache';$env:TEMP=Join-Path $Data 'temp';$env:TMP=$env:TEMP
 & $Py -m unittest discover -s tests -q;CheckExit 'FULL_REGRESSION'
 & $Py -m unittest discover -s tests -p test_v53.py -q;CheckExit 'V53_ADVERSARIAL'
 $All=@($Modified.Keys)+$New
 git add -- $All;CheckExit 'STAGE'
 git diff --cached --check;CheckExit 'DIFF_CHECK'
 $Staged=@(git diff --cached --name-only);CheckExit 'STAGED_FILES'
 if(@($Staged|Where-Object {$_ -notin $All}).Count -gt 0){throw 'UNEXPECTED_STAGED_FILES'}
 git commit -m 'fix: v53 verify every prior dendrite memory generation and market source';CheckExit 'COMMIT'
}catch{
 $All=@($Modified.Keys)+$New
 git restore --staged -- $All 2>$null|Out-Null
 foreach($f in $Copied){$dst=Join-Path $Repo ($f.Replace('/','\'));$src=Join-Path $PSScriptRoot ($f.Replace('/','\'))
  if((Test-Path $dst) -and (Get-FileHash $dst -Algorithm SHA256).Hash -eq (Get-FileHash $src -Algorithm SHA256).Hash){Remove-Item -LiteralPath $dst -Force}}
 foreach($f in $Backed){$dst=Join-Path $Repo ($f.Replace('/','\'));$back=Join-Path $Backup ($f.Replace('/','\'))
  if(Test-Path $back){Copy-Item -LiteralPath $back -Destination $dst -Force}}
 throw
}
if(@(git status --porcelain --untracked-files=all).Count -gt 0){throw 'POST_INSTALL_DIRTY'}
Write-Host "CQWE_V53_LOCAL_VERIFIED: $((git rev-parse HEAD).Trim())" -ForegroundColor Green
Write-Host "BACKUP=$Backup"
Write-Host 'D DRIVE | FULL MEMORY LINEAGE AUDIT | NO REAL ORDERS | NO AUTO PUSH'
