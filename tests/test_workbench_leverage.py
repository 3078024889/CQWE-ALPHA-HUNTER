from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest
from cqwe.workbench import PaperDesk

T=1800000000000


def quotes(mid=100,at=T):
    return {'BTCUSDT':{'bid':mid-.01,'ask':mid+.01,'observed_ms':at}}


class LeverageTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.desks=[]
    def tearDown(self):
        for d in self.desks:d.db.close()
        self.tmp.cleanup()
    def desk(self,name,leverage=10):
        d=PaperDesk(Path(self.tmp.name)/(name+'.db'),leverage)
        d.action({'action':'start','mode':'manual','request_id':'start-'+name+'-request'},quotes(),T)
        self.desks.append(d);return d
    def open(self,d,direction=1,amount='2'):
        return d.action({'action':'open','symbol':'BTCUSDT','direction':direction,'amount':amount,
            'request_id':'open-unique-request'},quotes(),T)['position']

    def test_margin_times_ten_is_notional_and_fee_basis(self):
        d=self.desk('ten');p=self.open(d)
        self.assertEqual(D(p['margin']),D(2));self.assertEqual(D(p['notional']),D(20))
        self.assertEqual(p['leverage'],10);self.assertEqual(D(p['entry_fee']),D('.01'))
        self.assertEqual(D(p['quantity'])*D(p['entry']),D(20))

    def test_same_margin_long_and_short_scale_net_pnl_and_fees(self):
        for direction in (1,-1):
            pnl=[];fees=[]
            for leverage in (1,10):
                d=self.desk(f'{direction}_{leverage}',leverage);self.open(d,direction)
                trade=d.close('BTCUSDT',quotes(101,T+1),T+1,'MANUAL_CLOSE')['trade']
                pnl.append(D(trade['net_pnl']));fees.append(D(d.state['fees']))
            self.assertAlmostEqual(float(pnl[1]),float(pnl[0]*10),places=12)
            self.assertAlmostEqual(float(fees[1]),float(fees[0]*10),places=12)

    def test_exposure_limit_uses_margin_and_allows_20_notional(self):
        d=self.desk('risk');self.open(d)
        self.assertEqual(D(d.state['positions']['BTCUSDT']['notional']),D(20))
        other={**quotes(),'ETHUSDT':quotes()['BTCUSDT']}
        with self.assertRaises(ValueError):
            d.action({'action':'open','symbol':'ETHUSDT','direction':1,'amount':'3','request_id':'risk-other-request'},other,T)

    def test_margin_breach_precedes_normal_stop_and_halts(self):
        d=self.desk('margin');self.open(d)
        d.cycle(quotes(49,T+1000),{},T+1000)
        self.assertFalse(d.state['positions']);self.assertTrue(d.state['halted'])
        self.assertEqual(d.state['trades'][0]['reason'],'SIMULATED_MARGIN_EXIT')

    def test_price_stop_does_not_silently_become_margin_roi_stop(self):
        d=self.desk('stop');self.open(d)
        d.cycle(quotes(99.9,T+1000),{},T+1000)
        self.assertTrue(d.state['positions'])
        d.cycle(quotes(99.6,T+2000),{},T+2000)
        self.assertEqual(d.state['trades'][0]['reason'],'STOP_LOSS')

    def test_cannot_relabel_an_existing_position_as_new_leverage(self):
        d=self.desk('migration',1);self.open(d)
        with self.assertRaises(ValueError):PaperDesk(Path(self.tmp.name)/'migration.db',10)
