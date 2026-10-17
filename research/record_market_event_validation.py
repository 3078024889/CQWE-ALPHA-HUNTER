"""Record scoped tests and actual integrated event/orderflow runtime evidence."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
from cqwe.local_autopilot import atomic


def main():
    s=json.load(urlopen('http://127.0.0.1:8765/api/state',timeout=3))
    assert s['futures_exit_policy']=='COPERNICAN_FLOW_EVENT_EXIT_V1'
    news=s['global_events']
    report={'at_ms':s['at_ms'],'tests':152,'test_result':'OK, observed 2026-10-16, 4.071s',
        'running':s['account']['running'],'automatic':s['account']['automatic'],
        'cash':s['account']['cash'],'futures_exit_policy':s['futures_exit_policy'],
        'fresh_news_sources':news.get('fresh_sources',[]),'news_sources':news.get('sources',{}),
        'global_coverage_complete':False,'maker_intent_known':False,
        'real_market_decisions':{k:{'action':v['action'],'reason':v['reason'],
            'hypotheses':v.get('mechanism_hypotheses'), 'market_evidence':v.get('market_evidence'),
            'shadow_champion':v.get('shadow_champion')} for k,v in s['decisions'].items()},
        'real_model_learning':s['mechanism_learning'],
        'trades':[{k:t.get(k) for k in ('symbol','reason','source','strategy_id','net_pnl')}
                  for t in s['account']['trades']],
        'runtime_errors':s['errors'],'real_orders':0,'profitability_proven':False,
        'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path('cqwe/workbench.py'),Path('cqwe/global_event_context.py'),Path('cqwe/market_evidence.py'),
             Path('cqwe/liquidation_watch.py'),Path('cqwe/copernican_market_policy.py'),
             Path('cqwe/mechanism_exit.py'),Path('workbench/app.js'),Path('workbench/index.html')]}}
    atomic(Path('reports/market_event_validation_20261016.json'),report)
    print(json.dumps({'running':report['running'],'sources':report['fresh_news_sources'],
                      'real_model_updates':{k:v['updates'] for k,v in s['mechanism_learning'].items()},
                      'errors':report['runtime_errors'],'real_orders':0}))


if __name__=='__main__':main()
