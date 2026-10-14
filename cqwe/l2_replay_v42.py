"""CQWE V42 synchronized Binance Spot diff depth, read-only microstructure.

Protocol follows official Binance local orderbook recipe (snapshot plus buffered U/u).
No API keys; no orders; no purported individual-maker identity or queue reconstruction.
A snapshot is never evidence of an actual queue fill.
"""
from __future__ import annotations
import argparse, collections, json, math, os, random, time, urllib.parse, urllib.request, threading, queue
from decimal import Decimal, InvalidOperation
from pathlib import Path
from .public_data_v29 import _digest

SYMBOLS=('BNBUSDT','BTCUSDT','ETHUSDT','SOLUSDT')
STREAM_ROOT='wss://stream.binance.com:9443/ws/'
REST_ROOT='https://data-api.binance.vision/api/v3/depth'


def qty(x):
    try: v=Decimal(str(x))
    except (InvalidOperation,TypeError): raise ValueError('INVALID_PRICE_OR_QTY')
    if not v.is_finite() or v<0:raise ValueError('INVALID_PRICE_OR_QTY')
    return v

class SequenceGap(ValueError): pass

class LocalBook:
    def __init__(self,symbol):
        if symbol not in SYMBOLS:raise ValueError('SYMBOL_NOT_ALLOWED')
        self.symbol=symbol;self.bids={};self.asks={};self.update_id=None
        self.synced=False;self.buffer=collections.deque(maxlen=3000)
        self.received_ms=None;self.snapshot_at_ms=None;self.events=0;self.resyncs=0

    def _side(self,raw):
        if not isinstance(raw,list):raise ValueError('INVALID_LEVEL_LIST')
        result={}
        for level in raw:
            if not isinstance(level,(list,tuple)) or len(level)<2:raise ValueError('INVALID_BOOK_LEVEL')
            price,amount=qty(level[0]),qty(level[1])
            if price==0:raise ValueError('ZERO_PRICE')
            if amount:result[price]=amount
        return result

    def queue(self,event,at_ms=None):
        self._validate_event(event)
        if self.synced:return self.apply(event,at_ms=at_ms)
        if len(self.buffer)==self.buffer.maxlen:raise SequenceGap('BUFFER_OVERFLOW_RESYNC')
        self.buffer.append((event,at_ms))
        return 'BUFFERED'

    def _validate_event(self,event):
        if not isinstance(event,dict) or event.get('e')!='depthUpdate' or event.get('s')!=self.symbol:raise ValueError('WRONG_DEPTH_EVENT')
        u=event.get('u');first=event.get('U')
        if not isinstance(first,int) or not isinstance(u,int) or first>u or first<0:raise ValueError('BAD_SEQUENCE_ID')
        if not isinstance(event.get('b'),list) or not isinstance(event.get('a'),list):raise ValueError('BAD_DEPTH_PAYLOAD')

    def synchronize(self,snapshot,at_ms=None):
        ident=snapshot.get('lastUpdateId')
        if not isinstance(ident,int) or ident<0:raise ValueError('BAD_SNAPSHOT_ID')
        bids=self._side(snapshot.get('bids'));asks=self._side(snapshot.get('asks'))
        if not bids or not asks or max(bids)>=min(asks):raise ValueError('INVALID_INITIAL_BOOK')
        if self.buffer and ident < self.buffer[0][0]['U']-1:raise SequenceGap('SNAPSHOT_BEHIND_FIRST_BUFFERED_EVENT')
        self.bids=bids;self.asks=asks;self.update_id=ident;self.synced=True;self.snapshot_at_ms=at_ms
        buffered=list(self.buffer);self.buffer.clear()
        for event,t in buffered:self.apply(event,at_ms=t)
        return self.summary()

    def apply(self,event,at_ms=None):
        self._validate_event(event)
        if not self.synced:raise SequenceGap('NOT_SYNCHRONIZED')
        first,last=event['U'],event['u']
        if last<=self.update_id:return 'STALE_IGNORED'
        if first>self.update_id+1:
            self.synced=False;self.resyncs+=1;self.buffer.clear()
            raise SequenceGap('SEQUENCE_GAP_RESYNC_REQUIRED')
        if last<self.update_id+1:raise SequenceGap('SEQUENCE_REGRESSION')
        next_bids=self.bids.copy();next_asks=self.asks.copy()
        for dest,updates in ((next_bids,event['b']),(next_asks,event['a'])):
            for level in updates:
                if not isinstance(level,(list,tuple)) or len(level)<2:raise ValueError('INVALID_BOOK_LEVEL')
                price,amount=qty(level[0]),qty(level[1])
                if price==0:raise ValueError('ZERO_PRICE')
                if amount:dest[price]=amount
                else:dest.pop(price,None)
        if not next_bids or not next_asks or max(next_bids)>=min(next_asks):
            self.synced=False;self.resyncs+=1
            raise SequenceGap('INVALID_BOOK_AFTER_DIFF')
        self.bids=next_bids;self.asks=next_asks;self.update_id=last;self.received_ms=at_ms;self.events+=1
        return 'APPLIED'

    def summary(self,limit=5):
        if not self.synced:raise SequenceGap('UNSYNCED_BOOK_NOT_TRUSTED')
        bids=sorted(self.bids.items(),reverse=True)[:limit];asks=sorted(self.asks.items())[:limit]
        if not bids or not asks:raise SequenceGap('EMPTY_BOOK')
        bid,ask=bids[0][0],asks[0][0]; mid=(bid+ask)/2
        bvol=sum(z for _,z in bids);avol=sum(z for _,z in asks)
        return {'symbol':self.symbol,'update_id':self.update_id,'best_bid':str(bid),'best_ask':str(ask),
          'mid':str(mid),'spread_bps':float((ask-bid)/mid*10000),
          'imbalance_l5':float((bvol-avol)/(bvol+avol)),
          'depth_levels':{'bid':len(self.bids),'ask':len(self.asks)},'depth_events_applied':self.events,
          'received_ms':self.received_ms,'snapshot_at_ms':self.snapshot_at_ms,'synced':True,
          'no_order_or_fill_claim':True}


