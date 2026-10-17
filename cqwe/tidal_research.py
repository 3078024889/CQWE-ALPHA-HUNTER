"""Causal book/flow learning and explicitly virtual, unlevered lifecycle research.

No private keys, order endpoints or autonomous real-money execution.
Thresholds are fixed experimental assumptions, not a trading recommendation.
"""
import collections
import copy
import math
from decimal import Decimal, ROUND_DOWN

from .copernican_experiment_v81_v85 import Network, digest
from .futures_orderbook import BookFault, number

D = Decimal


class FlowFeatures:
    def __init__(self):
        self.trades = collections.deque(maxlen=10000)
        self.last_trade_id = -1
        self.previous = None

    def trade(self, e, received_ns, symbol):
        if e.get('e') != 'aggTrade' or e.get('s') != symbol or type(e.get('m')) is not bool:
            raise BookFault('WRONG_AGG_TRADE')
        if type(e.get('a')) is not int or e['a'] < 0:
            raise BookFault('INVALID_TRADE_ID')
        price, quantity = number(e.get('p'), positive=True), number(e.get('q'), positive=True)
        if e['a'] <= self.last_trade_id:
            return
        self.last_trade_id = e['a']
        # m=True: buyer is maker, so this is seller-initiated volume.
        self.trades.append((received_ns, float(price*quantity)*(-1 if e['m'] else 1)))

    def sample(self, view, now_ns):
        while self.trades and self.trades[0][0] < now_ns-2_000_000_000:
            self.trades.popleft()
        values = [v for t,v in self.trades if now_ns-2_000_000_000 <= t <= now_ns]
        flow = sum(values)/sum(abs(v) for v in values) if values else 0.
        b,a,qb,qa = (float(view[k]) for k in ('bid','ask','bid_qty','ask_qty'))
        ofi = momentum = 0.
        if self.previous is not None:
            pb,pa,pqb,pqa = self.previous
            # Cont/Kukanov/Stoikov best-level order-flow imbalance increment.
            change = ((qb if b >= pb else 0)-(pqb if b <= pb else 0)
                      -(qa if a <= pa else 0)+(pqa if a >= pa else 0))
            ofi = change/(qb+qa+pqb+pqa)
            momentum = math.tanh(((a+b)/(pa+pb)-1)*10000/5)
        self.previous = b,a,qb,qa
        return [view['imbalance'], ofi, flow, momentum], bool(values)


def vwap(view, side, quantity, share=D('.1')):
    """At most 10% of each observed level, still only a hypothetical fill."""
    if side not in ('buy','sell') or quantity <= 0 or not D(0) < share <= D(1):
        raise ValueError('INVALID_VWAP_REQUEST')
    remaining = quantity
    total = D(0)
    for p,q in view['asks' if side == 'buy' else 'bids']:
        price, visible = number(p, positive=True), number(q)
        amount = min(remaining, visible*share)
        total += amount*price
        remaining -= amount
        if not remaining:
            return total/quantity
    return None


