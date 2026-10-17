"""V58 conservative fill simulation, bounded to a $10 unlevered cash account."""
from decimal import Decimal
from .cash_truth_v56 import money

def execute(cash, *, side, quantity, price, fee_bps, slip_bps, delay_ms=0, available_quantity=None):
    cash=money(cash); qty=money(quantity); px=money(price); fee=money(fee_bps); slip=money(slip_bps)
    if cash<0 or qty<=0 or px<=0 or fee<0 or slip<0 or side!='buy': raise ValueError('INVALID_UNLEVERAGED_ORDER')
    if not isinstance(delay_ms,int) or isinstance(delay_ms,bool) or delay_ms<0: raise ValueError('INVALID_DELAY')
    avail=qty if available_quantity is None else money(available_quantity)
    if avail<0: raise ValueError('INVALID_LIQUIDITY')
    filled=min(qty,avail)
    fill_price=px*(Decimal(1)+slip/Decimal(10000))
    total=filled*fill_price*(Decimal(1)+fee/Decimal(10000))
    if total>cash: return {'status':'REJECTED_INSUFFICIENT_CASH','filled_quantity':'0','simulated':True}
    status='FILLED' if filled==qty else ('PARTIAL' if filled>0 else 'UNFILLED')
    return {'status':status,'filled_quantity':str(filled),'gross_notional_usd':str(filled*fill_price),'fees_usd':str(filled*fill_price*fee/Decimal(10000)),'cash_after_usd':str(cash-total),'delay_ms':delay_ms,'simulated':True,'actual_profit_usd':None}
