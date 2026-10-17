"""Four-underlying, delayed-label research engine. All executions are virtual.

Rolling futures-mid outcomes are proxies, never external-venue resolution labels.
Models compete prequentially; bounded candidate selection is not open-ended AI.
"""
import collections
import copy
import json
import math
from decimal import Decimal as D, ROUND_DOWN

from .copernican_experiment_v81_v85 import digest
from .futures_orderbook import number
from .tidal_research import vwap
from .liquidity_research import LiquidityTape, LiquidityStudy

SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT')
KINDS = ('branch2', 'branch4', 'linear', 'frozen', 'reversion')
BASIS = 'BINANCE_USDM_PERPETUAL_MID_RECEIPT_TIME_PROXY'


def bounded(v, lo, hi):
    if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError('INVALID_FINITE_NUMBER')
    return float(v)


def config(horizons=(300, 900)):
    if (not isinstance(horizons, (list, tuple)) or not horizons or len(horizons) > 5
            or len(set(horizons)) != len(horizons)
            or any(type(h) is not int or h not in (60, 300, 600, 900, 1800, 3600) for h in horizons)):
        raise ValueError('INVALID_HORIZONS')
    return {'schema': 'CQWE_FOUR_MARKET_COUNCIL_V3', 'symbols': list(SYMBOLS),
            'horizons_seconds': sorted(horizons), 'label_basis': BASIS,
            'initial_cash': '10', 'fee_bps_each_side': '5', 'slip_bps_each_side': '2',
            'minimum_labels': 100, 'label_tolerance_ms': 2000,
            'max_symbol_exposure_fraction': '0.25', 'max_total_exposure_fraction': '0.5',
            'stop_bps': '30', 'take_bps': '60', 'max_drawdown': '0.1',
            'mode': 'PUBLIC_DATA_PAPER_ONLY'}


