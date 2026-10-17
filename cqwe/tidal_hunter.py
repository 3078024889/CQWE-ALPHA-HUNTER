"""Copernican Tidal Hunter: bounded PUBLIC USD-M orderbook/flow research.

Usage: python -m cqwe.tidal_hunter --symbol BTCUSDT --seconds 90
No credentials, trading endpoints, scheduler installation or real orders.
"""
import argparse
import collections
import json
import queue
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .copernican_experiment_v81_v85 import digest
from .futures_orderbook import BookFault, FuturesBook
from .tidal_research import OnlineLab

SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT')


def get_json(path, params=None):
    # Fixed public host and endpoints. No signed/account/order request capability.
    if path not in ('depth','exchangeInfo'):
        raise ValueError('PUBLIC_ENDPOINT_NOT_ALLOWED')
    url = 'https://fapi.binance.com/fapi/v1/'+path
    if params:
        url += '?'+urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=10) as response:
        raw = response.read(10_000_001)
    if len(raw) > 10_000_000:
        raise ValueError('HTTP_RESPONSE_BUDGET')
    return json.loads(raw)


def rules_for(info, symbol):
    matches = [s for s in info['symbols'] if s['symbol'] == symbol and s['status'] == 'TRADING']
    if len(matches) != 1:
        raise ValueError('MARKET_UNAVAILABLE')
    fs = {f['filterType']:f for f in matches[0]['filters']}
    lot = fs.get('MARKET_LOT_SIZE', fs['LOT_SIZE'])
    return {'step': lot['stepSize'], 'min_qty': lot['minQty'],
            'max_qty': lot['maxQty'], 'min_notional': fs['MIN_NOTIONAL']['notional']}


class Journal:
    def __init__(self, file):
        self.file = file
        self.sequence = 0
        self.previous = None
        self.bytes = 0

    def emit(self, kind, payload):
        row = {'sequence': self.sequence+1, 'previous': self.previous,
               'written_ns': time.time_ns(), 'kind':kind, 'payload':payload}
        row['sha256'] = digest(row)
        text = json.dumps(row, separators=(',', ':'), allow_nan=False)+'\n'
        if self.bytes+len(text.encode()) > 250_000_000:
            raise RuntimeError('CAPTURE_DISK_BUDGET')
        self.file.write(text)
        self.file.flush()
        self.sequence += 1
        self.previous = row['sha256']
        self.bytes += len(text.encode())


def write_new(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, allow_nan=False)


