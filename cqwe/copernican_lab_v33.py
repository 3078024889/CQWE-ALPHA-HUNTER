"""Bounded Copernican dendrite experiments. Research ONLY, NO auto-promotion.
Five independent axes (6 choices each) are functional, not just labels.
Chronological train/validation/sealed holdout. No executable account PnL claim.
"""
import argparse, hashlib, json, math
from pathlib import Path

TOPOLOGIES=('ring','chain','star','cross','cluster','skip')
RESPONSES=('coincidence','linear','threshold','sign','context','saturation')
PLASTICITY=('local_error','hebb','oja','three_factor','eligibility_trace','anti_correlation')
MEMORY=('none','recent','surprise','context','association','consolidation')
META=('fixed','error_slope','surprise','forgetting','branch_switch','confidence')
AXES={'topology':TOPOLOGIES,'response':RESPONSES,'plasticity':PLASTICITY,'memory':MEMORY,'meta':META}
RESEARCH_ONLY=True

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def specs():
    # Prespecified six contrasting genotypes; 6^5 is a SEARCH SPACE, NOT 7776 runs.
    return [dict(zip(AXES,(v[i] for v in AXES.values()))) for i in range(6)]

def links(t):
    if t=='ring':return ((0,1),(1,2),(2,3),(3,0))
    if t=='chain':return ((0,1),(1,2),(2,3))
    if t=='star':return ((0,1),(0,2),(0,3))
    if t=='cross':return ((0,3),(1,2),(0,2),(1,3))
    if t=='cluster':return ((0,1),(2,3))
    if t=='skip':return ((0,2),(1,3))
    raise ValueError('UNKNOWN_TOPOLOGY')

def respond(kind,x,ctx):
    if kind=='linear':return x
    if kind=='threshold':return 1. if x>.20 else -1. if x<-.20 else 0.
    if kind=='sign':return 1. if x>0 else -1. if x<0 else 0.
    if kind=='saturation':return math.tanh(x*2)
    if kind=='context':return x*(1 if ctx>=0 else -.5)
    if kind=='coincidence':return x if (x*ctx)>0 else 0.
    raise ValueError('UNKNOWN_RESPONSE')

def features(bars,i):
    # 4 bounded causal features, using ONLY candles <= i.
    price=float(bars[i][4]);prev=float(bars[i-1][4]);older=float(bars[i-4][4])
    if min(price,prev,older)<=0:raise ValueError('BAD_PRICE')
    vol=float(bars[i][7]);volprev=float(bars[i-1][7]);
    high=float(bars[i][2]);low=float(bars[i][3]);
    return [math.tanh(100*(price/prev-1)),math.tanh(30*(price/older-1)),
            math.tanh(math.log(max(vol,1e-8)/max(volprev,1e-8))/4),
            math.tanh(15*((price-low)/max(high-low,1e-10)-.5))]

class Dendrite:
    def __init__(self,spec):
        if set(spec)!=set(AXES) or any(spec[k] not in AXES[k] for k in AXES):raise ValueError('INVALID_GENOTYPE')
        self.spec=spec;self.w=[.15,-.10,.05,.08];self.trace=[0.]*4;self.memory=[0.]*4
        self.prev_error=0.;self.updates=0;self.ctx=0.
    def forward(self,x):
        value=list(x)
        for a,b in links(self.spec['topology']):
            value[b]=max(-2.,min(2.,value[b]+.20*x[a]))
        ctx=x[1]
        m=self.spec['memory']
        if m!='none':
            factor={'recent':.25,'surprise':.12,'context':.3 if ctx>=0 else .1,'association':.2,'consolidation':.4}.get(m,0.)
            value=[max(-2.,min(2.,v+factor*mv)) for v,mv in zip(value,self.memory)]
        response=[respond(self.spec['response'],v,ctx) for v in value]
        activation=sum(w*r for w,r in zip(self.w,response))
        self.ctx=ctx
        return math.tanh(activation),response
    def update(self,response,label,pred,x):
        err=label-pred
        m=self.spec['meta']
        rate={'fixed':.01,'error_slope':.01+min(.025,abs(err-self.prev_error)*.01),
              'surprise':.01+min(.025,abs(err)*.01),
              'forgetting':.015 if self.updates%64<32 else .006,
              'branch_switch':.015 if self.ctx<0 else .008,
              'confidence':.005 if abs(pred)>.25 else .02}[m]
        p=self.spec['plasticity']
        for i,r in enumerate(response):
            if p=='local_error':delta=err*r
            elif p=='hebb':delta=pred*r
            elif p=='oja':delta=pred*r-pred*pred*self.w[i]
            elif p=='three_factor':delta=err*r*(1 if abs(label)>.5 else .25)
            elif p=='eligibility_trace':
                self.trace[i]=.80*self.trace[i]+r
                delta=err*self.trace[i]
            else:delta=-pred*r
            self.w[i]=max(-1.,min(1.,self.w[i]+rate*delta))
        memory_kind=self.spec['memory']
        decay={'none':0.,'recent':.7,'surprise':.8,'context':.85,'association':.75,'consolidation':.96}[memory_kind]
        for i,v in enumerate(x):
            update=v
            if memory_kind=='surprise':update=v*min(1.,abs(err))
            if memory_kind=='association':update=v*label
            self.memory[i]=max(-2.,min(2.,decay*self.memory[i]+(1-decay)*update))
        self.prev_error=err;self.updates+=1

