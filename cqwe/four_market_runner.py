"""Continuous four-symbol public feeds, immutable rounds, deterministic replay.

python -m cqwe.four_market_runner --root D:/CQWE_DATA/four_market --rounds 5 --seconds 185
"""
import argparse
import collections
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import json
import os
import queue
import threading
import time
import urllib.request
from decimal import Decimal as D
from pathlib import Path

from .copernican_experiment_v81_v85 import digest
from .four_market_core import Engine, SYMBOLS, config
from .futures_orderbook import BookFault, FuturesBook
from .tidal_hunter import Journal, get_json, rules_for, write_new
from .tidal_research import FlowFeatures
from .liquidity_research import open_interest


def sources():
    names = ('four_market_core.py','four_market_runner.py','four_market_supervisor.py','prediction_catalog.py','liquidity_research.py','dendritic_council.py',
             'futures_orderbook.py','tidal_research.py','tidal_hunter.py','copernican_experiment_v81_v85.py')
    return {n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in names}


def checked(obj):
    if obj.get('sha256') != digest({k:v for k,v in obj.items() if k != 'sha256'}):
        raise ValueError('EVIDENCE_HASH_MISMATCH')
    return obj


class Processor:
    def __init__(self, engine, previous=None):
        self.engine = engine
        self.books = {s:FuturesBook(s) for s in SYMBOLS}
        self.flows = {s:FlowFeatures() for s in SYMBOLS}
        self.recent_flow = {s:None for s in SYMBOLS}
        self.recovering = {s:False for s in SYMBOLS}
        if previous:
            for s,st in previous['books'].items():
                b = self.books[s]
                for k,v in st.items():
                    if k in ('bids','asks'):
                        v = {D(p):D(q) for p,q in v}
                    elif k in ('bid_boundary','ask_boundary') and v is not None:
                        v = D(v)
                    setattr(b,k,v)
            for s,st in previous['flows'].items():
                self.flows[s].trades = collections.deque((tuple(r) for r in st['trades']), maxlen=10000)
                self.flows[s].last_trade_id = st['last_trade_id']
                self.flows[s].previous = st['previous']
            self.recent_flow = previous['recent_flow'].copy()
            self.recovering = previous['recovering'].copy()

    def state(self):
        books = {}
        for s,b in self.books.items():
            st = copy.deepcopy(vars(b))
            for k in ('bids','asks'):
                st[k] = [[str(p),str(q)] for p,q in st[k].items()]
            for k in ('bid_boundary','ask_boundary'):
                if k in st:
                    st[k] = str(st[k])
            books[s] = st
        flows = {s:{'trades':list(f.trades), 'last_trade_id':f.last_trade_id,
                     'previous':f.previous} for s,f in self.flows.items()}
        # Normalize tuples so in-memory and JSON-restored states hash identically.
        return json.loads(json.dumps({'books':books,'flows':flows,'recent_flow':self.recent_flow,
                                     'recovering':self.recovering}))

    def process(self, kind, p):
        if kind == 'SNAPSHOT':
            self.books[p['symbol']].snapshot(p['snapshot'])
        elif kind == 'FLOW':
            symbol = p['symbol']
            try:
                self.flows[symbol].trade(p['event'],p['received_ns'],symbol)
                self.recent_flow[symbol] = p['received_ns']
                self.engine.liquidity.trade(symbol,p['event'],p['received_ns'])
            except BookFault as exc:
                self.process('FAULT', {'symbol':symbol, 'reason':str(exc)})
        elif kind == 'DEPTH':
            symbol = p['symbol']
            try:
                if not self.books[symbol].apply(p['event'],p['received_ns']):
                    return
                if abs(p['at_ms']-p['event']['E']) > 2000:
                    raise BookFault('EXCHANGE_RECEIPT_CLOCK_SKEW_OR_LATENCY')
                view = self.books[symbol].view(p['now_ns'])
                view['decision_ns']=p['now_ns']
                try:
                    lb,la=self.books[symbol].top(p['now_ns'],depth=20)
                    view['liquidity_bids']=[[str(price),str(qty)] for price,qty in lb]
                    view['liquidity_asks']=[[str(price),str(qty)] for price,qty in la]
                except BookFault:
                    pass  # finite-depth liquidity analysis explicitly falls back to known top five
                recent = self.recent_flow[symbol]
                transport_recent = max((v for v in self.recent_flow.values() if v is not None), default=None)
                if (recent is None or transport_recent is None or
                        not 0 <= p['now_ns']-transport_recent <= 2_000_000_000):
                    return
                x,fresh = self.flows[symbol].sample(view,p['now_ns'])
                # A quiet symbol is zero observed flow, not a disconnected shared
                # socket. Require symbol coverage once and current transport liveness.
                self.engine.frame(symbol,p['at_ms'],view,x)
                self.recovering[symbol] = False
            except BookFault as exc:
                if str(exc) in ('STALE_BOOK','EXCHANGE_RECEIPT_CLOCK_SKEW_OR_LATENCY'):
                    # Keep applying contiguous deltas while a delayed queue catches up.
                    # Resnapshotting every stale delta creates an endless recovery loop.
                    if not self.recovering[symbol]:
                        self.engine.fault(symbol,str(exc))
                        self.flows[symbol].previous = None
                    self.recovering[symbol] = True
                else:
                    self.process('FAULT', {'symbol':symbol, 'reason':str(exc)})
        elif kind == 'FAULT':
            s = p['symbol']
            self.engine.fault(s,p['reason'])
            self.books[s] = FuturesBook(s)
            self.flows[s] = FlowFeatures()
            self.recent_flow[s] = None
            self.recovering[s] = True
        elif kind in ('MARK','OI','LIQUIDATION'):
            try:
                self.engine.liquidity.context(kind,p['symbol'],p['event'],p['received_ns'])
            except (ValueError,KeyError,TypeError) as exc:
                self.engine.emit('CONTEXT_REJECTED',{'symbol':p['symbol'],'kind':kind,'error_type':type(exc).__name__})
                self.engine.liquidity.invalidate_context(p['symbol'])
                self.engine.liquidity_study.fault(p['symbol'],self.engine.emit,'REJECTED_AUXILIARY_CONTEXT')
        elif kind == 'CONTEXT_FAULT':
            self.engine.liquidity.invalidate_context(p['symbol'])
            self.engine.liquidity_study.fault(p['symbol'],self.engine.emit,p['reason'])
            self.engine.emit('CONTEXT_UNAVAILABLE',p)
        elif kind == 'TICK':
            self.engine.tick(p['at_ms'])
        elif kind == 'EVENT_QUOTE':
            self.engine.event_quote(p)
        elif kind == 'EVENT_RESOLUTION':
            self.engine.event_resolve(p)
        elif kind == 'ROUND_END':
            self.engine.end_round()
        else:
            raise ValueError('UNKNOWN_INPUT_KIND')


