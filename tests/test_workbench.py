import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from cqwe.workbench import PaperDesk,Workbench,Handler

T=1800000000000
Q={'BTCUSDT':{'observed_ms':T,'bid':100.,'ask':100.02}}


class PaperDeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'paper.db';self.desk=PaperDesk(self.path)
        self.act('start',mode='manual')
    def tearDown(self):self.desk.db.close();self.tmp.cleanup()
    def act(self,kind,**args):
        return self.desk.action({'action':kind,'request_id':kind+str(self.desk.db.execute('SELECT count(*) FROM actions').fetchone()[0])+':unique-request',**args},Q,T)
    def open(self):return self.act('open',symbol='BTCUSDT',direction=1,amount='2')

    def test_manual_round_trip_charges_fees_and_spread(self):
        self.open();self.act('close',symbol='BTCUSDT')
        self.assertLess(float(self.desk.state['cash']),10)
        self.assertGreater(float(self.desk.state['fees']),0)
        self.assertEqual(len(self.desk.state['trades']),1)
        self.assertLess(float(self.desk.state['trades'][0]['net_pnl']),0)

    def test_repeated_request_is_idempotent(self):
        request={'action':'open','request_id':'same-unique-request','symbol':'BTCUSDT','direction':1,'amount':'2'}
        first=self.desk.action(request,Q,T);second=self.desk.action(request,Q,T)
        self.assertEqual(first,second);self.assertEqual(len(self.desk.state['positions']),1)

    def test_stale_price_bad_amount_and_risk_limit_rejected(self):
        for amount in ('0','-1','NaN','Infinity','3'):
            with self.assertRaises((ValueError,ArithmeticError)):self.act('open',symbol='BTCUSDT',direction=1,amount=amount)
        with self.assertRaises(ValueError):self.desk.action({'action':'open','request_id':'stale-request','symbol':'BTCUSDT','direction':1,'amount':'2'},Q,T+20000)
        self.assertFalse(self.desk.state['positions'])

    def test_pause_keeps_stop_loss_active(self):
        self.open();self.act('pause')
        self.desk.cycle({'BTCUSDT':{'bid':99.,'ask':99.02,'observed_ms':T+1000}}, {},T+1000)
        self.assertFalse(self.desk.state['positions']);self.assertEqual(self.desk.state['trades'][0]['reason'],'STOP_LOSS')

    def test_trend_continuation_and_trailing_exit(self):
        self.open();self.desk.cycle({'BTCUSDT':{'bid':101.,'ask':101.02,'observed_ms':T+1000}}, {},T+1000)
        self.assertTrue(self.desk.state['positions'])
        self.desk.cycle({'BTCUSDT':{'bid':100.7,'ask':100.72,'observed_ms':T+2000}}, {},T+2000)
        self.assertEqual(self.desk.state['trades'][-1]['reason'],'TRAILING_PROFIT_EXIT')

    def test_auto_needs_qualified_fresh_combined_signal(self):
        self.act('start',mode='automatic')
        d={'at_ms':T,'action':'OPEN_LONG','nodes':[],'event_context_fresh':True}
        self.desk.cycle(Q,{'BTCUSDT':d},T);self.assertFalse(self.desk.state['positions'])
        d['nodes']=[{'eligible':True,'weight':1}];d['at_ms']=T-20000
        self.desk.cycle(Q,{'BTCUSDT':d},T);self.assertFalse(self.desk.state['positions'])
        d['at_ms']=T;self.desk.cycle(Q,{'BTCUSDT':d},T);self.assertIn('BTCUSDT',self.desk.state['positions'])

    def test_auto_exit_has_cooldown_and_close_all_pauses(self):
        self.open();self.act('close_all');self.assertFalse(self.desk.state['running'])
        self.act('start',mode='automatic')
        d={'at_ms':T,'action':'OPEN_LONG','nodes':[{'eligible':True,'weight':1}],'event_context_fresh':True}
        self.desk.cycle(Q,{'BTCUSDT':d},T);self.assertFalse(self.desk.state['positions'])

    def test_persisted_position_recovers_without_auto_start(self):
        self.open();self.desk.db.close();self.desk=PaperDesk(self.path)
        self.assertIn('BTCUSDT',self.desk.state['positions']);self.assertFalse(self.desk.state['running'])

    def test_paper_mutation_rollback_on_save_failure(self):
        with patch.object(self.desk,'save',side_effect=RuntimeError('disk error')):
            with self.assertRaises(RuntimeError):self.open()
        self.assertFalse(self.desk.state['positions'])
        self.desk.db.close();self.desk=PaperDesk(self.path);self.assertFalse(self.desk.state['positions'])


class WorkbenchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Workbench(self.tmp.name)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.app=self.app;self.server.token='test-token'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.app.desk.db.close();self.tmp.cleanup()
    def request(self,path,data=None,headers=None):
        return urlopen(Request(self.url+path,data=json.dumps(data).encode() if data else None,headers=headers or {}),timeout=3)
    def test_public_state_and_page_load_without_starting_quotes(self):
        with self.request('/api/state') as r:
            d=json.load(r);self.assertFalse(d['worker_running']);self.assertEqual(d['real_orders'],0)
        with self.request('/') as r:self.assertIn('哥白尼',r.read().decode())
    def test_cross_site_and_tokenless_mutations_rejected(self):
        for headers in ({'Content-Type':'application/json'},
                        {'Content-Type':'application/json','X-CQWE-Token':'test-token','Origin':'https://evil.example'}):
            with self.assertRaises(HTTPError) as cm:self.request('/api/action',{'action':'start'},headers)
            self.assertEqual(cm.exception.code,403)
            cm.exception.close()
        with self.assertRaises(HTTPError) as cm:self.request('/bootstrap.js',headers={'Sec-Fetch-Site':'cross-site'})
        cm.exception.close()
    def test_bad_host_and_oversize_request_rejected(self):
        with self.assertRaises(HTTPError) as cm:self.request('/api/state',headers={'Host':'evil.example'})
        cm.exception.close()
        with self.assertRaises(HTTPError) as cm:self.request('/api/action',{'data':'x'*5000},
           {'Content-Type':'application/json','X-CQWE-Token':'test-token'})
        self.assertEqual(cm.exception.code,400)
        cm.exception.close()


if __name__=='__main__':unittest.main()
