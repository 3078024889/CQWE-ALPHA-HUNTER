"""Preserve positions and balance; explicitly supersede clock-based paper exits."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from cqwe.trend_exit import POLICY
from cqwe.local_autopilot import atomic


def main():
    root=Path('D:/CQWE_DATA/workbench_v1')
    with sqlite3.connect(root/'paper.sqlite3') as db:
        blob,sha=db.execute('SELECT payload,hash FROM state WHERE id=1').fetchone()
        if hashlib.sha256(blob.encode()).hexdigest()!=sha:raise ValueError('LEDGER_HASH')
        state=json.loads(blob);changed=[]
        for s,p in state['positions'].items():
            changed.append({'symbol':s,'original_expires_ms':p.get('expires_ms'),'entry':p['entry'],'quantity':p['quantity']})
            p['previous_expires_ms']=p.get('expires_ms');p['expires_ms']=None;p['exit_policy']=POLICY
        state.setdefault('exit_policy_stages',[]).append({'started_ms':time.time_ns()//1000000,'policy':POLICY,
            'balance':state['cash'],'positions_migrated':changed})
        state['futures_exit_policy']=POLICY
        blob=json.dumps(state,sort_keys=True,ensure_ascii=False,allow_nan=False)
        with db:db.execute('UPDATE state SET payload=?,hash=? WHERE id=1',(blob,hashlib.sha256(blob.encode()).hexdigest()))
    atomic(Path('reports/trend_exit_migration_20261016.json'),{'at_ms':time.time_ns()//1000000,
        'policy':POLICY,'cash_preserved':state['cash'],'positions_migrated':changed,
        'forecast_horizon_seconds':300,'real_orders':0})
    print(json.dumps({'migrated':changed,'cash':state['cash']}))


if __name__=='__main__':main()