def replay_round(folder):
    folder = Path(folder)
    initial = checked(json.loads((folder/'initial.json').read_text(encoding='utf-8')))
    if initial['source_sha256'] != sources():
        raise ValueError('REPLAY_CODE_CONTEXT_CHANGED')
    expected = collections.deque()
    e = Engine(initial['engine']['cfg'],initial['engine']['rules'],
               lambda k,p:expected.append((k,p)),initial['engine'])
    processor = Processor(e,initial['processor'])
    previous,sequence,inputs,derived = None,0,0,0
    path = folder/'journal.jsonl'
    if path.stat().st_size > 250_000_000:
        raise ValueError('REPLAY_FILE_BUDGET')
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if len(line) > 3_000_000:
                raise ValueError('REPLAY_LINE_BUDGET')
            row = checked(json.loads(line))
            if row['sequence'] != sequence+1 or row['previous'] != previous:
                raise ValueError('JOURNAL_CHAIN_BROKEN')
            kind,p = row['kind'],row['payload']
            if kind.startswith('INPUT_'):
                if expected:
                    raise ValueError('MISSING_DERIVED_RECORD')
                processor.process(kind[6:],p)
                inputs += 1
            elif kind.startswith('DERIVED_'):
                if not expected or expected.popleft() != (kind[8:],p):
                    raise ValueError('DERIVED_REPLAY_MISMATCH')
                derived += 1
            else:
                raise ValueError('UNKNOWN_JOURNAL_RECORD')
            previous,sequence = row['sha256'],row['sequence']
    if expected:
        raise ValueError('TRUNCATED_DERIVED_RECORDS')
    final = checked(json.loads((folder/'state.json').read_text(encoding='utf-8')))
    if final['engine'] != e.state() or final['processor'] != processor.state() or final['journal_tip'] != previous:
        raise ValueError('FINAL_REPLAY_MISMATCH')
    if final['source_sha256'] != initial['source_sha256'] or final['previous'] != initial['previous']:
        raise ValueError('ROUND_LINEAGE_OR_SOURCE')
    return {'journal_chain':True,'raw_book_reconstruction':True,'feature_replay':True,
            'causal_forecast_replay':True,'model_state_replay':True,'shared_cash_replay':True,
            'event_learning_replay':True,'checkpoint_lineage':True,'source_frozen':True,
            'four_symbols_and_no_real_orders':final['engine']['real_orders']==0 and all(
                final['engine']['frames'][s] > initial['engine']['frames'][s] for s in SYMBOLS),
            'inputs':inputs,'derived':derived,'journal_tip':previous,'state_sha256':final['sha256']}