def cost_crossing(entry,exit_,direction,fee_bps=10,slippage_bps=2):
    """Explicit hypothetical taker crossing, never asserts a fill; no PnL without future quotes."""
    if direction not in ('LONG','SHORT'):raise ValueError('INVALID_DIRECTION')
    for book in (entry,exit_):
        if book.get('synced') is not True:raise ValueError('UNSYNCED_EVIDENCE')
    entry_price=Decimal(str(entry['best_ask' if direction=='LONG' else 'best_bid']))
    exit_price=Decimal(str(exit_['best_bid' if direction=='LONG' else 'best_ask']))
    if not entry_price or not exit_price:raise ValueError('BAD_QUOTES')
    if not 0<=fee_bps<=100 or not 0<=slippage_bps<=100:raise ValueError('INVALID_COSTS')
    signed=(exit_price/entry_price-1) if direction=='LONG' else (entry_price/exit_price-1)
    return {'hypothetical_net_bps':float(signed*10000)-2*(fee_bps+slippage_bps),
      'execution_verified':False,'includes_spread_crossing':True,'fee_bps_per_side':fee_bps,
      'slippage_bps_per_side':slippage_bps,'no_real_or_paper_fill':True}


def fetch_snapshot(symbol,limit=1000):
    if symbol not in SYMBOLS or limit not in (100,500,1000):raise ValueError('BAD_SNAPSHOT_REQUEST')
    req=urllib.request.Request(REST_ROOT+'?'+urllib.parse.urlencode({'symbol':symbol,'limit':limit}),headers={'User-Agent':'CQWE-v42-public-L2/1.0'})
    with urllib.request.urlopen(req,timeout=12) as r:
        if r.status!=200:raise RuntimeError('SNAPSHOT_HTTP_ERROR')
        raw=r.read(2_000_001)
    if len(raw)>2_000_000:raise RuntimeError('SNAPSHOT_TOO_LARGE')
    return json.loads(raw)


def emit(folder,kind,payload):
    path=Path(folder);path.mkdir(parents=True,exist_ok=True)
    at=int(time.time_ns()//1_000_000)
    record={'schema':'CQWE_V42_L2_EVENT','kind':kind,'recorded_at_ms':at,'no_orders':True,'data':payload}
    record['sha256']=_digest(record)
    filename=path / f'{at}_{os.getpid()}_{random.randrange(1000000):06d}.json'
    with filename.open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,sort_keys=True,allow_nan=False)
    return filename


def verify(folder):
    counts={};last={}
    for path in sorted(Path(folder).glob('*.json')):
        rec=json.loads(path.read_text(encoding='utf8'))
        if rec.get('sha256')!=_digest({k:v for k,v in rec.items() if k!='sha256'}):raise ValueError('L2_HASH_MISMATCH')
        if rec.get('schema')!='CQWE_V42_L2_EVENT' or rec.get('no_orders') is not True:raise ValueError('UNTRUSTED_L2_RECORD')
        counts[rec['kind']]=counts.get(rec['kind'],0)+1;last[rec['kind']]=rec['recorded_at_ms']
    return {'version':'V42','counts':counts,'latest_recorded_ms':last,'only_observations':True,'profit_proven':False}