class Model:
    def __init__(self, kind):
        if kind not in KINDS:
            raise ValueError('UNKNOWN_MODEL')
        self.kind = kind
        self.weights = [.08, -.06, .04, .03, .02, -.01, .01, .02]
        self.memory = [0.] * 8
        self.updates = 0

    def predict(self, x):
        x = [bounded(v, -1, 1) for v in x]
        if len(x) != 8:
            raise ValueError('FEATURE_DIMENSION')
        u = [v + .1 * m for v, m in zip(x, self.memory)]
        groups = 4 if self.kind == 'branch4' else 2
        width = 8 // groups
        branches = [math.tanh(sum(self.weights[j] * u[j] for j in range(i, i + width)))
                    for i in range(0, 8, width)]
        z = sum(self.weights[j] * x[j] for j in range(8)) if self.kind == 'linear' else sum(branches) / groups
        p = 1 / (1 + math.exp(-z))
        if self.kind == 'reversion':
            p = .5 - .1 * x[0]
        return p, {'u': u, 'branches': branches, 'groups': groups}

    def learn(self, x, y, p, cache):
        if self.kind in ('frozen', 'reversion'):
            return
        previous = self.state()
        for j in range(8):
            groups = cache['groups']
            slope = 1. if self.kind == 'linear' else (1-cache['branches'][j // (8 // groups)]**2) / groups
            self.weights[j] = max(-1., min(1., self.weights[j] + .03 * (y-p) * slope * cache['u'][j]))
            self.memory[j] = .95 * self.memory[j] + .05 * x[j] * (2*y-1)
        self.updates += 1
        try:
            self.validate()
        except ValueError:
            self.__dict__.update(previous)
            raise

    def validate(self):
        if type(self.updates) is not int or self.updates < 0:
            raise ValueError('MODEL_UPDATES')
        for name in ('weights', 'memory'):
            if len(getattr(self, name)) != 8:
                raise ValueError('MODEL_DIMENSION')
            for v in getattr(self, name):
                bounded(v, -1, 1)

    def state(self):
        return copy.deepcopy(vars(self))


def score_new():
    return {'n': 0, 'brier_sum': 0., 'directional_n': 0, 'net_sum': 0., 'net_sq': 0., 'recent': []}


def lower_mean(s):
    n = s['directional_n']
    if n < 2:
        return None
    mean = s['net_sum'] / n
    variance = max(0., (s['net_sq'] - s['net_sum']**2/n) / (n-1))
    return mean - 3 * math.sqrt(variance/n)


def eligible(s, minimum=100):
    # Descriptive gate only: selection/multiple-testing effects remain uncorrected.
    lcb = lower_mean(s)
    return s['n'] >= minimum and s['directional_n'] >= minimum and s['brier_sum']/s['n'] < .24 and lcb is not None and lcb > 0


class Portfolio:
    """One unlevered virtual cash pool, shared across symbols and products."""
    def __init__(self, cfg):
        self.cfg = cfg
        self.cash = D(cfg['initial_cash'])
        self.peak = self.cash
        self.drawdown = D(0)
        self.futures = {}
        self.binary = {}
        self.closed = 0
        self.halted = False
        self.last_views = {}

    def reserved(self, symbol=None):
        fut = sum((D(p['entry'])*D(p['quantity']) for s,p in self.futures.items() if symbol is None or s == symbol), D(0))
        binary = sum((D(p['cost']) for p in self.binary.values() if symbol is None or p['symbol'] == symbol), D(0))
        return fut + binary

    def equity(self):
        total = self.cash
        for symbol,p in self.futures.items():
            if p.get('pending'):
                continue
            v = self.last_views.get(symbol)
            if v is None:
                continue
            px = D(v['bid' if p['direction'] == 1 else 'ask'])
            total += p['direction'] * D(p['quantity']) * (px-D(p['entry']))
        # Binary positions conservatively valued at zero until resolved; cost is already debited.
        return total

    def room(self, symbol):
        if any(p.get('force_exit') for p in self.futures.values()):
            return D(0)
        equity = max(D(0), self.equity())
        fut_reserve = sum((D(p['entry'])*D(p['quantity']) for p in self.futures.values()), D(0))
        return max(D(0), min(self.cash-fut_reserve,
                            equity*D(self.cfg['max_total_exposure_fraction'])-self.reserved(),
                            equity*D(self.cfg['max_symbol_exposure_fraction'])-self.reserved(symbol)))

    def frame(self, symbol, view, at_ms, emit, rules):
        self.last_views[symbol] = view
        equity = self.equity()
        self.peak = max(self.peak, equity)
        self.drawdown = max(self.drawdown, 1-equity/self.peak)
        if self.drawdown >= D(self.cfg['max_drawdown']):
            self.halted = True
        p = self.futures.get(symbol)
        if not p:
            return
        if at_ms-p['decision_ms'] < 250:
            return
        if p.get('pending'):
            if at_ms-p['decision_ms'] > 1500 or self.halted:
                del self.futures[symbol]
                emit('FUTURES_CANCELLED', {'symbol': symbol, 'reason': 'ENTRY_EXPIRED_OR_HALTED'})
                return
            del self.futures[symbol]  # release reservation while rechecking all limits
            self.open(symbol, view, at_ms, p['direction'], p['horizon'], p['evidence'], rules, emit)
            return
        px = D(view['bid' if p['direction'] == 1 else 'ask'])
        move = p['direction']*(px/D(p['entry'])-1)*10000
        reason = ('DRAWDOWN' if self.halted else 'FEED_RECOVERY_EXIT' if p.get('force_exit') else
                  'STOP' if move <= -D(self.cfg['stop_bps']) else 'TAKE' if move >= D(self.cfg['take_bps']) else
                  'TIME' if at_ms >= p['expires_ms'] else None)
        if not reason:
            return
        price = vwap(view, 'sell' if p['direction'] == 1 else 'buy', D(p['quantity']))
        if price is None:
            emit('FUTURES_EXIT_BLOCKED', {'symbol': symbol, 'reason': 'INSUFFICIENT_DEPTH'})
            return
        slip = D(self.cfg['slip_bps_each_side'])/10000
        price *= 1-slip if p['direction'] == 1 else 1+slip
        gross = p['direction']*D(p['quantity'])*(price-D(p['entry']))
        fee = price*D(p['quantity'])*D(self.cfg['fee_bps_each_side'])/10000
        self.cash += gross-fee
        del self.futures[symbol]
        self.closed += 1
        emit('FUTURES_CLOSE', {'symbol': symbol, 'price': str(price), 'gross': str(gross),
                              'fee': str(fee), 'cash': str(self.cash), 'reason': reason})

    def request(self, symbol, view, at_ms, direction, horizon, evidence, rules, emit):
        if self.halted or symbol in self.futures:
            return
        price = D(view['ask' if direction == 1 else 'bid'])
        step = D(rules['step'])
        room = self.room(symbol)
        qty = (room/price/step).to_integral_value(rounding=ROUND_DOWN)*step
        if qty < D(rules['min_qty']) or qty > D(rules['max_qty']) or qty*price < D(rules['min_notional']):
            emit('FUTURES_REJECT', {'symbol': symbol, 'reason': 'CASH_OR_EXCHANGE_MINIMUM', 'room': str(room)})
            return
        self.futures[symbol] = {'pending': True, 'entry': str(price), 'quantity': str(qty),
                               'direction': direction, 'decision_ms': at_ms, 'horizon': horizon, 'evidence': evidence}
        emit('FUTURES_INTENT', {'symbol': symbol, 'direction': direction, 'decision_ms': at_ms,
                               'horizon': horizon, 'quantity': str(qty), 'evidence': evidence})

    def open(self, symbol, view, at_ms, direction, horizon, evidence, rules, emit):
        room = self.room(symbol)
        slip = D(self.cfg['slip_bps_each_side'])/10000
        fee_rate = D(self.cfg['fee_bps_each_side'])/10000
        px = D(view['ask' if direction == 1 else 'bid'])*(1+slip if direction == 1 else 1-slip)
        step = D(rules['step'])
        qty = (room/(1+fee_rate)/px/step).to_integral_value(rounding=ROUND_DOWN)*step
        if qty < D(rules['min_qty']) or qty > D(rules['max_qty']) or qty*px < D(rules['min_notional']):
            emit('FUTURES_REJECT', {'symbol': symbol, 'reason': 'FILTER_AT_FILL'})
            return
        fill = vwap(view, 'buy' if direction == 1 else 'sell', qty)
        if fill is None:
            emit('FUTURES_REJECT', {'symbol': symbol, 'reason': 'DEPTH_AT_FILL'})
            return
        fill *= 1+slip if direction == 1 else 1-slip
        fee = fill*qty*fee_rate
        if fill*qty+fee > room:
            emit('FUTURES_REJECT', {'symbol': symbol, 'reason': 'SLIPPAGE_BUDGET'})
            return
        self.cash -= fee
        self.futures[symbol] = {'entry': str(fill), 'quantity': str(qty), 'direction': direction,
                               'decision_ms': at_ms, 'expires_ms': at_ms+horizon*1000,
                               'horizon': horizon, 'evidence': evidence}
        emit('FUTURES_OPEN', {'symbol': symbol, **self.futures[symbol], 'fee': str(fee), 'cash': str(self.cash)})

    def fault(self, symbol):
        p = self.futures.get(symbol)
        if p and p.get('pending'):
            del self.futures[symbol]
        elif p:
            p['force_exit'] = True

    def state(self):
        return {'cash': str(self.cash), 'peak': str(self.peak), 'drawdown': str(self.drawdown),
                'futures': copy.deepcopy(self.futures), 'binary': copy.deepcopy(self.binary),
                'closed': self.closed, 'halted': self.halted, 'last_views': copy.deepcopy(self.last_views)}


class Engine:
    def __init__(self, cfg=None, rules=None, emit=None, previous=None):
        self.cfg = cfg or config()
        self.rules = rules or {}
        self.emit = emit or (lambda kind, payload: None)
        self.models = {}
        self.scores = {}
        self.champions = {}
        self.pending = {}
        self.latest = {}
        self.last_ms = {}
        self.frames = {s: 0 for s in SYMBOLS}
        self.faults = {s: 0 for s in SYMBOLS}
        self.rounds = 0
        self.matured = 0
        self.dropped = 0
        self.promotions = []
        self.portfolio = Portfolio(self.cfg)
        self.liquidity = LiquidityTape()
        self.liquidity_study = LiquidityStudy(self.cfg['horizons_seconds'])
        self.council = {}
        self.events = {}
        self.event_models = {}
        self.event_scores = {}
        for symbol in SYMBOLS:
            for h in self.cfg['horizons_seconds']:
                key = f'{symbol}:{h}'
                self.models[key] = {k: Model(k) for k in KINDS}
                self.scores[key] = {k: score_new() for k in KINDS}
                self.champions[key] = 'branch2'
        if previous is not None:
            self.restore(previous)

    def fault(self, symbol, reason):
        self.faults[symbol] += 1
        self.latest.pop(symbol, None)
        for key in [k for k in self.pending if k.startswith(symbol+':')]:
            self.dropped += 1
            self.emit('LABEL_DROPPED', {'key': key, 'reason': reason, 'forecast_id': self.pending.pop(key)['id']})
        self.portfolio.fault(symbol)
        self.liquidity.invalidate(symbol)
        self.liquidity_study.fault(symbol,self.emit,reason)
        self.emit('RESEARCH_PAUSED', {'symbol': symbol, 'reason': reason})

    def frame(self, symbol, at_ms, view, x4):
        if symbol not in SYMBOLS or type(at_ms) is not int or at_ms < self.last_ms.get(symbol, -1):
            raise ValueError('FRAME_CLOCK_OR_SYMBOL')
        if view['symbol'] != symbol or view.get('synced') is not True:
            raise ValueError('INVALID_FRAME')
        if len(x4) != 4:
            raise ValueError('FEATURE_DIMENSION')
        if symbol in self.latest and at_ms-self.latest[symbol]['at_ms'] > 1500:
            self.fault(symbol, 'FRAME_CONTINUITY_GAP')
        self.last_ms[symbol] = at_ms
        self.frames[symbol] += 1
        mid = float(number(view['mid'], positive=True))
        previous = self.latest.get(symbol)
        move = 0. if previous is None else math.tanh((mid/previous['mid']-1)*10000/5)
        btc = self.latest.get('BTCUSDT')
        cross = btc['momentum'] if btc and 0 <= at_ms-btc['at_ms'] <= 1500 else 0.
        qb,qa = float(view['bid_qty']),float(view['ask_qty'])
        micro = (float(view['ask'])*qb+float(view['bid'])*qa)/(qb+qa)
        x = [bounded(v, -1, 1) for v in x4] + [math.tanh((micro/mid-1)*10000),
              math.tanh(view['spread_bps']/10), abs(move), cross]
        decision_ns=view.get('decision_ns',view['received_ns'])
        mx,quality = self.liquidity.sample(symbol,view,decision_ns,at_ms)
        self.liquidity_study.frame(symbol,at_ms,view,x,mx,quality,self.emit,
            2*(float(self.cfg['fee_bps_each_side'])+float(self.cfg['slip_bps_each_side'])))
        d=self.liquidity.data[symbol]
        if decision_ns-d.get('last_emitted_ns',-1_000_000_000)>=1_000_000_000:
            self.emit('LIQUIDITY_OBSERVATION',{'symbol':symbol,'at_ms':at_ms,**d['last_signals']})
            from .dendritic_council import decide
            self.council[symbol] = decide(self,symbol,at_ms,view,x,mx,quality)
            self.emit('COUNCIL_DECISION',self.council[symbol])
            d['last_emitted_ns']=decision_ns
        self.latest[symbol] = {'at_ms': at_ms, 'mid': mid, 'momentum': move}
        self.portfolio.frame(symbol, view, at_ms, self.emit, self.rules[symbol])
        for h in self.cfg['horizons_seconds']:
            key = f'{symbol}:{h}'
            old = self.pending.get(key)
            if old and at_ms >= old['due_ms']:
                del self.pending[key]
                if at_ms-old['due_ms'] > self.cfg['label_tolerance_ms']:
                    self.dropped += 1
                    self.emit('LABEL_DROPPED', {'key': key, 'reason': 'MATURITY_GAP', 'forecast_id': old['id']})
                elif mid == old['mid']:
                    self.dropped += 1
                    self.emit('LABEL_DROPPED', {'key': key, 'reason': 'TIE_EXCLUDED', 'forecast_id': old['id']})
                else:
                    y = int(mid > old['mid'])
                    losses = {}
                    round_cost = 2*(float(self.cfg['fee_bps_each_side'])+float(self.cfg['slip_bps_each_side']))
                    for kind,m in self.models[key].items():
                        p,cache = old['predictions'][kind]
                        loss = (p-y)**2
                        s = self.scores[key][kind]
                        s['n'] += 1
                        s['brier_sum'] += loss
                        s['recent'] = (s['recent']+[loss])[-50:]
                        direction = 1 if p >= .55 else -1 if p <= .45 else 0
                        if direction:
                            net = ((float(view['bid'])/float(old['ask'])-1)*10000 if direction == 1 else
                                   (float(old['bid'])-float(view['ask']))/float(old['bid'])*10000)-round_cost
                            s['directional_n'] += 1
                            s['net_sum'] += net
                            s['net_sq'] += net*net
                        m.learn(old['features'], y, p, cache)
                        losses[kind] = loss
                    self.matured += 1
                    self.emit('MATURED_PROXY', {'key': key, 'forecast_id': old['id'], 'at_ms': at_ms,
                                               'due_ms': old['due_ms'], 'label': y, 'basis': BASIS, 'losses': losses})
            if key in self.pending:
                continue
            predictions = {k: list(m.predict(x)) for k,m in self.models[key].items()}
            f = {'key': key, 'symbol': symbol, 'horizon': h, 'at_ms': at_ms, 'due_ms': at_ms+h*1000,
                 'mid': mid, 'bid': view['bid'], 'ask': view['ask'], 'features': x,
                 'predictions': predictions, 'basis': BASIS}
            f['id'] = digest(f)
            self.pending[key] = f
            champion = self.champions[key]
            p = predictions[champion][0]
            ready = eligible(self.scores[key][champion], self.cfg['minimum_labels'])
            self.emit('FORECAST_PROXY', {'forecast': f, 'champion': champion, 'probability_up': p,
                                        'research_gate': ready, 'external_event_compatible': False})
            if ready and h == self.cfg['horizons_seconds'][0] and (p >= .55 or p <= .45):
                reason=self.liquidity.entry_guard(symbol,at_ms,h,decision_ns)
                if reason:
                    self.emit('FUTURES_REJECT',{'symbol':symbol,'reason':reason})
                else:
                    self.portfolio.request(symbol, view, at_ms, 1 if p >= .55 else -1, h, f['id'], self.rules[symbol], self.emit)

    def tick(self, at_ms):
        for s,last in list(self.latest.items()):
            if at_ms-last['at_ms'] > 1500:
                self.fault(s, 'STALE_SYMBOL')

    def event_quote(self, q):
        """Normalized venue observations; adapter must supply exact rule/reference identity.

        Futures-mid proxy predictions are never reused as external event forecasts.
        Hashes provide provenance, not independent proof of oracle authenticity.
        """
        from .event_learning import source_hash
        for name in ('rules_sha256', 'source_sha256'):
            source_hash(q[name])
        if q['symbol'] not in SYMBOLS or q['venue'] not in ('binance_prediction', 'polymarket', 'fixture'):
            raise ValueError('EVENT_MARKET_IDENTITY')
        if q.get('collateral') != 'USDT':
            raise ValueError('EVENT_COLLATERAL_REQUIRES_SEPARATE_FX_ACCOUNTING')
        for name in ('at_ms','start_ms','end_ms','reference_ms','book_ms'):
            if type(q[name]) is not int:
                raise ValueError('EVENT_TIME_REQUIRED')
        if (not q['start_ms'] <= q['at_ms'] < q['end_ms'] or
                not 0 <= q['at_ms']-q['reference_ms'] <= 1500 or
                not 0 <= q['at_ms']-q['book_ms'] <= 1500):
            raise ValueError('EVENT_STALE_OR_CLOSED')
        duration = (q['end_ms']-q['start_ms'])//1000
        if duration not in self.cfg['horizons_seconds'] or q['end_ms']-q['start_ms'] != duration*1000:
            raise ValueError('EVENT_UNSUPPORTED_DURATION')
        basis = q['reference_basis']
        if not isinstance(basis, str) or not basis or basis == BASIS or len(basis) > 120:
            raise ValueError('EXACT_EXTERNAL_REFERENCE_REQUIRED')
        if q.get('reference_matches_rules') is not True or q.get('tie_rule') not in ('UP', 'DOWN', 'REFUND'):
            raise ValueError('UNVERIFIED_SETTLEMENT_RULES')
        ident = q['venue']+':'+str(q['market_id'])
        if len(ident) > 200:
            raise ValueError('EVENT_ID_BUDGET')
        if ident in self.events:
            return  # one committed forecast per real event
        if len(self.events) >= 10000:
            raise ValueError('EVENT_ARCHIVE_BUDGET')
        rate = number(q['fee_rate'])
        if rate > 1 or q.get('fee_formula') != 'RATE_P_ONE_MINUS_P':
            raise ValueError('UNKNOWN_EVENT_FEE')
        number(q['min_shares'], positive=True)
        for side in ('up','down'):
            if number(q[side+'_ask'], positive=True) >= 1:
                raise ValueError('EVENT_PRICE_RANGE')
            number(q[side+'_ask_size'])
        last = self.latest.get(q['symbol'])
        if last is None or not 0 <= q['at_ms']-last['at_ms'] <= 1500:
            raise ValueError('EVENT_UNDERLYING_STALE')
        ref,anchor = number(q['reference_price'], positive=True),number(q['anchor_price'], positive=True)
        # Entry-time bucket isolates very different remaining-time prediction problems.
        bucket = min(3, int(4*(q['end_ms']-q['at_ms'])/(duration*1000)))
        category = f"{q['venue']}:{q['symbol']}:{duration}:{basis}:{bucket}"
        x = [bounded(v,-1,1) for v in q['features']]
        if len(x) != 8:
            raise ValueError('EVENT_FEATURE_DIMENSION')
        p0 = bounded(q['market_probability_up'], .000001, .999999)
        if category not in self.event_models:
            if len(self.event_models) >= 200:
                raise ValueError('EVENT_MODEL_BUDGET')
            self.event_models[category] = Model('branch2')
            self.event_scores[category] = {'n':0, 'brier_sum':0., 'reference_brier_sum':0.}
        x[4] = math.tanh(float(ref/anchor-1)*10000/10)
        x[5] = (q['end_ms']-q['at_ms'])/(duration*1000)
        p,cache = self.event_models[category].predict(x)
        f = {'id':ident, 'category':category, 'quote':copy.deepcopy(q), 'p':p, 'p0':p0,
             'features':x, 'cache':cache, 'resolved':False}
        self.events[ident] = f
        self.emit('EVENT_FORECAST', {'id':ident, 'probability_up':p, 'market_probability_up':p0,
                                    'source_sha256':q['source_sha256'], 'category':category,
                                    'at_ms':q['at_ms'], 'end_ms':q['end_ms'], 'proxy_reused':False})
        s = self.event_scores[category]
        if s['n'] < self.cfg['minimum_labels'] or s['brier_sum'] >= s['reference_brier_sum'] or self.portfolio.halted:
            self.emit('EVENT_OBSERVE', {'id':ident, 'reason':'INSUFFICIENT_INDEPENDENT_EVENT_EVIDENCE'})
            return
        candidates = []
        for side,prob in (('UP',p),('DOWN',1-p)):
            price = number(q[side.lower()+'_ask'], positive=True)
            size = number(q[side.lower()+'_ask_size'])
            if price >= 1:
                raise ValueError('EVENT_PRICE_RANGE')
            cost = price+rate*price*(1-price)+D('.002')  # hypothetical execution buffer
            if D(str(prob))-cost > D('.03'):
                candidates.append((D(str(prob))-cost,side,cost,size))
        if not candidates:
            return
        _,side,cost,visible = max(candidates)
        shares = min((self.portfolio.room(q['symbol'])/cost).to_integral_value(rounding=ROUND_DOWN),
                     (visible*D('.1')).to_integral_value(rounding=ROUND_DOWN))
        if shares < number(q['min_shares'], positive=True):
            return
        total = shares*cost
        self.portfolio.cash -= total
        self.portfolio.binary[ident] = {'symbol':q['symbol'], 'side':side, 'shares':str(shares),
                                       'cost':str(total), 'rules_sha256':q['rules_sha256']}
        self.emit('EVENT_VIRTUAL_BUY', {'id':ident, **self.portfolio.binary[ident],
                                       'fill_assumption':'SNAPSHOT_10PCT_DEPTH_WITH_BUFFER_NOT_EXCHANGE_FILL'})

    def event_resolve(self, r):
        from .event_learning import source_hash
        source_hash(r['source_sha256'])
        ident = r['venue']+':'+str(r['market_id'])
        f = self.events.get(ident)
        if f is None or f['resolved']:
            raise ValueError('EVENT_UNKNOWN_OR_ALREADY_RESOLVED')
        if (r.get('final') is not True or r.get('rules_sha256') != f['quote']['rules_sha256']
                or type(r.get('at_ms')) is not int or r['at_ms'] < f['quote']['end_ms']):
            raise ValueError('EVENT_NOT_FINAL_OR_RULES_CHANGED')
        payouts = r['payouts']
        if not isinstance(payouts, list) or len(payouts) != 2:
            raise ValueError('EVENT_PAYOUT_LAYOUT')
        payouts = [number(v) for v in payouts]
        if sum(payouts) != 1:
            raise ValueError('EVENT_NONEXHAUSTIVE_PAYOUT')
        binary = payouts in ([D(1),D(0)], [D(0),D(1)])
        if binary:
            y = int(payouts[0] == 1)
            s = self.event_scores[f['category']]
            s['n'] += 1
            s['brier_sum'] += (f['p']-y)**2
            s['reference_brier_sum'] += (f['p0']-y)**2
            self.event_models[f['category']].learn(f['features'], y, f['p'], f['cache'])
        position = self.portfolio.binary.pop(ident, None)
        if position:
            payout = D(position['shares'])*payouts[0 if position['side']=='UP' else 1]
            self.portfolio.cash += payout
            self.portfolio.closed += 1
            self.emit('EVENT_VIRTUAL_SETTLE', {'id':ident, 'payout':str(payout),
                                              'net':str(payout-D(position['cost'])), 'cash':str(self.portfolio.cash)})
        f['resolved'] = True
        self.emit('EVENT_RESOLVED', {'id':ident, 'binary_learning_update':binary,
                                    'payouts':[str(v) for v in payouts], 'source_sha256':r['source_sha256']})

    def end_round(self):
        self.rounds += 1
        if self.rounds % 5 == 0:
            for key,scores in self.scores.items():
                current = self.champions[key]
                candidates = [k for k,s in scores.items() if k not in ('frozen','reversion') and eligible(s, self.cfg['minimum_labels'])]
                if not candidates:
                    continue
                best = min(candidates, key=lambda k: scores[k]['brier_sum']/scores[k]['n'])
                if (scores[best]['brier_sum']/scores[best]['n'] + .01 < scores[current]['brier_sum']/max(1,scores[current]['n'])):
                    self.champions[key] = best
                    row = {'round': self.rounds, 'key': key, 'from': current, 'to': best,
                           'reason': 'BOUNDED_PREQUENTIAL_CANDIDATE_SELECTION', 'profitability_proven': False}
                    self.promotions.append(row)
                    self.emit('MODEL_SELECTION', row)
            self.emit('FIVE_ROUND_REVIEW', {'round': self.rounds, 'matured': self.matured,
                                          'promotions': len(self.promotions), 'real_orders': 0})
            self.emit('LIQUIDITY_ABLATION_REVIEW',self.liquidity_study.summary())

    def state(self):
        obj = {'cfg': self.cfg, 'rules': self.rules,
               'models': {key: {k:m.state() for k,m in models.items()} for key,models in self.models.items()},
               'scores': self.scores, 'champions': self.champions, 'pending': self.pending,
               'latest': self.latest, 'last_ms': self.last_ms, 'frames': self.frames, 'faults': self.faults,
               'rounds': self.rounds, 'matured': self.matured, 'dropped': self.dropped,
               'promotions': self.promotions, 'portfolio': self.portfolio.state(), 'real_orders': 0}
        obj.update(events=self.events, event_models={k:m.state() for k,m in self.event_models.items()},
                   event_scores=self.event_scores,liquidity=self.liquidity.state(),
                   liquidity_study=self.liquidity_study.state(),council=self.council)
        obj = json.loads(json.dumps(obj, allow_nan=False))
        obj['sha256'] = digest(obj)
        return obj

    def restore(self, obj):
        if obj.get('sha256') != digest({k:v for k,v in obj.items() if k != 'sha256'}):
            raise ValueError('STATE_HASH_MISMATCH')
        if obj.get('cfg') != self.cfg or obj.get('rules') != self.rules or obj.get('real_orders') != 0:
            raise ValueError('STATE_CONTEXT_MISMATCH')
        if set(obj['models']) != set(self.models):
            raise ValueError('STATE_MODEL_KEYS')
        for key,models in self.models.items():
            if set(obj['models'][key]) != set(KINDS):
                raise ValueError('STATE_MODEL_KINDS')
            for kind,m in models.items():
                st = obj['models'][key][kind]
                if set(st) != set(m.state()) or st['kind'] != kind:
                    raise ValueError('STATE_MODEL_LAYOUT')
                m.__dict__.update(copy.deepcopy(st))
                m.validate()
        for name in ('scores','champions','pending','latest','last_ms','frames','faults','rounds','matured','dropped','promotions'):
            setattr(self, name, copy.deepcopy(obj[name]))
        self.events = copy.deepcopy(obj['events'])
        self.liquidity = LiquidityTape(obj['liquidity'])
        self.liquidity_study = LiquidityStudy(self.cfg['horizons_seconds'],obj['liquidity_study'])
        self.council = copy.deepcopy(obj['council'])
        self.event_scores = copy.deepcopy(obj['event_scores'])
        for k,st in obj['event_models'].items():
            m = Model('branch2')
            if set(st) != set(m.state()) or st['kind'] != 'branch2':
                raise ValueError('EVENT_MODEL_LAYOUT')
            m.__dict__.update(copy.deepcopy(st))
            m.validate()
            self.event_models[k] = m
        p = obj['portfolio']
        for name in ('cash','peak','drawdown'):
            value = D(p[name])
            if not value.is_finite():
                raise ValueError('NONFINITE_ACCOUNT')
            setattr(self.portfolio, name, value)
        for name in ('futures','binary','closed','halted','last_views'):
            setattr(self.portfolio, name, copy.deepcopy(p[name]))

    def summary(self):
        return {'schema': self.cfg['schema'], 'symbols': list(SYMBOLS), 'horizons_seconds': self.cfg['horizons_seconds'],
                'frames': self.frames, 'matured_proxy_labels': self.matured, 'dropped_labels': self.dropped,
                'pending_proxy_forecasts': len(self.pending), 'faults': self.faults, 'rounds': self.rounds,
                'champions': self.champions, 'scores': self.scores, 'portfolio': self.portfolio.state(),
                'real_orders': 0, 'account_profit': None, 'profitability_proven': False,
                'label_basis': BASIS, 'external_event_resolution_learning': True,
                'external_event_forecasts':len(self.events),
                'external_event_labels':sum(s['n'] for s in self.event_scores.values()),
                'liquidity_study':self.liquidity_study.summary(),
                'context_counts':{s:d['counters'].copy() for s,d in self.liquidity.data.items()},
                'council':self.council,
                'liquidity_last_observations':{s:d['last_signals'] for s,d in self.liquidity.data.items()}}
