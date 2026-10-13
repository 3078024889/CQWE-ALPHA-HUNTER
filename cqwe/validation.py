"""Time-block separated, no grid-search leakage; descriptive rather than predictive."""
import json
from pathlib import Path
from .core import valid_candles, save_json
from .alpha import decisions
from .portfolio import simulate, Parameters


def compare(candles, cash=10.0, fee_bps=5.0, slippage_bps=2.0):
    valid_candles(candles)
    if len(candles) < 300:
        raise ValueError('at least 300 5-minute candles required')
    cut=int(len(candles)*0.70)
    result={}
    for key, cs in (('earlier_70pct',candles[:cut]),('later_30pct',candles[cut:])):
        result[key]={}
        for method in ('breakout','reversal','baseline'):
            opts=Parameters(starting_cash=cash,fee_bps=fee_bps,slippage_bps=slippage_bps)
            d=decisions(cs,method=method)
            result[key][method]=simulate(cs,d,opts)
    return {'research_only':True,'sample_sizes':{'earlier':cut,'later':len(candles)-cut},
            'cost_assumptions':{'fee_bps_each_side':fee_bps,'slippage_bps_each_side':slippage_bps},
            'outcomes':result,'warning':'Simulation, not real PnL. Limited price-only data, no funding, spread, impact, liquidation or out-of-sample model selection.'}


def study_file(input_path, output_path='reports/v06_comparison.json'):
    candles=json.loads(Path(input_path).read_text(encoding='utf-8'))
    result=compare(candles)
    save_json(output_path,result)
    return result
