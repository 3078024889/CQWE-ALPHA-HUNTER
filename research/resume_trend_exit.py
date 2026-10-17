import json
from pathlib import Path
import time
from urllib.request import urlopen,Request


def main():
    base='http://127.0.0.1:8765'
    before=json.loads(Path('reports/trend_exit_transition_20261016.json').read_text(encoding='utf-8'))
    state=json.load(urlopen(base+'/api/state',timeout=3))
    if before['resume_automatic'] and not state['account']['halted']:
        token=json.loads(urlopen(base+'/bootstrap.js',timeout=3).read().decode().split('=',1)[1].rstrip(';'))
        data=json.dumps({'action':'start','mode':'automatic','request_id':'resume-trend-'+str(time.time_ns())}).encode()
        json.load(urlopen(Request(base+'/api/action',data=data,headers={'Content-Type':'application/json','X-CQWE-Token':token}),timeout=3))
    state=json.load(urlopen(base+'/api/state',timeout=3))
    print(json.dumps({'running':state['account']['running'],'automatic':state['account']['automatic'],
        'policy':state['futures_exit_policy'],'positions':state['account']['positions'],
        'forecast_horizon':state['prediction_horizon_seconds'],'errors':state['errors']},ensure_ascii=False))


if __name__=='__main__':main()
