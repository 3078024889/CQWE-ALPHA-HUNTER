"""Low-frequency public depth5 dendritic learner; paper qualification only."""
import copy
import hashlib
import math
from pathlib import Path
from .liquidity_research import Branch16


class PaperObserver:
    def __init__(self,previous=None):
        source=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.state=copy.deepcopy(previous) if previous else {'source':source,'banks':{},'last':{},'dropped':0}
        if self.state['source']!=source:raise ValueError('盘口学习代码已更新，请使用新的研究目录')

    def frame(self,symbol,quote,at):
        if not quote or not 0<=at-quote['observed_ms']<=10000:return None
        bid,ask=quote['bid'],quote['ask'];mid=(bid+ask)/2
        raw=quote['raw'];bids=raw['bids'];asks=raw['asks']
        bq=sum(float(q) for _,q in bids);aq=sum(float(q) for _,q in asks)
        top_b,top_a=float(bids[0][1]),float(asks[0][1])
        last=self.state['last'].get(symbol)
        move=math.tanh(math.log(mid/last['mid'])*1000) if last and 0<at-last['at']<=15000 else 0.
        # Four observable depth/price features; other compartments explicitly zero.
        x=[move,(bq-aq)/(bq+aq+1e-12),math.tanh((ask-bid)/mid*1000),
           (top_b-top_a)/(top_b+top_a+1e-12)]+[0.]*12
        bank=self.state['banks'].setdefault(symbol,{'model':Branch16().state(),'pending':None,
            'n':0,'brier_sum':0.,'policy_n':0,'net_sum':0.,'net_sq':0.})
        model=Branch16(bank['model']);pending=bank['pending']
        if pending and at>=pending['due']:
            bank['pending']=None
            if at-pending['due']>30000:self.state['dropped']+=1
            elif mid!=pending['mid']:
                y=int(mid>pending['mid']);p=pending['p'];bank['n']+=1;bank['brier_sum']+=(p-y)**2
                cp,cache=model.predict(pending['x']);model.learn(pending['x'],y,cp,cache)
                direction=1 if p>=.55 else -1 if p<=.45 else 0
                if direction:
                    net=((bid/pending['ask']-1) if direction==1 else (1-ask/pending['bid']))*10000-14
                    bank['policy_n']+=1;bank['net_sum']+=net;bank['net_sq']+=net*net
        p=model.predict(x)[0]
        if bank['pending'] is None:
            bank['pending']={'due':at+300000,'x':x,'p':p,'mid':mid,'bid':bid,'ask':ask}
        bank['model']=model.state();self.state['last'][symbol]={'at':at,'mid':mid}
        n=bank['policy_n'];mean=bank['net_sum']/n if n else 0.
        var=max(0,(bank['net_sq']-n*mean*mean)/(n-1)) if n>1 else 0.
        ready=n>=100 and mean-3*math.sqrt(var/n)>0 and bank['brier_sum']/bank['n']<.25
        action='OPEN_LONG' if ready and p>=.55 else 'OPEN_SHORT' if ready and p<=.45 else 'OBSERVE'
        return {'symbol':symbol,'at_ms':at,'horizon':300,'p_up':p,'action':action,
            'reason':'QUALIFIED_PAPER_NODE' if ready else 'INSUFFICIENT_PAST_EVIDENCE',
            'nodes':[{'id':'depth5:dendritic','p_up':p,'labels':bank['n'],'eligible':ready,'weight':1. if ready else 0.}],
            'execution_enabled':False,'paper_advisory_only':True,'profitability_proven':False,
            'limitations':'5-second REST sampling; incomplete orderflow; funding and size impact absent; selection not corrected'}