def capture(symbol, seconds, root, previous=None):
    if symbol not in SYMBOLS or type(seconds) is not int or not 15 <= seconds <= 600:
        raise ValueError('INVALID_CAPTURE_CONFIG')
    import websocket
    rules = rules_for(get_json('exchangeInfo'), symbol)
    folder = Path(root)/f'{symbol}_{time.time_ns()}_{uuid.uuid4().hex[:8]}'
    folder.mkdir(parents=True, exist_ok=False)
    urls = {'depth': f'wss://fstream.binance.com/public/ws/{symbol.lower()}@depth@100ms',
            'flow': f'wss://fstream.binance.com/market/ws/{symbol.lower()}@aggTrade'}
    incoming = queue.Queue(maxsize=20000)
    stop = threading.Event()
    sockets = []
    overflow = threading.Event()

    def put(item):
        try:
            incoming.put_nowait(item)
        except queue.Full:
            overflow.set()
            stop.set()

    def receive(name):
        for attempt in range(4):
            sock = None
            try:
                sock = websocket.create_connection(urls[name], timeout=8)
                sockets.append(sock)
                sock.settimeout(1)
                if attempt:
                    put(('RECONNECT',name,time.monotonic_ns(),{'attempt':attempt}))
                while not stop.is_set():
                    try:
                        raw = sock.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not raw or len(raw) > 2_000_000:
                        raise RuntimeError('EMPTY_OR_OVERSIZE_MESSAGE')
                    event = json.loads(raw)
                    event = event.get('data', event)
                    put(('RAW',name,time.monotonic_ns(),event))
                return
            except Exception as exc:
                if stop.is_set():
                    return
                put(('STREAM_FAULT',name,time.monotonic_ns(),{'error':type(exc).__name__}))
                if attempt == 3:
                    put(('FATAL',name,time.monotonic_ns(),{'error':'RECONNECT_BUDGET'}))
                    return
            finally:
                if sock is not None:
                    sock.close()

    threads = [threading.Thread(target=receive,args=(k,),daemon=True) for k in urls]
    status, error, resyncs = 'COMPLETE', None, 0
    frame_count = trade_count = 0
    with (folder/'capture.jsonl').open('x', encoding='utf-8') as f:
        journal = Journal(f)
        lab = OnlineLab(rules, journal.emit, symbol=symbol, previous=previous)
        journal.emit('START', {'schema':'CQWE_TIDAL_CAPTURE_V1', 'symbol':symbol,
                              'urls':urls, 'rules':rules, 'initial_checkpoint':lab.checkpoint(),
                              'previous':previous, 'seconds':seconds, 'real_orders':0})
        book = FuturesBook(symbol)
        for t in threads:
            t.start()
        started = time.monotonic()
        needs_snapshot = True
        flow_connected = False
        depth_connected = False
        last_healthy_ns = time.monotonic_ns()
        stale_paused = False
        try:
            while time.monotonic()-started < seconds:
                if overflow.is_set():
                    raise RuntimeError('INCOMING_QUEUE_OVERFLOW')
                try:
                    kind,name,received,event = incoming.get(timeout=.25)
                except queue.Empty:
                    if time.monotonic_ns()-last_healthy_ns > 2_000_000_000 and not stale_paused:
                        journal.emit('FAULT', {'reason':'NO_FRESH_DEPTH'})
                        lab.fault('NO_FRESH_DEPTH')
                        stale_paused = True
                    if time.monotonic_ns()-last_healthy_ns > 10_000_000_000:
                        raise RuntimeError('NO_FRESH_DEPTH_TIMEOUT')
                    continue
                if kind == 'FATAL':
                    raise RuntimeError(name+'_RECONNECT_BUDGET')
                if kind in ('STREAM_FAULT','RECONNECT'):
                    journal.emit(kind, {'stream':name, **event})
                    reason = name+'_'+kind
                    journal.emit('FAULT', {'reason':reason})
                    lab.fault(reason)
                    if name == 'depth':
                        needs_snapshot = True
                        depth_connected = kind == 'RECONNECT'
                    else:
                        flow_connected = kind == 'RECONNECT'
                    continue
                journal.emit('RAW_'+name.upper(), {'received_ns':received, 'event':event})
                if name == 'flow':
                    flow_connected = True
                    lab.flow.trade(event, received, symbol)
                    trade_count += 1
                    continue
                depth_connected = True
                if needs_snapshot:
                    snapshot = get_json('depth', {'symbol':symbol,'limit':1000})
                    journal.emit('SNAPSHOT', snapshot)
                    book.snapshot(snapshot)
                    needs_snapshot = False
                    resyncs += 1
                    if resyncs > 6:
                        raise RuntimeError('SNAPSHOT_REPAIR_BUDGET')
                try:
                    if not book.apply(event, received):
                        continue
                    now = time.monotonic_ns()
                    view = book.view(now)
                except BookFault as exc:
                    reason = str(exc)
                    if reason == 'STALE_BOOK':
                        if not stale_paused:
                            journal.emit('FAULT', {'reason':reason})
                            lab.fault(reason)
                            stale_paused = True
                        continue
                    journal.emit('FAULT', {'reason':reason})
                    lab.fault(reason)
                    needs_snapshot = True
                    continue
                last_healthy_ns = now
                stale_paused = False
                journal.emit('FRAME', {'now_ns':now, 'view':view})
                lab.book(view, now)
                frame_count += 1
            if not depth_connected or not flow_connected or frame_count == 0 or trade_count == 0:
                raise RuntimeError('MISSING_REQUIRED_PUBLIC_STREAM')
        except Exception as exc:
            status, error = 'FAILED', type(exc).__name__+': '+str(exc)
            journal.emit('FAULT', {'reason':error})
            lab.fault(error)
        finally:
            stop.set()
            for sock in sockets:
                sock.close()
            for t in threads:
                t.join(timeout=2)
        checkpoint = lab.checkpoint()
        paper = lab.paper.summary()
        journal.emit('STOP', {'status':status, 'error':error, 'checkpoint_sha256':checkpoint['sha256']})
        report = {'schema':'CQWE_TIDAL_SESSION_V1', 'status':status, 'error':error,
                  'symbol':symbol, 'duration_requested_seconds':seconds,
                  'synchronized_frames':frame_count, 'aggregate_trade_events':trade_count,
                  'snapshot_initializations':resyncs, 'matured_forecasts':lab.settled,
                  'memory_continued':previous is not None, 'stats':lab.stats,
                  'checkpoint':checkpoint, 'virtual_account':paper, 'virtual_ledger':lab.paper.ledger,
                  'feed_faults':lab.failures, 'capture_tip_sha256':journal.previous,
                  'unsettled_forecast':lab.pending is not None,
                  'real_orders':0, 'realized_account_profit_usdt':None,
                  'maker_identity_known':False, 'passive_fills_assumed':0,
                  'limitations':['Book is aggregated market-by-price, not maker identities or queue positions.',
                       '5-second quote crossing proxies use decision quotes; paper fills use later quotes.',
                       'Fees and slippage are assumptions. Funding, impact and actual executions unverified.',
                       'Virtual account resets per session; learned model memory can continue.',
                       'Confidence screen is descriptive, with no multiple-testing or dependence correction.',
                       'Short captures cannot establish a profitable strategy.']}
        report['sha256'] = digest(report)
        write_new(folder/'checkpoint.json', checkpoint)
        write_new(folder/'report.json', report)
    return folder, report


