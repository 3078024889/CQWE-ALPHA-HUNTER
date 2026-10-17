"""Binance USD-M market-by-price reconstruction. Public data, never orders.

Protocol reference (checked 2026-10-15): snapshot overlap U <= L <= u,
then pu == prior u. This is deliberately separate from Spot LocalBook.
"""
from decimal import Decimal, InvalidOperation


class BookFault(ValueError):
    pass


def number(value, *, positive=False):
    if isinstance(value, (float, bool)):
        raise BookFault('DECIMAL_STRING_REQUIRED')
    try:
        result = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        raise BookFault('INVALID_NUMBER') from None
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise BookFault('INVALID_NUMBER')
    return result


def levels(rows):
    if not isinstance(rows, list) or len(rows) > 10000:
        raise BookFault('INVALID_LEVELS')
    out = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != 2:
            raise BookFault('INVALID_LEVEL')
        price, quantity = number(row[0], positive=True), number(row[1])
        if price in out:
            raise BookFault('DUPLICATE_LEVEL')
        out[price] = quantity
    return out


class FuturesBook:
    def __init__(self, symbol):
        if symbol not in ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'):
            raise BookFault('UNSUPPORTED_SYMBOL')
        self.symbol = symbol
        self.bids = {}
        self.asks = {}
        self.update_id = None
        self.bridged = False
        self.valid = False
        self.received_ns = None
        self.applied = 0

    def snapshot(self, obj):
        self.valid = self.bridged = False
        ident = obj.get('lastUpdateId')
        if type(ident) is not int or ident < 0:
            raise BookFault('INVALID_SNAPSHOT_ID')
        bids, asks = levels(obj.get('bids')), levels(obj.get('asks'))
        if not bids or not asks or any(q <= 0 for q in (*bids.values(), *asks.values())):
            raise BookFault('EMPTY_SNAPSHOT')
        if max(bids) >= min(asks):
            raise BookFault('CROSSED_SNAPSHOT')
        self.bids, self.asks, self.update_id = bids, asks, ident
        self.bid_boundary, self.ask_boundary = min(bids), max(asks)
        self.valid = True

    def apply(self, event, received_ns):
        try:
            return self._apply(event, received_ns)
        except (BookFault, KeyError, TypeError):
            self.valid = self.bridged = False
            raise

    def _apply(self, e, received_ns):
        if not self.valid or self.update_id is None:
            raise BookFault('SNAPSHOT_REQUIRED')
        if e.get('e') != 'depthUpdate' or e.get('s') != self.symbol:
            raise BookFault('WRONG_MARKET')
        if any(type(e.get(k)) is not int or e[k] < 0 for k in ('U', 'u', 'pu', 'E')) or e['U'] > e['u']:
            raise BookFault('INVALID_SEQUENCE')
        if type(received_ns) is not int or received_ns < 0:
            raise BookFault('INVALID_RECEIPT_TIME')
        if self.received_ns is not None and received_ns < self.received_ns:
            raise BookFault('RECEIPT_TIME_REVERSED')
        changes = (levels(e.get('b')), levels(e.get('a')))
        if not self.bridged:
            if e['u'] < self.update_id:
                return False
            if not e['U'] <= self.update_id <= e['u']:
                raise BookFault('SNAPSHOT_NOT_BRIDGED')
        else:
            if e['u'] <= self.update_id:
                return False
            if e['pu'] != self.update_id:
                raise BookFault('DEPTH_PU_GAP')
        bids, asks = self.bids.copy(), self.asks.copy()
        for side, updates in ((bids, changes[0]), (asks, changes[1])):
            for price, amount in updates.items():
                if amount:
                    side[price] = amount
                else:
                    side.pop(price, None)
        # Restrict to the fully observed part of the initial finite snapshot.
        bids = {p:q for p,q in bids.items() if p >= self.bid_boundary}
        asks = {p:q for p,q in asks.items() if p <= self.ask_boundary}
        if not bids or not asks or max(bids) >= min(asks):
            raise BookFault('CROSSED_OR_EXHAUSTED_BOOK')
        if len(bids)+len(asks) > 20000:
            raise BookFault('BOOK_MEMORY_BUDGET')
        self.bids, self.asks = bids, asks
        self.update_id, self.received_ns = e['u'], received_ns
        self.bridged = True
        self.applied += 1
        return True

    def top(self, now_ns, depth=5, max_age_ms=1500):
        if not self.valid or not self.bridged:
            raise BookFault('UNSYNCHRONIZED_BOOK')
        if type(depth) is not int or not 1 <= depth <= 100:
            raise BookFault('INVALID_DEPTH')
        if now_ns < self.received_ns or now_ns-self.received_ns > max_age_ms*1_000_000:
            raise BookFault('STALE_BOOK')
        bids = sorted(self.bids.items(), reverse=True)[:depth]
        asks = sorted(self.asks.items())[:depth]
        if len(bids) != depth or len(asks) != depth:
            raise BookFault('INSUFFICIENT_KNOWN_DEPTH')
        return bids, asks

    def view(self, now_ns):
        bids, asks = self.top(now_ns)
        b, qb = bids[0]
        a, qa = asks[0]
        mid = (a+b)/2
        bv, av = sum(q for _,q in bids), sum(q for _,q in asks)
        return {'symbol': self.symbol, 'update_id': self.update_id,
                'bid': str(b), 'ask': str(a), 'bid_qty': str(qb), 'ask_qty': str(qa),
                'mid': str(mid), 'spread_bps': float((a-b)/mid*10000),
                'imbalance': float((bv-av)/(bv+av)),
                'bids': [[str(p),str(q)] for p,q in bids],
                'asks': [[str(p),str(q)] for p,q in asks],
                'received_ns': self.received_ns, 'synced': True}
