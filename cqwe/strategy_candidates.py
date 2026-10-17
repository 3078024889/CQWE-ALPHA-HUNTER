"""Independent close-bar research variants; not third-party EA reproductions."""
import math

SYMBOLS=('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT')
SPEC={
 'vol_rsi':{'atr':22,'atr_average':10,'rsi':5,'thresholds':[34,66],'exit_rsi':50},
 'ts_momentum':{'hours':168,'minimum_vol_units':1},
 'residual_pair':{'fit_hours':720,'entry_z':2,'exit_z':.5,'beta_limits':[.5,2]},
 'cross_momentum':{'hours':168,'rebalance':'UTC daily','minimum_log_dispersion':.02}}


def single_targets(bars,kind,symbol):
    if kind not in ('vol_rsi','ts_momentum'):raise ValueError('UNKNOWN_SINGLE_RULE')
    closes=[];tr=[];atrs=[];gain=loss=0.;direction=0;out=[]
    for i,b in enumerate(bars):
        if i>=200:
            if kind=='ts_momentum':
                changes=[math.log(y/x) for x,y in zip(closes[-169:-1],closes[-168:])]
                vol=math.sqrt(sum(x*x for x in changes)/len(changes))*math.sqrt(168)
                momentum=math.log(closes[-1]/closes[-169])
                direction=1 if momentum>vol else -1 if momentum<-vol else 0
            else:
                rsi=100*gain/(gain+loss) if gain+loss else 50
                atr=atrs[-1];expanded=atr>sum(atrs[-10:])/10
                if not direction and expanded:direction=1 if rsi>66 else -1 if rsi<34 else 0
                elif direction==1 and rsi<50 or direction==-1 and rsi>50:direction=0
        out.append({symbol:float(direction)} if direction else {})
        c=b['close'];delta=c-closes[-1] if closes else 0
        tr.append(max(b['high']-b['low'],abs(b['high']-closes[-1]),abs(b['low']-closes[-1])) if closes else b['high']-b['low'])
        atrs.append(sum(tr[-22:])/min(len(tr),22) if i<22 else (atrs[-1]*21+tr[-1])/22)
        if i<=5:
            gain=(gain*max(i-1,0)+max(delta,0))/max(i,1);loss=(loss*max(i-1,0)+max(-delta,0))/max(i,1)
        else:gain=(gain*4+max(delta,0))/5;loss=(loss*4+max(-delta,0))/5
        closes.append(c)
    return out


def pair_targets(asset,btc,symbol):
    if len(asset)!=len(btc) or any(a['time']!=b['time'] for a,b in zip(asset,btc)):raise ValueError('PAIR_TIMELINE_MISMATCH')
    xs=[math.log(b['close']) for b in btc];ys=[math.log(b['close']) for b in asset]
    # Prefix moments keep the rolling regression bounded and causal.
    px=[0.];py=[0.];pxx=[0.];pyy=[0.];pxy=[0.]
    for x,y in zip(xs,ys):
        px.append(px[-1]+x);py.append(py[-1]+y);pxx.append(pxx[-1]+x*x);pyy.append(pyy[-1]+y*y);pxy.append(pxy[-1]+x*y)
    direction=0;held_beta=1.;out=[]
    for i in range(len(xs)):
        if i>=722:
            a=i-721;b=i-1;n=720
            sx=px[b]-px[a];sy=py[b]-py[a];sxx=pxx[b]-pxx[a];syy=pyy[b]-pyy[a];sxy=pxy[b]-pxy[a]
            vx=sxx-sx*sx/n;cov=sxy-sx*sy/n
            beta=cov/vx if vx>1e-10 else 0;intercept=(sy-beta*sx)/n
            sd=math.sqrt(max(0,syy-sy*sy/n-beta*cov)/n)
            z=(ys[i-1]-intercept-beta*xs[i-1])/sd if sd>1e-8 else 0
            if not .5<=beta<=2:direction=0
            elif not direction and abs(z)>=2:direction=-1 if z>0 else 1;held_beta=beta
            elif direction and (abs(z)<=.5 or direction*z>0):direction=0
        out.append({symbol:direction/(1+held_beta),'BTCUSDT':-direction*held_beta/(1+held_beta)} if direction else {})
    return out


def basket_targets(data):
    n=len(data['BTCUSDT']);held={};out=[]
    for i in range(n):
        t=data['BTCUSDT'][i]['time']
        if any(len(v)!=n or v[i]['time']!=t for v in data.values()):raise ValueError('BASKET_TIMELINE_MISMATCH')
        if i>=200 and t%86400000==0:
            momentum={s:math.log(v[i-1]['close']/v[i-169]['close']) for s,v in data.items()}
            top=max(momentum,key=momentum.get);bottom=min(momentum,key=momentum.get)
            held={top:.5,bottom:-.5} if momentum[top]-momentum[bottom]>.02 else {}
        out.append(held.copy())
    return out


def candidates(data):
    out={}
    for s,bars in data.items():
        for kind in ('vol_rsi','ts_momentum'):out[kind+':'+s]=single_targets(bars,kind,s)
        if s!='BTCUSDT':out['residual_pair:'+s]=pair_targets(bars,data['BTCUSDT'],s)
    out['cross_momentum:four']=basket_targets(data)
    return out
