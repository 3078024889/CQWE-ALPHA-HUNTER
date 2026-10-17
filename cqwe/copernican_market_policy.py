"""Observable liquidity hypotheses plus event constraints; no known maker intent."""
import copy
import hashlib
import math
from pathlib import Path
from .liquidity_research import Branch16

KINDS=('market_event','without_flow','without_events','frozen')
POLICY='COPERNICAN_MARKET_EVENT_V1'


def hypotheses(evidence):
    if not evidence.get('ready'):return []
    flow=evidence['flow'];depletion=evidence['depletion'];refill=evidence['refill'];breakout=evidence['breakout']
    move=evidence['price_move_bps'];items=[]
    for direction in (1,-1):
        confirmations=[direction*flow>.25,direction*depletion>.01,direction*refill>.01,direction*breakout>.15]
        if confirmations[0] and sum(confirmations)>=2:
            items.append({'id':'LIQUIDITY_CONTINUATION','direction':direction,'confirmations':sum(confirmations),
                'strength':min(1.,abs(flow)*.5+sum(confirmations[1:])/6),'evidence':confirmations})
        # Aggressive buying meets ask replenishment without upward progress (or symmetric selling).
        absorption=[direction*flow>.35,direction*refill<-.02,abs(move)<1.]
        if all(absorption):items.append({'id':'POSSIBLE_ABSORPTION','direction':-direction,'confirmations':3,
            'strength':min(1.,abs(flow)*.6+min(abs(refill),.2)),'evidence':absorption})
        if evidence.get('liquidations_available'):
            liq=evidence['features'][4]
            path=[direction*liq>.1,direction*flow>.25,
                  direction*depletion>.01 or direction*refill>.01 or direction*breakout>.15]
            if all(path):items.append({'id':'SAMPLED_LIQUIDATION_CONTINUATION','direction':direction,
                'confirmations':3,'strength':min(1.,.5+abs(flow)*.3),'evidence':path})
    return sorted(items,key=lambda x:(x['strength'],x['confirmations']),reverse=True)