def verify_capture(path):
    previous = None
    rows = []
    with Path(path).open(encoding='utf-8') as f:
        for index,line in enumerate(f,1):
            if index > 500000 or len(line) > 2_100_000:
                raise ValueError('CAPTURE_READ_BUDGET')
            row = json.loads(line)
            if row.get('sequence') != index or row.get('previous') != previous:
                raise ValueError('CAPTURE_CHAIN')
            if row.get('sha256') != digest({k:v for k,v in row.items() if k != 'sha256'}):
                raise ValueError('CAPTURE_HASH')
            previous = row['sha256']
            rows.append(row)
    if not rows or rows[0]['kind'] != 'START' or rows[-1]['kind'] != 'STOP':
        raise ValueError('INCOMPLETE_CAPTURE')
    return rows


def replay(folder):
    folder = Path(folder)
    rows = verify_capture(folder/'capture.jsonl')
    start = rows[0]['payload']
    generated = collections.deque()
    lab = OnlineLab(start['rules'], lambda k,p:generated.append((k,p)),
                    symbol=start['symbol'], previous=start['previous'])
    book = FuturesBook(start['symbol'])
    pending_depth = None

    def apply_pending():
        nonlocal pending_depth
        if pending_depth is not None:
            try:
                book.apply(pending_depth['event'],pending_depth['received_ns'])
            except BookFault:
                pass  # The following FAULT/snapshot records preserve recovery.
            pending_depth = None
    if lab.checkpoint() != start['initial_checkpoint']:
        raise ValueError('INITIAL_MEMORY_REPLAY_MISMATCH')
    for row in rows[1:]:
        k,p = row['kind'],row['payload']
        if pending_depth is not None and k != 'SNAPSHOT':
            apply_pending()
        if k == 'RAW_DEPTH':
            pending_depth = p
        elif k == 'SNAPSHOT':
            book.snapshot(p)
            apply_pending()
        elif k == 'RAW_FLOW':
            lab.flow.trade(p['event'],p['received_ns'],start['symbol'])
        elif k == 'FRAME':
            if book.view(p['now_ns']) != p['view']:
                raise ValueError('RAW_BOOK_REPLAY_MISMATCH')
            lab.book(p['view'],p['now_ns'])
        elif k == 'FAULT':
            lab.fault(p['reason'])
        elif k in ('FORECAST','MATURED','LABEL_EXPIRED','PAUSE'):
            if not generated or generated.popleft() != (k,p):
                raise ValueError('RESEARCH_EVENT_REPLAY_MISMATCH')
    if generated:
        raise ValueError('MISSING_RESEARCH_EVENTS')
    report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    if report.get('sha256') != digest({k:v for k,v in report.items() if k != 'sha256'}):
        raise ValueError('REPORT_HASH')
    if report['capture_tip_sha256'] != rows[-1]['sha256'] or report['checkpoint'] != lab.checkpoint():
        raise ValueError('FINAL_MEMORY_REPLAY_MISMATCH')
    if report['virtual_account'] != lab.paper.summary() or report['virtual_ledger'] != lab.paper.ledger:
        raise ValueError('VIRTUAL_LEDGER_REPLAY_MISMATCH')
    return {'capture_chain_verified':True, 'causal_model_replay_equal':True,
            'virtual_ledger_replay_equal':True, 'records':len(rows), 'real_orders':0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbol',choices=SYMBOLS,default='BTCUSDT')
    p.add_argument('--seconds',type=int,default=90)
    p.add_argument('--root',default='D:/CQWE_DATA/tidal_hunter')
    p.add_argument('--previous',help='Prior checkpoint.json; carries models, not virtual positions')
    p.add_argument('--replay',help='Verify and replay a completed capture directory')
    a = p.parse_args()
    if a.replay:
        print(json.dumps(replay(a.replay),indent=2))
        return
    previous = json.loads(Path(a.previous).read_text(encoding='utf-8')) if a.previous else None
    folder,report = capture(a.symbol,a.seconds,a.root,previous)
    result = {k:report[k] for k in ('status','error','symbol','synchronized_frames',
                                   'aggregate_trade_events','matured_forecasts','real_orders')}
    result.update({'session_dir':str(folder),'virtual_account':report['virtual_account']})
    if report['status'] == 'COMPLETE':
        result['replay'] = replay(folder)
    print(json.dumps(result,indent=2))
    if report['status'] != 'COMPLETE':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
