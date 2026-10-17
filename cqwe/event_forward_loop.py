"""Transactional forward event learning. Public data only; no account/order access.

Each prediction is committed before its outcome. Missed quotes are dropped, never
backfilled into forward evidence. Historical replay remains a separate dataset.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import shutil
import time
from urllib.request import urlopen

from .copernican_experiment_v81_v85 import digest
from .four_market_core import SYMBOLS
from .liquidity_research import Branch16
from .local_autopilot import atomic, exclusive
from .historical_curriculum import public

HORIZONS=(300,900,3600)
SCHEMA='CQWE_EVENT_FORWARD_V1'


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def causal_features(types,at_ms,closed):
    from research.learn_event_history import features
    by={b['time']:b for b in closed}
    anchor=(at_ms//60000)*60000
    response=[]
    for h in HORIZONS:
        bars=[by.get(t) for t in range(anchor-h*1000,anchor,60000)]
        if not all(bars):raise ValueError('PRE_EVENT_HISTORY_GAP')
        if any(b['time']+60000>at_ms for b in bars):raise ValueError('FUTURE_FEATURE')
        prices=[float(b[k]) for b in bars for k in ('open','close')]
        if any(not math.isfinite(p) or p<=0 for p in prices):raise ValueError('FEATURE_PRICE')
        response.append({'horizon':h,'pre_return_bps':(float(bars[-1]['close'])/float(bars[0]['open'])-1)*10000})
    return features(types,at_ms,response)


class ForwardLoop:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=10)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS models(k TEXT PRIMARY KEY,state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS predictions(
          id TEXT PRIMARY KEY,cluster TEXT NOT NULL,symbol TEXT NOT NULL,h INTEGER NOT NULL,
          at INTEGER NOT NULL,due INTEGER NOT NULL,p REAL NOT NULL,x TEXT NOT NULL,
          bid REAL NOT NULL,ask REAL NOT NULL,direction INTEGER NOT NULL,
          status TEXT NOT NULL,result TEXT,
          UNIQUE(cluster,symbol,h));
        CREATE TABLE IF NOT EXISTS journal(
          seq INTEGER PRIMARY KEY,payload TEXT NOT NULL,previous TEXT NOT NULL,hash TEXT NOT NULL);
        ''')
        source={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest()
                for n in ('event_forward_loop.py','liquidity_research.py','event_council_bridge.py',
                          'four_market_core.py','copernican_experiment_v81_v85.py')}
        # Feature implementation is also versioned, even though shared with offline research.
        source['features']=hashlib.sha256((Path(__file__).parent.parent/'research/learn_event_history.py').read_bytes()).hexdigest()
        expected=encode({'schema':SCHEMA,'sources':source,'fee_bps_per_side':5.,'slippage_bps_per_side':2.,
                         'direction_threshold':.55,'horizons':HORIZONS})
        with self.db:
            old=self.db.execute("SELECT v FROM meta WHERE k='context'").fetchone()
            if old and old['v']!=expected:raise ValueError('SOURCE_OR_CONFIG_CHANGED_USE_NEW_ROOT')
            self.db.execute("INSERT OR IGNORE INTO meta VALUES('context',?)",(expected,))
        self.verify()

    def close(self):self.db.close()

    def log(self,payload):
        prior=self.db.execute('SELECT hash FROM journal ORDER BY seq DESC LIMIT 1').fetchone()
        prev=prior['hash'] if prior else '0'*64
        blob=encode(payload);sha=digest({'previous':prev,'payload':blob})
        self.db.execute('INSERT INTO journal(payload,previous,hash) VALUES(?,?,?)',(blob,prev,sha))

    def model(self,key):
        row=self.db.execute('SELECT state FROM models WHERE k=?',(key,)).fetchone()
        return Branch16(json.loads(row['state'])) if row else Branch16()

    @staticmethod
    def quote(q,now):
        if not q:return None
        bid,ask=q.get('bid'),q.get('ask');at=q.get('observed_ms')
        if (type(at) is not int or not 0<=now-at<=5000 or
            type(bid) not in (float,int) or type(ask) not in (float,int) or
            not math.isfinite(bid) or not math.isfinite(ask) or not 0<bid<=ask):return None
        return bid,ask

    def tick(self,now,events,quotes,histories):
        if type(now) is not int:raise ValueError('CLOCK_TYPE')
        with self.db:
            row=self.db.execute("SELECT v FROM meta WHERE k='last_ms'").fetchone()
            if row and now<int(row['v']):raise ValueError('CLOCK_REVERSED')
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('last_ms',?)",(str(now),))
            # Outcomes and parameter updates commit together; crash/restart cannot learn twice.
            for f in self.db.execute("SELECT * FROM predictions WHERE status='PENDING' AND due<=? ORDER BY due,id",(now,)).fetchall():
                q=self.quote(quotes.get(f['symbol']),now)
                if now-f['due']>30000:
                    self.db.execute("UPDATE predictions SET status='DROPPED',result=? WHERE id=?",
                                    (encode({'reason':'MISSED_MATURITY_NO_FORWARD_BACKFILL','at_ms':now}),f['id']))
                    self.log({'kind':'DROP','id':f['id'],'at_ms':now});continue
                if not q or quotes[f['symbol']]['observed_ms']<f['due']:continue
                bid,ask=q;entry=(f['bid']+f['ask'])/2;exit_mid=(bid+ask)/2
                y=int(exit_mid>entry) if exit_mid!=entry else None
                direction=f['direction']
                # Counterfactual price-taker return: observed bid/ask, fees and extra slippage.
                # No fills/queue/liquidity size/funding assumptions are certified by this proxy.
                gross=(bid/f['ask']-1)*10000 if direction==1 else (1-ask/f['bid'])*10000 if direction==-1 else 0.
                net=gross-14. if direction else 0.
                result={'at_ms':now,'quote':quotes[f['symbol']],'y':y,
                        'brier':(f['p']-y)**2 if y is not None else None,
                        'frozen_brier':.25 if y is not None else None,
                        'counterfactual_net_bps':net,'funding_included':False,'executed':False}
                if y is not None:
                    key=f"{f['symbol']}:{f['h']}";m=self.model(key);x=json.loads(f['x'])
                    # Score the original forecast; train gradient at current parameters.
                    p,cache=m.predict(x);m.learn(x,y,p,cache)
                    self.db.execute('INSERT OR REPLACE INTO models VALUES(?,?)',(key,encode(m.state())))
                self.db.execute("UPDATE predictions SET status='MATURED',result=? WHERE id=?",(encode(result),f['id']))
                self.log({'kind':'OUTCOME','id':f['id'],'result':result})
            groups={}
            for e in events:
                t=e['scheduled_ms']
                # Start observing at/after announcement. A late calendar never creates old predictions.
                if type(t) is not int or not 0<=now-t<=60000:continue
                if e.get('time_granularity','MINUTE')!='MINUTE':continue
                if not e.get('source_url'):continue
                groups.setdefault(t,[]).append(e)
            for anchor,items in sorted(groups.items()):
                types=sorted({e['event_type'] for e in items});cluster='TIME_'+str(anchor)
                for symbol in SYMBOLS:
                    q=self.quote(quotes.get(symbol),now)
                    if not q:continue
                    try:x=causal_features(types,now,histories.get(symbol,[]))
                    except ValueError:continue
                    for h in HORIZONS:
                        if self.db.execute('SELECT 1 FROM predictions WHERE cluster=? AND symbol=? AND h=?',(cluster,symbol,h)).fetchone():continue
                        if self.db.execute("SELECT 1 FROM predictions WHERE symbol=? AND h=? AND status='PENDING'",(symbol,h)).fetchone():continue
                        key=f'{symbol}:{h}';m=self.model(key);p=m.predict(x)[0]
                        direction=1 if p>=.55 else -1 if p<=.45 else 0
                        f={'cluster':cluster,'symbol':symbol,'h':h,'at_ms':now,'due_ms':now+h*1000,
                           'p_up':p,'x':x,'quote':quotes[symbol],'types':types,'source_events':items,
                           'model_sha256':digest(m.state()),'counterfactual_direction':direction,
                           'pre_history':histories[symbol],
                           'action':'OBSERVE','execution_enabled':False}
                        ident=digest(f)
                        self.db.execute('INSERT INTO predictions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (ident,cluster,symbol,h,now,now+h*1000,p,encode(x),q[0],q[1],direction,'PENDING',None))
                        self.log({'kind':'FORECAST','id':ident,'forecast':f})
            return self.status(now,events)

    def status(self,now,events=()):
        counts={r['status']:r['n'] for r in self.db.execute('SELECT status,count(*) n FROM predictions GROUP BY status')}
        scores={}
        for row in self.db.execute("SELECT symbol,h,result FROM predictions WHERE status='MATURED'"):
            result=json.loads(row['result']);key=f"{row['symbol']}:{row['h']}"
            s=scores.setdefault(key,{'n':0,'brier_sum':0.,'counterfactual_net_bps_sum':0.})
            if result['y'] is not None:s['n']+=1;s['brier_sum']+=result['brier']
            s['counterfactual_net_bps_sum']+=result['counterfactual_net_bps']
        upcoming=sorted([e for e in events if now<e['scheduled_ms']<=now+1800000],key=lambda e:e['scheduled_ms'])
        forecasts={f"{r['symbol']}:{r['h']}":{'p_up':r['p'],'at_ms':r['at'],'due_ms':r['due']}
                   for r in self.db.execute("SELECT symbol,h,p,at,due FROM predictions WHERE status='PENDING'")}
        return {'schema':SCHEMA,'at_ms':now,'counts':counts,'scores':scores,
                'upcoming_30min':upcoming,'node_forecasts':forecasts,'action':'OBSERVE','execution_enabled':False,
                'reason':'EVENT_NODE_REQUIRES_INDEPENDENT_COSTED_FORWARD_VALIDATION',
                'calendar_or_consensus_complete':False,'profitability_proven':False,
                'real_orders':0,'historical_backfill_is_forward_evidence':False}

    def verify(self):
        prev='0'*64;predicted=set();outcomes=set();forecasts={};results={};models={}
        for row in self.db.execute('SELECT * FROM journal ORDER BY seq'):
            if row['previous']!=prev or row['hash']!=digest({'previous':prev,'payload':row['payload']}):raise ValueError('JOURNAL_HASH')
            item=json.loads(row['payload']);kind=item['kind'];ident=item['id']
            if kind=='FORECAST':
                if ident in predicted:raise ValueError('DUPLICATE_FORECAST')
                predicted.add(ident)
                f=item['forecast']
                if digest(f)!=ident:raise ValueError('FORECAST_HASH')
                if f['x']!=causal_features(f['types'],f['at_ms'],f['pre_history']):raise ValueError('FEATURE_REPLAY')
                key=f"{f['symbol']}:{f['h']}";m=models.setdefault(key,Branch16())
                if digest(m.state())!=f['model_sha256'] or m.predict(f['x'])[0]!=f['p_up']:raise ValueError('FORECAST_MODEL_REPLAY')
                forecasts[ident]=f
            else:
                if ident not in predicted or ident in outcomes:raise ValueError('OUTCOME_ORDER')
                outcomes.add(ident)
                if kind=='OUTCOME' and not forecasts[ident]['due_ms']<=item['result']['at_ms']<=forecasts[ident]['due_ms']+30000:
                    raise ValueError('OUTCOME_TIME')
                results[ident]=item
                if kind=='OUTCOME':
                    f=forecasts[ident];out=item['result'];q=out['quote']
                    if not self.quote(q,out['at_ms']) or q['observed_ms']<f['due_ms']:raise ValueError('OUTCOME_QUOTE')
                    entry=(f['quote']['bid']+f['quote']['ask'])/2;exit_mid=(q['bid']+q['ask'])/2
                    y=int(exit_mid>entry) if exit_mid!=entry else None
                    if out['y']!=y or out['brier']!=((f['p_up']-y)**2 if y is not None else None):raise ValueError('OUTCOME_SCORE')
                    if y is not None:
                        key=f"{f['symbol']}:{f['h']}";m=models[key];p,cache=m.predict(f['x'])
                        m.learn(f['x'],y,p,cache)
            prev=row['hash']
        if len(predicted)!=self.db.execute('SELECT count(*) FROM predictions').fetchone()[0]:raise ValueError('JOURNAL_TABLE_COUNT')
        for row in self.db.execute('SELECT * FROM predictions'):
            f=forecasts[row['id']]
            actual=(row['cluster'],row['symbol'],row['h'],row['at'],row['due'],row['p'],json.loads(row['x']),row['bid'],row['ask'],row['direction'])
            expected=(f['cluster'],f['symbol'],f['h'],f['at_ms'],f['due_ms'],f['p_up'],f['x'],f['quote']['bid'],f['quote']['ask'],f['counterfactual_direction'])
            if actual!=expected:raise ValueError('FORECAST_TABLE_TAMPERED')
            result=results.get(row['id'])
            status='MATURED' if result and result['kind']=='OUTCOME' else 'DROPPED' if result else 'PENDING'
            if row['status']!=status:raise ValueError('OUTCOME_TABLE_STATUS')
            if status=='MATURED' and json.loads(row['result'])!=result['result']:raise ValueError('OUTCOME_TABLE_TAMPERED')
        saved={r['k']:json.loads(r['state']) for r in self.db.execute('SELECT * FROM models')}
        replayed={k:m.state() for k,m in models.items() if m.updates}
        if saved!=replayed:raise ValueError('MODEL_STATE_REPLAY')
        return {'forecasts':len(predicted),'outcomes':len(outcomes),'journal_head':prev}


def capture(symbol):
    start=time.time_ns()
    with urlopen('https://fapi.binance.com/fapi/v1/depth?symbol='+symbol+'&limit=5',timeout=8) as stream:
        body=stream.read(100001)
    at=time.time_ns()//1000000
    if len(body)>100000 or at-start//1000000>5000:raise ValueError('QUOTE_RESPONSE_BUDGET_OR_LATENCY')
    raw=json.loads(body)
    if type(raw.get('T')) is not int or abs(at-raw['T'])>5000:raise ValueError('STALE_EXCHANGE_QUOTE_OR_CLOCK')
    return {'observed_ms':at,'bid':float(raw['bids'][0][0]),'ask':float(raw['asks'][0][0]),
            'source':'BINANCE_USDM_PUBLIC_DEPTH5','raw':raw,'raw_sha256':hashlib.sha256(body).hexdigest()}


def run(root,calendar,seconds,book_state=None):
    if not 1<=seconds<=3600:raise ValueError('BOUNDED_RUN_REQUIRED_1_TO_3600_SECONDS')
    if __import__('os').name=='nt':
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    with exclusive(root):
        loop=ForwardLoop(root/'forward.sqlite3');end=time.monotonic()+seconds;errors=[];histories={};last_history=0
        body=Path(calendar).read_bytes();doc=json.loads(body);events=doc.get('events',doc.get('plans',[]))
        atomic(root/'calendar_snapshot.json',{'loaded_ms':time.time_ns()//1000000,'source_path':str(calendar),
                                            'raw_sha256':hashlib.sha256(body).hexdigest(),'events':events})
        try:
            while time.monotonic()<end:
                if (shutil.disk_usage(root).free<1073741824 or
                    sum(p.stat().st_size for p in root.glob('forward.sqlite3*'))>100000000):
                    raise RuntimeError('RESEARCH_DISK_BUDGET_PAUSE')
                quotes={}
                # No quote polling outside an event window or outstanding maturity window.
                now=time.time_ns()//1000000
                active=any(0<=now-e['scheduled_ms']<=60000 for e in events)
                pending=loop.db.execute("SELECT count(*) FROM predictions WHERE status='PENDING'").fetchone()[0]
                if active or pending:
                    for symbol in SYMBOLS:
                        try:
                            quotes[symbol]=capture(symbol)
                            if active and now-last_history>30000:
                                bars=public('klines',{'symbol':symbol,'interval':'1m','limit':62})
                                histories[symbol]=[{'time':r[0],'open':r[1],'close':r[4]} for r in bars if r[6]<now]
                        except Exception as exc:errors.append({'symbol':symbol,'error':str(exc),'at_ms':now})
                    if active:last_history=now
                status=loop.tick(time.time_ns()//1000000,events,quotes,histories)
                status['unified_advisory']={s:{'action':'OBSERVE','reason':'NO_FRESH_ORDERBOOK_COUNCIL_INPUT',
                                              'execution_enabled':False} for s in SYMBOLS}
                if book_state:
                    from .four_market_runner import checked
                    from .event_council_bridge import combine
                    try:
                        book_path=Path(book_state)
                        if book_path.stat().st_size>10000000:raise ValueError('BOOK_STATE_BUDGET')
                        book=checked(json.loads(book_path.read_text(encoding='utf-8')))
                        council=book.get('engine',book).get('council',{})
                        for symbol,decision in council.items():
                            try:status['unified_advisory'][symbol]=combine(decision,status,status['at_ms'])
                            except ValueError as exc:errors.append({'symbol':symbol,'error':str(exc),'at_ms':now})
                    except Exception as exc:errors.append({'source':'book_state','error':str(exc),'at_ms':now})
                status.update(errors=errors[-20:],calendar_sha256=hashlib.sha256(body).hexdigest(),resident=False)
                atomic(root/'status.json',status)
                time.sleep(min(5,max(0,end-time.monotonic())))
            status.update(loop.verify());status['state']='BOUNDED_RUN_FINISHED'
            atomic(root/'status.json',status)
            print(encode(status),flush=True)
        finally:loop.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='D:/CQWE_DATA/event_forward_v1')
    p.add_argument('--calendar',default='reports/macro_watch_plan_expanded_20261016.json')
    p.add_argument('--seconds',type=int,default=60)
    p.add_argument('--book-state',help='Optional checksummed fresh shadow council checkpoint; advisory only')
    a=p.parse_args();run(a.root,a.calendar,a.seconds,a.book_state)
