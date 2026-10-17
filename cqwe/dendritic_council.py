"""Deterministic model routing and explainable shadow actions, never order access."""
import math


def decide(engine, symbol, at_ms, view, baseline, micro, quality):
    """Fuse only past-scored nodes; an unvalidated node gets zero decision weight."""
    nodes = []
    h = engine.cfg['horizons_seconds'][0]
    key = f'{symbol}:{h}'
    for kind, model in engine.models[key].items():
        score = engine.scores[key][kind]
        n = score['n']
        p = model.predict(baseline)[0]
        # Match the original descriptive paper gate, not a profitability certificate.
        from .four_market_core import eligible
        ready = kind != 'frozen' and eligible(score, engine.cfg['minimum_labels'])
        nodes.append({'id':kind, 'p_up':p, 'labels':n, 'eligible':ready,
                      'weight':math.exp(-8*score['brier_sum']/n) if ready else 0.})
    bank = engine.liquidity_study.models[key]
    for kind, model in bank.items():
        x = baseline + micro
        if kind == 'control':
            x = baseline + [0.]*8
        elif kind == 'no_liquidation':
            x = x.copy(); x[12] = x[13] = 0.
        nodes.append({'id':'liquidity:'+kind, 'p_up':model.predict(x)[0],
                      'labels':engine.liquidity_study.stats[key]['n'],
                      'eligible':False, 'weight':0.})
    total = sum(n['weight'] for n in nodes)
    p = sum(n['p_up']*n['weight'] for n in nodes)/total if total else .5
    liq, flow, refill = micro[4], micro[2], micro[1]
    mechanism = ('LIQUIDATION_CONTINUATION' if abs(liq)>.1 and liq*flow>0 and abs(flow)>.25
                 and liq*refill>=0 else 'POSSIBLE_ABSORPTION' if abs(liq)>.1 and liq*refill<-.05
                 else 'NO_CONFIRMED_LIQUIDATION_PATH')
    position = engine.portfolio.futures.get(symbol)
    guard = engine.liquidity.entry_guard(symbol,at_ms,h,view.get('decision_ns',view['received_ns']))
    ready = bool(total) and quality['context_ready'] and not guard and not engine.portfolio.halted
    if position and not position.get('pending'):
        move = position['direction']*(float(view['bid' if position['direction']==1 else 'ask'])/
                                     float(position['entry'])-1)*10000
        close = (engine.portfolio.halted or position.get('force_exit') or at_ms>=position['expires_ms']
                 or move <= -float(engine.cfg['stop_bps']) or move >= float(engine.cfg['take_bps']))
        action = 'CLOSE' if close else 'HOLD'
        reason = 'POSITION_EXIT_RULE' if close else 'POSITION_WITHIN_EXIT_RULES'
    elif position:
        action,reason = 'WAIT','PAPER_ENTRY_PENDING'
    elif ready and (p>=.55 or p<=.45):
        action,reason = ('OPEN_LONG' if p>=.55 else 'OPEN_SHORT'),'QUALIFIED_NODE_CONSENSUS'
    else:
        action,reason = 'OBSERVE',guard or ('INSUFFICIENT_PAST_EVIDENCE' if not total else
                                          'CONTEXT_OR_RISK_GATE' if not ready else 'WEAK_CONSENSUS')
    return {'symbol':symbol,'at_ms':at_ms,'horizon':h,'action':action,'reason':reason,
            'p_up':p,'nodes':nodes,'mechanism_hypothesis':mechanism,
            'paper_advisory_only':True,'execution_enabled':False,'maker_identity_known':False,
            'next_plan':'WAIT_FOR_MATURE_LABELS_AND_COMPARE_COST_ADJUSTED_OUTCOMES'}
