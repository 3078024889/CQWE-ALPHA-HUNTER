"""CQWE V21 offline time-forward orchestration with resumable, verified checkpoints.
Public 5-minute datasets only. No broker access or orders. Backtest replay != live trading.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from .self_evolution_v20 import offline_evolution, continuation_update, sha, SCHEMA
from .dendritic_v19 import validate_inputs

PERIOD=300000
SCHEMA_V21=21

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    temp.replace(path)

def read_markets(inputs):
    data={};origins={}
    for item in inputs:
        p=Path(item); sym=p.stem.split('_')[0].upper()
        if not sym.isalnum() or not sym or sym in data:raise ValueError('BAD_OR_DUPLICATE_MARKET')
        data[sym]=json.loads(p.read_text(encoding='utf-8-sig'))
        origins[sym]=digest(p)
    times,aligned=validate_inputs(data)
    # No silent intersection trimming; every market must share identical open times.
    for name,bars in data.items():
        if len(bars)!=len(times) or any(int(b[0])!=t for b,t in zip(bars,times)):
            raise ValueError('MISALIGNED_MARKET_DATA')
    return times,aligned,origins

def verify_saved(store):
    root=Path(store)
    ledger_path=root/'ledger.json'
    if not ledger_path.is_file():raise FileNotFoundError('LEDGER_MISSING')
    led=json.loads(ledger_path.read_text(encoding='utf-8'))
    if led.get('schema')!=SCHEMA_V21 or not isinstance(led.get('episodes'),list) or not led['episodes']:
        raise ValueError('BAD_LEDGER')
    previous=None
    for k,row in enumerate(led['episodes']):
        state_path=root/row['checkpoint']
        if not state_path.is_file() or digest(state_path)!=row['checkpoint_file_sha256']:
            raise ValueError('CHECKPOINT_DIGEST_MISMATCH')
        state=json.loads(state_path.read_text(encoding='utf-8'))
        if state.get('schema')!=SCHEMA or int(state['last_seen_ms'])!=row['last_seen_ms']:
            raise ValueError('CHECKPOINT_STATE_MISMATCH')
        if sha(state)!=row['state_sha256']:
            raise ValueError('CHECKPOINT_STATE_HASH_MISMATCH')
        if not (root/row['report']).is_file() or digest(root/row['report'])!=row['report_sha256']:
            raise ValueError('REPORT_DIGEST_MISMATCH')
        if row['previous_episode_sha256']!=previous:
            raise ValueError('BROKEN_EPISODE_CHAIN')
        temp={key:value for key,value in row.items() if key!='episode_sha256'}
        if sha(temp)!=row['episode_sha256']:raise ValueError('BAD_EPISODE_HASH')
        if k and row['last_seen_ms']<=led['episodes'][k-1]['last_seen_ms']:
            raise ValueError('NONMONOTONIC_WATERMARK')
        # Validate V20 continuation journal hashes, which are not checked by the base V20 loader.
        if k:
            prev_state=json.loads((root/led['episodes'][k-1]['checkpoint']).read_text(encoding='utf-8'))
            before=prev_state.get('journal',[])
            after=state.get('journal',[])
            if len(after)!=len(before)+1 or after[:-1]!=before:
                raise ValueError('BROKEN_CONTINUATION_JOURNAL')
            entry=after[-1]
            expected_hash=before[-1]['entry_sha256'] if before else prev_state['selection_sha256']
            if entry.get('previous_hash')!=expected_hash or sha({j:v for j,v in entry.items() if j!='entry_sha256'})!=entry.get('entry_sha256'):
                raise ValueError('BROKEN_JOURNAL_HASH')
        previous=row['episode_sha256']
    if led['tip_sha256']!=previous:raise ValueError('BAD_LEDGER_TIP')
    return {'verified_episodes':len(led['episodes']),'last_seen_ms':led['episodes'][-1]['last_seen_ms'],
            'tip_sha256':led['tip_sha256'],'research_only':True}

def _append(root,ledger,state,report,kind):
    root=Path(root)
    ix=len(ledger['episodes'])
    name=f'state_{ix:04d}.json'
    # Store immutable named snapshots. Replaying a pre-existing index is an error.
    dest=root/name
    if dest.exists():raise ValueError('CHECKPOINT_ALREADY_EXISTS')
    atomic(dest,state)
    report_name=f'report_{ix:04d}.json'
    atomic(root/report_name,report)
    previous=ledger['episodes'][-1]['episode_sha256'] if ledger['episodes'] else None
    row={'index':ix,'kind':kind,'checkpoint':name,'checkpoint_file_sha256':digest(dest),
         'state_sha256':sha(state),'report':report_name,'report_sha256':digest(root/report_name),
         'last_seen_ms':state['last_seen_ms'],'previous_episode_sha256':previous}
    row['episode_sha256']=sha(row)
    ledger['episodes'].append(row);ledger['tip_sha256']=row['episode_sha256']
    atomic(root/'ledger.json',ledger)
    return row

def replay(inputs,store,initial_fraction=.60,chunk=288,stop_after=None):
    times,data,origins=read_markets(inputs)
    if not .5<=initial_fraction<=.8 or not isinstance(chunk,int) or chunk<240 or not isinstance(stop_after,(int,type(None))) or (stop_after is not None and stop_after<1):
        raise ValueError('BAD_REPLAY_SETTINGS')
    n=len(times)
    if n<1000:raise ValueError('NEED_LONG_HISTORY')
    # Initial length chosen so all subsequent episodes have exactly ``chunk`` bars.
    k=int((n-int(n*initial_fraction))//chunk)
    initial=n-k*chunk
    if k<1 or initial<500:raise ValueError('NO_FULL_CONTINUATION_EPISODE')
    root=Path(store)
    # A run can resume only with the EXACT same source data bytes and config.
    config={'schema':SCHEMA_V21,'source_sha256':origins,'symbols':sorted(data),
            'total_bars':n,'initial_bars':initial,'chunk_bars':chunk,
            'initial_fraction':initial_fraction,'last_source_open_ms':times[-1]}
    ledger_path=root/'ledger.json'
    if ledger_path.exists():
        check=verify_saved(root)
        ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
        if ledger['config']!=config:raise ValueError('DATA_OR_CONFIG_CHANGED')
        state=json.loads((root/ledger['episodes'][-1]['checkpoint']).read_text(encoding='utf-8'))
    else:
        # Do not overwrite a partially populated directory without an authoritative ledger.
        if root.exists() and any(root.iterdir()):raise ValueError('NONEMPTY_UNVERIFIED_STORE')
        root.mkdir(parents=True,exist_ok=True)
        first={s:bars[:initial] for s,bars in data.items()}
        report,state=offline_evolution(first)
        state['data_last_open_ms']=state['last_seen_ms']
        ledger={'schema':SCHEMA_V21,'config':config,'episodes':[],'tip_sha256':None}
        _append(root,ledger,state,report,'INITIAL_OFFLINE_SELECTION')
    complete=0
    while len(ledger['episodes'])-1<k:
        if stop_after is not None and complete>=stop_after:break
        episode=len(ledger['episodes']) # episode 1 begins at initial
        lo=initial+(episode-1)*chunk
        new={s:bars[lo:lo+chunk] for s,bars in data.items()}
        next_state,entry=continuation_update(state,new)
        _append(root,ledger,next_state,{'mode':'PREQUENTIAL','event':entry,'not_independent_holdout':True},'CONTINUATION')
        state=next_state;complete+=1
    verified=verify_saved(root)
    return {'research_only':True,'completed_episodes':len(ledger['episodes'])-1,
            'planned_episodes':k,'initial_bars':initial,'newly_completed':complete,
            'verified':verified,'no_orders':True,'virtual_realized_profit_usd':None,
            'warning':'Prequential replay is an adaptive research experiment, not an independent trading PnL or live performance.'}

def main():
    p=argparse.ArgumentParser(description='CQWE V21 persistent time-forward evidence replay, no orders')
    sub=p.add_subparsers(dest='cmd',required=True)
    r=sub.add_parser('replay');r.add_argument('--inputs',nargs='+',required=True);r.add_argument('--store',required=True)
    r.add_argument('--chunk',type=int,default=288);r.add_argument('--stop-after',type=int)
    v=sub.add_parser('verify');v.add_argument('--store',required=True)
    a=p.parse_args()
    result=verify_saved(a.store) if a.cmd=='verify' else replay(a.inputs,a.store,chunk=a.chunk,stop_after=a.stop_after)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('CQWE_V21_VERIFIED_REPLAY_PASS | RESEARCH ONLY | NO ORDERS')
if __name__=='__main__':main()
