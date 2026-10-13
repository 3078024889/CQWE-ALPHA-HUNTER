"""Offline cash-only execution simulator. Research, never an exchange trading client."""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class Parameters:
    starting_cash: float = 10.0
    allocation: float = 0.20
    fee_bps: float = 5.0
    slippage_bps: float = 2.0
    max_equity_drawdown: float = 0.05
    hold_bars: int = 12

    def __post_init__(self):
        if not all(math.isfinite(x) for x in (self.starting_cash,self.allocation,self.fee_bps,self.slippage_bps,self.max_equity_drawdown)):
            raise ValueError('non-finite parameters')
        if self.starting_cash <= 0 or not 0 < self.allocation <= 1 or not 0 < self.max_equity_drawdown < 1 or self.fee_bps < 0 or self.slippage_bps < 0 or self.hold_bars < 1:
            raise ValueError('invalid parameters')


def simulate(candles, decisions, params=Parameters()):
    """Decisions: index of completed signal bar -> {'long', 'flat'}.

    Enter at next candle OPEN, exit at horizon candle CLOSE; no leverage.
    If signal is overlapping an open position, ignore it.
    Fee/slippage charged on executed notional. No TP/SL or liquidation modeled.
    """
    cash = params.starting_cash
    qty = 0.0
    exit_index = -1
    trades = []
    peak = cash
    max_dd = 0.0
    stopped = False
    equity_curve = []
    pending = None
    for i, bar in enumerate(candles):
        price = float(bar[4])
        if price <= 0 or not math.isfinite(price):
            raise ValueError('invalid price')
        # Exit at close, after all intra-bar uncertainty; no impossible intrabar stop assumption.
        if qty > 0 and i == exit_index:
            fill = price * (1 - params.slippage_bps / 10000)
            gross = qty * fill
            fee = gross * params.fee_bps / 10000
            cash += gross - fee
            trades[-1].update(exit_index=i, exit_fill=fill, pnl=cash - trades[-1]['cash_before'])
            qty = 0.0
        equity = cash + qty * price
        peak = max(peak, equity)
        dd = 1 - equity / peak
        max_dd = max(max_dd, dd)
        if dd >= params.max_equity_drawdown:
            stopped = True
        if pending is not None and i == pending and qty == 0 and not stopped and i + params.hold_bars - 1 < len(candles):
            open_ = float(bar[1]); fill = open_ * (1 + params.slippage_bps/10000)
            amount = cash * params.allocation
            fee = amount * params.fee_bps/10000
            prior = cash
            qty = (amount-fee)/fill
            cash -= amount
            exit_index = i + params.hold_bars - 1
            trades.append({'entry_index':i,'entry_fill':fill,'cash_before':prior,'size_cash':amount,'entry_fee':fee})
            pending = None
        if i in decisions and decisions[i] == 'long' and qty == 0 and not stopped and pending is None:
            pending = i+1
        equity_curve.append(round(cash + qty * price, 9))
    if qty > 0:
        raise ValueError('unclosed position: insufficient horizon')
    final_equity = cash
    return {'initial_cash':params.starting_cash,'final_equity':round(final_equity,8),
            'net_profit':round(final_equity-params.starting_cash,8),
            'max_drawdown_pct':round(max_dd*100,5),'trades':trades,'stopped':stopped,
            'equity_curve':equity_curve,'simulation_only':True,'leverage':1}
