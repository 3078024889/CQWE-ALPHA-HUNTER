$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe'
$Files=@('cqwe/market_replay_v43.py','cqwe/l2_trade_capture_v43.py','tests/test_v43.py','README_MASTER_V43.md','INSTALL_MASTER_V43.ps1','RUN_ONCE_V43.ps1')
function Checked([string]$step){if($LASTEXITCODE -ne 0){throw "${step}_FAILED exit=$LASTEXITCODE"}}
if(!(Test-Path (Join-Path $Repo '.git')) -or !(Test-Path $Py)){throw 'REPO_OR_PYTHON_MISSING'}
Set-Location $Repo
$Branch=(& git branch --show-current).Trim();Checked 'BRANCH';if($Branch -ne 'main'){throw 'MAIN_REQUIRED'}
$Status=@(git status --porcelain --untracked-files=all);Checked 'STATUS';if($Status.Count -gt 0){git status --short;throw 'WORKTREE_NOT_CLEAN_REFUSED'}
if(!(Test-Path 'cqwe/l2_replay_v42.py')){throw 'V42_REQUIRED'}
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
 & $Py -m unittest discover -s tests -p test_v43.py -q;Checked 'V43_TESTS'
 git add -- $Files;Checked 'STAGE';git diff --cached --check;Checked 'DIFF_CHECK'
 $Staged=@(git diff --cached --name-only);Checked 'STAGED_CHECK'
 if(@($Staged|Where-Object {$_ -notin $Files}).Count -gt 0){throw 'UNEXPECTED_STAGED_FILES'}
 git commit -m 'feat: v43 D-drive synchronized trade/L2 capture and conservative execution replay';Checked 'COMMIT'
}catch{
 git restore --staged -- $Files 2>$null|Out-Null
 foreach($file in $Added){
  $src=Join-Path $PSScriptRoot ($file.Replace('/','\'));$dst=Join-Path $Repo ($file.Replace('/','\'))
  if((Test-Path $src) -and (Test-Path $dst)){
   if((Get-FileHash $src -Algorithm SHA256).Hash -eq (Get-FileHash $dst -Algorithm SHA256).Hash){Remove-Item $dst -Force}
  }
 }
 Write-Host 'V43_INSTALL_ABORTED; HISTORICAL JOURNALS AND TASKS UNTOUCHED' -ForegroundColor Yellow
 throw
}
$Post=@(git status --porcelain --untracked-files=all);Checked 'POST_STATUS'
if($Post.Count -gt 0){git status --short;throw 'POST_INSTALL_DIRTY'}
Write-Host "CQWE_V43_LOCAL_VERIFIED: $((git rev-parse HEAD).Trim())" -ForegroundColor Green
Write-Host 'D DRIVE DATA | NO ORDERS | NO AUTO PUSH | NO VERIFIED PROFIT'
