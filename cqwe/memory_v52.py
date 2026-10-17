"""Immutable validated per-symbol dendrite memory. No orders or promotion."""
from __future__ import annotations
import contextlib, hashlib, json, math, os
from pathlib import Path
from .copernican_lab_v33 import Dendrite, specs
from .forward_lab_v47 import audit_file

ROOT=Path('D:/CQWE_DATA/memory_v52')
FIELDS=('w','trace','memory','prev_error','updates','ctx')


def _bytes(obj):
    return (json.dumps(obj,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf8')

def _sha(raw):return hashlib.sha256(raw).hexdigest()

def _verify_state(state):
    if not isinstance(state,list) or len(state)!=6:raise ValueError('INVALID_MEMORY_COUNT')
    for i,item in enumerate(state):
        if not isinstance(item,dict) or set(item)!=set(FIELDS)|{'spec'} or item['spec']!=specs()[i]:
            raise ValueError('INVALID_MEMORY_GENOTYPE')
        for field,bound in (('w',1.),('trace',10.),('memory',2.)):
            v=item[field]
            if not isinstance(v,list) or len(v)!=4 or any(type(n) not in (int,float) or not math.isfinite(n) or abs(n)>bound for n in v):
                raise ValueError('INVALID_MEMORY_VECTOR')
        for field,bound in (('prev_error',3.),('ctx',2.)):
            n=item[field]
            if type(n) not in (int,float) or not math.isfinite(n) or abs(n)>bound:raise ValueError('INVALID_MEMORY_SCALAR')
        if type(item['updates']) is not int or not 0<=item['updates']<=10**10:
            raise ValueError('INVALID_MEMORY_UPDATES')
    return True

def snapshot(models):
    out=[]
    for m in models:
        out.append({'spec':dict(m.spec),'w':list(m.w),'trace':list(m.trace),
                    'memory':list(m.memory),'prev_error':m.prev_error,'updates':m.updates,'ctx':m.ctx})
    _verify_state(out)
    return out

def restored(state):
    _verify_state(state)
    models=[Dendrite(sp) for sp in specs()]
    for m,item in zip(models,state):
        for key in FIELDS:
            v=item[key]
            setattr(m,key,list(v) if isinstance(v,list) else v)
    return models

def _folder(root,symbol):
    if symbol not in {'BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT'}:raise ValueError('UNSUPPORTED_SYMBOL')
    base=Path(root)
    temp_root = Path(os.environ.get("TEMP", r"C:\Windows\Temp")).resolve()
    try:
        resolved_base = base.resolve()
        resolved_temp = temp_root.resolve()
        is_temp_root = (
            os.path.commonpath((str(resolved_base), str(resolved_temp))).casefold()
            == str(resolved_temp).casefold()
        )
    except (OSError, ValueError):
        is_temp_root = False
    allow_temp_for_tests = (os.environ.get("CQWE_ALLOW_NON_D_MEMORY_TESTS") == "1" and is_temp_root)
    if os.name == "nt" and base.drive.upper() != "D:" and not allow_temp_for_tests:
        raise ValueError("D_DRIVE_REQUIRED")
    return base/symbol

@contextlib.contextmanager
def symbol_lock(root,symbol):
    folder=_folder(root,symbol);folder.mkdir(parents=True,exist_ok=True)
    lock=folder/'.process.lock'
    with open(lock,'a+b') as f:
        f.seek(0,2)
        if f.tell()==0:f.write(b'0');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:raise RuntimeError('MEMORY_WRITER_BUSY') from exc
        else:
            import fcntl
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as exc:raise RuntimeError('MEMORY_WRITER_BUSY') from exc
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)

def load(root,symbol):
    folder=_folder(root,symbol)
    files=sorted(folder.glob('checkpoint_*.json'))
    previous=None;seen=set();last=None;previous_updates=None
    for index,file in enumerate(files,1):
        if file.name!=f'checkpoint_{index:08d}.json':raise ValueError('CHECKPOINT_SEQUENCE_GAP')
        raw=file.read_bytes()
        sidecar=file.with_suffix('.sha256')
        if not sidecar.is_file() or sidecar.read_text(encoding='ascii').strip()!=_sha(raw):
            raise ValueError('CHECKPOINT_DIGEST_MISMATCH')
        doc=json.loads(raw)
        if set(doc)!={'schema','symbol','generation','previous_sha256','source_file','source_sha256',
                      'settled_events','state','research_only','no_orders'}:raise ValueError('CHECKPOINT_SCHEMA_MISMATCH')
        if doc['schema']!='CTI_V52_MEMORY' or doc['symbol']!=symbol or doc['generation']!=index or doc['previous_sha256']!=previous:
            raise ValueError('CHECKPOINT_CHAIN_INVALID')
        if doc['research_only'] is not True or doc['no_orders'] is not True:raise ValueError('CHECKPOINT_PERMISSION_INVALID')
        _verify_state(doc['state'])
        if doc['source_sha256'] in seen:raise ValueError('DUPLICATE_SOURCE_SESSION')
        if type(doc['settled_events']) is not int or doc['settled_events']<1:raise ValueError('UNSETTLED_CHECKPOINT')
        # Every generation must be traceable to authentic, causally audited market data.
        # Checking only the newest capture leaves historical lineage vulnerable to corruption.
        source=Path(doc['source_file'])
        if not source.is_file() or _sha(source.read_bytes())!=doc['source_sha256']:
            raise ValueError('HISTORICAL_SOURCE_EVIDENCE_MISSING_OR_CHANGED')
        verified=audit_file(source)
        if verified['settled']!=doc['settled_events']:
            raise ValueError('HISTORICAL_SOURCE_AUDIT_FAILED')
        from .market_replay_v43 import read_chain
        rows=read_chain(source)
        first=next((r for r in rows if r['kind']=='START'),None)
        if not first or first['payload'].get('symbol')!=symbol or first['payload'].get('initial_memory_checkpoint_sha256')!=doc['previous_sha256']:
            raise ValueError('HISTORICAL_SESSION_LINEAGE_MISMATCH')
        total_updates=sum(x['updates'] for x in doc['state'])
        expected=(previous_updates or 0)+6*doc['settled_events']
        if total_updates!=expected:
            raise ValueError('HISTORICAL_MEMORY_UPDATE_COUNT_MISMATCH')
        previous_updates=total_updates
        seen.add(doc['source_sha256']);previous=_sha(raw);last=doc
    return last,previous

def commit(root,symbol,models,source_path,prior_sha,prior_doc):
    folder=_folder(root,symbol);folder.mkdir(parents=True,exist_ok=True)
    now,sha=load(root,symbol)
    if sha!=prior_sha:raise ValueError('MEMORY_CHANGED_DURING_CAPTURE')
    if now!=prior_doc:raise ValueError('MEMORY_STATE_CHANGED_DURING_CAPTURE')
    source=Path(source_path)
    verified=audit_file(source)
    if verified['settled']<1:raise ValueError('NO_VALID_SETTLED_EVENT')
    new_state=snapshot(models)
    start_updates=sum(x['updates'] for x in prior_doc['state']) if prior_doc else 0
    if sum(x['updates'] for x in new_state)!=start_updates+6*verified['settled']:
        raise ValueError('MEMORY_UPDATE_COUNT_MISMATCH')
    # Initial checkpoint lineage must be recorded in the independently audited session.
    from .market_replay_v43 import read_chain
    rows=read_chain(source)
    start=next((r for r in rows if r['kind']=='START'),None)
    if not start or start['payload'].get('initial_memory_checkpoint_sha256')!=prior_sha:
        raise ValueError('SESSION_MEMORY_LINEAGE_MISMATCH')
    raw_source=source.read_bytes();source_sha=_sha(raw_source)
    generation=1 if prior_doc is None else prior_doc['generation']+1
    doc={'schema':'CTI_V52_MEMORY','symbol':symbol,'generation':generation,'previous_sha256':prior_sha,
         'source_file':str(source.resolve()),'source_sha256':source_sha,'settled_events':verified['settled'],
         'state':new_state,'research_only':True,'no_orders':True}
    destination=folder/f'checkpoint_{generation:08d}.json'
    with destination.open('xb') as f:
        raw=_bytes(doc);f.write(raw);f.flush();os.fsync(f.fileno())
    with destination.with_suffix('.sha256').open('x',encoding='ascii') as f:
        f.write(_sha(raw)+'\n');f.flush();os.fsync(f.fileno())
    return {'generation':generation,'checkpoint_sha256':_sha(raw),'settled':verified['settled'],
            'source_sha256':source_sha,'checkpoint_file':str(destination)}