class PaperAccount:
    def __init__(self, rules, *, cash='10', fee_bps='5', latency_ms=250):
        self.cash = number(cash, positive=True)
        self.initial_cash = self.cash
        self.fee = number(fee_bps)/D(10000)
        if self.fee > D('.1') or type(latency_ms) is not int or not 0 <= latency_ms <= 10000:
            raise ValueError('INVALID_PAPER_CONFIG')
        for k in ('step','min_qty','max_qty','min_notional'):
            number(rules[k], positive=True)
        self.rules = rules
        self.latency_ns = latency_ms*1_000_000
        self.position = self.pending = None
        self.ledger = []
        self.paused = False
        self.closed_trades = 0
        self.peak = self.cash
        self.drawdown = D(0)
        self.cooldown_until = 0

    def equity(self, view):
        if self.position is None:
            return self.cash
        p = self.position
        mark = D(view['bid' if p['direction'] == 1 else 'ask'])
        return self.cash + D(p['direction'])*p['quantity']*(mark-p['entry'])

    def pause(self, reason):
        self.pending = None
        self.paused = True
        self.ledger.append({'event': 'PAUSED', 'reason': reason, 'simulated': True,
                            'position_retained': self.position is not None})

    def request(self, kind, direction, now_ns, reason):
        if self.pending is not None or self.paused:
            return False
        if kind not in ('entry', 'exit') or direction not in (-1, 1):
            raise ValueError('INVALID_VIRTUAL_ACTION')
        if (kind == 'entry') == (self.position is not None):
            return False
        if kind == 'entry' and (now_ns < self.cooldown_until or self.cash <= 0 or self.drawdown >= D('.1')):
            return False
        self.pending = {'kind': kind, 'direction': direction, 'due_ns': now_ns+self.latency_ns,
                        'reason': reason, 'decision_ns': now_ns}
        self.ledger.append({'event': 'VIRTUAL_INTENT', **self.pending, 'simulated': True})
        return True

    def advance(self, view, now_ns):
        if (view.get('synced') is not True or now_ns < view['received_ns']
                or now_ns-view['received_ns'] > 1_500_000_000):
            self.pause('STALE_OR_UNSYNCED')
            return
        self.paused = False
        eq = self.equity(view)
        self.peak = max(self.peak, eq)
        self.drawdown = max(self.drawdown, 1-eq/self.peak)
        action = self.pending
        if action is None or now_ns < action['due_ns']:
            return
        self.pending = None
        if now_ns > action['due_ns']+1_000_000_000:
            self.ledger.append({'event': 'VIRTUAL_EXPIRED', 'simulated': True})
            return
        if action['kind'] == 'entry':
            direction = action['direction']
            price = D(view['ask' if direction == 1 else 'bid'])
            # Reinvestment uses CLOSED virtual cash only; floating gains are excluded.
            budget = self.cash*D('.5')/(1+self.fee)
            step = D(self.rules['step'])
            qty = (budget/price/step).to_integral_value(rounding=ROUND_DOWN)*step
            if qty < D(self.rules['min_qty']) or qty > D(self.rules['max_qty']) or qty*price < D(self.rules['min_notional']):
                self.ledger.append({'event': 'VIRTUAL_REJECT_FILTER', 'simulated': True})
                return
            fill = vwap(view, 'buy' if direction == 1 else 'sell', qty)
            if fill is None or fill*qty*(1+self.fee) > self.cash:
                self.ledger.append({'event': 'VIRTUAL_REJECT_LIQUIDITY_OR_CASH', 'simulated': True})
                return
            fee = fill*qty*self.fee
            self.cash -= fee
            self.position = {'direction': direction, 'quantity': qty, 'entry': fill,
                             'opened_ns': now_ns}
            self.ledger.append({'event': 'VIRTUAL_OPEN', 'direction': direction,
                                'quantity': str(qty), 'price': str(fill), 'fee': str(fee),
                                'cash_after': str(self.cash), 'simulated': True})
        else:
            p = self.position
            fill = vwap(view, 'sell' if p['direction'] == 1 else 'buy', p['quantity'])
            if fill is None:
                self.ledger.append({'event': 'VIRTUAL_EXIT_LIQUIDITY_MISSING', 'simulated': True})
                return
            gross = D(p['direction'])*p['quantity']*(fill-p['entry'])
            fee = fill*p['quantity']*self.fee
            self.cash += gross-fee
            self.ledger.append({'event': 'VIRTUAL_CLOSE', 'direction': p['direction'],
                                'quantity': str(p['quantity']), 'price': str(fill),
                                'gross_pnl': str(gross), 'fee': str(fee),
                                'cash_after': str(self.cash), 'reason': action['reason'],
                                'simulated': True})
            self.position = None
            self.closed_trades += 1
            self.cooldown_until = now_ns+2_000_000_000

    def manage(self, view, now_ns, direction):
        if self.position is None:
            if direction:
                self.request('entry', direction, now_ns, 'PAST_NET_EVIDENCE_AND_FLOW')
            return
        p = self.position
        px = D(view['bid' if p['direction'] == 1 else 'ask'])
        move = D(p['direction'])*(px/p['entry']-1)*10000
        reason = ('DRAWDOWN' if self.drawdown >= D('.1') else
                  'STOP' if move <= -20 else 'TAKE' if move >= 40 else
                  'TIME' if now_ns-p['opened_ns'] >= 20_000_000_000 else
                  'REVERSAL' if direction == -p['direction'] else None)
        if reason:
            self.request('exit', p['direction'], now_ns, reason)

    def summary(self):
        # Independently replay ledger cash; public data cannot prove an exchange fill.
        replay = self.initial_cash
        for row in self.ledger:
            if row['event'] == 'VIRTUAL_OPEN':
                replay -= D(row['fee'])
            elif row['event'] == 'VIRTUAL_CLOSE':
                replay += D(row['gross_pnl'])-D(row['fee'])
            if 'cash_after' in row and replay != D(row['cash_after']):
                raise ArithmeticError('VIRTUAL_LEDGER_MISMATCH')
        if replay != self.cash:
            raise ArithmeticError('VIRTUAL_CASH_MISMATCH')
        return {'virtual_cash_usdt': str(self.cash), 'closed_virtual_trades': self.closed_trades,
                'position': {k:str(v) for k,v in self.position.items()} if self.position else None,
                'pending': self.pending, 'paused': self.paused, 'ledger_balanced': True,
                'simulated': True, 'real_orders': 0, 'realized_account_profit_usdt': None}


