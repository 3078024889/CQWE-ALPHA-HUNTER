
"""CQWE Copernican V32.

Unified, public-data paper-trading research core.
- Bybit V5 public market data only; no API keys and no order endpoints.
- BTC is the crypto regime anchor; altcoins may deviate only with measured residual strength.
- 24h/6h/4h/1h/30m/15m/5m are one multi-timeframe dendritic state.
- 5m is aggregated into the higher frames; three 5m observations form a 15m confirmation.
- Direction and exits are structure/liquidity driven, not fixed-percent targets.
- Order-book liquidity is treated as liquidity, never as guaranteed liquidation.
- Event context is an optional veto/weighting input; it cannot invent events.
- Decisions are deterministic and auditable from an immutable evidence snapshot.
"""
from __future__ import annotations
import argparse, dataclasses, datetime as dt, hashlib, json, math, statistics, time
from pathlib import Path
from typing import Any, Iterable
import urllib.parse, urllib.request, urllib.error

BYBIT = "https://api.bybit.com"
SYMBOLS = ("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT")
FRAMES = (5,15,30,60,240,360,1440)
FRAME_NAMES = {5:"5m",15:"15m",30:"30m",60:"1h",240:"4h",360:"6h",1440:"24h"}

@dataclasses.dataclass(frozen=True)
class Bar:
    t:int; o:float; h:float; l:float; c:float; v:float; q:float

@dataclasses.dataclass(frozen=True)
class Level:
    price:float
    strength:float
    kind:str

def _num(x:Any)->float:
    v=float(x)
    if not math.isfinite(v): raise ValueError("nonfinite number")
    return v