def quote_forward(folder,seconds=60,fee_bps=10,slippage_bps=2):
    """Only nonoverlapping pairs within same START-to-STOP verified capture session."""
    sessions=[];current=None
    for path in sorted(Path(folder).glob('*.json')):
        r=json.loads(path.read_text(encoding='utf8'))
        if r.get('sha256')!=_digest({k:v for k,v in r.items() if k!='sha256'}):raise ValueError('L2_HASH_MISMATCH')
        kind=r['kind'];d=r['data']
        if kind=='START':
            current=[(r['recorded_at_ms'],d)];sessions.append(current)
        elif kind=='GAP':current=None
        elif kind=='STOP':current=None
        elif kind=='BOOK' and current is not None:current.append((r['recorded_at_ms'],d))
    out=[]
    for seq in sessions:
        i=0
        while i<len(seq):
            t,start=seq[i]
            direction='LONG' if start['imbalance_l5']>0.25 else ('SHORT' if start['imbalance_l5']<-.25 else None)
            if direction is None:i+=1;continue
            eligible=[j for j in range(i+1,len(seq)) if (seconds*1000)<=seq[j][0]-t<=seconds*1000+15000 and
              seq[j][1]['symbol']==start['symbol'] and seq[j][1]['update_id']>start['update_id']]
            if not eligible:i+=1;continue
            j=eligible[0];res=cost_crossing(start,seq[j][1],direction,fee_bps,slippage_bps)
            out.append({'start_ms':t,'end_ms':seq[j][0],'symbol':start['symbol'],'direction':direction,**res})
            i=j+1
    vals=[x['hypothetical_net_bps'] for x in out]
    return {'complete_or_partial_sessions':len(sessions),'evaluated_nonoverlap_pairs':len(vals),
     'mean_hypothetical_net_bps':sum(vals)/len(vals) if vals else None,
     'positive_quote_proxy_pairs':sum(v>0 for v in vals),'sample_sufficient':len(vals)>=100,
     'executable_edge_proven':False,'real_profit_usd':0.0,
     'limitations':'No real order fills, queue, latency, execution delay, partial fills or market impact. No pairs across session reset.'}


def live(symbol='BNBUSDT',seconds=65,folder='reports/v42_l2_events'):
    try:import websocket
    except ImportError as e:raise RuntimeError('DEPENDENCY_MISSING: python -m pip install websocket-client') from e
    if symbol not in SYMBOLS or seconds<5 or seconds>3600:raise ValueError('INVALID_CAPTURE_CONFIG')
    book=LocalBook(symbol)
    ws=websocket.create_connection(STREAM_ROOT+symbol.lower()+'@depth@100ms',timeout=8,enable_multithread=True)
    incoming=queue.Queue(maxsize=3000);stop=threading.Event();errors=[]
    def recv_loop():
        ws.settimeout(2)
        while not stop.is_set():
            try:
                msg=json.loads(ws.recv())
                if msg.get('e')=='depthUpdate':incoming.put_nowait((msg,int(time.time()*1000)))
            except websocket.WebSocketTimeoutException:continue
            except queue.Full:errors.append('RECEIVER_OVERFLOW');stop.set();break
            except Exception as e:errors.append('WS_DISCONNECT_'+type(e).__name__);stop.set();break
    reader=threading.Thread(target=recv_loop,daemon=True);reader.start()
    began=time.monotonic();recorded=0;buffered=0
    try:
        warm=time.monotonic()
        while time.monotonic()-warm<4 and buffered<10:
            if errors:raise RuntimeError(errors[-1])
            try:msg,t=incoming.get(timeout=.5)
            except queue.Empty:continue
            book.queue(msg,t);buffered+=1
        if not buffered:raise RuntimeError('NO_DEPTH_EVENTS_BEFORE_SNAPSHOT')
        # Snapshot requested with WS reader running, preserving events during REST latency.
        for attempt in range(3):
            snapshot=fetch_snapshot(symbol)
            while True:
                try:msg,t=incoming.get_nowait();book.queue(msg,t);buffered+=1
                except queue.Empty:break
            try:book.synchronize(snapshot,int(time.time()*1000));break
            except SequenceGap:
                if attempt==2:raise
                time.sleep(1)
        emit(folder,'START',book.summary());recorded+=1
        last_emit=time.monotonic()
        while time.monotonic()-began<seconds:
            if errors:raise RuntimeError(errors[-1])
            try:msg,t=incoming.get(timeout=.5)
            except queue.Empty:continue
            try:
                result=book.apply(msg,t)
                if result=='APPLIED' and time.monotonic()-last_emit>=1:
                    emit(folder,'BOOK',book.summary());recorded+=1;last_emit=time.monotonic()
            except SequenceGap as exc:
                emit(folder,'GAP',{'symbol':symbol,'reason':str(exc),'last_update_id':book.update_id});recorded+=1
                raise RuntimeError('UNSYNCED_STOP_NO_PREDICTIONS') from exc
        emit(folder,'STOP',book.summary());recorded+=1
    finally:
        stop.set();ws.close();reader.join(timeout=3)
    return {'symbol':symbol,'buffered':buffered,'events_applied':book.events,'records':recorded,'synced':book.synced,'no_orders':True}


def main():
    p=argparse.ArgumentParser();p.add_argument('--symbol',choices=SYMBOLS,default='BNBUSDT');p.add_argument('--seconds',type=int,default=65)
    p.add_argument('--folder',default='reports/v42_l2_events');p.add_argument('--audit',action='store_true');a=p.parse_args()
    if not a.audit:print('CQWE_V42_LIVE '+json.dumps(live(a.symbol,a.seconds,a.folder),sort_keys=True))
    print('CQWE_V42_AUDIT '+json.dumps(verify(a.folder),sort_keys=True))
    print('CQWE_V42_QUOTE_PROXY '+json.dumps(quote_forward(a.folder),sort_keys=True))
    print('PUBLIC REAL L2 | READ ONLY | NO EXECUTABLE PROFIT OR FILL CLAIM')
if __name__=='__main__':main()
