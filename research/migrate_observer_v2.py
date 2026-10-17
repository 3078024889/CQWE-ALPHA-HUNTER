"""Offline atomic model migration with original ledger and source diagnosis retained."""
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import time
from cqwe.paper_observer_v2 import PaperObserver
from cqwe.local_autopilot import atomic


def main():
    try:
        with socket.create_connection(('127.0.0.1',8765),timeout=1):raise RuntimeError('STOP_WORKBENCH_BEFORE_MIGRATION')
    except (ConnectionRefusedError,TimeoutError):pass
    root=Path('D:/CQWE_DATA/workbench_v1')
    with sqlite3.connect(root/'paper.sqlite3') as db:
        blob,sha=db.execute('SELECT payload,hash FROM state WHERE id=1').fetchone()
        if hashlib.sha256(blob.encode()).hexdigest()!=sha:raise ValueError('ACCOUNT_HASH')
        state=json.loads(blob)
        if state['positions']:raise ValueError('EXISTING_POSITION_REQUIRES_ORIGINAL_EXIT_RULES')
        archive=root/'stage_archives'/('observer_v1_'+str(time.time_ns()));archive.mkdir(parents=True)
        with sqlite3.connect(archive/'paper.sqlite3') as backup:db.backup(backup)
        old=state['observer'];diagnosis={}
        for s,b in old['banks'].items():
            bound=sum(abs(w)*(1+.1*abs(m)) for w,m in zip(b['model']['weights'][:4],b['model']['memory'][:4]))
            import math
            upper=1/(1+math.exp(-math.tanh(bound)/4))
            diagnosis[s]={'matured':b['n'],'qualified_direction_samples':b['policy_n'],
                          'old_probability_upper_bound_at_saved_weights':upper,'threshold':.55}
        resume=state['running'] and state['automatic']
        state['observer']=PaperObserver.migrate_legacy(old).state
        state['research_stage']={'name':'OBSERVER_V2_EXPLORATION','started_ms':time.time_ns()//1000000,
            'starting_cash':state['cash'],'leverage':state['leverage'],
            'exploration_margin_fraction':'.05','max_exploration_positions':1,
            'exploration_max_hold_seconds':300,'per_symbol_entry_interval_seconds':600,
            'previous_archive':str(archive)}
        state.update(running=False,automatic=False)
        updated=json.dumps(state,sort_keys=True,ensure_ascii=False,allow_nan=False)
        with db:db.execute('UPDATE state SET payload=?,hash=? WHERE id=1',(updated,hashlib.sha256(updated.encode()).hexdigest()))
    report={'archive':str(archive),'diagnosis':diagnosis,'resume_automatic':resume,
            'stage':state['research_stage'],'manual_trades_retained':len(state['trades']),
            'server_was_listening':False,'real_orders':0,'profitability_proven':False}
    atomic(Path('reports/observer_v2_migration_20261016.json'),report)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
