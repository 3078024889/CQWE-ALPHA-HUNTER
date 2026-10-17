"""Observable liquidity and sampled liquidation research, not trader-intent inference.

No public book reveals the complete conditional-order book. Force-order snapshots
are sampled; their observed notional is not total exchange liquidation volume.
"""
import collections
import copy
import datetime
import json
import math
from decimal import Decimal as D
from urllib.parse import urlencode
from urllib.request import urlopen

from .copernican_experiment_v81_v85 import digest
from .futures_orderbook import number

SYMBOLS = ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT')


def open_interest(symbol):
    if symbol not in SYMBOLS:
        raise ValueError('UNSUPPORTED_PUBLIC_OI_SYMBOL')
    url = 'https://fapi.binance.com/fapi/v1/openInterest?'+urlencode({'symbol':symbol})
    with urlopen(url,timeout=6) as response:
        raw = response.read(100001)
    if len(raw)>100000:
        raise ValueError('OPEN_INTEREST_RESPONSE_BUDGET')
    obj = json.loads(raw)
    if obj.get('symbol')!=symbol:
        raise ValueError('OPEN_INTEREST_SYMBOL')
    number(obj['openInterest'])
    return obj


def fresh(at, now, ms):
    return at is not None and 0 <= now-at <= ms*1_000_000


