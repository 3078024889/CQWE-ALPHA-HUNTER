"""Persistent, time-based execution gates around unvalidated shadow models.

Exits do not imply opposite entry. Rank candidates once across the portfolio;
reversals must independently pass entry, background and persistence gates.
"""
import copy
import hashlib
from pathlib import Path

POLICY='COPERNICAN_PORTFOLIO_RESEARCH_V1'


class PortfolioRouter:
    def __init__(self,state=None):
        source=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.state=copy.deepcopy(state) if state else {'source':source,'signals':{}}
        if self.state['source']!=source:raise ValueError('ROUTER_SOURCE_CHANGED_ARCHIVE_REQUIRED')

    def route(self,decisions,contexts,account,at):
        result=copy.deepcopy(decisions);candidates=[]
        trades=account.get('trades',[]);last=max(trades,key=lambda t:t['closed_ms'],default=None)
        for symbol,d in result.items():
            h=next(iter(d.get('mechanism_hypotheses',[])),None)
            fresh=0<=at-d.get('at_ms',-100000)<=10000 and 0<=at-d.get('market_evidence',{}).get('at_ms',-100000)<=15000
            direction=h.get('direction',0) if h and fresh and d.get('market_evidence',{}).get('ready') else 0
            disagreement=bool(h and any(other.get('direction')==-h['direction'] and
                h['strength']-other.get('strength',0)<.15 for other in d.get('mechanism_hypotheses',[])))
            if disagreement:direction=0
            prev=self.state['signals'].get(symbol)
            continuous=prev and prev['direction']==direction and 0<at-prev['at_ms']<=20000
            since=prev['since_ms'] if continuous else at
            self.state['signals'][symbol]={'direction':direction,'since_ms':since,'at_ms':at}
            duration=at-since if direction else 0
            context=contexts.get(symbol,{})
            context_ready=context.get('ready') and 0<=at-context.get('at_ms',-1000000)<=600000
            regime=context.get('regime',{}).get('direction',0) if context_ready else 0
            position=account.get('positions',{}).get(symbol)
            d['market_background']=context
            route={'policy':POLICY,'signal_duration_ms':duration,'regime_direction':regime,
                   'macro_direction':'UNAVAILABLE','reversal_candidate':False,'reverse_after_close':False,
                   'liquidation_map_execution_weight':0,'profitability_proven':False}
            d['portfolio_route']=route
            if position:
                if d.get('action')=='CLOSE':
                    if duration<60000:
                        d.update(action='HOLD',reason='REVERSAL_PERSISTENCE_WAIT',exit_basis=None)
                    else:
                        route['reversal_candidate']=direction==-position['direction']
                        route['status']='EXIT_ONLY_REASSESS_OPPOSITE_ENTRY'
                continue
            if d.get('action') not in ('OPEN_LONG','OPEN_SHORT'):continue
            expected=1 if d['action']=='OPEN_LONG' else -1
            block=('STALE_ROUTER_INPUT' if not fresh else 'HYPOTHESES_DISAGREE' if disagreement else 'SLOW_CONTEXT_UNAVAILABLE' if not context_ready else
                   'REGIME_CONFLICT_OR_UNCLEAR' if regime!=expected or direction!=expected else
                   'ENTRY_PERSISTENCE_WAIT' if duration<90000 else
                   'PORTFOLIO_COOLDOWN' if last and at-last['closed_ms']<90000 else None)
            if block:
                d.update(action='OBSERVE',reason=block,exploration_allowed=False);route['status']=block;continue
            latest_symbol=max((t for t in trades if t['symbol']==symbol),key=lambda t:t['closed_ms'],default=None)
            reverse=bool(latest_symbol and latest_symbol.get('reason')=='FLOW_LIQUIDITY_REVERSAL'
                         and latest_symbol['direction']==-expected and 90000<=at-latest_symbol['closed_ms']<300000)
            if latest_symbol and at-latest_symbol['closed_ms']<300000 and not reverse:
                d.update(action='OBSERVE',reason='SAME_SYMBOL_COOLDOWN',exploration_allowed=False);continue
            if not reverse and at-account.get('last_exploration',{}).get(symbol,-600000)<600000:
                d.update(action='OBSERVE',reason='EXPLORATION_CADENCE',exploration_allowed=False);continue
            route.update(reverse_after_close=reverse,reversal_candidate=reverse,status='RANKED_PAPER_CANDIDATE')
            # This is evidence ranking, not expected net profit or a probability.
            route['rank_score']=h['strength']+min(duration/300000,1)*.1
            candidates.append((int(reverse),route['rank_score'],symbol))
        ranked=sorted(candidates,reverse=True)
        for rank,(_,_,symbol) in enumerate(ranked):
            result[symbol]['portfolio_route']['rank']=rank+1
            if rank:
                result[symbol].update(action='OBSERVE',reason='HIGHER_RANKED_PORTFOLIO_CANDIDATE',exploration_allowed=False)
        return result
