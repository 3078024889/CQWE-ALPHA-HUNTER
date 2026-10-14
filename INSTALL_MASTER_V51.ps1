$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe';$Data='D:\CQWE_DATA'
function Checked([string]$label){if($LASTEXITCODE -ne 0){throw "${label}_FAILED exit=$LASTEXITCODE"}}
$Modified=@{
 'cqwe/forward_lab_v47.py'='47a96bd556ae1b85a7860ca7431f6d2fe18a9d2e0d64de4108674ce84d1ec1ca';
 'cqwe/l2_forward_v47.py'='f570e16a02361fbb549780adc1d3e242a00fe5e6885ac61f4ba5a717d0968700'
}
$New=@('tests/test_v51.py','INSTALL_MASTER_V51.ps1','RUN_ONCE_V51.ps1','README_MASTER_V51.md')
if(!(Test-Path (Join-Path $Repo '.git')) -or !(Test-Path $Py)){throw 'REPOSITORY_OR_PYTHON_MISSING'}
Set-Location $Repo
if((git branch --show-current).Trim() -ne 'main'){throw 'MAIN_BRANCH_REQUIRED'};Checked 'BRANCH'
if(@(git status --porcelain --untracked-files=all).Count -gt 0){throw 'DIRTY_WORKTREE_REFUSED'};Checked 'STATUS'
if(!(Test-Path 'tests\test_v50.py')){throw 'V50_BASE_REQUIRED'}
$Backup=Join-Path $Data ('source_backups\v51_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Force -Path $Backup|Out-Null
$Copied=New-Object System.Collections.Generic.List[string]
$Backed=New-Object System.Collections.Generic.List[string]
try{
 foreach($f in $Modified.Keys){
  $src=Join-Path $PSScriptRoot ($f.Replace('/','\'));$dst=Join-Path $Repo ($f.Replace('/','\'))
  if(!(Test-Path $src) -or !(Test-Path $dst)){throw "MISSING_SOURCE: $f"}
  $got=(Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLowerInvariant()
  if($got -ne $Modified[$f]){throw "MODIFIED_BASE_REFUSED: $f expected=$($Modified[$f]) actual=$got"}
 }
 foreach($f in $New){
  $src=Join-Path $PSScriptRoot ($f.Replace('/','\'));$dst=Join-Path $Repo ($f.Replace('/','\'))
  if(!(Test-Path $src)){throw "PACKAGE_MISSING: $f"};if(Test-Path $dst){throw "REFUSE_OVERWRITE: $f"}
 }
 foreach($f in $Modified.Keys){
  $dst=Join-Path $Repo ($f.Replace('/','\'));$src=Join-Path $PSScriptRoot ($f.Replace('/','\'))
  $back=Join-Path $Backup ($f.Replace('/','\'))
  New-Item -ItemType Directory -Force -Path (Split-Path $back -Parent)|Out-Null
  Copy-Item -LiteralPath $dst -Destination $back -ErrorAction Stop
  $Backed.Add($f)
  Copy-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop
 }
 foreach($f in $New){
  $dst=Join-Path $Repo ($f.Replace('/','\'));$src=Join-Path $PSScriptRoot ($f.Replace('/','\'))
  Copy-Item -LiteralPath $src -Destination $dst -ErrorAction Stop;$Copied.Add($f)
 }
 & $Py -m unittest discover -s tests -q;Checked 'FULL_REGRESSION'
 & $Py -m unittest discover -s tests -p test_v51.py -q;Checked 'V51_FALSIFICATION'
 $All=@($Modified.Keys)+$New
 git add -- $All;Checked 'STAGE'
 git diff --cached --check;Checked 'DIFF_CHECK'
 $Staged=@(git diff --cached --name-only);Checked 'STAGED_FILES'
 if(@($Staged|Where-Object {$_ -notin $All}).Count -gt 0){throw 'UNEXPECTED_STAGED_FILES'}
 git commit -m 'fix: v51 precommit anchor to latest preceding book across settlement';Checked 'COMMIT'
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
Write-Host "CQWE_V51_LOCAL_VERIFIED: $((git rev-parse HEAD).Trim())" -ForegroundColor Green
Write-Host "BACKUP=$Backup"
Write-Host 'D DRIVE | NO REAL ORDERS | NO AUTO PUSH | NO TASK CHANGES'
