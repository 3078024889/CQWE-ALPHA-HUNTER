"""Resume the already-authorized automatic paper experiment after the 10x migration."""
import json
from pathlib import Path
import time
from urllib.request import urlopen,Request
from cqwe.local_autopilot import atomic


def main():
    base='http://127.0.0.1:8765'
    transition=json.loads(Path('reports/leverage_stage_transition_20261016.json').read_text(encoding='utf-8'))
    state=json.load(urlopen(base+'/api/state',timeout=3))
    assert state['mode']=='PUBLIC_DATA_PAPER_ONLY' and state['account']['leverage']==10
    assert not state['account']['positions']
    if transition['resume_automatic']:
        token=json.loads(urlopen(base+'/bootstrap.js',timeout=3).read().decode().split('=',1)[1].rstrip(';'))
        data=json.dumps({'action':'start','mode':'automatic','request_id':'resume-ten-'+str(time.time_ns())}).encode()
        json.load(urlopen(Request(base+'/api/action',data=data,headers={'Content-Type':'application/json','X-CQWE-Token':token}),timeout=3))
    state=json.load(urlopen(base+'/api/state',timeout=3))
    atomic(Path('reports/leverage_10x_runtime_20261016.json'),{
        'at_ms':state['at_ms'],'stage_started_ms':state['account']['stage_started_ms'],
        'leverage':state['account']['leverage'],'running':state['account']['running'],
        'automatic':state['account']['automatic'],'cash':state['account']['cash'],
        'positions':len(state['account']['positions']),'book_labels':state['book_labels'],
        'real_orders':0,'maintenance_rate_assumption':'1% constant, paper only; not Binance bracket data',
        'previous_stage_archive':transition['archive']})
    print(json.dumps({'leverage':state['account']['leverage'],'running':state['account']['running'],
                      'automatic':state['account']['automatic'],'cash':state['account']['cash'],'real_orders':0}))


if __name__=='__main__':main()
