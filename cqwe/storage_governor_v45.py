"""V45 D-only conservative space steward.

Dry-run is default. Only explicit apply can remove verified transient cache
files from a strict owned prefix; raw L2, ledgers, logs, memory and reports are
never deletion candidates. Never follows symlinks. No automatic purge task.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, time
from pathlib import Path

ROOT=Path('D:/CQWE_DATA')
# Only recomputable Python bytecode cache in an owned subtree.
DELETE_PREFIX=('pycache',)
SAFE_EXT={'.pyc'}
MIN_AGE_DAYS=7

def _under(child, root):
    try:child.relative_to(root);return True
    except ValueError:return False

def plan(root=ROOT, *, now=None):
    root=Path(root).absolute();now=time.time() if now is None else now
    if os.name=='nt' and root.drive.upper()!='D:' and not (os.environ.get("CQWE_ALLOW_NON_D_MEMORY_TESTS") == "1" and os.path.normcase(os.path.abspath(os.fspath(root))).startswith(os.path.normcase(os.path.abspath(os.environ.get("TEMP", os.path.join(os.environ.get("SystemDrive", "C:"), "Windows", "Temp")))) + os.sep)):raise ValueError('D_DRIVE_REQUIRED')
    if root.is_symlink():raise ValueError('SYMLINK_ROOT_REFUSED')
    files=[];total=0
    cache=root/'pycache'
    if cache.exists():
      for dirpath, dirnames, names in os.walk(cache,followlinks=False):
        d=Path(dirpath)
        dirnames[:]=[n for n in dirnames if not (d/n).is_symlink()]
        for name in names:
            f=d/name
            if f.is_symlink() or not f.is_file() or f.suffix not in SAFE_EXT:continue
            if not _under(f.absolute(),cache.absolute()):continue
            st=f.stat()
            if now-st.st_mtime<MIN_AGE_DAYS*86400:continue
            files.append({'path':str(f),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,
                          'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
            total+=st.st_size
    return {'schema':'CQWE_V45_DISK_SAFE_PLAN','root':str(root),'files':files,
      'reclaimable_bytes':total,'apply_required':True,
      'protected':['l2_v43','l2_v44','research_v45','logs','reports','v21_evidence','v38_cash_account','checkpoints'],
      'not_deleted_by_default':True}

def apply(root, saved_plan):
    expected=plan(root)
    if expected!=saved_plan:raise ValueError('PLAN_CHANGED_REVIEW_REQUIRED')
    removed=0
    for meta in saved_plan['files']:
        p=Path(meta['path'])
        if p.is_symlink() or not p.is_file():raise ValueError('CACHE_CHANGED')
        st=p.stat()
        if st.st_mtime_ns!=meta['mtime_ns'] or st.st_size!=meta['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=meta['sha256']:
            raise ValueError('CACHE_CHANGED')
    # All prechecks complete: delete only strictly listed .pyc files.
    for meta in saved_plan['files']:
        Path(meta['path']).unlink();removed+=1
    return {'removed_verified_cache_files':removed,'bytes_planned':saved_plan['reclaimable_bytes']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(ROOT));p.add_argument('--apply-pyc-only',action='store_true');a=p.parse_args()
    report=plan(a.root)
    print('CQWE_V45_DISK_PLAN',json.dumps({'reclaimable_bytes':report['reclaimable_bytes'],
      'safe_candidates':len(report['files']),'evidence_deleted':False}))
    if a.apply_pyc_only:
        print('CQWE_V45_EXPLICIT_CACHE_PURGE',json.dumps(apply(a.root,report)))
    else:print('DRY RUN ONLY | NO DATA OR LOG DELETION | NO EVIDENCE LOSS')
if __name__=='__main__':main()
