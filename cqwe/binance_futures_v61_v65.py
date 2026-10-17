"""CQWE V61–65: Binance USD-M futures research sandbox. No live endpoints/orders.
Data is caller-supplied snapshots. Strict Decimal accounting; absolutely no API keys.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json

D = Decimal

def num(x):
    if isinstance(x, bool) or isinstance(x, float):
        raise ValueError('DECIMAL_STRING_REQUIRED')
    try: v = D(str(x))
    except (InvalidOperation, ValueError): raise ValueError('INVALID_NUMBER') from None
    if not v.is_finite(): raise ValueError('NONFINITE_NUMBER')
    return v

def gtzero(x):
    x=num(x)
    if x<=0: raise ValueError('POSITIVE_REQUIRED')
    return x

@dataclass(frozen=True)
class Rules:
    symbol: str
    min_qty: Decimal
    step: Decimal
    tick: Decimal
    min_notional: Decimal
    max_qty: Decimal

    @classmethod
    def parse(cls, payload, symbol):
        # Explicitly use exchangeInfo symbol filters, never assume defaults.
        found = [s for s in payload.get('symbols',[]) if s.get('symbol')==symbol and s.get('status')=='TRADING']
        if len(found)!=1: raise ValueError('SYMBOL_NOT_TRADING')
        filters={f['filterType']:f for f in found[0].get('filters',[])}
        try:
            lot=filters['LOT_SIZE'];price=filters['PRICE_FILTER'];notional=filters['MIN_NOTIONAL']
            return cls(symbol, gtzero(lot['minQty']), gtzero(lot['stepSize']), gtzero(price['tickSize']),
                       gtzero(notional['notional']),gtzero(lot['maxQty']))
        except (KeyError,TypeError): raise ValueError('MISSING_EXCHANGE_FILTER') from None

    def check(self, quantity, price):
        qty=gtzero(quantity); px=gtzero(price)
        if qty<self.min_qty or qty>self.max_qty or qty%self.step!=0: raise ValueError('LOT_FILTER_FAIL')
        if px%self.tick!=0: raise ValueError('PRICE_FILTER_FAIL')
        if qty*px<self.min_notional: raise ValueError('NOTIONAL_FILTER_FAIL')
        return qty,px

class Sandbox:
    """Isolated one-way position, symmetric entry/exit costs, explicit funding.
    This is NOT an exchange liquidation engine or live matching engine.
    """
    def __init__(self, capital='10', max_fraction='0.2', fee_bps='5', slip_bps='5'):
        self.initial=gtzero(capital);self.cash=self.initial
        self.fraction=gtzero(max_fraction)
        if self.fraction>1: raise ValueError('INVALID_RISK_FRACTION')
        self.fee=num(fee_bps);self.slip=num(slip_bps)
        if min(self.fee,self.slip)<0:raise ValueError('NEGATIVE_COST')
        self.position=None;self.log=[]

    def open(self, rules, side, quantity, price, *, leverage=1, timestamp_ms=None):
        if self.position is not None:raise ValueError('ONE_POSITION_ONLY')
        if side not in ('LONG','SHORT'):raise ValueError('INVALID_SIDE')
        if leverage!=1: raise ValueError('LEVERAGE_DISABLED')
        qty,px=rules.check(quantity,price)
        execution=px*(1+(self.slip if side=='LONG' else -self.slip)/D(10000))
        notional=qty*execution; fee=notional*self.fee/D(10000)
        if notional+fee>self.cash*self.fraction:raise ValueError('RISK_CAP_EXCEEDED')
        self.cash-=fee
        self.position={'side':side,'qty':qty,'entry':execution,'margin':notional,'entry_fee':fee,
                       'symbol':rules.symbol,'timestamp_ms':timestamp_ms}
        self.log.append({'event':'OPEN','symbol':rules.symbol,'side':side,'qty':str(qty),'price':str(execution),'fee':str(fee),'simulated':True})
        return self.log[-1]

    def close(self, price, *, funding_bps='0'):
        if self.position is None:raise ValueError('NO_POSITION')
        pos=self.position;px=gtzero(price);fund=num(funding_bps)
        if abs(fund)>D(10000):raise ValueError('FUNDING_OUT_OF_RANGE')
        exit_price=px*(1+(-self.slip if pos['side']=='LONG' else self.slip)/D(10000))
        direction=D(1) if pos['side']=='LONG' else D(-1)
        pnl=(exit_price-pos['entry'])*pos['qty']*direction
        exit_fee=exit_price*pos['qty']*self.fee/D(10000)
        # Positive funding: long pays short; negative: short pays long.
        funding=pos['margin']*fund/D(10000)*direction
        self.cash+=pnl-exit_fee-funding
        result={'event':'CLOSE','symbol':pos['symbol'],'gross_pnl':str(pnl),'entry_fee':str(pos['entry_fee']),
                'exit_fee':str(exit_fee),'funding_paid':str(funding),
                'roundtrip_net_pnl':str(pnl-pos['entry_fee']-exit_fee-funding),
                'equity':str(self.cash),'simulated':True,'realized_cash_profit':None}
        self.position=None;self.log.append(result)
        return result

    def report(self):
        if self.position is not None:raise ValueError('OPEN_POSITION_UNMARKED')
        r={'mode':'OFFLINE_RESEARCH_ONLY','initial_usd':str(self.initial),'ending_equity_usd':str(self.cash),
           'simulated_net_usd':str(self.cash-self.initial),'real_cash_pnl_usd':None,
           'events':self.log,'live_order_enabled':False,'leverage_enabled':False}
        r['sha256']=sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()
        return r


def reject_unsafe_environment(config):
    if not isinstance(config,dict) or config.get('mode')!='OFFLINE':raise ValueError('LIVE_MODE_BLOCKED')
    if any(k.lower() in ('api_key','secret','api_secret','private_key') for k in config):raise ValueError('CREDENTIALS_NOT_ACCEPTED')
    if config.get('auto_promotion',False) or config.get('live_trading',False):raise ValueError('AUTONOMY_BLOCKED')
    return True
