$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Data='D:\CQWE_DATA';$Py='C:\Python314\python.exe'
function Checked([string]$name){if($LASTEXITCODE -ne 0){throw "${name}_FAILED exit=$LASTEXITCODE"}}
$Modified=@{'cqwe/l2_forward_v47.py'='7fa719000e1c7c32e72a66f952fbc6c0426ea0018009ccd83757b60c84e4fcf8'}
$New=@('cqwe/memory_v52.py','cqwe/forward_supervisor_v52.py','tests/test_v52.py',
       'RUN_FORWARD_V52.ps1','ENABLE_FORWARD_V52.ps1','RUN_ONCE_V52.ps1','INSTALL_MASTER_V52.ps1','README_MASTER_V52.md')
if(!(Test-Path (Join-Path $Repo '.git')) -or !(Test-Path $Py)){throw 'REPO_OR_PYTHON_MISSING'}
Set-Location $Repo
if((git branch --show-current).Trim() -ne 'main'){throw 'MAIN_BRANCH_REQUIRED'};Checked 'BRANCH'
if(@(git status --porcelain --untracked-files=all).Count -gt 0){throw 'DIRTY_WORKTREE_REFUSED'};Checked 'STATUS'
if(!(Test-Path 'tests\test_v51.py')){throw 'V51_BASE_REQUIRED'}
$Backup=Join-Path $Data ('source_backups\v52_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
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
 & $Py -m unittest discover -s tests -q;Checked 'FULL_REGRESSION'
 & $Py -m unittest discover -s tests -p test_v52.py -q;Checked 'V52_ADVERSARIAL'
 $All=@($Modified.Keys)+$New
 git add -- $All;Checked 'STAGE'
 git diff --cached --check;Checked 'DIFF_CHECK'
 $Staged=@(git diff --cached --name-only);Checked 'STAGED_FILES'
 if(@($Staged|Where-Object {$_ -notin $All}).Count -gt 0){throw 'UNEXPECTED_STAGED_FILES'}
 git commit -m 'feat: v52 immutable dendrite checkpoints and forward memory continuation';Checked 'COMMIT'
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
Write-Host "CQWE_V52_LOCAL_VERIFIED: $((git rev-parse HEAD).Trim())" -ForegroundColor Green
Write-Host "BACKUP=$Backup"
Write-Host 'D DRIVE | MEMORY CHAIN | NO REAL ORDERS | NO AUTO PUSH'
