"""One small public websocket: sampled force orders and four mark-price heartbeats."""
from collections import deque
import json
import threading
import time
from .four_market_core import SYMBOLS


class LiquidationWatch:
    def __init__(self):
        self.lock=threading.RLock();self.stop=threading.Event();self.thread=None;self.socket=None
        self.connected=False;self.last_ms=None;self.error=None;self.marks={}
        self.orders={s:deque(maxlen=100) for s in SYMBOLS}

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.thread=threading.Thread(target=self.run,name='CQWE-sampled-liquidations',daemon=True);self.thread.start()

    def run(self):
        import websocket
        streams='!forceOrder@arr/'+'/'.join(s.lower()+'@markPrice@1s' for s in SYMBOLS)
        url='wss://fstream.binance.com/market/stream?streams='+streams
        failures=0
        while not self.stop.is_set():
            sock=None
            try:
                sock=websocket.create_connection(url,timeout=5);self.socket=sock
                with self.lock:self.connected=True;self.error=None
                while not self.stop.is_set():
                    try:raw=sock.recv()
                    except websocket.WebSocketTimeoutException:continue
                    if not raw or len(raw)>100000:raise ValueError('CONTEXT_MESSAGE_SIZE')
                    item=json.loads(raw);event=item.get('data',item);now=time.time_ns()//1000000
                    with self.lock:
                        self.last_ms=now
                        if event.get('e')=='markPriceUpdate' and event.get('s') in SYMBOLS:
                            self.marks[event['s']]={'event':event,'received_ms':now}
                        elif event.get('e')=='forceOrder' and event.get('o',{}).get('s') in SYMBOLS and event.get('st',1)==1:
                            self.orders[event['o']['s']].append({'event':event,'received_ms':now,'received_ns':time.monotonic_ns()})
            except Exception as exc:
                with self.lock:self.error=str(exc);self.connected=False;self.marks={}
                failures+=1
            finally:
                if sock:
                    try:sock.close()
                    except Exception:pass
            self.stop.wait(min(60,5*failures))

    def snapshot(self,symbol,at):
        with self.lock:
            return {'connected':self.connected and self.last_ms is not None and 0<=at-self.last_ms<=15000,
                'mark':self.marks.get(symbol),'orders':[v for v in self.orders[symbol] if 0<=at-v['received_ms']<=30000],
                'error':self.error,'sampled_only':True}

    def close(self):
        self.stop.set()
        if self.socket:
            try:self.socket.close()
            except Exception:pass
