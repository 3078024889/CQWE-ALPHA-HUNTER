import unittest
from cqwe.event_council_bridge import combine


class EventBridgeTests(unittest.TestCase):
    def book(self,action='OPEN_LONG'):
        return {'symbol':'BTCUSDT','horizon':300,'at_ms':100000,'action':action,
                'nodes':[],'p_up':.7,'execution_enabled':False}

    def state(self):
        return {'at_ms':100000,'scores':{},'upcoming_30min':[], 'execution_enabled':False}

    def test_unvalidated_event_has_zero_weight_and_preserves_probability(self):
        b=self.book();s=combine(b,self.state(),100000)
        self.assertEqual(s['event_weight'],0);self.assertEqual(s['p_up'],.7)
        self.assertEqual(s['action'],'OPEN_LONG');self.assertFalse(s['execution_enabled'])
        self.assertEqual(b['nodes'],[])

    def test_missing_stale_or_future_event_context_vetoes_entry(self):
        for state in (None,{**self.state(),'at_ms':1},{**self.state(),'at_ms':100001}):
            self.assertEqual(combine(self.book(),state,100000)['action'],'WAIT')

    def test_calendar_risk_veto_preserves_close_and_hold(self):
        state=self.state();state['upcoming_30min']=[{'scheduled_ms':105000}]
        self.assertEqual(combine(self.book(),state,100000)['action'],'WAIT')
        for action in ('CLOSE','HOLD'):
            self.assertEqual(combine(self.book(action),state,100000)['action'],action)

    def test_stale_book_and_live_input_rejected(self):
        with self.assertRaises(ValueError):combine(self.book(),self.state(),120000)
        with self.assertRaises(ValueError):combine({**self.book(),'execution_enabled':True},self.state(),100000)


if __name__=='__main__':unittest.main()
