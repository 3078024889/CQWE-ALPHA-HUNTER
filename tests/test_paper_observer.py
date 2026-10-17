import unittest
from cqwe.paper_observer import PaperObserver


def quote(at,mid=100):
    return {'observed_ms':at,'bid':mid-.01,'ask':mid+.01,'raw':{'bids':[[str(mid-.01),'10']], 'asks':[[str(mid+.01),'12']]}}


class PaperObserverTests(unittest.TestCase):
    def test_delayed_label_and_resume(self):
        learner=PaperObserver();d=learner.frame('BTCUSDT',quote(1000),1000)
        self.assertFalse(d['nodes'][0]['eligible'])
        learner=PaperObserver(learner.state);learner.frame('BTCUSDT',quote(301000,101),301000)
        self.assertEqual(learner.state['banks']['BTCUSDT']['n'],1)
        self.assertEqual(learner.state['banks']['BTCUSDT']['model']['updates'],1)
        learner.frame('BTCUSDT',quote(302000,102),302000)
        self.assertEqual(learner.state['banks']['BTCUSDT']['n'],1)

    def test_shutdown_gap_is_not_forward_evidence(self):
        learner=PaperObserver();learner.frame('BTCUSDT',quote(1000),1000)
        learner.frame('BTCUSDT',quote(400000,101),400000)
        self.assertEqual(learner.state['dropped'],1);self.assertEqual(learner.state['banks']['BTCUSDT']['n'],0)

    def test_stale_quote_and_changed_source_rejected(self):
        learner=PaperObserver();self.assertIsNone(learner.frame('BTCUSDT',quote(1000),20000))
        state=learner.state;state['source']='changed'
        with self.assertRaises(ValueError):PaperObserver(state)
