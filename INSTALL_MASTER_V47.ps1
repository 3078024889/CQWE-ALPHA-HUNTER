$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe'
$Files=@('cqwe/l2_forward_v47.py','cqwe/forward_lab_v47.py','tests/test_v47.py','README_MASTER_V47.md','INSTALL_MASTER_V47.ps1','RUN_FORWARD_V47.ps1','ENABLE_FORWARD_V47.ps1','RUN_ONCE_V47.ps1')
function Checked([string]$step){if($LASTEXITCODE -ne 0){throw "${step}_FAILED exit=$LASTEXITCODE"}}
if(!(Test-Path (Join-Path $Repo '.git')) -or !(Test-Path $Py)){throw 'REPO_OR_PYTHON_MISSING'}
Set-Location $Repo
if((& git branch --show-current).Trim() -ne 'main'){throw 'MAIN_REQUIRED'};Checked 'BRANCH'
$Status=@(git status --porcelain --untracked-files=all);Checked 'STATUS';if($Status.Count -gt 0){git status --short;throw 'WORKTREE_NOT_CLEAN_REFUSED'}
foreach($dep in @('cqwe\four_asset_lab_v44.py','cqwe\copernican_lab_v33.py','cqwe\l2_trade_capture_v43.py')){if(!(Test-Path $dep)){throw "DEPENDENCY_MISSING $dep"}}
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
 & $Py -m unittest discover -s tests -p test_v47.py -q;Checked 'V47_TESTS'
 git add -- $Files;Checked 'STAGE';git diff --cached --check;Checked 'DIFF_CHECK'
 $Staged=@(git diff --cached --name-only);Checked 'STAGED_CHECK'
 if(@($Staged|Where-Object {$_ -notin $Files}).Count -gt 0){throw 'UNEXPECTED_STAGED_FILES'}
 git commit -m 'feat: v47 four asset prospective precommit dendritic shadow sampling';Checked 'COMMIT'
}catch{
 git restore --staged -- $Files 2>$null|Out-Null
 foreach($file in $Added){$src=Join-Path $PSScriptRoot ($file.Replace('/','\'));$dst=Join-Path $Repo ($file.Replace('/','\'))
  if((Test-Path $src) -and (Test-Path $dst) -and (Get-FileHash $src -Algorithm SHA256).Hash -eq (Get-FileHash $dst -Algorithm SHA256).Hash){Remove-Item $dst -Force}}
 Write-Host 'V47_INSTALL_ABORTED; EVIDENCE AND TASKS UNTOUCHED' -ForegroundColor Yellow
 throw
}
$Post=@(git status --porcelain --untracked-files=all);Checked 'POST_STATUS';if($Post.Count -gt 0){throw 'POST_INSTALL_DIRTY'}
Write-Host "CQWE_V47_LOCAL_VERIFIED: $((git rev-parse HEAD).Trim())" -ForegroundColor Green
Write-Host 'PROSPECTIVE PUBLIC SPOT DATA | FOUR SYMBOLS | NO REAL ORDERS NO AUTO PUSH'
