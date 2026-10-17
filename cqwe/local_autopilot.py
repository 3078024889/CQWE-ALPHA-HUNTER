"""Local public-data research service: restart, offline curriculum, live observation.

No account credentials, order endpoints, shell-generated code or paid services.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from .copernican_experiment_v81_v85 import digest
from .four_market_runner import checked, sources
from .historical_curriculum import public, initial, catch_up


def atomic(path,obj):
    obj={k:v for k,v in obj.items() if k!='sha256'}
    obj['sha256']=digest(obj)
    temp=path.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8') as f:
        json.dump(obj,f,ensure_ascii=False,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


@contextlib.contextmanager
def exclusive(root):
    with (root/'service.lock').open('a+b') as f:
        if os.name=='nt':
            import msvcrt
            if f.tell()==0:
                f.write(b'0');f.flush()
            f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name=='nt':
                f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def accepted(root):
    found=[]
    for p in sorted((root/'sessions').glob('*/LATEST.json')):
        pointer=checked(json.loads(p.read_text(encoding='utf-8')))
        name=pointer['round_name']
        if len(name)!=12 or not name.startswith('round_') or not name[6:].isdigit():
            raise ValueError('AUTOPILOT_POINTER_PATH')
        folder=p.parent/name
        st=checked(json.loads((folder/'state.json').read_text(encoding='utf-8')))
        if st['source_sha256']!=sources() or st['sha256']!=pointer['state_sha256']:
            raise ValueError('AUTOPILOT_SOURCE_OR_CHECKPOINT_CHANGED')
        report_path=folder/'report.json'
        if not report_path.exists():
            # Runner promotes LATEST immediately before atomically creating report.
            continue
        report=checked(json.loads(report_path.read_text(encoding='utf-8')))
        if report['state_sha256']!=st['sha256'] or len(report['checks'])!=10 or not all(report['checks'].values()):
            raise ValueError('AUTOPILOT_UNAUDITED_CHECKPOINT')
        found.append((st['engine']['rounds'],folder,st))
    return max(found,key=lambda x:x[0]) if found else None


def prepare(root):
    latest=accepted(root)
    folder=root/'sessions'/f'session_{time.time_ns()}'
    folder.mkdir(parents=True)
    if latest:
        _,old,st=latest
        seed=folder/old.name;seed.mkdir()
        # Historical journal stays at its original location. The state preserves
        # its previous hash; seed files are not declared newly audited rounds.
        shutil.copyfile(old/'state.json',seed/'state.json')
        pointer={'round_name':old.name,'state_sha256':st['sha256']}
        atomic(folder/'LATEST.json',pointer)
        atomic(folder/'seed_origin.json',{'source_folder':str(old),'state_sha256':st['sha256']})
    return folder


def footprint(root):
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink())


def stop_child(child):
    if child is None or child.poll() is not None:
        return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,timeout=15)
    else:
        os.killpg(child.pid,signal.SIGTERM)
    try:
        child.wait(timeout=15)
    except subprocess.TimeoutExpired:
        if os.name!='nt':
            os.killpg(child.pid,signal.SIGKILL)
        child.kill();child.wait(timeout=10)


def history_step(root,days,pages):
    path=root/'history_state.json'
    now=public('time')['serverTime']
    state=checked(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else initial(now,days)
    def save(page):
        target=root/'history_pages'/f'{digest(page)}.json'
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            atomic(target,page)
    state=catch_up(state,now,save,pages=pages)
    atomic(path,state)
    return {'pages':state['pages'],'symbols':{s:{'labels':v['labels'],'cursor_ms':v['cursor']}
                                             for s,v in state['symbols'].items()},
            'historical_only':True,'live_weights_modified':False}


def serve(root,*,seconds=300,rounds=12,days=30,pages=4,max_bytes=4_000_000_000,cycles=None):
    if not 1<=days<=730 or not 1<=pages<=32 or (cycles is not None and cycles<1):
        raise ValueError('AUTOPILOT_CURRICULUM_BUDGET')
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    child=None;log=None;stopping=False
    def halt(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGINT,halt);signal.signal(signal.SIGTERM,halt)
    with exclusive(root):
        context={'source_sha256':sources(),'service_sha256':{
            n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest()
            for n in ('local_autopilot.py','historical_curriculum.py')},
            'days':days,'seconds':seconds,'rounds':rounds,'max_bytes':max_bytes}
        anchor=root/'anchor.json'
        if anchor.exists():
            if checked(json.loads(anchor.read_text(encoding='utf-8')))['context']!=context:
                raise ValueError('AUTOPILOT_CONTEXT_CHANGED_USE_NEW_ROOT')
        else:
            atomic(anchor,{'context':context,'real_orders':0})
        iteration=0;failures=0;retry_at=0.;next_history=0.;next_health=0.;history={}
        try:
            while not stopping:
                now=time.monotonic()
                if now<next_health:
                    time.sleep(1);continue
                next_health=now+5
                used=footprint(root);free=shutil.disk_usage(root).free
                if used>max_bytes or free<2_000_000_000:
                    stop_child(child)
                    atomic(root/'status.json',{'status':'PAUSED_DISK_BUDGET','used_bytes':used,
                        'free_bytes':free,'observed_ns':time.time_ns(),'real_orders':0})
                    return
                if child is not None and child.poll() is not None:
                    code=child.returncode;log.close();log=None;child=None
                    failures=failures+1 if code else 0
                    retry_at=now+min(300,5*2**min(failures,6))
                    if cycles is not None and iteration>=cycles:
                        break
                if now>=next_history:
                    try:
                        history=history_step(root,days,pages)
                    except Exception as exc:
                        history={'status':'RETRY_LATER','error':type(exc).__name__+': '+str(exc)}
                    next_history=time.monotonic()+300
                if child is None and now>=retry_at:
                    folder=prepare(root)
                    log=(folder/'process.log').open('a',encoding='utf-8')
                    child=subprocess.Popen([sys.executable,'-u','-m','cqwe.four_market_runner',
                        '--root',str(folder),'--rounds',str(rounds),'--seconds',str(seconds),'--no-catalog'],
                        cwd=Path(__file__).resolve().parents[1],stdout=log,stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
                        start_new_session=os.name!='nt')
                    iteration+=1
                good=accepted(root)
                atomic(root/'status.json',{'status':'OBSERVING' if child else 'RETRY_BACKOFF',
                    'observed_ns':time.time_ns(),'child_pid':child.pid if child else None,
                    'accepted_rounds':good[0] if good else 0,'history':history,'used_bytes':used,
                    'council':good[2]['engine']['council'] if good else {},
                    'research_plan':{'next_review_round':((good[0] if good else 0)//5+1)*5,
                        'review_every_rounds':5,'replay_checks_per_round':10,
                        'next_task':'FILL_HISTORY_GAPS_AND_COLLECT_NEW_PRECOMMITTED_LABELS',
                        'candidate_policy':'FINITE_PREDECLARED_NODES_WITH_RECORDED_FAILURES',
                        'automatic_source_code_rewriting':False},
                    'real_orders':0,'profitability_proven':False,'code_self_rewriting':False})
        finally:
            stop_child(child)
            if log:
                log.close()
        atomic(root/'status.json',{'status':'STOPPED','observed_ns':time.time_ns(),'real_orders':0})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True);p.add_argument('--seconds',type=int,default=300)
    p.add_argument('--rounds',type=int,default=12);p.add_argument('--days',type=int,default=30)
    p.add_argument('--pages',type=int,default=4);p.add_argument('--cycles',type=int)
    a=p.parse_args()
    if not 15<=a.seconds<=3600 or not 1<=a.rounds<=288 or a.seconds*a.rounds>86400:
        p.error('invalid live research budget')
    serve(a.root,seconds=a.seconds,rounds=a.rounds,days=a.days,pages=a.pages,cycles=a.cycles)


if __name__=='__main__':
    main()
