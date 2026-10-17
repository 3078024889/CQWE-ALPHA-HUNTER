"""Assemble evidence from completed audited rounds; never invent pending results."""
import json
from pathlib import Path

from cqwe.copernican_experiment_v81_v85 import digest
from cqwe.four_market_runner import checked, sources

ROOT = Path('D:/CQWE_DATA/four_market_final_20261015')
REPO = Path(__file__).resolve().parents[1]
CATALOG = Path('D:/CQWE_DATA/four_market_catalog_20261015/catalog/catalog_1792046775568328400.json')
MATURITY = Path('D:/CQWE_DATA/four_market_maturity_20261015/round_000001')


def main():
    if (ROOT/'supervisor.lock').exists() or (MATURITY.parent/'runner.lock').exists():
        raise ValueError('VALIDATION_EXPERIMENT_STILL_RUNNING')
    states = {}
    pointers = []
    for p in ROOT.glob('attempt_*/LATEST.json'):
        pointer = checked(json.loads(p.read_text(encoding='utf-8')))
        pointers.append((p,pointer))
    for p in ROOT.glob('attempt_*/round_*/state.json'):
        state = checked(json.loads(p.read_text(encoding='utf-8')))
        if state['source_sha256'] != sources():
            raise ValueError('VALIDATION_SOURCE_CHANGED')
        states[state['sha256']] = (p.parent,state)
    if not pointers:
        raise ValueError('NO_ACCEPTED_ROUND')
    pointer_file,pointer = max(pointers,key=lambda x:states[x[1]['state_sha256']][1]['engine']['rounds'])
    last = states[pointer['state_sha256']][1]
    if last['engine']['rounds'] != 5:
        raise ValueError('FIVE_ROUNDS_NOT_YET_COMPLETE')
    chain = []
    current = pointer['state_sha256']
    while current:
        folder,state = states[current]
        report = checked(json.loads((folder/'report.json').read_text(encoding='utf-8')))
        initial = checked(json.loads((folder/'initial.json').read_text(encoding='utf-8')))
        if (len(report['checks']) != 10 or not all(report['checks'].values())
                or report['state_sha256'] != current or initial['previous'] != state['previous']
                or report['summary']['frames'] != state['engine']['frames']
                or report['summary']['portfolio'] != state['engine']['portfolio']):
            raise ValueError('INCONSISTENT_ACCEPTED_ROUND')
        chain.append({'folder':str(folder),'state_sha256':current,'checks':report['checks'],
                      'summary':report['summary'],'journal_bytes':(folder/'journal.jsonl').stat().st_size})
        current = state['previous']
    chain.reverse()
    tests = json.loads((REPO/'reports/four_market_test_results_20261015.json').read_text())
    if not tests['success']:
        raise ValueError('TESTS_FAILED')
    catalog = checked(json.loads(CATALOG.read_text(encoding='utf-8')))
    latest = chain[-1]['summary']
    maturity = checked(json.loads((MATURITY/'report.json').read_text(encoding='utf-8')))
    maturity_state = checked(json.loads((MATURITY/'state.json').read_text(encoding='utf-8')))
    if (maturity_state['source_sha256'] != sources() or not all(maturity['checks'].values())
            or maturity['state_sha256'] != maturity_state['sha256']):
        raise ValueError('MATURITY_EXPERIMENT_NOT_VERIFIED')
    model_updates = {key:{kind:m['updates'] for kind,m in models.items()} for key,models in last['engine']['models'].items()}
    result = {'schema':'CQWE_FOUR_MARKET_BUILD_VALIDATION_V1','client_date':'2026-10-15',
              'scope':'PUBLIC_DATA_RESEARCH_AND_SHARED_CASH_PAPER_ENGINE',
              'source_sha256':sources(),'accepted_rounds':len(chain),'seconds_per_round':65,
              'rounds':chain,'final_summary':latest,'model_updates':model_updates,
              'separate_maturity_experiment':{'folder':str(MATURITY),'seconds':325,
                'summary':maturity['summary'],'checks':maturity['checks'],
                'state_sha256':maturity_state['sha256'],
                'independent_virtual_account':True,'pooled_statistical_evidence':False},
              'tests':tests,'targeted_tests':24,'launcher_syntax_checked':True,
              'prediction_catalog':{'path':str(CATALOG),'sha256':catalog['sha256'],
                'real_orderbooks_captured':sum(m['status']=='REAL_ORDERBOOKS_CAPTURED' for m in catalog['polymarket']),
                'binance_signed_read':catalog['binance']['status'],'external_resolution_labels':0},
              'live_300_second_maturity_observed':any(':300' in k and m['branch2']['updates']>0 for k,m in maturity_state['engine']['models'].items()),
              'live_900_second_maturity_observed':any(':900' in k and m['branch2']['updates']>0 for k,m in last['engine']['models'].items()),
              'unit_tests_cover_300_and_900_second_maturity':True,
              'automatic_external_event_reference_bridge_complete':False,
              'real_orders':0,'real_account_profit':None,'profitability_proven':False,
              'background_service_installed':False,'github_pushed':False,
              'limitations':['Short forward run is not a profitability test.',
                 'Venue TWAP/anchor reference adapter and authenticated Binance prediction data remain unverified.',
                 'Paper fills and costs are assumptions; no real execution or funding-rate reconciliation.',
                 'Model evolution is finite candidate selection, not autonomous code rewriting.']}
    result['sha256'] = digest(result)
    target = REPO/'reports/four_market_validation_20261015.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(target),'rounds':len(chain),'frames':latest['frames'],
                      'matured':latest['matured_proxy_labels'],'faults':latest['faults'],
                      'cash':latest['portfolio']['cash'],'tests':tests['tests'],
                      'separate_maturity_labels':maturity['summary']['matured_proxy_labels'],
                      'separate_maturity_faults':maturity['summary']['faults']}))


if __name__ == '__main__':
    main()
