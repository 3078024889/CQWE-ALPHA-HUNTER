$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe'
$Files=@('cqwe/l2_replay_v42.py','tests/test_v42.py','README_MASTER_V42.md','RUN_ONCE_V42.ps1','INSTALL_MASTER_V42.ps1')
function Checked([string]$step){if($LASTEXITCODE -ne 0){throw "${step}_FAILED exit=$LASTEXITCODE"}}
if(!(Test-Path (Join-Path $Repo '.git')) -or !(Test-Path $Py)){throw 'REPO_OR_PYTHON_MISSING'}
Set-Location $Repo
$Branch=(& git branch --show-current).Trim();Checked 'BRANCH';if($Branch -ne 'main'){throw 'MAIN_REQUIRED'}
$Status=@(git status --porcelain --untracked-files=all);Checked 'STATUS';if($Status.Count -gt 0){git status --short;throw 'WORKTREE_NOT_CLEAN_REFUSED'}
if(!(Test-Path 'cqwe/micro_forward_v41.py')){throw 'V41_REQUIRED'}
$Added=New-Object System.Collections.Generic.List[string]
try{
 foreach($file in $Files){
  $src=Join-Path $PSScriptRoot ($file.Replace('/','\'));$dst=Join-Path $Repo ($file.Replace('/','\'))
  if(!(Test-Path $src)){throw "PACKAGE_FILE_MISSING $file"}
  if(Test-Path $dst){throw "REFUSE_OVERWRITE $file"}
  New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent)|Out-Null
  Copy-Item $src $dst;$Added.Add($file)
 }
 & $Py -m unittest discover -s tests -q;Checked 'ALL_TESTS'
 & $Py -m unittest discover -s tests -p test_v42.py -q;Checked 'V42_TESTS'
 & $Py -m cqwe.l2_replay_v42 --audit;Checked 'OFFLINE_L2_AUDIT'
 git add -- $Files;Checked 'STAGE';git diff --cached --check;Checked 'DIFF_CHECK'
 $Staged=@(git diff --cached --name-only);Checked 'STAGED_CHECK'
 if(@($Staged|Where-Object {$_ -notin $Files}).Count -gt 0){throw 'UNEXPECTED_STAGED_FILES'}
 git commit -m 'feat: v42 synchronized public L2 depth and strict quote proxy';Checked 'COMMIT'
}catch{
 git restore --staged -- $Files 2>$null|Out-Null
 foreach($file in $Added){
  $src=Join-Path $PSScriptRoot ($file.Replace('/','\'));$dst=Join-Path $Repo ($file.Replace('/','\'))
  if((Test-Path $src) -and (Test-Path $dst)){
   if((Get-FileHash $src -Algorithm SHA256).Hash -eq (Get-FileHash $dst -Algorithm SHA256).Hash){Remove-Item $dst -Force}
  }
 }
 Write-Host 'V42_INSTALL_ABORTED; JOURNALS AND TASKS UNTOUCHED' -ForegroundColor Yellow
 throw
}
$Post=@(git status --porcelain --untracked-files=all);Checked 'POST_STATUS'
if($Post.Count -gt 0){git status --short;throw 'POST_INSTALL_DIRTY'}
Write-Host "CQWE_V42_LOCAL_VERIFIED: $((git rev-parse HEAD).Trim())" -ForegroundColor Green
Write-Host 'READ ONLY PUBLIC MARKET | NO REAL ORDERS | NO AUTO PUSH | NO LIVE PROFIT CLAIM'
