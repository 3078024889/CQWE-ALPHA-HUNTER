"""Versioned shadow forecasts. Nothing here places or authorizes an order."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from . import strategy_candidates

HOUR=3600000


def admission(history,forward,quality):
    reasons=[]
    if history.get('historical_gate_pass') is not True:reasons.append('HISTORY_NOT_PASSED')
    if forward.get('n',0)<100 or forward.get('span_days',0)<30:reasons.append('FORWARD_SAMPLE_INSUFFICIENT')
    edge=forward.get('net_lower_confidence_bps',float('-inf'))
    if not math.isfinite(edge) or edge<=0:reasons.append('NET_EDGE_NOT_ESTABLISHED')
    for key in ('funding_reconciled','order_filters_validated','execution_model_validated','selection_bias_checked'):
        if quality.get(key) is not True:reasons.append(key.upper())
    return {'research_gate_pass':not reasons,'reasons':reasons,'execution_weight':0,'real_orders_enabled':False}


def targets_from_closed_history(histories,at):
    if set(histories)!=set(strategy_candidates.SYMBOLS):raise ValueError('FOUR_HISTORIES_REQUIRED')
    data={}
    for s,rows in histories.items():
        bars=[]
        for r in rows:
            if int(r[6])>=at:continue
            t=int(r[0]);o,h,l,c=map(float,(r[1],r[2],r[3],r[4]))
            if int(r[6])!=t+HOUR-1 or not all(math.isfinite(x) and x>0 for x in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('BAD_RESEARCH_BAR')
            if bars and t-bars[-1]['time']!=HOUR:raise ValueError('RESEARCH_HISTORY_GAP')
            bars.append({'time':t,'open':o,'high':h,'low':l,'close':c})
        if len(bars)<722 or not 0<=at-(bars[-1]['time']+HOUR)<=HOUR:raise ValueError('RESEARCH_HISTORY_INCOMPLETE_OR_STALE')
        # Placeholder supplies a next-bar signal; its own prices are never inputs to that signal.
        last=bars[-1];bars.append({'time':last['time']+HOUR,**{k:last['close'] for k in ('open','high','low','close')}})
        data[s]=bars
    return {key:values[-1] for key,values in strategy_candidates.candidates(data).items()}


class ShadowBench:
    def __init__(self,path):
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);'
            'CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY,candidate TEXT,created INTEGER,due INTEGER,payload TEXT,status TEXT);'
            'CREATE TABLE IF NOT EXISTS outcomes(id TEXT PRIMARY KEY,at INTEGER,net_proxy_bps REAL,payload TEXT);')
        source=hashlib.sha256(Path(__file__).read_bytes()+Path(strategy_candidates.__file__).read_bytes()).hexdigest()
        old=self.db.execute("SELECT value FROM meta WHERE key='source'").fetchone()
        if old and old[0]!=source:self.db.close();raise ValueError('SHADOW_SOURCE_CHANGED_USE_NEW_LEDGER')
        with self.db:self.db.execute("INSERT OR IGNORE INTO meta VALUES('source',?)",(source,))
        self.source=source

    @staticmethod
    def fresh(quotes,symbols,at):
        return all(s in quotes and 0<=at-quotes[s].get('observed_ms',-100000)<=15000
                   and all(math.isfinite(quotes[s].get(k,0)) for k in ('bid','ask'))
                   and 0<quotes[s]['bid']<=quotes[s]['ask'] for s in symbols)

    def tick(self,quotes,at,targets=None):
        with self.db:
            for ident,due,payload in self.db.execute("SELECT id,due,payload FROM forecasts WHERE status='PENDING' AND due<=?",(at,)).fetchall():
                p=json.loads(payload);weights=p['weights']
                if at-due>30000:
                    self.db.execute("UPDATE forecasts SET status='MISSED' WHERE id=?",(ident,));continue
                if not self.fresh(quotes,weights,at):continue
                gross=0.;fees=0.;exits={}
                for s,w in weights.items():
                    px=quotes[s]['bid']*(1-.0002) if w>0 else quotes[s]['ask']*(1+.0002)
                    ratio=px/p['entries'][s];gross+=w*(ratio-1);fees+=abs(w)*.0005*(1+ratio);exits[s]=px
                net=(gross-fees)*10000
                outcome={'at_ms':at,'exit_prices':exits,'net_proxy_bps':net,'funding_reconciled':False,
                         'kind':'ONE_HOUR_OPPORTUNITY_PROXY_NOT_STRATEGY_PNL','execution_weight':0}
                self.db.execute('INSERT INTO outcomes VALUES(?,?,?,?)',(ident,at,net,json.dumps(outcome)))
                self.db.execute("UPDATE forecasts SET status='SCORED' WHERE id=?",(ident,))
            for candidate,weights in (targets or {}).items():
                if not weights:continue
                if not all(s in strategy_candidates.SYMBOLS and math.isfinite(w) and w!=0 for s,w in weights.items()) or not math.isclose(sum(abs(w) for w in weights.values()),1,abs_tol=1e-8):raise ValueError('BAD_SHADOW_WEIGHTS')
                if not self.fresh(quotes,weights,at):continue
                if self.db.execute("SELECT 1 FROM forecasts WHERE candidate=? AND status='PENDING'",(candidate,)).fetchone():continue
                ident=candidate+':'+str(at//HOUR)
                p={'source':self.source,'weights':weights,'entries':{s:quotes[s]['ask']*(1+.0002) if w>0 else quotes[s]['bid']*(1-.0002) for s,w in weights.items()},
                   'at_ms':at,'due_ms':at+HOUR,'horizon_seconds':3600,'execution_weight':0}
                self.db.execute("INSERT OR IGNORE INTO forecasts VALUES(?,?,?,?,?,'PENDING')",(ident,candidate,at,at+HOUR,json.dumps(p,sort_keys=True)))

    def snapshot(self):
        counts=dict(self.db.execute('SELECT status,count(*) FROM forecasts GROUP BY status'))
        nodes=[]
        for candidate,n,avg,sq,first,last in self.db.execute('SELECT f.candidate,count(*),avg(o.net_proxy_bps),sum(o.net_proxy_bps*o.net_proxy_bps),min(o.at),max(o.at) FROM forecasts f JOIN outcomes o ON f.id=o.id GROUP BY f.candidate'):
            var=max(0,(sq-n*avg*avg)/(n-1)) if n>1 else 0.
            # Online descriptive node score; proxy omits funding, so never used for trading.
            nodes.append({'id':candidate,'n':n,'mean_proxy_bps':avg,'proxy_lower_confidence_bps':avg-3*math.sqrt(var/n),
                          'span_days':(last-first)/86400000,'execution_weight':0,'funding_reconciled':False})
        return {'counts':counts,'nodes':nodes,'source_sha256':self.source,'horizon_seconds':3600,'real_orders':0,
                'label':'Shadow opportunities only; not fills or complete strategy P&L','profitability_proven':False}


class ResearchLoop:
    def __init__(self,path,fetch,catalog=None):
        self.bench=ShadowBench(path);self.fetch=fetch;self.histories={};self.checked={};self.cursor=0;self.last_proposed=None;self.errors={};self.targets=None
        self.catalog=catalog or []

    def refresh_one(self,at):
        s=strategy_candidates.SYMBOLS[self.cursor%4];self.cursor+=1
        if self.checked.get(s)==at//HOUR:return
        self.checked[s]=at//HOUR
        try:
            rows=self.fetch('klines',{'symbol':s,'interval':'1h','limit':800})
            self.histories[s]=rows;self.errors.pop(s,None)
        except Exception as exc:self.histories.pop(s,None);self.errors[s]=str(exc)[:160]

    def tick(self,quotes,at):
        if self.last_proposed!=at//HOUR and len(self.histories)==4:
            try:
                self.targets=targets_from_closed_history(self.histories,at)
                self.last_proposed=at//HOUR
            except (ValueError,KeyError,IndexError,TypeError) as exc:self.errors['history']=str(exc)[:160]
            else:self.errors.pop('history',None)
        self.bench.tick(quotes,at,self.targets if self.last_proposed==at//HOUR else None)
        snapshot=self.bench.snapshot();observed={n['id']:n for n in snapshot['nodes']}
        snapshot['admission']=[{'id':h['id'],**admission(h,
            {**observed.get(h['id'],{}),'net_lower_confidence_bps':float('-inf')},
            {'funding_reconciled':False,'order_filters_validated':False,'execution_model_validated':False,'selection_bias_checked':False})}
            for h in self.catalog]
        return {**snapshot,'errors':self.errors.copy(),'cached_symbols':list(self.histories)}

    def close(self):self.bench.db.close()
