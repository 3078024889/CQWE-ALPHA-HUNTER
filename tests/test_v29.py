import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cqwe.public_data_v29 import collect, _bar, PERIOD

FIRST=1791870300000
NOW=FIRST+251*PERIOD

def candle(t):
    return [t,'100','102','99','101','3',t+PERIOD-1,'301',10,'1','100','0']

def fetch(sym,start,end):
    return [candle(i) for i in range(start,min(end+1,start+1000*PERIOD),PERIOD)]

class CollectorTests(unittest.TestCase):
    def go(self,dir,now=NOW,fn=fetch):
        with patch('cqwe.public_data_v29.verify_saved',return_value={'last_seen_ms':FIRST-PERIOD,'tip_sha256':'f'*64}):
            return collect('unused',dir,fetch=fn,now_ms=now)
    def test_first_250_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.go(d);self.assertTrue(a['forward_ready']);self.assertEqual(a['bars_per_symbol'],251)
            b=self.go(d,now=NOW+2*PERIOD);self.assertEqual(b['new_bars_by_symbol']['BTCUSDT'],2)
            self.assertEqual(b['bars_per_symbol'],253)
    def test_partial_not_ready(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.go(d,now=FIRST+20*PERIOD);self.assertFalse(a['forward_ready']);self.assertEqual(a['bars_per_symbol'],20)
    def test_no_uncclosed(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.go(d,now=FIRST+PERIOD//2);self.assertEqual(a['bars_per_symbol'],0)
    def test_missing_gap(self):
        with tempfile.TemporaryDirectory() as d:
            def gap(s,a,b):return [candle(a),candle(a+2*PERIOD)]
            with self.assertRaisesRegex(ValueError,'GAP'):self.go(d,fn=gap)
    def test_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            def dup(s,a,b):return [candle(a),candle(a)]
            with self.assertRaisesRegex(ValueError,'DUPLICATE'):self.go(d,fn=dup)
    def test_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            self.go(d)
            Path(d,'BTCUSDT_5m.json').write_text('[]')
            with self.assertRaisesRegex(ValueError,'TAMPERED'):self.go(d)
    def test_wrong_tip(self):
        with tempfile.TemporaryDirectory() as d:
            self.go(d)
            with patch('cqwe.public_data_v29.verify_saved',return_value={'last_seen_ms':FIRST-PERIOD,'tip_sha256':'e'*64}):
                with self.assertRaisesRegex(ValueError,'CHECKPOINT_CHANGED'):collect('unused',d,fetch=fetch,now_ms=NOW)
    def test_bad_candle(self):
        b=candle(FIRST);b[2]='98'
        with self.assertRaisesRegex(ValueError,'BAD_PRICE'):_bar(b,NOW)
    def test_partial_failure_leaves_no_files(self):
        with tempfile.TemporaryDirectory() as d:
            def fail(s,a,b):
                if s=='SOLUSDT':raise RuntimeError('HTTP_451')
                return fetch(s,a,b)
            with self.assertRaisesRegex(RuntimeError,'HTTP_451'):self.go(d,fn=fail)
            self.assertFalse(Path(d,'manifest_v29.json').exists())
            self.assertFalse(Path(d,'BTCUSDT_5m.json').exists())
    def test_reject_modified_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            self.go(d)
            p=Path(d,'manifest_v29.json');x=json.loads(p.read_text());x['bars_per_symbol']=100;p.write_text(json.dumps(x))
            with self.assertRaisesRegex(ValueError,'MANIFEST_TAMPERED'):self.go(d)
    def test_limit(self):
        from cqwe.public_data_v29 import _download
        b=_download('BTCUSDT',FIRST,FIRST+1001*PERIOD,fetch)
        self.assertEqual(len(b),1002)
    def test_complete_bar_boundary(self):
        self.assertIsNone(_bar(candle(FIRST),FIRST+PERIOD-1))
        self.assertEqual(_bar(candle(FIRST),FIRST+PERIOD)[0],FIRST)
if __name__=='__main__':unittest.main()
