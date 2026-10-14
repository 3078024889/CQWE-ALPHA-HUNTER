$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe'
$Files=@('cqwe/forward_supervisor_v49.py','tests/test_v49.py','INSTALL_MASTER_V49.ps1','RUN_ONCE_V49.ps1','RUN_FORWARD_V49.ps1','README_MASTER_V49.md')
function Checked([string]$label){if($LASTEXITCODE -ne 0){throw "${label}_FAILED code=$LASTEXITCODE"}}
if(!(Test-Path (Join-Path $Repo '.git')) -or !(Test-Path $Py)){throw 'REPOSITORY_OR_PYTHON_MISSING'}
Set-Location $Repo
if((git branch --show-current).Trim() -ne 'main'){throw 'MAIN_BRANCH_REQUIRED'};Checked 'BRANCH'
if(@(git status --porcelain --untracked-files=all).Count -gt 0){throw 'DIRTY_WORKTREE_REFUSED'};Checked 'STATUS'
if(!(Test-Path 'tests\test_v48.py') -or !(Test-Path 'cqwe\forward_lab_v47.py')){throw 'V48_BASE_REQUIRED'}
$Added=New-Object System.Collections.Generic.List[string]
try{
 foreach($f in $Files){
  $src=Join-Path $PSScriptRoot ($f.Replace('/','\'))
  $dst=Join-Path $Repo ($f.Replace('/','\'))
  if(!(Test-Path $src)){throw "PACKAGE_MISSING: $f"}
  if(Test-Path $dst){throw "REFUSE_OVERWRITE: $f"}
  New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent)|Out-Null
  Copy-Item -LiteralPath $src -Destination $dst;$Added.Add($f)
 }
 & $Py -m unittest discover -s tests -q;Checked 'FULL_REGRESSION'
 & $Py -m unittest discover -s tests -p test_v49.py -q;Checked 'V49_ADVERSARIAL'
 git add -- $Files;Checked 'STAGE'
 git diff --cached --check;Checked 'DIFF_CHECK'
 $Staged=@(git diff --cached --name-only);Checked 'STAGED_FILES'
 if(@($Staged|Where-Object {$_ -notin $Files}).Count -gt 0){throw 'UNEXPECTED_STAGED_FILE'}
 git commit -m 'feat: v49 isolated four-market precommit retries and evidence reports';Checked 'COMMIT'
}catch{
 git restore --staged -- $Files 2>$null|Out-Null
 foreach($f in $Added){$dst=Join-Path $Repo ($f.Replace('/','\'));$src=Join-Path $PSScriptRoot ($f.Replace('/','\'))
  if((Test-Path $dst) -and (Get-FileHash $dst -Algorithm SHA256).Hash -eq (Get-FileHash $src -Algorithm SHA256).Hash){Remove-Item -LiteralPath $dst -Force}
 }
 throw
}
if(@(git status --porcelain --untracked-files=all).Count -gt 0){throw 'POST_INSTALL_DIRTY'}
Write-Host "CQWE_V49_LOCAL_VERIFIED: $((git rev-parse HEAD).Trim())" -ForegroundColor Green
Write-Host 'NO REAL ORDERS | NO AUTO PUSH | EXISTING TASKS UNCHANGED'
