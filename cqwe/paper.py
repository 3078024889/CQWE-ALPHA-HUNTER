"""Cash-only, long-only paper ledger; isolated from any real exchange account."""
from dataclasses import dataclass,field

@dataclass
class Ledger:
    cash:float=10.0
    qty:float=0.0
    fees:float=0.0
    trades:list=field(default_factory=list)
    max_allocation:float=.20
    fee_bps:float=5.0
    slippage_bps:float=2.0
    initial:float=10.0
    stopped:bool=False

    def __post_init__(self):
        if self.cash<=0 or not 0<self.max_allocation<=1: raise ValueError('invalid ledger')
        self.initial=self.cash

    def equity(self,price):
        if price<=0:raise ValueError('invalid price')
        return self.cash+self.qty*price

    def buy(self,price,allocation=None):
        if self.stopped or self.qty>0: return False
        if price<=0: raise ValueError('bad price')
        allocation=self.max_allocation if allocation is None else min(allocation,self.max_allocation)
        if not 0<allocation<=self.max_allocation: raise ValueError('allocation outside limit')
        budget=self.cash*allocation; fill=price*(1+self.slippage_bps/10000)
        commission=budget*self.fee_bps/10000
        self.qty=(budget-commission)/fill; self.cash-=budget;self.fees+=commission
        self.trades.append({'side':'PAPER_BUY','qty':self.qty,'fill':fill,'commission':commission})
        return True

    def sell(self,price):
        if price<=0: raise ValueError('bad price')
        if self.qty<=0: return False
        fill=price*(1-self.slippage_bps/10000)
        gross=self.qty*fill;commission=gross*self.fee_bps/10000
        self.cash+=gross-commission;self.fees+=commission
        self.trades.append({'side':'PAPER_SELL','qty':self.qty,'fill':fill,'commission':commission})
        self.qty=0
        if self.cash < self.initial*.95:self.stopped=True
        return True
