"""Closed-candle reversal and trailing protection; independent of forecast horizons."""
from decimal import Decimal as D

POLICY='CLOSED_1M_REVERSAL_TRAILING_V1'


def validate_bars(raw,now):
    bars=[]
    for r in raw:
        if len(r)!=12 or type(r[0]) is not int or r[6]!=r[0]+59999:raise ValueError('CANDLE_SCHEMA')
        if r[6]>=now:continue
        o,h,l,c=map(D,map(str,r[1:5]))
        if any(not p.is_finite() or p<=0 for p in (o,h,l,c)) or h<max(o,c) or l>min(o,c) or h<l:
            raise ValueError('CANDLE_OHLC')
        if bars and r[0]!=bars[-1]['time']+60000:raise ValueError('CANDLE_GAP')
        bars.append({'time':r[0],'end':r[6],'open':str(o),'high':str(h),'low':str(l),'close':str(c)})
    return bars


def evaluate(position,bid,ask,at,bars=()):
    direction=D(position['direction']);entry=D(position['entry'])
    px=bid if direction==1 else ask
    move=direction*(px/entry-1)*10000
    tracking=position.setdefault('exit_tracking',{'best_move_bps':str(max(D(0),move)),
        'trailing_armed':False,'reverse_confirmations':0,'last_bar_end':None})
    best=max(D(tracking['best_move_bps']),move);tracking['best_move_bps']=str(best)
    tracking['trailing_armed']=best>=40
    position['exit_policy']=POLICY
    tracking['current_move_bps']=str(move)
    if move<=-30:return 'STOP_LOSS'
    if best>=40 and best-move>=20:return 'TRAILING_PROFIT_EXIT'
    # Only newly closed candles after entry can confirm reversal. Never use a forming candle.
    eligible=[b for b in bars if b['end']>position['opened_ms'] and b['end']<at]
    if not eligible:
        tracking['candle_status']='WAIT_FOR_CLOSED_POST_ENTRY_CANDLES';return None
    last=eligible[-1]
    if at-last['end']>90000:
        tracking['candle_status']='STALE_CANDLES';return None
    if len(eligible)<2:
        tracking['candle_status']='WAIT_FOR_SECOND_CANDLE';return None
    a,b=eligible[-2:]
    if b['time']-a['time']!=60000:
        tracking['candle_status']='CANDLE_GAP';return None
    opposite=[direction*(D(v['close'])-D(v['open']))<0 for v in (a,b)]
    tracking['reverse_confirmations']=sum(opposite)
    tracking['last_bar_end']=b['end'];tracking['candle_status']='FRESH'
    change=direction*(D(b['close'])/D(a['open'])-1)*10000
    further=direction*(D(b['close'])-D(a['close']))<0
    if all(opposite) and further and change<=-5:return 'CANDLE_REVERSAL'
    return None