def _request(path:str, params:dict[str,Any]|None=None, timeout:int=12)->dict[str,Any]:
    qs=urllib.parse.urlencode(params or {})
    url=BYBIT+path+("?" + qs if qs else "")
    req=urllib.request.Request(url, headers={"User-Agent":"CQWE-Copernican-V32/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                obj=json.load(r)
            if obj.get("retCode") != 0:
                raise RuntimeError(f"BYBIT_{obj.get('retCode')}:{obj.get('retMsg')}")
            return obj
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == 2: raise RuntimeError(f"BYBIT_PUBLIC_FEED_FAILED:{e}") from e
            time.sleep(0.5*(attempt+1))

def server_time_ms()->int:
    r=_request("/v5/market/time")
    return int(r["result"]["timeNano"])//1_000_000

def fetch_klines(symbol:str, interval:int=5, limit:int=1000)->list[Bar]:
    if symbol not in SYMBOLS: raise ValueError("unsupported symbol")
    if interval not in (5,15,30,60,240,360,1440): raise ValueError("unsupported interval")
    if not 100 <= limit <= 5000: raise ValueError("limit 100..5000")
    now=server_time_ms()
    step=interval*60_000
    # Bybit REST caps a single kline response at 1000. Paginate backward with
    # end timestamps; every page is revalidated and merged deterministically.
    remaining=limit
    end=now-1
    rows=[]
    while remaining>0:
        page=min(1000,remaining)
        r=_request("/v5/market/kline",{"category":"linear","symbol":symbol,"interval":str(interval),
                                       "limit":page,"end":end})
        batch=r["result"]["list"]
        if not batch: break
        rows.extend(batch)
        oldest=int(batch[-1][0])
        next_end=oldest-1
        if next_end>=end: raise ValueError("kline pagination failed to advance")
        end=next_end
        remaining-=len(batch)
        if len(batch)<page: break
    out=[]
    for row in reversed(rows):
        t=int(row[0]); ctime=t+step
        if ctime > now: continue
        b=Bar(t,_num(row[1]),_num(row[2]),_num(row[3]),_num(row[4]),_num(row[5]),_num(row[6]))
        if b.l <= 0 or b.h < b.l or not (b.l <= b.o <= b.h and b.l <= b.c <= b.h) or b.v < 0 or b.q < 0:
            raise ValueError(f"invalid candle {symbol} {interval} {t}")
        if out and b.t != out[-1].t + step: raise ValueError("missing/duplicate kline")
        out.append(b)
    if len(out) < 30: raise ValueError(f"insufficient closed bars {symbol} {interval}")
    return out

def fetch_orderbook(symbol:str, limit:int=200)->dict[str,Any]:
    r=_request("/v5/market/orderbook",{"category":"linear","symbol":symbol,"limit":limit})
    x=r["result"]
    return {
        "symbol":symbol,"ts":int(x["ts"]),"seq":int(x["seq"]),
        "bids":[[_num(a),_num(b)] for a,b in x["b"]],
        "asks":[[_num(a),_num(b)] for a,b in x["a"]],
    }

def fetch_derivatives(symbol:str)->dict[str,Any]:
    tick=_request("/v5/market/tickers",{"category":"linear","symbol":symbol})["result"]["list"][0]
    oi=_request("/v5/market/open-interest",{"category":"linear","symbol":symbol,"intervalTime":"5min","limit":50})["result"]["list"]
    fund=_request("/v5/market/funding/history",{"category":"linear","symbol":symbol,"limit":10})["result"]["list"]
    oi_out=sorted([{"ts":int(x["timestamp"]),"oi":_num(x["openInterest"])} for x in oi], key=lambda x:x["ts"])
    fund_out=sorted([{"ts":int(x["fundingRateTimestamp"]),"rate":_num(x["fundingRate"])} for x in fund], key=lambda x:x["ts"], reverse=True)
    return {
        "ticker":{k:tick.get(k) for k in ("lastPrice","indexPrice","markPrice","bid1Price","ask1Price","volume24h","turnover24h","fundingRate")},
        "oi":oi_out,
        "funding":fund_out,
    }

def _aggregate_5m(bars:list[Bar], minutes:int)->list[Bar]:
    if minutes == 5: return bars
    step=minutes*60_000
    buckets={}
    for b in bars:
        key=(b.t//step)*step
        buckets.setdefault(key,[]).append(b)
    out=[]
    for t, xs in sorted(buckets.items()):
        if len(xs) != minutes//5: continue
        if any(xs[i].t != xs[i-1].t+300_000 for i in range(1,len(xs))): continue
        out.append(Bar(t,xs[0].o,max(x.h for x in xs),min(x.l for x in xs),xs[-1].c,sum(x.v for x in xs),sum(x.q for x in xs)))
    return out

def _ema(xs:list[float], n:int)->float:
    if not xs: return math.nan
    a=2/(n+1); e=xs[0]
    for x in xs[1:]: e=a*x+(1-a)*e
    return e

def _trend(bars:list[Bar])->dict[str,Any]:
    # Each frame is evaluated on its own completed bars. A frame may have only
    # a few observations (notably 24h), so the score is based on return across
    # nested windows plus EMA relation rather than pretending 30 daily bars exist.
    if len(bars)<5: raise ValueError("trend needs >=5 bars")
    c=[x.c for x in bars]
    def ret(n): return c[-1]/c[-1-n]-1 if len(c)>n else 0.0
    r1=ret(1); r3=ret(3); r6=ret(6); r12=ret(12)
    efast=_ema(c[-min(len(c),20):],min(20,len(c)))
    eslow=_ema(c[-min(len(c),max(5,min(50,len(c)))):],max(5,min(50,len(c))))
    slope=ret(min(12,len(c)-1))
    score=sum(1 if x>0 else -1 if x<0 else 0 for x in (r1,r3,r6,r12))
    score += 1 if efast>eslow else -1 if efast<eslow else 0
    score += 1 if slope>0 else -1 if slope<0 else 0
    direction="LONG" if score>=3 else "SHORT" if score<=-3 else "NEUTRAL"
    return {"direction":direction,"score":score,"return_1":r1,"return_3":r3,"return_6":r6,"return_12":r12,
            "ema_fast":efast,"ema_slow":eslow,"slope":slope}

def _levels(bars:list[Bar], n:int=160)->dict[str,list[Level]]:
    xs=bars[-n:]
    # Pivot clustering: local extrema become candidate structural levels.
    raw=[]
    for i in range(2,len(xs)-2):
        if xs[i].h>=xs[i-1].h and xs[i].h>=xs[i-2].h and xs[i].h>xs[i+1].h and xs[i].h>xs[i+2].h:
            raw.append(Level(xs[i].h,1.0,"R"))
        if xs[i].l<=xs[i-1].l and xs[i].l<=xs[i-2].l and xs[i].l<xs[i+1].l and xs[i].l<xs[i+2].l:
            raw.append(Level(xs[i].l,1.0,"S"))
    # Cluster within 0.15% of price. Strength is recurrence, capped.
    price=xs[-1].c
    result={"supports":[],"resistances":[]}
    for kind in ("S","R"):
        vals=[x.price for x in raw if x.kind==kind]
        vals.sort()
        clusters=[]
        for p in vals:
            if not clusters or abs(p-clusters[-1][-1])/price>0.0015: clusters.append([p])
            else: clusters[-1].append(p)
        levels=[Level(sum(g)/len(g),min(5.0,1.0+0.8*(len(g)-1)),kind) for g in clusters]
        if kind=="S":
            result["supports"]=sorted([x for x in levels if x.price<price],key=lambda x:x.price,reverse=True)[:3]
        else:
            result["resistances"]=sorted([x for x in levels if x.price>price],key=lambda x:x.price)[:3]
    return result

def _book_clusters(book:dict[str,Any], price:float)->dict[str,list[Level]]:
    def side(levels, direction):
        if not levels: return []
        sizes=[q for _,q in levels]
        med=statistics.median(sizes) or 1.0
        candidates=[]
        for p,q in levels:
            dist=abs(p-price)/price
            if dist > 0.03: continue
            ratio=q/med
            if ratio>=2:
                candidates.append(Level(p,min(10.0,ratio),direction))
        return sorted(candidates,key=lambda x:abs(x.price-price))
    return {"bid":side(book["bids"],"BID_LIQUIDITY"),"ask":side(book["asks"],"ASK_LIQUIDITY")}

def _taker_from_bars(bars:list[Bar], n:int=12)->float:
    xs=bars[-n:]
    # Bybit kline turnover has no taker-buy field, so use candle body/range as a
    # conservative directional proxy. It is explicitly not labelled aggressive flow.
    vals=[]
    for b in xs:
        rng=max(b.h-b.l, b.c*1e-9)
        vals.append((b.c-b.o)/rng)
    return statistics.mean(vals) if vals else 0.0

def _oi_change(series:list[dict[str,Any]])->float|None:
    if len(series)<2: return None
    a,b=series[-2]["oi"],series[-1]["oi"]
    return b/a-1 if a else None

def _residual(asset:dict[str,Any], btc:dict[str,Any])->float:
    ar=asset["returns"]["4h"]; br=btc["returns"]["4h"]
    return ar-br

def _event_state(event_context:dict[str,Any]|None)->dict[str,Any]:
    if not event_context: return {"veto":False,"risk":"NORMAL","events":[]}
    events=event_context.get("events",[])
    now=int(event_context.get("now_ms",0))
    active=[]
    for e in events:
        start=int(e.get("start_ms",0)); end=int(e.get("end_ms",start))
        if start<=now<=end: active.append(e)
    risk="HIGH" if any(str(e.get("risk","")).upper()=="HIGH" for e in active) else "NORMAL"
    return {"veto":bool(event_context.get("new_entry_veto",False)) and bool(active),"risk":risk,"events":active}

def _decision(symbol:str, state:dict[str,Any], btc:dict[str,Any], book:dict[str,Any], event:dict[str,Any])->dict[str,Any]:
    frames=state["frames"]
    anchor=btc["frames"]
    high=[frames[x]["score"] for x in ("24h","6h","4h","1h")]
    low=[frames[x]["score"] for x in ("30m","15m","5m")]
    macro=statistics.mean(high)
    micro=statistics.mean(low)
    anchor_macro=statistics.mean(anchor[x]["score"] for x in ("24h","6h","4h","1h"))
    residual=state["residual_4h"]
    # Primary direction is anchored by the higher timeframe. Altcoins need residual
    # confirmation to differ from BTC; absent that, they inherit the anchor direction.
    if anchor_macro >= 2.0:
        regime="LONG"
    elif anchor_macro <= -2.0:
        regime="SHORT"
    else:
        regime="NEUTRAL"
    asset_bias=macro
    if symbol!="BTCUSDT":
        if regime=="LONG" and residual < -0.008: asset_bias-=1.5
        if regime=="SHORT" and residual > 0.008: asset_bias+=1.5
    action="HOLD"
    if not event["veto"] and regime=="LONG" and asset_bias>=2.0 and micro>=0.0: action="LONG"
    elif not event["veto"] and regime=="SHORT" and asset_bias<=-2.0 and micro<=0.0: action="SHORT"
    elif regime=="NEUTRAL": action="HOLD"
    price=state["price"]
    levels=state["levels"]
    liquidity=_book_clusters(book,price)
    bid_depth=sum(q for p,q in book.get("bids",[]) if abs(p-price)/price<=0.01)
    ask_depth=sum(q for p,q in book.get("asks",[]) if abs(p-price)/price<=0.01)
    if action=="LONG":
        opp=[x.price for x in liquidity["ask"] if x.price>price]
        targets=[x.price for x in levels["resistances"] if x.price>price]
        pool=sorted(opp+targets)
        target=pool[0] if pool else price*(1+max(0.002,abs(state["atr_pct"])*1.5))
        stop=levels["supports"][0].price if levels["supports"] else price*(1- max(0.003,abs(state["atr_pct"])*1.5))
    elif action=="SHORT":
        opp=[x.price for x in liquidity["bid"] if x.price<price]
        targets=[x.price for x in levels["supports"] if x.price<price]
        pool=sorted(opp+targets,reverse=True)
        target=pool[0] if pool else price*(1-max(0.002,abs(state["atr_pct"])*1.5))
        stop=levels["resistances"][0].price if levels["resistances"] else price*(1+ max(0.003,abs(state["atr_pct"])*1.5))
    else: target=stop=None
    return {"symbol":symbol,"action":action,"regime":regime,"macro_score":round(macro,3),
            "micro_score":round(micro,3),"btc_anchor_score":round(anchor_macro,3),
            "residual_4h":round(residual,6),"event_veto":event["veto"],
            "entry_reference":price,"stop_invalidation":stop,"dynamic_exit_reference":target,
            "book_bid_depth_1pct":bid_depth,"book_ask_depth_1pct":ask_depth,
            "book_imbalance_1pct":((bid_depth-ask_depth)/(bid_depth+ask_depth)) if (bid_depth+ask_depth)>0 else 0.0,
            "support_1":levels["supports"][0].price if levels["supports"] else None,
            "support_2":levels["supports"][1].price if len(levels["supports"])>1 else None,
            "support_3":levels["supports"][2].price if len(levels["supports"])>2 else None,
            "resistance_1":levels["resistances"][0].price if levels["resistances"] else None,
            "resistance_2":levels["resistances"][1].price if len(levels["resistances"])>1 else None,
            "resistance_3":levels["resistances"][2].price if len(levels["resistances"])>2 else None,
            "exit_policy":"EXIT_BEFORE_OPPOSING_LIQUIDITY_OR_STRUCTURE; NEVER_FIXED_PERCENT"}

def snapshot(symbol:str, event_context:dict[str,Any]|None=None)->dict[str,Any]:
    bars5=fetch_klines(symbol,5,5000)
    frames={}
    for m in FRAMES:
        xs=_aggregate_5m(bars5,m)
        frames[FRAME_NAMES[m]]=_trend(xs)
    price=bars5[-1].c
    levels=_levels(bars5)
    atr=sum(max(x.h-x.l,abs(x.h-bars5[i-1].c),abs(x.l-bars5[i-1].c)) for i,x in enumerate(bars5[-15:],start=len(bars5)-15))/14
    deriv=fetch_derivatives(symbol)
    book=fetch_orderbook(symbol)
    return {"symbol":symbol,"asof_ms":bars5[-1].t,"price":price,
            "frames":frames,"levels":levels,"atr_pct":atr/price,
            "returns":{"4h":frames["4h"]["return_12"],"24h":frames["24h"]["return_12"]},
            "oi_change_5m":_oi_change(deriv["oi"]),
            "funding_rate":deriv["funding"][0]["rate"] if deriv["funding"] else None,
            "funding_history":deriv["funding"],
            "ticker":deriv["ticker"],"book":book}

def run_once(event_context:dict[str,Any]|None=None)->dict[str,Any]:
    raw={s:snapshot(s,event_context) for s in SYMBOLS}
    btc=raw["BTCUSDT"]
    event=_event_state(event_context)
    decisions=[]
    for s in SYMBOLS:
        state = dict(raw[s])
        state["residual_4h"] = (
            state["returns"]["4h"] - btc["returns"]["4h"]
        )
        d=_decision(s,state,btc,state["book"],event)
        d["asof_ms"]=raw[s]["asof_ms"]
        d["frames"]=raw[s]["frames"]
        d["oi_change_5m"]=raw[s]["oi_change_5m"]
        d["funding_rate"]=raw[s]["funding_rate"]
        d["funding_history"]=raw[s].get("funding_history", [])
        decisions.append(d)
    # Single portfolio state: no opposing asset orders within one crypto regime.
    regime=decisions[0]["regime"]
    allowed=[d for d in decisions if d["action"]==regime]
    selected=sorted(allowed,key=lambda x:(x["macro_score"],abs(x["residual_4h"])),reverse=(regime=="LONG"))[:2] if regime!="NEUTRAL" else []
    for d in decisions:
        d["portfolio_selected"]=d in selected
        if d["portfolio_selected"]:
            entry = d.get("entry_reference")
            stop = d.get("stop_invalidation")
            if isinstance(entry, (int, float)) and isinstance(stop, (int, float)) and entry > 0 and stop > 0:
                distance = abs(entry - stop) / entry
                if 0 < distance < 0.5:
                    d["trailing_stop_distance_fraction"] = distance
                    d["trailing_stop_policy"] = "ONE_INITIAL_RISK_UNIT_FROM_FAVORABLE_EXTREME"
    evidence=json.dumps({"raw":raw,"decisions":decisions},sort_keys=True,default=str,separators=(",",":")).encode()
    return {"version":"CQWE-COPERNICAN-V32","mode":"PUBLIC_DATA_PAPER_ONLY","real_orders":0,
            "generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"regime":regime,
            "event":event,"decisions":decisions,"evidence_sha256":hashlib.sha256(evidence).hexdigest()}

def save_report(report:dict[str,Any],path:str)->None:
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding="utf-8");tmp.replace(p)

def main():
    ap=argparse.ArgumentParser(description="CQWE Copernican V32 public-data paper engine")
    ap.add_argument("--output",default="reports/copernican_v32_live.json")
    ap.add_argument("--event-context")
    args=ap.parse_args()
    ctx=json.loads(Path(args.event_context).read_text(encoding="utf-8")) if args.event_context else None
    report=run_once(ctx);save_report(report,args.output)
    print(json.dumps({"version":report["version"],"mode":report["mode"],"real_orders":0,
                      "regime":report["regime"],"selected":[d["symbol"] for d in report["decisions"] if d["portfolio_selected"]],
                      "evidence_sha256":report["evidence_sha256"]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
