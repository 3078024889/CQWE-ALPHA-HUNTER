"""V43 bounded Binance public L2 + raw trade capture on D:.

One combined read-only public stream; locally sequenced events, timed snapshot,
fail-closed on stale WS, overflows and depth sequence gap. No trading endpoints.
"""
from __future__ import annotations
import argparse, json, os, queue, threading, time, uuid
from pathlib import Path
from .l2_replay_v42 import LocalBook, SequenceGap, fetch_snapshot, SYMBOLS
from .market_replay_v43 import hash_record, read_chain, ten_stresses

WS_ROOT='wss://stream.binance.com:9443/stream?streams='
DATA_ROOT=Path('D:/CQWE_DATA/l2_v43')

def append_chain(f,seq,prev,session,kind,payload):
    r={'schema':'CQWE_V43_CAPTURE','sequence':seq,'prev_sha256':prev,'session_id':session,
       'received_ns':time.time_ns(),'kind':kind,'payload':payload}
    r['sha256']=hash_record(r)
    f.write(json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n');f.flush()
    return r['sha256']

def live(symbol='BNBUSDT',seconds=75,root=DATA_ROOT):
    if symbol not in SYMBOLS or not 20<=seconds<=600:raise ValueError('BAD_CAPTURE_CONFIG')
    root=Path(root).resolve()
    if root.drive and root.drive.upper()!='D:':raise ValueError('D_DRIVE_REQUIRED')
    if os.name=='nt' and root.drive.upper()!='D:':raise ValueError('D_DRIVE_REQUIRED')
    try:import websocket
    except ImportError as exc:raise RuntimeError('WEBSOCKET_CLIENT_MISSING') from exc
    root.mkdir(parents=True,exist_ok=True)
    session=uuid.uuid4().hex;path=root/(f'{symbol}_{int(time.time())}_{session}.jsonl')
    book=LocalBook(symbol);incoming=queue.Queue(maxsize=15000);stopped=threading.Event();errors=[]
    ws=websocket.create_connection(WS_ROOT+f'{symbol.lower()}@depth@100ms/{symbol.lower()}@trade',timeout=10,enable_multithread=True)
    def recv():
        ws.settimeout(2)
        while not stopped.is_set():
            try:
                msg=json.loads(ws.recv())
                item=msg.get('data',msg)
                if item.get('e') in ('depthUpdate','trade'):
                    incoming.put_nowait((item,time.time_ns()))
            except websocket.WebSocketTimeoutException:continue
            except queue.Full:errors.append('QUEUE_OVERFLOW');stopped.set();break
            except Exception as e:errors.append(f'WS_DISCONNECTED_{type(e).__name__}');stopped.set();break
    reader=threading.Thread(target=recv,daemon=True);reader.start()
    seq=0;prev='0'*64;started=time.monotonic();applied=0;trade_count=0;last_book_emit=0
    # Keep alive on network timeout; never create simulated data from missing events.
    try:
      with path.open('x',encoding='utf8',buffering=1) as f:
        def record(kind,payload):
            nonlocal seq,prev
            seq+=1;prev=append_chain(f,seq,prev,session,kind,payload)
        buffered=0
        while buffered<10 and time.monotonic()-started<5:
            if errors:raise RuntimeError(errors[-1])
            try:event,t=incoming.get(timeout=.5)
            except queue.Empty:continue
            if event['e']=='depthUpdate':book.queue(event,t//1_000_000);buffered+=1
            elif event['e']=='trade':record('TRADE',{'price':event['p'],'qty':event['q'],'buyer_is_maker':event['m'],'trade_id':event['t'],'exchange_time_ms':event['T'],'pre_sync':True});trade_count+=1
        if not buffered:raise RuntimeError('NO_DEPTH_EVENTS')
        # Snapshot while receiver continues filling queue; drain buffered increments.
        for attempt in range(3):
            snap=fetch_snapshot(symbol)
            while True:
                try:event,t=incoming.get_nowait()
                except queue.Empty:break
                if event['e']=='depthUpdate':book.queue(event,t//1_000_000)
                else:record('TRADE',{'price':event['p'],'qty':event['q'],'buyer_is_maker':event['m'],'trade_id':event['t'],'exchange_time_ms':event['T'],'pre_sync':True});trade_count+=1
            try:book.synchronize(snap,int(time.time()*1000));break
            except SequenceGap:
                if attempt==2:raise
                time.sleep(.5)
        record('START',{'symbol':symbol,'last_update_id':book.update_id,'synced':True})
        while time.monotonic()-started<seconds:
            if errors:raise RuntimeError(errors[-1])
            try:event,t=incoming.get(timeout=1)
            except queue.Empty:continue
            if event['e']=='depthUpdate':
                try:res=book.apply(event,t//1_000_000)
                except SequenceGap:
                    record('GAP',{'reason':'SEQUENCE_OR_INVALID_BOOK','last_update_id':book.update_id});raise
                if res=='APPLIED':
                    applied+=1
                    if time.monotonic()-last_book_emit>=.5:
                        bid=max(book.bids);ask=min(book.asks)
                        record('BOOK',{'symbol':symbol,'synced':True,'update_id':book.update_id,
                            'bid':str(bid),'ask':str(ask),'bid_qty':str(book.bids[bid]),'ask_qty':str(book.asks[ask]),
                            'book_received_ms':t//1_000_000})
                        last_book_emit=time.monotonic()
            elif event['e']=='trade':
                record('TRADE',{'price':event['p'],'qty':event['q'],'buyer_is_maker':event['m'],
                    'trade_id':event['t'],'exchange_time_ms':event['T'],'pre_sync':False});trade_count+=1
        record('STOP',{'reason':'DURATION_COMPLETED','synced':book.synced})
    except BaseException as e:
        # Do not stitch sessions after a fault; leave incomplete evidence for audit.
        errors.append(f'CAPTURE_ABORTED_{type(e).__name__}: {e}')
        raise
    finally:
        stopped.set();ws.close();reader.join(timeout=3)
    records=read_chain(path)
    return {'status':'V43_CAPTURE_COMPLETE','file':str(path),'records':len(records),
      'depth_events_applied':applied,'trades_observed':trade_count,'ten_stresses':ten_stresses(records),
      'no_orders':True,'actual_fills_known':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--symbol',choices=SYMBOLS,default='BNBUSDT');p.add_argument('--seconds',type=int,default=75)
    p.add_argument('--root',default=str(DATA_ROOT));a=p.parse_args()
    print('CQWE_V43_LIVE '+json.dumps(live(a.symbol,a.seconds,a.root),sort_keys=True))
    print('D DRIVE DATA | PUBLIC STREAM ONLY | NO ACCOUNT KEYS | NO REAL ORDERS')
if __name__=='__main__':main()