class LiquidityTape:
    def __init__(self, previous=None):
        self.data = {s:{'previous':None,'trades':[],'last_trade_id':-1,'range':[], 'liquidations':[], 'seen':[],
                        'mark':None,'oi':None,'oi_change':0.,'counters':{'liquidations':0,'marks':0,'oi':0},
                        'last_signals':None} for s in SYMBOLS}
        if previous is not None:
            if set(previous)!=set(SYMBOLS):
                raise ValueError('LIQUIDITY_STATE_SYMBOLS')
            self.data = copy.deepcopy(previous)

    def trade(self,symbol,event,received_ns):
        if event.get('s')!=symbol or type(event.get('m')) is not bool:
            raise ValueError('LIQUIDITY_TRADE_LAYOUT')
        if type(event.get('a')) is not int or event['a']<0:
            raise ValueError('LIQUIDITY_TRADE_ID')
        d=self.data[symbol]
        if event['a']<=d['last_trade_id']:
            return
        price,qty = number(event['p'],positive=True),number(event['q'],positive=True)
        notional = float(price*qty)
        if not math.isfinite(notional):
            raise ValueError('LIQUIDITY_TRADE_OVERFLOW')
        d['last_trade_id']=event['a']
        d['trades'].append([received_ns,-notional if event['m'] else notional])
        d['trades']=d['trades'][-5000:]

    def context(self,kind,symbol,event,received_ns):
        d=self.data[symbol]
        if kind=='MARK':
            if (event.get('e')!='markPriceUpdate' or event.get('s')!=symbol
                    or type(event.get('E')) is not int or event['E']<0):
                raise ValueError('INVALID_MARK_EVENT')
            mark,index=number(event['p'],positive=True),number(event['i'],positive=True)
            rate=D(event['r'])
            if not rate.is_finite() or abs(rate)>1 or type(event.get('T')) is not int or event['T']<0:
                raise ValueError('INVALID_FUNDING_CONTEXT')
            d['mark']={'received_ns':received_ns,'mark':str(mark),'index':str(index),
                       'funding_rate':str(rate),'next_funding_ms':event['T'],'exchange_ms':event['E']}
            d['counters']['marks']+=1
        elif kind=='OI':
            if event.get('symbol')!=symbol or type(event.get('time')) is not int or event['time']<0:
                raise ValueError('INVALID_OPEN_INTEREST')
            value=number(event['openInterest'])
            old=d['oi']
            change=math.tanh(float(value/D(old['value'])-1)*100) if old and D(old['value']) else 0.
            d['oi_change']=change
            d['oi']={'received_ns':received_ns,'value':str(value),'exchange_ms':event['time']}
            d['counters']['oi']+=1
        elif kind=='LIQUIDATION':
            order=event.get('o',{})
            if (event.get('e')!='forceOrder' or order.get('s')!=symbol or order.get('S') not in ('BUY','SELL')
                    or type(order.get('T')) is not int or order['T']<0):
                raise ValueError('INVALID_LIQUIDATION_EVENT')
            # Do not count original size q, or repeatedly sum cumulative quantity z.
            last_qty=number(order['l'])
            cumulative=number(order['z'])
            if last_qty>cumulative:
                raise ValueError('LIQUIDATION_FILL_QUANTITY')
            avg=number(order['ap'],positive=last_qty>0)
            ident=digest(event)
            if ident in d['seen']:
                return
            observed=float(last_qty*avg)
            if not math.isfinite(observed):
                raise ValueError('LIQUIDATION_OVERFLOW')
            d['seen']=(d['seen']+[ident])[-4096:]
            # BUY liquidates a short; SELL liquidates a long. No prediction implied.
            d['liquidations'].append([received_ns,observed if order['S']=='BUY' else -observed])
            d['liquidations']=d['liquidations'][-2000:]
            d['counters']['liquidations']+=1
        else:
            raise ValueError('UNKNOWN_LIQUIDITY_CONTEXT')

    def invalidate(self,symbol):
        d=self.data[symbol]
        for name in ('trades','range','liquidations'):
            d[name]=[]
        d['previous']=None
        d['last_signals']=None

    def invalidate_context(self,symbol):
        self.data[symbol]['mark']=None
        self.data[symbol]['oi']=None

    def sample(self,symbol,view,now_ns,at_ms=None):
        d=self.data[symbol]
        d['trades']=[r for r in d['trades'] if now_ns-10_000_000_000<=r[0]<=now_ns]
        d['liquidations']=[r for r in d['liquidations'] if now_ns-30_000_000_000<=r[0]<=now_ns]
        d['range']=[r for r in d['range'] if now_ns-60_000_000_000<=r[0]<=now_ns]
        bids={str(D(p).normalize()):float(q) for p,q in view.get('liquidity_bids',view['bids'])}
        asks={str(D(p).normalize()):float(q) for p,q in view.get('liquidity_asks',view['asks'])}
        previous=d['previous']
        depletion=refill=0.
        if previous:
            # Compare only the intersection of fully observed price ranges. Missing
            # prices inside that intersection are known zero; outside it are unknown.
            removed,added=[],[]
            for name,side in (('bids',bids),('asks',asks)):
                old=previous[name]
                boundary=max(min(map(D,side)),min(map(D,old))) if name=='bids' else min(max(map(D,side)),max(map(D,old)))
                observable=[p for p in side.keys() | old.keys() if (D(p)>=boundary if name=='bids' else D(p)<=boundary)]
                removed.append(sum(max(0.,old.get(p,0.)-side.get(p,0.)) for p in observable))
                added.append(sum(max(0.,side.get(p,0.)-old.get(p,0.)) for p in observable))
            scale=sum(bids.values())+sum(asks.values())+sum(previous['bids'].values())+sum(previous['asks'].values())
            depletion=(removed[1]-removed[0])/max(scale,1e-12)
            refill=(added[0]-added[1])/max(scale,1e-12)
        mid=float(number(view['mid'],positive=True))
        total_depth=sum(float(p)*q for p,q in bids.items())+sum(float(p)*q for p,q in asks.items())
        trades=[r[1] for r in d['trades']]
        flow=sum(trades)/sum(abs(v) for v in trades) if trades else 0.
        # Only earlier observations define the candidate range; no future extrema.
        past=[r[1] for r in d['range']]
        breakout=0.
        if len(past)>=10:
            high,low=max(past),min(past)
            breakout=math.tanh((mid/high-1)*10000/5) if mid>high else math.tanh((mid/low-1)*10000/5) if mid<low else 0.
        liq=[r[1] for r in d['liquidations']]
        liq_total=sum(abs(v) for v in liq)
        liq_signed=sum(liq)/liq_total if liq_total else 0.
        mark=d['mark']
        mark_ok=bool(mark and fresh(mark['received_ns'],now_ns,3000))
        oi_ok=bool(d['oi'] and fresh(d['oi']['received_ns'],now_ns,65000))
        if at_ms is not None:
            mark_ok=mark_ok and -2000<=at_ms-mark['exchange_ms']<=3000
            oi_ok=oi_ok and -2000<=at_ms-d['oi']['exchange_ms']<=65000
        basis=math.tanh(float(D(mark['mark'])/D(mark['index'])-1)*10000/10) if mark_ok else 0.
        x=[depletion,refill,flow,breakout,liq_signed,math.tanh(liq_total/max(total_depth,1e-12)),
           basis,d['oi_change'] if oi_ok else 0.]
        if not all(math.isfinite(v) and abs(v)<=1 for v in x):
            raise ValueError('INVALID_LIQUIDITY_FEATURE')
        quality={'mark_fresh':mark_ok,'open_interest_fresh':oi_ok,
                 'context_ready':mark_ok and oi_ok,'sampled_liquidations_only':True,
                 'stop_orders_visible':False,'cancellation_vs_execution_identified':False}
        d['range'].append([now_ns,mid]);d['range']=d['range'][-1200:]
        d['previous']={'bids':bids,'asks':asks}
        d['last_signals']={'features':x,'quality':quality,'mid':mid,
                           'observed_prior_high':max(past) if past else None,'observed_prior_low':min(past) if past else None,
                           'visible_bid_levels':sorted([[p,q] for p,q in bids.items()],key=lambda r:float(r[0])*r[1],reverse=True)[:3],
                           'visible_ask_levels':sorted([[p,q] for p,q in asks.items()],key=lambda r:float(r[0])*r[1],reverse=True)[:3],
                           'inferred_stop_locations':False,'maker_identity_known':False}
        return x,quality

    def entry_guard(self,symbol,at_ms,horizon,now_ns):
        mark=self.data[symbol]['mark']
        if not mark or not fresh(mark['received_ns'],now_ns,3000):
            return 'MARK_AND_FUNDING_CONTEXT_UNAVAILABLE'
        if mark['next_funding_ms'] <= at_ms+horizon*1000:
            return 'UNRECONCILED_FUNDING_WINDOW'
        return None

    def state(self):
        return copy.deepcopy(self.data)


