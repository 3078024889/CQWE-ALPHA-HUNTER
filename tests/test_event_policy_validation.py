import unittest
from research.event_policy_validation import evaluate_policy


class PolicyValidationTests(unittest.TestCase):
    def sample(self,p=.8):
        return ({'forecasts':[{'key':'BTCUSDT:300','phase':'holdout','at_ms':1,'p_up':{'selected':p,'better_in_hindsight':.01}}],
                 'chosen_from_validation':{'BTCUSDT:300':'selected'}},
                [{'anchor_ms':1,'symbol':'BTCUSDT','responses':[{'horizon':300,'status':'OBSERVED','return_bps':10}]}])

    def test_right_direction_can_lose_after_costs(self):
        learning,rows=self.sample()
        result=evaluate_policy(learning,rows)
        self.assertEqual(result['summaries']['BTCUSDT:300']['total_net_bps_proxy'],-4)
        self.assertFalse(result['profitability_proven'])

    def test_abstention_has_no_fictitious_trade_or_profit(self):
        learning,rows=self.sample(.5)
        s=evaluate_policy(learning,rows)['summaries']['BTCUSDT:300']
        self.assertEqual(s['counterfactual_trades'],0);self.assertIsNone(s['mean_net_bps_per_trade'])

    def test_ambiguous_duplicate_labels_rejected(self):
        import copy
        learning,rows=self.sample();second=copy.deepcopy(rows[0]);second['responses'][0]['return_bps']=-10
        with self.assertRaises(ValueError):evaluate_policy(learning,rows+[second])


if __name__=='__main__':unittest.main()
