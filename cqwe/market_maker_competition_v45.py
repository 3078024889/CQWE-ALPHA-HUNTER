"""Transparent public-quote market-making benchmark research, NOT actual MM fills.

A market-by-price public book does not identify makers or an individual queue.
This module compares signed *future markouts* and crossing-cost proxies for
predeclared decisions. Passive maker outcomes are never counted as fills or PnL.
"""
from __future__ import annotations
import hashlib
import json
import math
import statistics

FEE_BPS_PER_SIDE = 10.0
SLIP_BPS_PER_SIDE = 2.0


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _outcome(move, position, cross_long):
    """Hypothetical market-order round trip; short actions are NOT actionable in $10 spot mode."""
    if position == 0:
        return 0.0
    if position == 1:
        return cross_long
    # Symmetric mid-price proxy costs, not executable spot-shorting economics.
    return -move - 2 * (FEE_BPS_PER_SIDE + SLIP_BPS_PER_SIDE)


def policies(event):
    """Predeclared textbook MM-inspired policies, no unknown private MM identity.

    Inventory-skew policy uses only running past hypothetical exposure, not future data.
    No passive executions are asserted for any policy.
    """
    x = event['features']
    imbalance, drift = float(x[0]), float(x[1])
    return {
        'cash_do_nothing': 0,
        'always_cross_buy': 1,
        'book_imbalance_filter': 1 if imbalance > 0.25 else 0,
        'trend_and_book_agree': 1 if imbalance > 0.15 and drift > 0.1 else 0,
    }


def evaluate(events):
    """Compare on same post-decision quotes. No fit, no promotions, no actual fills.

    Feature-determined policy outcomes are *proxy* outcomes; seller-side market
    making and resting-order fills require queue/flow simulation and live fills.
    """
    last = -1
    stats = {name: [] for name in ('cash_do_nothing', 'always_cross_buy',
                                   'book_imbalance_filter', 'trend_and_book_agree',
                                   'inventory_skew_proxy')}
    markouts = []
    inventory = 0.0
    for e in events:
        start = int(e['decision_ns']); end = int(e['outcome_ns'])
        if start < 0 or end <= start or start <= last:
            raise ValueError('NONCAUSAL_OR_OVERLAPPING_COMPETITION')
        move = float(e['move_bps']); long_cross = float(e['long_cross_proxy_bps'])
        if not all(math.isfinite(v) for v in (move,long_cross)):
            raise ValueError('INVALID_PROXY_VALUE')
        if len(e['features']) != 4 or not all(math.isfinite(float(x)) for x in e['features']):
            raise ValueError('INVALID_FEATURES')
        for name, direction in policies(e).items():
            if direction:
                stats[name].append(_outcome(move, direction, long_cross))
        # Stylised maker *quote selection*: skew quote toward reducing inventory,
        # but no resting order is counted as filled. A markout is not a PnL.
        bid_markout = move
        ask_markout = -move
        desired_side = 'BID' if float(e['features'][0]) > 0.15 - inventory*.1 else 'ASK'
        markouts.append(bid_markout if desired_side=='BID' else ask_markout)
        inventory = max(-1.0,min(1.0,inventory + (0.05 if desired_side=='BID' else -0.05)))
        last = end
    result={}
    for name, values in stats.items():
        if name == 'inventory_skew_proxy':
            # No paper maker fills: no PnL statistic from predicted maker orders.
            result[name] = {'signals':len(markouts),'hypothetical_fill_count':0,
                            'mean_future_signed_mid_markout_bps':round(statistics.mean(markouts),8) if markouts else None,
                            'mean_crossing_proxy_bps':None,'profit_proven':False}
        else:
            result[name]={'signals':len(values),'hypothetical_fill_count':0,
                          'mean_crossing_proxy_bps':round(statistics.mean(values),8) if values else None,
                          'profit_proven':False}
    report={'schema':'CQWE_V45_MM_COMPETITION_PROXY','event_count':len(events),
            'research_only':True,'individual_market_makers_identified':False,
            'maker_queue_position_known':False,'actual_fills':0,'real_profit_usd':0.0,
            'promotion_allowed':False,'benchmarks':result,
            'limitations':'Public market-by-price L2; stylized policies and future quote proxies only. No maker fills, queue identity, executable short sale or OOS claim.'}
    report['sha256']=_digest(report)
    return report