class Branch16:
    def __init__(self,previous=None):
        self.weights=[.03,-.02,.02,.01]*4
        self.memory=[0.]*16
        self.updates=0
        if previous:
            if set(previous)!=set(vars(self)) or type(previous['updates']) is not int or previous['updates']<0:
                raise ValueError('BRANCH16_STATE')
            for name in ('weights','memory'):
                if len(previous[name])!=16 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1 for v in previous[name]):
                    raise ValueError('BRANCH16_PARAMETERS')
            self.__dict__.update(copy.deepcopy(previous))

    def predict(self,x):
        if len(x)!=16 or any(not math.isfinite(v) or abs(v)>1 for v in x):
            raise ValueError('BRANCH16_FEATURES')
        u=[v+.1*m for v,m in zip(x,self.memory)]
        branches=[math.tanh(sum(self.weights[j]*u[j] for j in range(i,i+4))) for i in range(0,16,4)]
        p=1/(1+math.exp(-sum(branches)/4))
        return [p,{'u':u,'branches':branches}]

    def learn(self,x,y,p,cache):
        for j in range(16):
            gradient=(y-p)*(1-cache['branches'][j//4]**2)*cache['u'][j]/4
            self.weights[j]=max(-1.,min(1.,self.weights[j]+.03*gradient))
            self.memory[j]=.95*self.memory[j]+.05*x[j]*(2*y-1)
        self.updates+=1

    def state(self):
        return copy.deepcopy(vars(self))


class LiquidityStudy:
    KINDS=('control','liquidity','no_liquidation','frozen')

    def __init__(self,horizons,previous=None):
        self.horizons=horizons
        self.models={f'{s}:{h}':{k:Branch16() for k in self.KINDS} for s in SYMBOLS for h in horizons}
        self.stats={key:{'n':0,'loss_sum':{k:0. for k in self.KINDS},'paired_gain_sum':0.,
                        'paired_gain_sq':0.,'directional_n':0,'net_quote_proxy_sum':0.,'dates':[]} for key in self.models}
        self.pending={}
        self.dropped=0
        if previous:
            if set(previous['models'])!=set(self.models):
                raise ValueError('LIQUIDITY_STUDY_CONTEXT')
            self.models={key:{k:Branch16(st) for k,st in bank.items()} for key,bank in previous['models'].items()}
            if any(set(bank)!=set(self.KINDS) for bank in self.models.values()):
                raise ValueError('LIQUIDITY_STUDY_MODEL_KINDS')
            self.stats=copy.deepcopy(previous['stats'])
            self.pending=copy.deepcopy(previous['pending'])
            self.dropped=previous['dropped']

    def fault(self,symbol,emit,reason):
        for key in [k for k in self.pending if k.startswith(symbol+':')]:
            f=self.pending.pop(key);self.dropped+=1
            emit('LIQUIDITY_LABEL_DROPPED',{'key':key,'id':f['id'],'reason':reason})

    def frame(self,symbol,at_ms,view,baseline,micro,quality,emit,cost_bps):
        if not quality['context_ready']:
            self.fault(symbol,emit,'AUXILIARY_CONTEXT_MISSING_OR_STALE')
            return
        mid=float(view['mid'])
        full=baseline+micro
        ablated=full.copy();ablated[12]=ablated[13]=0.
        features={'control':baseline+[0.]*8,'liquidity':full,'no_liquidation':ablated,'frozen':full}
        for h in self.horizons:
            key=f'{symbol}:{h}'
            f=self.pending.get(key)
            if f and at_ms>=f['due_ms']:
                del self.pending[key]
                if at_ms-f['due_ms']>2000 or mid==f['mid']:
                    self.dropped+=1
                    emit('LIQUIDITY_LABEL_DROPPED',{'key':key,'id':f['id'],'reason':'MATURITY_GAP_OR_TIE'})
                else:
                    y=int(mid>f['mid']);s=self.stats[key];loss={}
                    for kind,m in self.models[key].items():
                        p,c=f['predictions'][kind];loss[kind]=(p-y)**2
                        s['loss_sum'][kind]+=loss[kind]
                        if kind!='frozen':m.learn(f['features'][kind],y,p,c)
                    s['n']+=1
                    gain=loss['control']-loss['liquidity']
                    s['paired_gain_sum']+=gain;s['paired_gain_sq']+=gain*gain
                    day=datetime.datetime.fromtimestamp(at_ms/1000,datetime.timezone.utc).date().isoformat()
                    if day not in s['dates']:s['dates'].append(day)
                    p=f['predictions']['liquidity'][0]
                    direction=1 if p>=.55 else -1 if p<=.45 else 0
                    if direction:
                        net=((float(view['bid'])/float(f['ask'])-1)*10000 if direction==1 else
                             (float(f['bid'])-float(view['ask']))/float(f['bid'])*10000)-cost_bps
                        s['directional_n']+=1;s['net_quote_proxy_sum']+=net
                    emit('LIQUIDITY_MATURED',{'key':key,'id':f['id'],'label':y,'at_ms':at_ms,
                                             'paired_brier_gain':gain,'loss':loss,'proxy_label':True})
            if key not in self.pending:
                f={'key':key,'at_ms':at_ms,'due_ms':at_ms+h*1000,'mid':mid,'bid':view['bid'],'ask':view['ask'],
                   'features':features,'predictions':{k:m.predict(features[k]) for k,m in self.models[key].items()},
                   'quality':quality}
                f['id']=digest(f);self.pending[key]=f
                emit('LIQUIDITY_FORECAST',f)

    def state(self):
        return {'models':{key:{k:m.state() for k,m in bank.items()} for key,bank in self.models.items()},
                'stats':copy.deepcopy(self.stats),'pending':copy.deepcopy(self.pending),'dropped':self.dropped}

    def summary(self):
        result={}
        for key,s in self.stats.items():
            n=s['n'];mean=s['paired_gain_sum']/n if n else None
            se=math.sqrt(max(0.,(s['paired_gain_sq']-s['paired_gain_sum']**2/n)/(n-1))/n) if n>1 else None
            result[key]={'n':n,'mean_brier':{k:v/n if n else None for k,v in s['loss_sum'].items()},
                         'paired_gain_mean':mean,'descriptive_lower_bound':mean-3*se if se is not None else None,
                         'directional_n':s['directional_n'],
                         'net_quote_proxy_mean_bps':s['net_quote_proxy_sum']/s['directional_n'] if s['directional_n'] else None,
                         'distinct_utc_dates':len(s['dates'])}
        return {'comparisons':result,'dropped':self.dropped,'pending':len(self.pending),
                'execution_enabled':False,'profitability_proven':False,
                'selection_corrected_or_independent_validation':False}
