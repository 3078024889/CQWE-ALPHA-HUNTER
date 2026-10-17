"""Bounded public repository discovery. Never import or execute fetched code."""
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen
from urllib.parse import urlencode

REPOS=[
 ('hummingbot/hummingbot','market_making_funding',['README.md','LICENSE','scripts/funding_rate_arb.py']),
 ('hummingbot/quants-lab','research_workflow',['README.md','LICENSE']),
 ('nkaz001/hftbacktest','orderbook_execution',['README.rst','LICENSE']),
 ('vnpy/vnpy_ctastrategy','trend_volatility',['README.md','LICENSE','vnpy_ctastrategy/strategies/atr_rsi_strategy.py','vnpy_ctastrategy/strategies/turtle_signal_strategy.py']),
 ('QuantConnect/Lean','pairs_multiasset',['readme.md','LICENSE','Algorithm.Framework/Alphas/BasePairsTradingAlphaModel.py']),
 ('nautechsystems/nautilus_trader','event_driven_execution',['README.md','LICENSE']),
 ('microsoft/qlib','model_research',['README.md','LICENSE']),
 ('AI4Finance-Foundation/FinRL','reinforcement_learning',['README.md','LICENSE']),
 ('freqtrade/freqtrade','strategy_testing',['README.md','LICENSE','docs/lookahead-analysis.md']),
 ('jesse-ai/jesse','strategy_testing',['README.md','LICENSE']),
 ('mementum/backtrader','event_driven_testing',['README.rst','LICENSE']),
 ('stefanjansen/machine-learning-for-trading','crossasset_research',['README.md','LICENSE']),
 ('EA31337/EA31337','mt5_multistrategy',['README.md','LICENSE.md']),
 ('Polymarket/agents','prediction_events',['README.md','LICENSE']),
 ('Polymarket/poly-market-maker','prediction_market_making',['README.md','LICENSE']),
 ('kachence/polymm','prediction_market_making',['README.md','LICENSE']),
]
QUERIES=['market making language:Python stars:>100 archived:false',
         'funding rate arbitrage archived:false','polymarket market maker archived:false',
         'statistical arbitrage language:Python stars:>50 archived:false',
         'MQL5 expert advisor stars:>20 archived:false','algorithmic trading framework stars:>1000 archived:false']


def get(url,cap=300000):
    req=Request(url,headers={'User-Agent':'CQWE-public-research','Accept':'application/vnd.github+json' if 'api.github.com/' in url else 'text/plain'})
    with urlopen(req,timeout=6) as r:raw=r.read(cap+1)
    if len(raw)>cap:raise ValueError('SOURCE_SIZE_BUDGET')
    return raw


def main():
    root=Path('tmp/strategy_discovery_20261016');root.mkdir(exist_ok=True,parents=True)
    report={'at_ms':time.time_ns()//1000000,'scope':'six bounded GitHub indexed queries, curated official repositories; not all world repositories',
            'queries':[],'repositories':[],'third_party_code_executed':False,'exhaustive':False}
    for q in QUERIES:
        try:
            raw=get('https://api.github.com/search/repositories?'+urlencode({'q':q,'per_page':10,'sort':'stars'}));r=json.loads(raw)
            report['queries'].append({'query':q,'total_indexed':r['total_count'],'returned':[
                {'repo':i['full_name'],'url':i['html_url'],'license':(i.get('license') or {}).get('spdx_id'),'stars':i['stargazers_count']} for i in r['items']],
                'sha256':hashlib.sha256(raw).hexdigest()})
        except Exception as e:report['queries'].append({'query':q,'error':str(e)})
    for repo,family,files in REPOS:
        record={'repo':repo,'url':'https://github.com/'+repo,'family':family,'files':[],'profitability_verified':False}
        try:
            meta=json.loads(get('https://api.github.com/repos/'+repo));branch=meta['default_branch']
            ref=json.loads(get('https://api.github.com/repos/'+repo+'/git/ref/heads/'+branch))
            sha=ref['object']['sha'];record.update(commit=sha,license=(meta.get('license') or {}).get('spdx_id'),archived=meta['archived'],pushed_at=meta['pushed_at'])
            for name in files:
                url='https://raw.githubusercontent.com/'+repo+'/'+sha+'/'+name
                try:
                    raw=get(url);path=root/(repo.replace('/','__')+'__'+name.replace('/','__'));path.write_bytes(raw)
                    record['files'].append({'path':name,'local':str(path),'url':url,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'captured':True})
                except Exception as e:record['files'].append({'path':name,'url':url,'captured':False,'error':str(e)})
        except Exception as e:record['error']=str(e)
        report['repositories'].append(record)
        Path('reports/strategy_repository_discovery_20261016.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({'repo':repo,'commit':record.get('commit'),'license':record.get('license'),'captured':sum(f.get('captured',False) for f in record['files']),'error':record.get('error')}),flush=True)
    print(json.dumps({'queries':len(report['queries']),'curated':len(report['repositories']),'distinct_indexed_returned':len({i['repo'] for q in report['queries'] for i in q.get('returned',[])})}),flush=True)


if __name__=='__main__':main()
