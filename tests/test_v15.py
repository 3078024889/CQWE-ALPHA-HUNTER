import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.live_books_v15 import (decode_binary_market,book_levels,capture,save_snapshot,replay,public_get,GAMMA,CLOB)

TOKEN_A='123'; TOKEN_B='456'
def market(**extra):
    m={'id':'1','conditionId':'0x'+'a'*64,'question':'Test','outcomes':'["Yes", "No"]',
        'clobTokenIds':'["123", "456"]','active':True,'closed':False,'enableOrderBook':True}
    m.update(extra);return m

def faked(base,path,params):
    if (base,path)==(GAMMA,'/markets'):return [market()]
    token=params['token_id']
    return {'asset_id':token,'asks':[{'price':'.45','size':'100'}],'bids':[]}

class V15Tests(unittest.TestCase):
    def test_binary_token_identity(self):
        self.assertEqual(decode_binary_market(market())['tokens'],['123','456'])
    def test_wrong_outcome_rejected(self):
        self.assertIsNone(decode_binary_market(market(outcomes='["Up", "Down"]')))
    def test_duplicate_token_rejected(self):
        self.assertIsNone(decode_binary_market(market(clobTokenIds='["123", "123"]')))
    def test_closed_rejected(self):
        self.assertIsNone(decode_binary_market(market(closed=True)))
    def test_invalid_book_level(self):
        with self.assertRaises(ValueError):book_levels({'asks':[{'price':'nan','size':10}]})
    def test_allowlist_reject_orders(self):
        with self.assertRaises(ValueError):public_get(CLOB,'/order',{})
    @patch('cqwe.live_books_v15.time.sleep')
    def test_capture_is_not_executable(self,_sleep):
        result=capture(fetcher=faked,clock=iter([1000,1200]).__next__,delay=0)
        x=result['snapshots'][0]
        self.assertEqual(x['estimate']['decision'],'OBSERVATION_ONLY_NOT_EXECUTABLE')
        self.assertFalse(x['quote_age_verified'])
        self.assertFalse(x['estimate']['executable'])
        self.assertAlmostEqual(x['estimate']['indicative_net_after_buffers_usd'],.9)
    def test_wrong_asset_rejected(self):
        def bad(base,path,params):
            if base==GAMMA:return [market()]
            return {'asset_id':'999','asks':[{'price':'.4','size':20}]}
        r=capture(fetcher=bad,clock=lambda:1000,delay=0)
        self.assertEqual(r['snapshots'][0]['decision'],'REJECT_INVALID_BOOK')
    def test_insufficient_depth(self):
        def shallow(base,path,params):
            if base==GAMMA:return [market()]
            return {'asset_id':params['token_id'],'asks':[{'price':'.4','size':1}]}
        r=capture(fetcher=shallow,clock=lambda:1000,delay=0)
        self.assertEqual(r['snapshots'][0]['estimate']['decision'],'REJECT_DEPTH')
    def test_save_replay_and_dedupe(self):
        r=capture(fetcher=faked,clock=lambda:1000,delay=0)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'book.json'; info=save_snapshot(r,p)
            self.assertEqual(len(info['sha256']),64)
            rr=replay([str(p),str(p)])
            self.assertEqual(rr['observations'],1)
            self.assertEqual(rr['verified_executable_trades'],0)
            self.assertIsNone(rr['realized_profit_usd'])
    def test_invalid_schema(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'book.json';p.write_text('{}')
            with self.assertRaises(ValueError):replay([str(p)])
    def test_resource_bounds(self):
        with self.assertRaises(ValueError):capture(limit=500,fetcher=faked)
        with self.assertRaises(ValueError):capture(shares=10000,fetcher=faked)

if __name__=='__main__':unittest.main()
