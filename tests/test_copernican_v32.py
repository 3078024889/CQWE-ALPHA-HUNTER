
import unittest
from cqwe.copernican_v32 import Bar, _aggregate_5m, _trend, _levels, _decision

def bars(n=400,start=100.0,step=300000):
    out=[]
    p=start
    for i in range(n):
        p *= 1.0002
        out.append(Bar(i*step,p*0.999,p*1.001,p*0.998,p,100+i,100000+i))
    return out

class V32Tests(unittest.TestCase):
    def test_three_five_minute_make_fifteen(self):
        x=bars(12)
        y=_aggregate_5m(x,15)
        self.assertEqual(len(y),4)
        self.assertAlmostEqual(y[0].o,x[0].o)
        self.assertAlmostEqual(y[0].c,x[2].c)
    def test_uptrend_is_long(self):
        self.assertEqual(_trend(bars(100))["direction"],"LONG")
    def test_support_resistance_are_structural(self):
        x=bars(200)
        lv=_levels(x)
        self.assertIsInstance(lv["supports"],list)
        self.assertIsInstance(lv["resistances"],list)
    def test_alt_does_not_reverse_anchor_without_residual(self):
        x=bars(200)
        frames={k:_trend(_aggregate_5m(x, int(k[:-1])*60 if k.endswith("h") else int(k[:-1])))
                for k in []}
        # Direct decision contract: LONG anchor + positive macro/micro may only yield LONG/HOLD.
        state={"frames":{k:{"score":4} for k in ("24h","6h","4h","1h","30m","15m","5m")},
               "residual_4h":0.0,"price":100.0,"levels":{"supports":[],"resistances":[]},
               "atr_pct":0.01,"returns":{"4h":0.01,"24h":0.02}}
        btc={"frames":{k:{"score":4} for k in ("24h","6h","4h","1h","30m","15m","5m")}}
        book={"bids":[],"asks":[]}
        event={"veto":False}
        d=_decision("ETHUSDT",state,btc,book,event)
        self.assertEqual(d["action"],"LONG")
        self.assertNotEqual(d["action"],"SHORT")
    def test_event_veto_blocks_new_entry(self):
        state={"frames":{k:{"score":4} for k in ("24h","6h","4h","1h","30m","15m","5m")},
               "residual_4h":0.0,"price":100.0,"levels":{"supports":[],"resistances":[]},
               "atr_pct":0.01,"returns":{"4h":0.01,"24h":0.02}}
        btc={"frames":{k:{"score":4} for k in ("24h","6h","4h","1h","30m","15m","5m")}}
        d=_decision("BTCUSDT",state,btc,{"bids":[],"asks":[]},{"veto":True})
        self.assertEqual(d["action"],"HOLD")

if __name__=="__main__":
    unittest.main()
