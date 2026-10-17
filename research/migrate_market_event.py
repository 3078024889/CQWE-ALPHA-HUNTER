import hashlib
import json
from pathlib import Path
import sqlite3
import time
from cqwe.mechanism_exit import POLICY
from cqwe.local_autopilot import atomic


def main():
    transition=json.loads(Path('reports/market_event_transition_20261016.json').read_text(encoding='utf-8'))
    with sqlite3.connect('D:/CQWE_DATA/workbench_v1/paper.sqlite3') as db:
        blob,sha=db.execute('SELECT payload,hash FROM state WHERE id=1').fetchone()
        if hashlib.sha256(blob.encode()).hexdigest()!=sha:raise ValueError('LEDGER_HASH')
        state=json.loads(blob);changed=[]
        for s,p in state['positions'].items():
            changed.append({'symbol':s,'entry':p['entry'],'quantity':p['quantity'],'old_exit_policy':p.get('exit_policy')})
            p['exit_policy']=POLICY;p['expires_ms']=None
        state['futures_exit_policy']=POLICY
        state.setdefault('research_stage_history',[]).append(state.get('research_stage',{}))
        state['research_stage']={'name':'COPERNICAN_MARKET_EVENT_V1','started_ms':time.time_ns()//1000000,
            'cash_at_start':state['cash'],'previous_archive':transition['archive'],
            'event_coverage_complete':False,'maker_intent_known':False,'exploration_unvalidated':True}
        blob=json.dumps(state,sort_keys=True,ensure_ascii=False,allow_nan=False)
        with db:db.execute('UPDATE state SET payload=?,hash=? WHERE id=1',(blob,hashlib.sha256(blob.encode()).hexdigest()))
    atomic(Path('reports/market_event_migration_20261016.json'),{'stage':state['research_stage'],
            'cash_preserved':state['cash'],'positions_preserved':changed,'trades_preserved':len(state['trades']),'real_orders':0})
    print(json.dumps({'cash':state['cash'],'positions':changed,'trades_preserved':len(state['trades'])}))


if __name__=='__main__':main()
