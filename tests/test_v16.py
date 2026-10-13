import json
import tempfile
import unittest
from pathlib import Path
from cqwe.provenance_v16 import audit,canonical_hash,observation

C1='0x'+'a'*64
C2='0x'+'b'*64

def obs(cid=C1,yes=.45,no=.45):
    share=10
    return {'market':{'condition_id':cid,'tokens':['123','456']},'observation_start_ms':100,'observation_end_ms':120,
            'quote_age_verified':False,'yes_asks':[{'price':yes,'size':20}],
            'no_asks':[{'price':no,'size':20}],
            'estimate':{'indicative_net_after_buffers_usd':round(share*(1-yes-no)-.1,8)}}

def payload(rows):
    return {'research_only':True,'schema_version':1,'snapshots':rows,'requested_shares':10,'fee_buffer_usd':.1}

class V16Tests(unittest.TestCase):
    def test_market_hash_differs(self):
        self.assertNotEqual(canonical_hash(obs()),canonical_hash(obs(C2)))
    def test_same_file_hash_is_intentional(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s.json';p.write_text(json.dumps(payload([obs(),obs(C2)])))
            records=audit([p])['records']
            self.assertEqual(records[0]['source_file_sha256'],records[1]['source_file_sha256'])
            self.assertNotEqual(records[0]['observation_sha256'],records[1]['observation_sha256'])
    def test_duplicate_removed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s.json';p.write_text(json.dumps(payload([obs(),obs()])))
            r=audit([p,p]);self.assertEqual(r['unique_observations'],1)
            self.assertEqual(r['duplicate_observations_removed'],3)
    def test_mismatch_fails(self):
        a=obs();a['estimate']['indicative_net_after_buffers_usd']=100
        with self.assertRaises(ValueError):observation(a,10,.1)
    def test_zero_depth(self):
        a=obs();a['yes_asks'][0]['size']=1;a['estimate']={}
        self.assertEqual(observation(a,10,.1)['decision'],'REJECT_DEPTH')
    def test_negative_spread(self):
        a=obs(yes=.55,no=.55)
        self.assertLess(observation(a,10,.1)['net_after_buffer_usd'],0)
    def test_still_not_executable(self):
        self.assertFalse(observation(obs(),10,.1)['executable'])
    def test_invalid_token_mapping(self):
        a=obs();a['market']['tokens']=['1','1']
        with self.assertRaises(ValueError):observation(a,10,.1)
    def test_invalid_time(self):
        a=obs();a['observation_end_ms']=99
        with self.assertRaises(ValueError):observation(a,10,.1)
    def test_bad_file_schema(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s.json';p.write_text('{}')
            with self.assertRaises(ValueError):audit([p])
    def test_zero_cost_not_profit(self):
        a=obs(yes=.49,no=.49);a['estimate']['indicative_net_after_buffers_usd']=.2
        self.assertEqual(observation(a,10,0)['decision'],'OBSERVATION_ONLY_NOT_EXECUTABLE')
    def test_invalid_count(self):
        with self.assertRaises(ValueError):audit([])

if __name__=='__main__': unittest.main()