class MarketCouncil:
    def __init__(self,previous=None):
        source=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.state=copy.deepcopy(previous) if previous else {'source':source,'banks':{},'confirmations':{},'dropped':0}
        if self.state['source']!=source:raise ValueError('MARKET_POLICY_SOURCE_CHANGED_ARCHIVE_REQUIRED')

    def decide(self,symbol,quote,base,micro,global_events,calendar,at,position=None):
        mid=(quote['bid']+quote['ask'])/2
        spread=(quote['ask']-quote['bid'])/mid*10000
        # Context entries describe availability/risk, never assert the sign of a headline.
        event_x=[min(1.,len(global_events.get('potential_acute_events',[]))/3),
                 float(bool(calendar.get('upcoming_30min'))),
                 len(global_events.get('fresh_sources',[]))/max(1,global_events.get('source_count',8)),1.]
        top_b=float(quote['raw']['bids'][0][1]);top_a=float(quote['raw']['asks'][0][1])
        baseline=[math.tanh(micro.get('price_move_bps',0)/5),(top_b-top_a)/(top_b+top_a+1e-12),math.tanh(spread/10),1.]
        x=baseline+micro.get('features',[0.]*8)+event_x
        vectors={'market_event':x,'without_flow':x[:6]+[0.]+x[7:],
                 'without_events':x[:12]+[0.]*4,'frozen':x}
        bank=self.state['banks'].setdefault(symbol,{'models':{k:Branch16().state() for k in KINDS},
            'scores':{k:{'n':0,'brier_sum':0.,'policy_n':0,'net_sum':0.,'net_sq':0.} for k in KINDS},'pending':None})
        models={k:Branch16(st) for k,st in bank['models'].items()}
        pending=bank['pending']
        if pending and at>=pending['due']:
            bank['pending']=None
            if at-pending['due']>30000:self.state['dropped']+=1
            elif mid!=pending['mid']:
                y=int(mid>pending['mid'])
                for k in KINDS:
                    p=pending['p'][k];s=bank['scores'][k];s['n']+=1;s['brier_sum']+=(p-y)**2
                    if k!='frozen':
                        cp,cache=models[k].predict(pending['x'][k]);models[k].learn(pending['x'][k],y,cp,cache)
                    direction=1 if p>=.55 else -1 if p<=.45 else 0
                    if direction:
                        net=((quote['bid']/pending['ask']-1) if direction==1 else (1-quote['ask']/pending['bid']))*10000-14
                        s['policy_n']+=1;s['net_sum']+=net;s['net_sq']+=net*net
        predictions={k:models[k].predict(vectors[k])[0] if k!='frozen' else .5 for k in KINDS}
        if bank['pending'] is None and micro.get('ready'):
            bank['pending']={'due':at+300000,'p':predictions,'x':vectors,'mid':mid,'bid':quote['bid'],'ask':quote['ask']}
        bank['models']={k:m.state() for k,m in models.items()}
        nodes=[]
        for k in KINDS:
            s=bank['scores'][k];n=s['policy_n'];mean=s['net_sum']/n if n else 0.
            var=max(0,(s['net_sq']-n*mean*mean)/(n-1)) if n>1 else 0.
            eligible=(k=='market_event' and n>=100 and mean-3*math.sqrt(var/n)>0 and s['brier_sum']/s['n']<.25)
            nodes.append({'id':'copernican:'+k,'p_up':predictions[k],'labels':s['n'],'eligible':eligible,
                          'weight':1. if eligible else 0.,'brier':s['brier_sum']/s['n'] if s['n'] else None})
        candidates=hypotheses(micro);candidate=candidates[0] if candidates else None
        prior=self.state['confirmations'].get(symbol)
        matching=bool(candidate and prior and prior['direction']==candidate['direction'] and prior['id']==candidate['id'] and 0<at-prior['at']<=20000)
        count=prior['n']+1 if matching else 1 if candidate else 0
        self.state['confirmations'][symbol]={'at':at,'n':count,'id':candidate['id'] if candidate else None,
                                            'direction':candidate['direction'] if candidate else 0}
        diag=base.get('diagnostics',{});event_fresh=bool(global_events.get('fresh_sources')) and 0<=at-global_events.get('at_ms',-100000)<=15000
        scheduled=bool(calendar.get('upcoming_30min'))
        event_veto=bool(global_events.get('entry_veto')) or scheduled
        context_ready=(micro.get('ready') and micro.get('mark_fresh') and micro.get('oi_fresh')
                       and 0<=at-micro.get('at_ms',-100000)<=15000)
        reason=('ORDERFLOW_INCOMPLETE_OR_STALE' if not context_ready else 'GLOBAL_CONTEXT_UNAVAILABLE' if not event_fresh else
                'EVENT_RISK_VETO' if event_veto else 'FUNDING_WINDOW_UNRECONCILED' if micro.get('funding_window_veto') else
                'MECHANISM_NOT_CONFIRMED' if not candidate or count<2 or candidate['strength']<.35 else
                'INSUFFICIENT_OBSERVATION' if diag.get('warmup_seconds',0)<60 else
                'RANGE_BELOW_COST_BUFFER' if diag.get('observed_range_bps',0)<diag.get('cost_buffer_bps',float('inf')) else
                'MECHANISM_EXPLORATION_CANDIDATE')
        action='HOLD' if position else 'OBSERVE';explore=False;exit_basis=None
        if position:
            # Opposing flow AND replenishment/depletion must persist; candle colors are irrelevant.
            if context_ready and candidate and candidate['direction']!=position['direction'] and count>=2 and candidate['strength']>=.45:
                action='CLOSE';reason='OPPOSING_FLOW_LIQUIDITY_CONFIRMED';exit_basis='FLOW_LIQUIDITY_REVERSAL'
            else:reason='POSITION_SUPPORTED_OR_REVERSAL_UNCONFIRMED'
        elif reason=='MECHANISM_EXPLORATION_CANDIDATE':
            action='OPEN_LONG' if candidate['direction']==1 else 'OPEN_SHORT';explore=True
        result={**base,'symbol':symbol,'at_ms':at,'horizon':300,'action':action,'reason':reason,'p_up':predictions['market_event'],'nodes':nodes,
            'diagnostics':{**diag,'directional_policy_samples':bank['scores']['market_event']['policy_n'],
                           'labels':bank['scores']['market_event']['n'],'baseline_labels':diag.get('labels',0)},
            'exploration_allowed':explore,'paper_only':True,'execution_enabled':False,
            'policy':POLICY,'exit_basis':exit_basis,'event_context_fresh':event_fresh,
            'mechanism_hypotheses':candidates,'mechanism_confirmations':count,
            'market_evidence':micro,'global_event_context':global_events,
            'maker_intent_known':False,'profitability_proven':False,
            'feature_quality':{'liquidation_unknown':not micro.get('liquidations_available'),
                               'global_coverage_incomplete':True,'trained_nodes_are_unvalidated':not any(n['eligible'] for n in nodes)},
            'shadow_champion':min((n for n in nodes if n['labels']>=20),key=lambda n:n['brier'])['id']
                 if any(n['labels']>=20 for n in nodes) else None}
        # No model validation is silently granted to experimental mechanism rules.
        return result
