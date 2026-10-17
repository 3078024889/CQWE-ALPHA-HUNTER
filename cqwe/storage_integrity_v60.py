"""V60 bounded append-only experiment archive, no deletions or scheduling."""
import hashlib,json,os
from pathlib import Path

def archive(root, name, report, *, max_bytes=1000000):
    root=Path(root).resolve()
    if not isinstance(name,str) or not name or name in ('.','..') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in name):raise ValueError('BAD_ARCHIVE_NAME')
    if not isinstance(report,dict) or not report:raise ValueError('BAD_ARCHIVE_REPORT')
    if not isinstance(max_bytes,int) or isinstance(max_bytes,bool) or max_bytes<=0:raise ValueError('BAD_BUDGET')
    data=(json.dumps(report,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
    if len(data)>max_bytes:raise ValueError('ARCHIVE_BUDGET_EXCEEDED')
    root.mkdir(parents=True,exist_ok=True)
    if root.is_symlink():raise ValueError('SYMLINK_ARCHIVE_ROOT')
    dest=root/(name+'.json')
    with dest.open('xb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    return {'path':str(dest),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'retention':'IMMUTABLE_NO_DELETE'}
