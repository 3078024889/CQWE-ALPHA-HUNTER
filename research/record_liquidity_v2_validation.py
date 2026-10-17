"""Record only completed, hash-checked V2 public-data evidence."""
import json
from pathlib import Path

from cqwe.copernican_experiment_v81_v85 import digest
from cqwe.four_market_runner import checked, sources


def main():
    repo = Path(__file__).resolve().parents[1]
    root = Path('D:/CQWE_DATA/liquidity_v2_forward_20261015')
    folder = root/'round_000001'
    if (root/'runner.lock').exists():
        raise ValueError('EXPERIMENT_STILL_RUNNING')
    state = checked(json.loads((folder/'state.json').read_text(encoding='utf-8')))
    report = checked(json.loads((folder/'report.json').read_text(encoding='utf-8')))
    pointer = checked(json.loads((root/'LATEST.json').read_text(encoding='utf-8')))
    if (state['source_sha256'] != sources() or report['state_sha256'] != state['sha256']
            or pointer['state_sha256'] != state['sha256']
            or len(report['checks']) != 10 or not all(report['checks'].values())):
        raise ValueError('EXPERIMENT_NOT_VERIFIED')
    tests = json.loads((repo/'reports/liquidity_v2_test_results_20261015.json').read_text())
    if not tests['success']:
        raise ValueError('TESTS_FAILED')
    result = {
        'schema':'CQWE_LIQUIDITY_V2_VALIDATION', 'client_date':'2026-10-15',
        'source_sha256':sources(), 'folder':str(folder), 'seconds':325,
        'checks':report['checks'], 'state_sha256':state['sha256'],
        'summary':report['summary'], 'tests':tests,
        'shadow_model_updates':{key:{kind:model['updates'] for kind,model in bank.items()}
            for key,bank in state['engine']['liquidity_study']['models'].items()},
        'actual_liquidation_events_are_sampled':True,
        'third_party_liquidation_heatmap_integrated':False,
        'real_orders':0, 'real_account_profit':None, 'profitability_proven':False,
        'github_pushed':False, 'background_service_installed':False,
        'limitations':['325 seconds cannot validate profitability or 900-second labels.',
            'Observed liquidation snapshots are not complete market liquidation volume.',
            'Orderbook changes do not reveal hidden stops or maker identities.',
            'Shadow ablation statistics are descriptive and not selection corrected.',
            'Hypothetical liquidation map zones are not yet learner inputs.']}
    result['sha256'] = digest(result)
    target = repo/'reports/liquidity_v2_validation_20261015.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(target),'summary':report['summary'],
                      'checks':report['checks'],'tests':tests},ensure_ascii=False))


if __name__ == '__main__':
    main()
