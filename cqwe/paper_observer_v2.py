"""Causal five-minute learning and explicitly unvalidated paper exploration."""
import copy
import hashlib
import math
from pathlib import Path
from .liquidity_research import Branch16

LEGACY_SOURCE='b56bc08cea34a067e1a9ea87140a13d861717063f9cbf84fc19a5f8694437ff4'


class ActiveBranch(Branch16):
    def predict(self,x):
        super().predict(x)
        u=[v+.1*m for v,m in zip(x,self.memory)]
        branch=math.tanh(sum(self.weights[j]*u[j] for j in range(4)))
        return [1/(1+math.exp(-branch)),{'u':u,'branch':branch}]

    def learn(self,x,y,p,cache):
        for j in range(4):
            gradient=(y-p)*(1-cache['branch']**2)*cache['u'][j]
            self.weights[j]=max(-1.,min(1.,self.weights[j]+.03*gradient))
            self.memory[j]=.95*self.memory[j]+.05*x[j]*(2*y-1)
        self.updates+=1


class PaperObserver:
    def __init__(self,previous=None):
        source=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.state=copy.deepcopy(previous) if previous else {'source':source,'banks':{},'last':{},'dropped':0}
        if self.state['source']!=source:raise ValueError('盘口学习代码已更新，请先归档并迁移研究阶段')

    @classmethod
    def migrate_legacy(cls,previous):
        if previous['source']!=LEGACY_SOURCE:raise ValueError('UNRECOGNIZED_LEGACY_SOURCE')
        result=cls()
        result.state['migration']={'from_source':LEGACY_SOURCE,'warm_weights_only':True,
            'validation_scores_reset':True,'previous_labels':{s:b['n'] for s,b in previous['banks'].items()}}
        for s,bank in previous['banks'].items():
            result.state['banks'][s]=result.bank(ActiveBranch(bank['model']).state())
        return result

    @staticmethod
    def bank(model=None):
        return {'model':model or ActiveBranch().state(),'pending':None,'n':0,'directional_n':0,
                'brier_sum':0.,'policy_n':0,'net_sum':0.,'net_sq':0.,'trail':[],
                'classes':{'UP':0,'DOWN':0,'FLAT':0},'last_exploration_ms':None}

    def frame(self,symbol,quote,at):
        if not quote or not 0<=at-quote['observed_ms']<=10000:return None
        bid,ask=quote['bid'],quote['ask'];mid=(bid+ask)/2
        bids=quote['raw']['bids'];asks=quote['raw']['asks']
        bq=sum(float(q) for _,q in bids);aq=sum(float(q) for _,q in asks)
        top_b,top_a=float(bids[0][1]),float(asks[0][1])
        last=self.state['last'].get(symbol)
        if last and at<last['at']:raise ValueError('OBSERVER_CLOCK_REVERSED')
        move=math.tanh(math.log(mid/last['mid'])*1000) if last and 0<at-last['at']<=15000 else 0.
        x=[move,(bq-aq)/(bq+aq+1e-12),math.tanh((ask-bid)/mid*1000),
           (top_b-top_a)/(top_b+top_a+1e-12)]+[0.]*12
        bank=self.state['banks'].setdefault(symbol,self.bank())
        model=ActiveBranch(bank['model']);pending=bank['pending']
        if pending and at>=pending['due']:
            bank['pending']=None
            if at-pending['due']>30000:self.state['dropped']+=1
            else:
                bank['n']+=1
                ret=(mid/pending['mid']-1)*10000;band=pending['flat_band_bps']
                bank['classes']['UP' if ret>band else 'DOWN' if ret<-band else 'FLAT']+=1
                if mid!=pending['mid']:
                    y=int(mid>pending['mid']);p=pending['p'];bank['directional_n']+=1;bank['brier_sum']+=(p-y)**2
                    cp,cache=model.predict(pending['x']);model.learn(pending['x'],y,cp,cache)
                    direction=1 if p>=.55 else -1 if p<=.45 else 0
                    if direction:
                        net=((bid/pending['ask']-1) if direction==1 else (1-ask/pending['bid']))*10000-14
                        bank['policy_n']+=1;bank['net_sum']+=net;bank['net_sq']+=net*net
        p=model.predict(x)[0];spread=(ask-bid)/mid*10000
        if bank['pending'] is None:
            bank['pending']={'due':at+300000,'x':x,'p':p,'mid':mid,'bid':bid,'ask':ask,'flat_band_bps':14+spread}
        bank['model']=model.state();self.state['last'][symbol]={'at':at,'mid':mid}
        n=bank['policy_n'];mean=bank['net_sum']/n if n else 0.
        var=max(0,(bank['net_sq']-n*mean*mean)/(n-1)) if n>1 else 0.
        ready=n>=100 and mean-3*math.sqrt(var/n)>0 and bank['brier_sum']/bank['directional_n']<.25
        # Recent range is an experimental filter, never claimed as expected profit.
        trail=bank['trail']
        if last and at-last['at']>15000:trail=[]
        trail=[v for v in trail if at-v['at']<=300000]
        if not trail or trail[-1]['at']!=at:trail.append({'at':at,'mid':mid})
        bank['trail']=trail[-90:]
        span=at-trail[0]['at'];movement=(mid/trail[0]['mid']-1)*10000
        observed_range=(max(v['mid'] for v in trail)-min(v['mid'] for v in trail))/trail[0]['mid']*10000
        floor=14+spread+4
        reason=('EXPLORATION_WARMUP' if span<60000 else 'RANGE_BELOW_COST_BUFFER' if observed_range<floor else
                'FLAT_OR_WEAK_TREND' if abs(movement)<8 else
                'EXPLORATION_CADENCE' if bank['last_exploration_ms'] is not None and at-bank['last_exploration_ms']<600000 else
                'EXPLORATION_CANDIDATE')
        exploration=not ready and reason=='EXPLORATION_CANDIDATE'
        action=('OPEN_LONG' if p>=.55 else 'OPEN_SHORT' if p<=.45 else 'OBSERVE') if ready else (
                'OPEN_LONG' if movement>0 else 'OPEN_SHORT') if exploration else 'OBSERVE'
        return {'symbol':symbol,'at_ms':at,'horizon':300,'p_up':p,'action':action,
            'reason':'QUALIFIED_PAPER_NODE' if ready else reason,'exploration_allowed':exploration,'paper_only':True,
            'forecast_class':'UP' if p>=.55 else 'DOWN' if p<=.45 else 'UNCERTAIN',
            'diagnostics':{'labels':bank['n'],'directional_policy_samples':n,'required_policy_samples':100,
                'probability_gate':'.55/.45','warmup_seconds':span/1000,'observed_range_bps':observed_range,
                'cost_buffer_bps':floor,'observed_move_bps':movement,'classes':bank['classes'].copy(),
                'next_label_ms':bank['pending']['due'],'exploration_is_validated':False},
            'nodes':[{'id':'depth5:active_dendritic','p_up':p,'labels':bank['n'],'eligible':ready,'weight':1. if ready else 0.}],
            'execution_enabled':False,'paper_advisory_only':True,'profitability_proven':False,
            'limitations':'REST depth5; exploration unvalidated; funding and size impact absent; selection not corrected'}