def candles(path):
    raw=Path(path).read_bytes(); rows=json.loads(raw.decode('utf-8-sig'))
    if not isinstance(rows,list) or len(rows)<120:raise ValueError('INSUFFICIENT_HISTORY')
    old=None
    for r in rows:
        if not isinstance(r,list) or len(r)<12:raise ValueError('INVALID_KLINE_SCHEMA')
        ts=int(r[0]);
        if old is not None and ts-old!=300000:raise ValueError('NONCONTIGUOUS_HISTORY')
        old=ts
    return rows,hashlib.sha256(raw).hexdigest()

def score(rows,model,start,end,learn):
    outcomes=[];correct=0;entered=0
    for i in range(max(start,4),end):
        x=features(rows,i);pred,response=model.forward(x)
        result=float(rows[i+1][4])/float(rows[i][4])-1
        label=1. if result>0 else -1. if result<0 else 0.
        # per-event long-only mark-to-close proxy, NOT a trade or account PnL.
        if pred>.08:
            entered+=1
            outcomes.append(result-.0014) # fixed illustrative round-trip friction 14bps
        correct+=int((pred>0)==(result>0))
        if learn:model.update(response,label,pred,x)
    n=end-max(start,4)
    return {'observations':n,'positive_predictions':entered,
            'directional_hit_fraction':round(correct/n,8) if n else None,
            'mean_cost_adjusted_event_proxy':round(sum(outcomes)/len(outcomes),10) if outcomes else None}

def evaluate(paths,output):
    if len(paths)!=4:raise ValueError('FOUR_MARKETS_REQUIRED')
    sources={};markets={}
    for p in paths:
        symbol=Path(p).name.split('_')[0]
        if symbol in markets:raise ValueError('DUPLICATE_MARKET')
        markets[symbol],sources[symbol]=candles(p)
    if set(markets)!={'BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT'}:raise ValueError('MARKET_SET_MISMATCH')
    if len({len(v) for v in markets.values()})!=1:raise ValueError('UNALIGNED_LENGTH')
    n=len(next(iter(markets.values())));t=int((n-1)*.60);v=int((n-1)*.80)
    results=[]
    for spec in specs():
        run=[]
        for symbol,rows in sorted(markets.items()):
            model=Dendrite(spec)
            train=score(rows,model,4,t,True)
            val=score(rows,model,t,v,False)
            test=score(rows,model,v,n-1,False)
            run.append({'symbol':symbol,'train':train,'validation':val,'sealed_holdout':test})
        results.append({'genotype':spec,'markets':run})
    report={'version':'V33_COPERNICAN_BOUNDED_RESEARCH','research_only':True,'no_orders':True,
            'no_autopromotion':True,'historical_data_previously_researched':True,
            'independent_out_of_sample_claim':False,'account_pnl_available':False,
            'mechanism_axes':{k:list(v) for k,v in AXES.items()},
            'total_possible_combinations':6**5,'evaluated_predeclared_candidates':len(results),
            'chronological_split':{'train_stop_index':t,'validation_stop_index':v,'length':n},
            'source_sha256':sources,'candidates':results,
            'warning':'Event proxies are overlapping/non-executable, not realized PnL; historical data were previously inspected.'}
    report['sha256']=digest(report)
    target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if json.loads(target.read_text(encoding='utf8'))!=report:raise ValueError('REFUSE_OVERWRITE_CHANGED_EVIDENCE')
    else:target.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',nargs='+',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();r=evaluate(a.inputs,a.output)
    print('CQWE_V33_DENDRITE_RESEARCH_PASS candidates=',len(r['candidates']),'observed_markets=',len(r['source_sha256']))
    print('HISTORICAL RESEARCH ONLY | NO INDEPENDENT PROFIT CLAIM | NO ORDERS')
if __name__=='__main__':main()
