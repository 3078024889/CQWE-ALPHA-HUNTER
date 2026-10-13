import json
import tempfile
import unittest
from pathlib import Path
from cqwe.web3_lab_v18 import cpmm_quote,route_evidence,audit
from cqwe.unified_paper_v18 import portfolio,run


def candles(n=80,trend=.002):
    out=[];price=100.
    for i in range(n):
        prior=price;price=prior*(1+trend)
        out.append([i*300000,str(prior),str(price*1.001),str(prior*.999),str(price),'1',i*300000+299999,'100',1,'1','40','0'])
    return out


class V18Web3(unittest.TestCase):
    def test_zero_fee_reference(self):
        q=cpmm_quote(10,1000,1000,0);self.assertAlmostEqual(q['output'],10000/1010)
    def test_fee_reduces_output(self):
        self.assertLess(cpmm_quote(10,1000,1000,30)['output'],cpmm_quote(10,1000,1000,0)['output'])
    def test_large_trade_worse(self):
        self.assertGreater(cpmm_quote(100,1000,1000)['total_degradation_bps'],cpmm_quote(1,1000,1000)['total_degradation_bps'])
    def test_invalid_reserves(self):
        for a,x,y,f in [(0,1,1,30),(1,0,1,30),(1,1,0,30),(1,1,1,-1),(1,1,1,10000),(1,float('nan'),1,30)]:
            with self.assertRaises(ValueError):cpmm_quote(a,x,y,f)
    def test_route_stale(self):
        q=route_evidence([{'id':'r','output_usd':9}],quote_age_ms=2500)
        self.assertEqual(q['decision'],'REJECT_STALE_OR_UNKNOWN_AGE');self.assertFalse(q['executable'])
    def test_route_price_and_gas(self):
        q=route_evidence([{'id':'b','output_usd':10.1},{'id':'a','output_usd':10.3}],gas_usd=.4,quote_age_ms=100)
        self.assertAlmostEqual(q['best_after_assumed_gas_usd'],9.9)
        self.assertIsNone(q['realized_profit_usd'])
    def test_route_duplicate_rejected(self):
        with self.assertRaises(ValueError):route_evidence([{'id':'a','output_usd':1},{'id':'a','output_usd':2}])
    def test_audit_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'q.json';p.write_text(json.dumps({'type':'cpmm','amount_in':5,'reserve_in':100,'reserve_out':200}))
            self.assertEqual(len(audit(p)['sha256']),64)

class V18Unified(unittest.TestCase):
    def test_unified_single_capital(self):
        q=portfolio({'BTCUSDT':candles(),'ETHUSDT':candles(trend=.004)},min_notional_usd=1)
        self.assertEqual(q['initial_virtual_usd'],10);self.assertEqual(q['symbols'],['BTCUSDT','ETHUSDT']);self.assertTrue(q['ledger_balanced'])
    def test_realistic_minimum_no_orders(self):
        q=portfolio({'BTCUSDT':candles()})
        self.assertEqual(q['entries'],0);self.assertEqual(q['final_virtual_usd'],10)
        self.assertGreater(q['rejected']['min_notional'],0)
    def test_larger_gas_decreases_equity(self):
        params={'min_notional_usd':1,'allocation':.5}
        a=portfolio({'BTCUSDT':candles()},gas_usd_per_order=0,**params)
        b=portfolio({'BTCUSDT':candles()},gas_usd_per_order=.1,**params)
        self.assertLess(b['final_virtual_usd'],a['final_virtual_usd'])
    def test_no_negative_cash(self):
        q=portfolio({'BTCUSDT':candles()},min_notional_usd=1,allocation=1,fee_bps=500,gas_usd_per_order=.3)
        self.assertTrue(q['ledger_balanced'])
        self.assertTrue(all(t['cash_after_usd']>=-1e-7 for t in q['trades']))
    def test_gap_reject(self):
        x=candles();x.pop(20)
        with self.assertRaises(ValueError):portfolio({'BTCUSDT':x})
    def test_no_common_time_reject(self):
        x=candles();y=candles()
        for b in y:b[0]+=100000000;b[6]+=100000000
        with self.assertRaises(ValueError):portfolio({'BTCUSDT':x,'ETHUSDT':y})
    def test_reject_malformed_cost(self):
        with self.assertRaises(ValueError):portfolio({'BTCUSDT':candles()},gas_usd_per_order=-1)
    def test_run_reproducible(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'BTCUSDT_5m.json';p.write_text(json.dumps(candles()))
            a=run([p],Path(d)/'a.json',min_notional_usd=1)
            b=run([p],Path(d)/'b.json',min_notional_usd=1)
            self.assertEqual(a,b);self.assertTrue(a['portfolio']['ledger_balanced'])
    def test_no_future_signal(self):
        a=candles();b=candles();b[-1][4]=str(float(b[-1][4])*1.01);b[-1][2]=str(float(b[-1][4])*1.001)
        x=portfolio({'BTCUSDT':a},min_notional_usd=1)
        y=portfolio({'BTCUSDT':b},min_notional_usd=1)
        self.assertEqual([r for r in x['trades'] if r['side']=='BUY'],[r for r in y['trades'] if r['side']=='BUY'])

if __name__=='__main__':unittest.main()
