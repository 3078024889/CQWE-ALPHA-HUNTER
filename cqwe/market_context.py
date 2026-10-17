"""Closed-bar price regime and explicitly hypothetical liquidation scenarios.

No inference of private stops, trader identities, leverage, or outstanding USD.
The scenario surface is a research display, never an entry authorization.
"""
import hashlib
import json
import math


def build_context(rows, at):
    bars=[]
    for r in rows:
        if int(r[6])>=at:continue
        o,h,l,c,v=map(float,(r[1],r[2],r[3],r[4],r[5]))
        if not all(math.isfinite(x) and x>0 for x in (o,h,l,c)) or not math.isfinite(v) or v<0 or not l<=min(o,c)<=max(o,c)<=h:
            raise ValueError('INVALID_CONTEXT_BAR')
        bars.append((int(r[0]),o,h,l,c,v,int(r[6])))
    if len(bars)<32 or any(b[0]-a[0]!=900000 for a,b in zip(bars,bars[1:])):
        return {'ready':False,'reason':'MISSING_OR_GAPPED_15M_HISTORY','at_ms':at}
    if not 0<at-bars[-1][6]<=930000:
        return {'ready':False,'reason':'STALE_15M_HISTORY','at_ms':at}
    closes=[b[4] for b in bars];last=closes[-1]
    r1=math.log(last/closes[-5])*10000;r4=math.log(last/closes[-17])*10000
    returns=[math.log(b/a)*10000 for a,b in zip(closes[-33:],closes[-32:])]
    vol=math.sqrt(sum(r*r for r in returns)/len(returns))
    # Fixed research thresholds, not a fitted claim of profitable expected return.
    direction=1 if r1>max(10,vol) and r4>max(20,2*vol) else -1 if r1<-max(10,vol) and r4<-max(20,2*vol) else 0
    bins={}
    for i,bar in enumerate(bars):
        entry=(bar[2]+bar[3]+bar[4])/3
        for leverage in (10,25,50):
            for maintenance in (.005,.01):
                for side in (1,-1):
                    level=entry*(1-side*(1/leverage-maintenance))
                    # OHLC cannot reveal within-bar order. Exclude the entry bar;
                    # conservatively discard any subsequently crossed scenario.
                    if (side==1 and any(b[3]<=level for b in bars[i+1:])) or (side==-1 and any(b[2]>=level for b in bars[i+1:])):continue
                    if (side==1 and level>=last) or (side==-1 and level<=last):continue
                    bucket=round(math.log(level/last)/.001)
                    key=(side,bucket)
                    bins[key]=bins.get(key,0.)+bar[5]*math.exp(-(len(bars)-1-i)/32)/6
    maximum=max(bins.values(),default=1.) or 1.
    zones=sorted(({'price':last*math.exp(bucket*.001),'side':'LONG_SCENARIO' if side==1 else 'SHORT_SCENARIO',
                   'relative_intensity':value/maximum} for (side,bucket),value in bins.items()),key=lambda z:z['relative_intensity'],reverse=True)[:12]
    return {'ready':True,'at_ms':at,'available_after_ms':bars[-1][6]+1,'bar_close_ms':bars[-1][6],
            'source_sha256':hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest(),
            'regime':{'direction':direction,'return_1h_bps':r1,'return_4h_bps':r4,'volatility_15m_bps':vol,
                      'kind':'PRICE_REGIME_NOT_MACRO_FORECAST','profitability_proven':False},
            'liquidation_scenarios':{'zones':zones,'kind':'MODEL_RELATIVE_INTENSITY_NOT_DOLLARS','execution_weight':0,
                'assumptions':{'leverage':[10,25,50],'maintenance':[.005,.01],'equal_scenario_weights':True,
                               'entries':'historical typical price','volume_is_not_open_interest':True},
                'private_stops_known':False,'actual_liquidation_prices_known':False}}


class ContextCache:
    def __init__(self,fetch):self.fetch=fetch;self.cache={};self.attempts={}

    def get(self,symbol,at,refresh=True):
        if refresh and at-self.attempts.get(symbol,-300000)>=300000:
            self.attempts[symbol]=at
            try:self.cache[symbol]=build_context(self.fetch('klines',{'symbol':symbol,'interval':'15m','limit':100}),at)
            except Exception as exc:
                # Do not refresh a failed cache's age or silently reuse a good regime.
                self.cache[symbol]={'ready':False,'at_ms':at,'reason':'CONTEXT_FETCH_FAILED','error':str(exc)[:200]}
        result=self.cache.get(symbol,{'ready':False,'reason':'CONTEXT_UNAVAILABLE'})
        if not 0<=at-result.get('at_ms',-1000000)<=600000:
            return {'ready':False,'reason':'CONTEXT_EXPIRED','at_ms':at}
        return result
