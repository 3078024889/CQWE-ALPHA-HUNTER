$ErrorActionPreference='Stop'
$Repo='D:\CQWE\alpha-hunter';$Py='C:\Python314\python.exe';$Data='D:\CQWE_DATA'
$Replace='cqwe/microstructure_v40.py'
$New=@('tests/test_v48.py','INSTALL_MASTER_V48.ps1','RUN_ONCE_V48.ps1','README_MASTER_V48.md')
$Expected='1F987D0FA2229B792761BA67985AD93A08C4E31BA9EBB7499615C75E05269EA7'
function Checked([string]$step){if($LASTEXITCODE -ne 0){throw "${step}_FAILED exit=$LASTEXITCODE"}}
if(!(Test-Path (Join-Path $Repo '.git')) -or !(Test-Path $Py)){throw 'REPO_OR_PYTHON_MISSING'}
Set-Location $Repo
if((& git branch --show-current).Trim() -ne 'main'){throw 'MAIN_REQUIRED'};Checked 'BRANCH'
$Dirty=@(git status --porcelain --untracked-files=all);Checked 'STATUS'
if($Dirty.Count -gt 0){throw 'WORKTREE_NOT_CLEAN_REFUSED'}
if(!(Test-Path 'cqwe\l2_forward_v47.py')){throw 'V47_MISSING'}
$Old=Join-Path $Repo ($Replace.Replace('/','\'))
if(!(Test-Path $Old)){throw 'V40_SOURCE_MISSING'}
if((Get-FileHash $Old -Algorithm SHA256).Hash -ne $Expected){throw 'V40_HASH_MISMATCH_REFUSE_OVERWRITE'}
$Backup=Join-Path $Data ('source_backups\v48_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Force -Path $Backup|Out-Null
Copy-Item -LiteralPath $Old -Destination (Join-Path $Backup 'microstructure_v40.py')
$Added=New-Object System.Collections.Generic.List[string]
$WasReplaced=$false
try{
 foreach($f in $New){
  $src=Join-Path $PSScriptRoot ($f.Replace('/','\'));$dst=Join-Path $Repo ($f.Replace('/','\'))
  if(!(Test-Path $src)){throw "PACKAGE_FILE_MISSING $f"}
  if(Test-Path $dst){throw "REFUSE_OVERWRITE $f"}
  New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent)|Out-Null
  Copy-Item $src $dst;$Added.Add($f)
 }
 $Src=Join-Path $PSScriptRoot ($Replace.Replace('/','\'))
 Copy-Item -LiteralPath $Src -Destination $Old -Force;$WasReplaced=$true
 & $Py -m unittest discover -s tests -q;Checked 'ALL_TESTS'
 & $Py -m unittest discover -s tests -p test_v48.py -q;Checked 'V48_TESTS'
 $Allowed=@($New)+@($Replace)
 git add -- $Allowed;Checked 'STAGE'
 git diff --cached --check;Checked 'DIFF_CHECK'
 $Staged=@(git diff --cached --name-only);Checked 'STAGED_CHECK'
 if(@($Staged|Where-Object {$_ -notin $Allowed}).Count -gt 0){throw 'UNEXPECTED_STAGED_FILES'}
 git commit -m 'fix: v48 quarantine stale aggregate trades with explicit provenance';Checked 'COMMIT'
}catch{
 git restore --staged -- $New $Replace 2>$null|Out-Null
 if($WasReplaced){Copy-Item -LiteralPath (Join-Path $Backup 'microstructure_v40.py') -Destination $Old -Force}
 foreach($f in $Added){$dst=Join-Path $Repo ($f.Replace('/','\'));$src=Join-Path $PSScriptRoot ($f.Replace('/','\'))
  if((Test-Path $dst) -and (Test-Path $src) -and (Get-FileHash $dst -Algorithm SHA256).Hash -eq (Get-FileHash $src -Algorithm SHA256).Hash){Remove-Item -LiteralPath $dst -Force}
 }
 Write-Host "V48_INSTALL_FAILED; ORIGINAL_SOURCE_BACKUP=$Backup" -ForegroundColor Yellow
 throw
}
$Post=@(git status --porcelain --untracked-files=all);Checked 'POST_STATUS'
if($Post.Count -gt 0){throw 'POST_INSTALL_DIRTY'}
Write-Host "CQWE_V48_LOCAL_VERIFIED: $((git rev-parse HEAD).Trim())" -ForegroundColor Green
Write-Host "OLD_SOURCE_BACKUP=$Backup"
Write-Host 'NO ORDERS | NO AUTO PUSH | TASK SCHEDULE UNCHANGED'
