"""Low-frequency observable orderflow, book changes, OI and funding context."""
import hashlib
import json
import math
import time
from urllib.parse import urlencode
from urllib.request import urlopen
from .liquidity_research import LiquidityTape


def request(endpoint,params):
    if endpoint not in ('aggTrades','openInterest','premiumIndex'):raise ValueError('PUBLIC_ENDPOINT_ONLY')
    with urlopen('https://fapi.binance.com/fapi/v1/'+endpoint+'?'+urlencode(params),timeout=4) as r:body=r.read(600001)
    if len(body)>600000:raise ValueError('MARKET_CONTEXT_BUDGET')
    return json.loads(body),hashlib.sha256(body).hexdigest()


class MarketEvidence:
    def __init__(self):
        self.tape=LiquidityTape();self.aux={};self.samples={};self.last={};self.mids={};self.oi_history={}

    def capture(self,symbol,quote,stream=None):
        now=time.time_ns()//1000000;exchange=quote['raw']['T'];errors=[]
        rows,sha=request('aggTrades',{'symbol':symbol,'startTime':exchange-10000,'endTime':exchange,'limit':1000})
        if not isinstance(rows,list):raise ValueError('AGGREGATE_TRADE_SCHEMA')
        complete=len(rows)<1000 and all(rows[i]['a']==rows[i-1]['a']+1 for i in range(1,len(rows)))
        # Missing/truncated batches never qualify as full recent orderflow.
        aux=self.aux.setdefault(symbol,{})
        streamed_mark=stream.get('mark') if stream else None
        if streamed_mark and 0<=now-streamed_mark['received_ms']<=5000:
            e=streamed_mark['event']
            obj={'symbol':symbol,'markPrice':e['p'],'indexPrice':e['i'],'lastFundingRate':e['r'],
                 'nextFundingTime':e['T'],'time':e['E']}
            aux['premiumIndex']={'raw':obj,'sha256':hashlib.sha256(json.dumps(e,sort_keys=True).encode()).hexdigest(),
                                 'received_ms':streamed_mark['received_ms']}
        for endpoint in ('openInterest','premiumIndex'):
            old=aux.get(endpoint)
            if not old or now-old['received_ms']>=30000:
                try:
                    obj,hash_=request(endpoint,{'symbol':symbol})
                    if obj.get('symbol')!=symbol:raise ValueError('SYMBOL_MISMATCH')
                    aux[endpoint]={'raw':obj,'sha256':hash_,'received_ms':time.time_ns()//1000000}
                except Exception as exc:errors.append(endpoint+': '+str(exc))
        return {'rows':rows,'trade_sha256':sha,'complete':complete,'received_ms':time.time_ns()//1000000,
                'exchange_ms':exchange,'aux':aux.copy(),'errors':errors,'stream':stream or {}}

    def frame(self,symbol,quote,batch,at):
        if not batch:return {'ready':False,'reason':'MISSING_ORDERFLOW','features':[0.]*8}
        now_ns=time.monotonic_ns();last=self.last.get(symbol)
        if last and at-last>20000:self.tape.invalidate(symbol);self.samples[symbol]=0
        price_move=((quote['bid']+quote['ask'])/2/self.mids[symbol]-1)*10000 if symbol in self.mids and last and at-last<=20000 else 0.
        self.last[symbol]=at;self.mids[symbol]=(quote['bid']+quote['ask'])/2
        stream=batch.get('stream',{})
        for item in stream.get('orders',[]):
            self.tape.context('LIQUIDATION',symbol,item['event'],item['received_ns'])
        for r in batch['rows']:
            if (type(r.get('m')) is not bool or type(r.get('a')) is not int or type(r.get('T')) is not int
                or not batch['exchange_ms']-10000<=r['T']<=batch['exchange_ms']):raise ValueError('TRADE_LAYOUT_OR_TIME')
            event={'s':symbol,'m':r['m'],'a':r['a'],'p':r['p'],'q':r['q']}
            self.tape.trade(symbol,event,now_ns)
        raw=quote['raw'];view={'mid':str((quote['bid']+quote['ask'])/2),'bids':raw['bids'],'asks':raw['asks']}
        x,quality=self.tape.sample(symbol,view,now_ns,at)
        self.samples[symbol]=self.samples.get(symbol,0)+1
        aux=batch['aux'];mark=aux.get('premiumIndex');oi=aux.get('openInterest')
        mark_ok=bool(mark and 0<=at-mark['received_ms']<=60000)
        oi_ok=bool(oi and 0<=at-oi['received_ms']<=90000)
        funding_soon=False;funding=None;basis=0.;oi_value=None;oi_change=0.
        if mark_ok:
            m=mark['raw'];funding=float(m['lastFundingRate'])
            basis=math.tanh((float(m['markPrice'])/float(m['indexPrice'])-1)*1000)
            offset=batch['exchange_ms']-quote['observed_ms']
            funding_soon=0<=m['nextFundingTime']-(at+offset)<=300000
        if oi_ok:
            oi_value=float(oi['raw']['openInterest']);old=self.oi_history.get(symbol)
            if not math.isfinite(oi_value) or oi_value<0:raise ValueError('OI_VALUE')
            if not old or old['at']!=oi['received_ms']:
                change=math.tanh((oi_value/old['value']-1)*100) if old and old['value'] else 0.
                self.oi_history[symbol]={'at':oi['received_ms'],'value':oi_value,'change':change}
            oi_change=self.oi_history[symbol]['change']
        if not all(math.isfinite(v) for v in x+[basis]):raise ValueError('NONFINITE_EVIDENCE')
        return {'at_ms':at,'ready':batch['complete'] and at-batch['received_ms']<=15000 and self.samples[symbol]>=3,
            'features':x[:6]+[basis,oi_change], 'flow':x[2],'depletion':x[0],'refill':x[1],'breakout':x[3],
            'price_move_bps':price_move,'oi_change':oi_change,
            'mark_fresh':mark_ok,'oi_fresh':oi_ok,'open_interest':oi_value,'funding_rate':funding,
            'funding_window_veto':funding_soon,'trade_batch_complete':batch['complete'],
            'trade_count':len(batch['rows']),'samples':self.samples[symbol],
            'source_hashes':{'trades':batch['trade_sha256'],'mark':mark['sha256'] if mark else None,
                             'oi':oi['sha256'] if oi else None},
            'liquidations_available':bool(stream.get('connected')),'sampled_liquidations_only':True,
            'maker_identity_known':False,'stop_orders_visible':False,
            'cancellation_vs_execution_identified':False,'sampling':'REST10s-trades_and_5-level-snapshots'}