class Feeds:
    def __init__(self):
        self.incoming = queue.Queue(maxsize=30000)
        self.stop = threading.Event()
        self.overflow = threading.Event()
        self.sockets = []
        self.threads = []

    def put(self, item):
        try:
            self.incoming.put_nowait(item)
        except queue.Full:
            self.overflow.set()
            self.stop.set()

    def receive(self, name):
        import websocket
        route = 'public' if name == 'DEPTH' else 'market'
        suffix = '@depth@100ms' if name == 'DEPTH' else '@aggTrade'
        streams = ('!forceOrder@arr/'+'/'.join(s.lower()+'@markPrice@1s' for s in SYMBOLS)
                   if name=='CONTEXT' else '/'.join(s.lower()+suffix for s in SYMBOLS))
        url = f'wss://fstream.binance.com/{route}/stream?streams={streams}'
        for attempt in range(6):
            sock = None
            try:
                sock = websocket.create_connection(url,timeout=8)
                self.sockets.append(sock)
                sock.settimeout(1)
                while not self.stop.is_set():
                    try:
                        raw = sock.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not raw or len(raw) > 2_000_000:
                        raise ValueError('STREAM_MESSAGE_BUDGET')
                    obj = json.loads(raw)
                    event = obj.get('data',obj)
                    kind=name
                    if name=='CONTEXT':
                        if event.get('e')=='forceOrder':
                            kind='LIQUIDATION';symbol=event.get('o',{}).get('s')
                            if symbol not in SYMBOLS or event.get('st',1)!=1:
                                continue
                        elif event.get('e')=='markPriceUpdate':
                            kind='MARK';symbol=event.get('s')
                        else:
                            raise ValueError('UNKNOWN_CONTEXT_EVENT')
                    else:
                        symbol = event.get('s')
                    if symbol not in SYMBOLS:
                        raise ValueError('STREAM_SYMBOL')
                    self.put((kind, {'symbol':symbol,'event':event,'received_ns':time.monotonic_ns()}))
                return
            except Exception as exc:
                if self.stop.is_set():
                    return
                for symbol in SYMBOLS:
                    self.put(('CONTEXT_FAULT' if name=='CONTEXT' else 'FAULT',{'symbol':symbol,'reason':name+'_'+type(exc).__name__}))
                if attempt == 5:
                    if name!='CONTEXT':self.put(('FATAL',{'reason':name+'_RECONNECT_BUDGET'}))
                    return
                self.stop.wait(min(2**attempt,10))
            finally:
                if sock:
                    sock.close()

    def start(self):
        self.threads = [threading.Thread(target=self.receive,args=(k,),daemon=True) for k in ('DEPTH','FLOW','CONTEXT')]
        self.threads.append(threading.Thread(target=self.oi_poll,daemon=True))
        for t in self.threads:
            t.start()

    def oi_poll(self):
        while not self.stop.is_set():
            for symbol in SYMBOLS:
                if self.stop.is_set():return
                try:
                    event=open_interest(symbol)
                    self.put(('OI',{'symbol':symbol,'event':event,'received_ns':time.monotonic_ns()}))
                except Exception as exc:
                    self.put(('CONTEXT_FAULT',{'symbol':symbol,'reason':'OI_'+type(exc).__name__}))
            self.stop.wait(30)

    def close(self):
        self.stop.set()
        for s in self.sockets:
            s.close()
        for t in self.threads:
            t.join(timeout=2)


def envelope(engine, processor, previous, tip):
    obj = {'engine':engine.state(),'processor':processor.state(),'previous':previous,
           'source_sha256':sources(),'journal_tip':tip}
    obj['sha256'] = digest(obj)
    return obj