class OnlineLab:
    def __init__(self, rules, emit, *, symbol='BTCUSDT', previous=None):
        self.symbol, self.emit = symbol, emit
        self.models = {k: Network(k) for k in ('dendritic','linear','frozen')}
        self.stats = {k: {'n':0, 'mean':0., 'm2':0.} for k in
                      (*self.models, 'imbalance', 'reversion_quote_proxy', 'cash')}
        self.config = {'horizon_ns': 5_000_000_000, 'fee_bps_each_side': 5,
                       'extra_slip_bps_each_side': 2, 'minimum_observations': 30,
                       'virtual_rules': rules, 'schema': 'CQWE_TIDAL_ORDERBOOK_V1',
                       'symbol': symbol}
        self.pending = None
        self.last_sample_ns = 0
        self.settled = 0
        self.failures = []
        self.paper = PaperAccount(rules)
        self.flow = FlowFeatures()
        self.previous_sha256 = None
        if previous is not None:
            self._restore(previous)

    def checkpoint(self):
        obj = {'config': self.config, 'models': {k:m.state() for k,m in self.models.items()},
               'stats': copy.deepcopy(self.stats), 'settled': self.settled,
               'previous_sha256': self.previous_sha256,
               'account_continuation': False, 'real_orders': 0}
        obj['sha256'] = digest(obj)
        return obj

    def _restore(self, obj):
        if obj.get('sha256') != digest({k:v for k,v in obj.items() if k != 'sha256'}):
            raise ValueError('MEMORY_HASH_MISMATCH')
        if obj.get('config') != self.config or obj.get('real_orders') != 0 or obj.get('account_continuation') is not False:
            raise ValueError('MEMORY_CONTEXT_MISMATCH')
        if type(obj.get('settled')) is not int or obj['settled'] < 0:
            raise ValueError('MEMORY_COUNT')
        for k,m in self.models.items():
            state = obj['models'][k]
            if set(state) != set(m.state()) or state['kind'] != k:
                raise ValueError('MEMORY_MODEL_SCHEMA')
            if type(state['updates']) is not int or state['updates'] < 0:
                raise ValueError('MEMORY_UPDATES')
            for name in ('weights','memory'):
                if len(state[name]) != 4 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1 for v in state[name]):
                    raise ValueError('MEMORY_PARAMETERS')
            m.__dict__.update(copy.deepcopy(state))
        if set(obj['stats']) != set(self.stats):
            raise ValueError('MEMORY_STATS_SCHEMA')
        for s in obj['stats'].values():
            if set(s) != {'n','mean','m2'} or type(s['n']) is not int or s['n'] < 0 or any(
                    type(s[k]) not in (int,float) or not math.isfinite(s[k]) for k in ('mean','m2')) or s['m2'] < 0:
                raise ValueError('MEMORY_STATS')
            if s['n'] > obj['settled']:
                raise ValueError('MEMORY_OBSERVATIONS')
        if any(obj['models'][k]['updates'] != obj['settled'] for k in ('dendritic','linear')) or obj['models']['frozen']['updates'] != 0:
            raise ValueError('MEMORY_LEARNING_COUNT')
        self.stats = copy.deepcopy(obj['stats'])
        self.settled = obj['settled']
        self.previous_sha256 = obj['sha256']

    def fault(self, reason):
        # Never learn a delayed label across a feed gap. Retain only matured memory.
        self.pending = None
        self.flow = FlowFeatures()
        self.paper.pause(reason)
        self.failures.append(reason)
        self.emit('PAUSE', {'reason': reason, 'pending_forecast_discarded': True})

    def _gate(self, predictions, flow_fresh, x):
        options = []
        for k in ('dendritic','linear'):
            s = self.stats[k]
            if s['n'] >= 30:
                lcb = s['mean']-3*math.sqrt(max(0,s['m2'])/(s['n']-1)/s['n'])
                if lcb > 0 and abs(predictions[k]) > .05:
                    direction = 1 if predictions[k] > 0 else -1
                    if flow_fresh and x[2]*direction > 0 and x[0]*direction > 0:
                        options.append((lcb,k,direction))
        return max(options)[2] if options else 0

    def book(self, view, now_ns):
        self.paper.advance(view, now_ns)
        x, fresh = self.flow.sample(view, now_ns)
        if self.pending is not None and now_ns >= self.pending['time_ns']+self.config['horizon_ns']:
            p = self.pending
            self.pending = None
            if now_ns > p['time_ns']+self.config['horizon_ns']+1_000_000_000:
                self.emit('LABEL_EXPIRED', {'decision_ns': p['time_ns']})
            else:
                mid = float(view['mid'])
                move = (mid/p['mid']-1)*10000
                long_net = (float(view['bid'])/p['ask']-1)*10000-14
                short_net = (p['bid']-float(view['ask']))/p['bid']*10000-14
                outcomes = {}
                for k,pred in p['predictions'].items():
                    if abs(pred) <= .05:
                        continue
                    net = long_net if pred > 0 else short_net
                    s = self.stats[k]
                    s['n'] += 1
                    delta = net-s['mean']
                    s['mean'] += delta/s['n']
                    s['m2'] += delta*(net-s['mean'])
                    outcomes[k] = net
                for k,m in self.models.items():
                    # Cache stored at decision time; label only after mature quote.
                    m.learn(p['x'], math.tanh(move/10), p['predictions'][k], p['caches'][k])
                self.settled += 1
                self.emit('MATURED', {'decision_ns': p['time_ns'], 'move_bps': move,
                          'crossing_proxy_net_bps': outcomes,
                          'learning_updates': {k:m.updates for k,m in self.models.items()}})
        predictions = {k:m.predict(x)[0] for k,m in self.models.items()}
        direction = self._gate(predictions, fresh, x)
        self.paper.manage(view, now_ns, direction)
        if self.pending is None and now_ns-self.last_sample_ns >= 1_000_000_000:
            caches = {k:m.predict(x)[1] for k,m in self.models.items()}
            predictions.update({'imbalance': x[0], 'reversion_quote_proxy': -x[0], 'cash':0.})
            # Commit prediction and exact input book BEFORE the future label arrives.
            self.emit('FORECAST', {'decision_ns': now_ns, 'book': view, 'features': x,
                      'flow_fresh': fresh, 'predictions': predictions,
                      'paper_direction': direction, 'model_sha256': digest(self.checkpoint()),
                      'maker_identity_known': False, 'passive_fills_assumed': 0})
            self.pending = {'time_ns': now_ns, 'mid':float(view['mid']),
                            'ask':float(view['ask']), 'bid':float(view['bid']),
                            'x':x, 'predictions':predictions, 'caches':caches}
            self.last_sample_ns = now_ns
