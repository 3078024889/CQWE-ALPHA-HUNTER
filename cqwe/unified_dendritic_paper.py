"""Experimental 12-expert/four-family portfolio, plus delayed Branch16 learning.

Paper allocation is separate from validated research admission. No live orders.
"""
import copy
import hashlib
import math
from pathlib import Path
from .liquidity_research import Branch16
from .strategy_candidates import SYMBOLS

POLICY='UNIFIED_DENDRITIC_PAPER_V1'
FAMILIES=('vol_rsi','ts_momentum','residual_pair','cross_momentum')
IDS=tuple([f'{k}:{s}' for s in SYMBOLS for k in ('vol_rsi','ts_momentum')]+
          [f'residual_pair:{s}' for s in SYMBOLS if s!='BTCUSDT']+['cross_momentum:four'])


class UnifiedCouncil:
    def __init__(self,state=None):
        sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.state=copy.deepcopy(state) if state else {'source':sha,'banks':{},'signature':None,'since':None,'at':None,'dropped':0}
        if self.state['source']!=sha:raise ValueError('UNIFIED_SOURCE_CHANGED_ARCHIVE_REQUIRED')

    def decide(self,targets,history_hour,quotes,evidence,news,calendar,at,positions):
        valid=isinstance(targets,dict) and set(targets)==set(IDS) and history_hour==at//3600000
        targets=targets if valid else {k:{} for k in IDS}
        vectors={f:{s:0. for s in SYMBOLS} for f in FAMILIES}
        for f in FAMILIES:
            members=[k for k in IDS if k.startswith(f+':')]
            for key in members:
                if sum(abs(w) for w in targets[key].values())>1.0000001:raise ValueError('UNIFIED_GROSS_TARGET')
                for s,w in targets[key].items():
                    if s not in SYMBOLS or not math.isfinite(w) or abs(w)>1:raise ValueError('UNIFIED_BAD_TARGET')
                    vectors[f][s]+=w/len(members)
        weights={s:sum(v[s] for v in vectors.values())/4 for s in SYMBOLS}
        weights={s:w for s,w in weights.items() if abs(w)>.0001}
        gross=sum(abs(w) for w in weights.values())
        active=sum(any(abs(w)>1e-6 for w in v.values()) for v in vectors.values())
        neural={}
        for s in SYMBOLS:
            if s not in quotes:continue
            q=quotes[s];mid=(q['bid']+q['ask'])/2
            bank=self.state['banks'].setdefault(s,{'model':Branch16().state(),'pending':None,'n':0,'brier':0.})
            model=Branch16(bank['model']);p=bank['pending']
            if p and at>=p['due']:
                bank['pending']=None
                if at-p['due']>30000 or mid==p['mid'] or not 0<=at-q['observed_ms']<=10000:self.state['dropped']+=1
                else:
                    y=int(mid>p['mid']);bank['n']+=1;bank['brier']+=(p['p']-y)**2
                    model.learn(p['x'],y,p['p'],p['cache'])
            micro=evidence.get(s,{})
            x=[float(targets[k].get(s,0)) for k in IDS]+[
                max(-1.,min(1.,float(micro.get('flow',0)))),max(-1.,min(1.,float(micro.get('depletion',0)))),
                float(bool(news.get('entry_veto') or calendar.get('upcoming_30min'))),1.]
            prob,cache=model.predict(x)
            if valid and not bank['pending'] and 0<=at-q['observed_ms']<=10000:
                bank['pending']={'due':at+300000,'mid':mid,'x':x,'p':prob,'cache':cache}
            bank['model']=model.state()
            neural[s]={'p_up':prob,'labels':bank['n'],'updates':model.updates,'brier':bank['brier']/bank['n'] if bank['n'] else None,
                       'features':x,'branches':cache['branches'],'validated':False}
        signature=tuple((s,1 if weights[s]>0 else -1) for s in sorted(weights))
        prior=self.state
        # JSON roundtrips turn tuples into lists; store a canonical string.
        import json
        sig=json.dumps(signature,separators=(',',':'))
        continuous=sig==prior.get('signature') and prior.get('at') is not None and 0<at-prior['at']<=20000
        since=prior['since'] if continuous else at
        prior.update(signature=sig,since=since,at=at)
        duration=at-since
        fresh=all(s in quotes and 0<=at-quotes[s]['observed_ms']<=10000 and
                  evidence.get(s,{}).get('ready') and evidence[s].get('mark_fresh') and evidence[s].get('oi_fresh')
                  and 0<=at-evidence[s].get('at_ms',-100000)<=15000 for s in weights)
        news_fresh=bool(news.get('fresh_sources')) and 0<=at-news.get('at_ms',-100000)<=15000
        veto=bool(news.get('entry_veto') or calendar.get('upcoming_30min'))
        funding=any(evidence.get(s,{}).get('funding_window_veto') for s in weights)
        reason=('CANDIDATE_HISTORY_UNAVAILABLE' if not valid else 'NO_ACTIVE_EXPERTS' if not weights or gross<.05 else
                'FAMILY_QUORUM_MISSING' if active<2 else 'ENSEMBLE_MARKET_DATA_STALE' if not fresh else
                'ENSEMBLE_EVENT_CONTEXT_STALE' if not news_fresh else 'ENSEMBLE_EVENT_VETO' if veto else
                'ENSEMBLE_FUNDING_VETO' if funding else 'ENSEMBLE_PERSISTENCE_WAIT' if duration<90000 else
                'ENSEMBLE_PAPER_CANDIDATE')
        action='OPEN_BASKET' if reason=='ENSEMBLE_PAPER_CANDIDATE' else 'OBSERVE'
        if positions:
            opposite=any(s in weights and weights[s]*p['direction']<0 for s,p in positions.items())
            supported=any(s in weights and weights[s]*p['direction']>0 for s,p in positions.items())
            close=valid and fresh and duration>=60000 and (opposite or not supported)
            action='CLOSE_BASKET' if close else 'HOLD_BASKET'
            reason='ENSEMBLE_DIRECTION_CHANGED' if close else 'ENSEMBLE_HOLD'
        return {'policy':POLICY,'at_ms':at,'action':action,'reason':reason,'weights':weights,'gross_weight':gross,
                'margin_budget_fraction':.05,'active_families':active,'duration_ms':duration,
                'families':vectors,'experts':copy.deepcopy(targets),'neural':neural,
                'event_veto':veto,'paper_only':True,'real_orders_enabled':False,'profitability_proven':False,
                'neural_role':'learning_only_until_independent_validation','research_qualification_granted':False}