def exchange_clock():
    samples = []
    for _ in range(3):
        begin = time.monotonic_ns()
        with urllib.request.urlopen('https://fapi.binance.com/fapi/v1/time',timeout=10) as response:
            raw = response.read(10001)
        end = time.monotonic_ns()
        if len(raw)>10000:
            raise ValueError('CLOCK_RESPONSE_BUDGET')
        server = json.loads(raw)['serverTime']
        if type(server) is not int:
            raise ValueError('INVALID_SERVER_TIME')
        samples.append({'monotonic_ns':end,'estimated_server_ms':server+(end-begin)/2_000_000,
                        'uncertainty_ms':(end-begin)/2_000_000})
    best = min(samples,key=lambda s:s['uncertainty_ms'])
    if best['uncertainty_ms'] > 750:
        raise ValueError('CLOCK_UNCERTAINTY_TOO_HIGH')
    return best


def run(root, *, rounds=5, seconds=300, horizons=(300,900), catalog=True, event_inbox=None):
    if type(rounds) is not int or not 1 <= rounds <= 288 or type(seconds) is not int or not 15 <= seconds <= 3600 or rounds*seconds > 86400:
        raise ValueError('RUN_BUDGET')
    cfg = config(horizons)
    root = Path(root)
    root.mkdir(parents=True,exist_ok=True)
    lock = root/'runner.lock'
    with lock.open('x') as f:
        f.write(str(os.getpid()))
    feeds = Feeds()
    pool = None
    try:
        info = get_json('exchangeInfo')
        clock = exchange_clock()
        def now_ms():
            return int(clock['estimated_server_ms']+(time.monotonic_ns()-clock['monotonic_ns'])/1_000_000)
        write_new(root/f'clock_{time.time_ns()}.json',clock)
        rules = {s:rules_for(info,s) for s in SYMBOLS}
        latest = root/'LATEST.json'
        before = None
        if latest.exists():
            pointer = checked(json.loads(latest.read_text(encoding='utf-8')))
            name = pointer['round_name']
            if not isinstance(name,str) or not name.startswith('round_') or len(name)!=12 or not name[6:].isdigit():
                raise ValueError('INVALID_POINTER_PATH')
            before = checked(json.loads((root/name/'state.json').read_text(encoding='utf-8')))
            if pointer['state_sha256'] != before['sha256'] or before['source_sha256'] != sources():
                raise ValueError('SOURCE_OR_POINTER_CHANGED_USE_NEW_ROOT')
        engine = Engine(cfg,rules,previous=before['engine'] if before else None)
        resuming = before is not None
        processor = Processor(engine)  # reconnect always discards transport state
        reports = []
        audits = collections.deque()
        pool = ProcessPoolExecutor(max_workers=1)

        def finish_audits(wait=False):
            while audits and (wait or audits[0][0].done()):
                future,folder,state,report = audits.popleft()
                audit = future.result()
                checks = {k:v for k,v in audit.items() if type(v) is bool}
                if len(checks) != 10 or not all(checks.values()):
                    raise RuntimeError('ROUND_AUDIT_FAILED_PRIOR_CHECKPOINT_RETAINED')
                # Ordered promotion prevents a later audit bypassing a failed ancestor.
                pointer = {'round_name':folder.name,'state_sha256':state['sha256']}
                pointer['sha256'] = digest(pointer)
                tmp = root/'LATEST.tmp'
                with tmp.open('w',encoding='utf-8') as out:
                    json.dump(pointer,out,allow_nan=False)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(tmp,latest)
                report['checks'] = checks
                report['sha256'] = digest(report)
                write_new(folder/'report.json',report)
                reports.append(report)
                summary = report['summary']
                print(json.dumps({'round':report['round'],'frames':summary['frames'],
                                  'matured_proxy_labels':summary['matured_proxy_labels'],
                                  'checks_passed':len(checks),'virtual_cash':summary['portfolio']['cash'],
                                  'folder':str(folder)}),flush=True)
        processed_files = set()
        if catalog:
            from .prediction_catalog import collect
            print(json.dumps({'catalog':collect(root/'catalog',horizons=cfg['horizons_seconds'])}),flush=True)
        feeds.start()
        for _ in range(rounds):
            index = engine.rounds+1
            folder = root/f'round_{index:06d}'
            folder.mkdir(exist_ok=False)
            prev_hash = before['sha256'] if before else None
            initial = envelope(engine,processor,prev_hash,None)
            write_new(folder/'initial.json',initial)
            resyncs = {s:0 for s in SYMBOLS}
            started,last_tick = time.monotonic(),0.
            with (folder/'journal.jsonl').open('x',encoding='utf-8') as f:
                journal = Journal(f)
                engine.emit = lambda k,p:journal.emit('DERIVED_'+k,p)

                def consume(kind,p):
                    journal.emit('INPUT_'+kind,p)
                    processor.process(kind,p)

                if resuming and _ == 0:
                    for s in SYMBOLS:
                        consume('FAULT',{'symbol':s,'reason':'PROCESS_RESTART_CONTINUITY_LOST'})
                while time.monotonic()-started < seconds:
                    finish_audits()
                    if feeds.overflow.is_set():
                        raise RuntimeError('PUBLIC_QUEUE_OVERFLOW')
                    try:
                        kind,p = feeds.incoming.get(timeout=.25)
                    except queue.Empty:
                        kind,p = None,None
                    if kind == 'FATAL':
                        raise RuntimeError(p['reason'])
                    if kind == 'DEPTH':
                        symbol = p['symbol']
                        if not processor.books[symbol].valid:
                            resyncs[symbol] += 1
                            if resyncs[symbol] > 20:
                                raise RuntimeError(symbol+'_SNAPSHOT_REPAIR_BUDGET')
                            snapshot = get_json('depth',{'symbol':symbol,'limit':1000})
                            consume('SNAPSHOT',{'symbol':symbol,'snapshot':snapshot})
                        p.update(at_ms=now_ms(), now_ns=time.monotonic_ns())
                    if kind:
                        consume(kind,p)
                    if time.monotonic()-last_tick >= 1:
                        consume('TICK',{'at_ms':now_ms()})
                        if event_inbox:
                            for path in sorted(Path(event_inbox).glob('*.json'))[:10000]:
                                if path.name in processed_files:
                                    continue
                                if path.stat().st_size > 100000:
                                    raise ValueError('EVENT_INBOX_FILE_BUDGET')
                                item = json.loads(path.read_text(encoding='utf-8'))
                                if item['kind'] not in ('EVENT_QUOTE','EVENT_RESOLUTION'):
                                    raise ValueError('EVENT_INBOX_KIND')
                                identity = item['payload']['venue']+':'+str(item['payload']['market_id'])
                                existing_event = engine.events.get(identity)
                                if existing_event and (item['kind']=='EVENT_QUOTE' or existing_event['resolved']):
                                    processed_files.add(path.name)
                                    continue
                                # Never interpret code, instructions or an arbitrary URL from an inbox.
                                consume(item['kind'],item['payload'])
                                processed_files.add(path.name)
                        last_tick = time.monotonic()
                consume('ROUND_END',{})
                state = envelope(engine,processor,prev_hash,journal.previous)
            write_new(folder/'state.json',state)
            report = {'round':index,'summary':copy.deepcopy(engine.summary()),'journal_tip':journal.previous,
                      'state_sha256':state['sha256'],'real_orders':0}
            if len(audits) >= 2:
                raise RuntimeError('AUDIT_BACKLOG_BUDGET')
            audits.append((pool.submit(replay_round,str(folder)),folder,state,report))
            before = state
        feeds.close()
        finish_audits(wait=True)
        return reports
    except BaseException as exc:
        failure = {'status':'STOPPED_WITHOUT_PROMOTING_FAILED_ROUND','error':type(exc).__name__+': '+str(exc),
                   'at_ms':time.time_ns()//1_000_000,'real_orders':0}
        write_new(root/f'failure_{time.time_ns()}.json',failure)
        raise
    finally:
        feeds.close()
        if pool is not None:
            pool.shutdown(wait=True,cancel_futures=True)
        lock.unlink()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='D:/CQWE_DATA/four_market_liquidity_v2')
    p.add_argument('--rounds',type=int,default=5)
    p.add_argument('--seconds',type=int,default=300)
    p.add_argument('--horizons',default='300,900')
    p.add_argument('--replay')
    p.add_argument('--catalog-only',action='store_true')
    p.add_argument('--no-catalog',action='store_true')
    p.add_argument('--event-inbox')
    a = p.parse_args()
    if a.replay:
        print(json.dumps(replay_round(a.replay)))
    elif a.catalog_only:
        from .prediction_catalog import collect
        print(json.dumps(collect(Path(a.root)/'catalog'),ensure_ascii=False))
    else:
        run(a.root,rounds=a.rounds,seconds=a.seconds,horizons=tuple(int(h) for h in a.horizons.split(',')),
            catalog=not a.no_catalog,event_inbox=a.event_inbox)


if __name__ == '__main__':
    main()
