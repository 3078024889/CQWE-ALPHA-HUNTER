"""Enable only the user-authorized experimental paper ensemble."""
import json
import time
from pathlib import Path
from urllib.request import Request,urlopen
from cqwe.unified_dendritic_paper import POLICY


def main():
    b='http://127.0.0.1:8765';s=json.load(urlopen(b+'/api/state',timeout=3))
    if s.get('real_orders')!=0 or s.get('mode')!='PUBLIC_DATA_PAPER_ONLY':raise ValueError('NOT_PAPER_WORKBENCH')
    if s['account']['positions']:raise ValueError('EXISTING_POSITION_REQUIRES_REVIEW')
    t=json.loads(urlopen(b+'/bootstrap.js',timeout=3).read().decode().split('=',1)[1].rstrip(';'))
    data=json.dumps({'action':'start','mode':'automatic','policy':POLICY,'request_id':'activate-unified-'+str(time.time_ns())}).encode()
    result=json.load(urlopen(Request(b+'/api/action',data=data,headers={'Content-Type':'application/json','X-CQWE-Token':t}),timeout=3))
    state=json.load(urlopen(b+'/api/state',timeout=3));a=state['account']
    assert a['automatic'] and a['running'] and a['active_policy']==POLICY
    out={'at_ms':state['at_ms'],'active_policy':a['active_policy'],'automatic':a['automatic'],'running':a['running'],
         'stage':a['ensemble_stage'],'initial_cash':s['account']['cash'],'initial_fees':s['account']['fees'],'prior_trade_count':len(s['account']['trades']),
         'mode':state['mode'],'real_orders':state['real_orders'],'user_authorized_experimental_simulation':True}
    Path('reports/unified_simulation_activation_20261016.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps(out))


if __name__=='__main__':main()
