import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from research.learn_event_history import evaluate,features
from research.event_history_impact import window,daily_window,summarize
from research.extract_release_values import extract


def row(t,index=0):
    rs=[{'horizon':h,'status':'OBSERVED','label':1 if index%2 else -1,
         'return_bps':10. if index%2 else -10.,'pre_return_bps':2.,'range_bps':20.,
         'max_lower_wick_bps':5.,'max_upper_wick_bps':3.} for h in (300,900,3600)]
    return {'anchor_ms':t,'symbol':'BTCUSDT','event_type':'US_CPI','event_id':'E'+str(index),
            'cluster_id':'TIME_'+str(t),'responses':rs}


class EventHistoryTests(unittest.TestCase):
    def sample(self):
        return [row(1700000000000+i*86400000,i) for i in range(50)]

    def test_central_and_eastern_times_agree(self):
        for day in ('2025-01-08','2025-07-02'):
            d=dt.datetime.fromisoformat(day)
            ct=d.replace(hour=7,minute=15,tzinfo=ZoneInfo('America/Chicago'))
            et=d.replace(hour=8,minute=15,tzinfo=ZoneInfo('America/New_York'))
            self.assertEqual(ct.timestamp(),et.timestamp())

    def test_daylight_saving_changes_utc_release_hour(self):
        a=dt.datetime(2025,1,15,8,30,tzinfo=ZoneInfo('America/New_York'))
        b=dt.datetime(2025,7,15,8,30,tzinfo=ZoneInfo('America/New_York'))
        self.assertEqual(a.astimezone(dt.timezone.utc).hour,13)
        self.assertEqual(b.astimezone(dt.timezone.utc).hour,12)

    def test_training_labels_mature_before_train_boundary(self):
        r=evaluate(self.sample())
        self.assertLess(r['last_training_label_maturity_ms'],r['train_end_ms'])
        self.assertTrue(all(v==30 for v in r['model_updates'].values()))
        self.assertFalse(r['execution_eligible'])

    def test_duplicate_simultaneous_headlines_do_not_double_labels(self):
        a=self.sample();b=copy.deepcopy(a)
        for v in b:v['event_type']='US_RETAIL'
        single=evaluate(a);double=evaluate(a+b)
        self.assertEqual(single['groups'],double['groups'])
        self.assertEqual(single['model_updates'],double['model_updates'])

    def test_changing_future_holdout_does_not_change_forecasts(self):
        a=self.sample();b=copy.deepcopy(a)
        for row_ in b[40:]:
            for r in row_['responses']:r['label']=-r['label']
        x=evaluate(a);y=evaluate(b)
        self.assertEqual(x['forecasts'],y['forecasts'])
        self.assertEqual(x['chosen_from_validation'],y['chosen_from_validation'])

    def test_feature_vector_does_not_use_post_event_returns(self):
        a=row(1700000000000);b=copy.deepcopy(a)
        for r in b['responses']:r['return_bps']=10000.
        self.assertEqual(features(['US_CPI'],a['anchor_ms'],a['responses']),
                         features(['US_CPI'],b['anchor_ms'],b['responses']))

    def test_small_history_does_not_create_fake_holdout(self):
        with self.assertRaises(ValueError):evaluate(self.sample()[:10])

    def test_window_has_all_minutes_and_wick_fields(self):
        event={'event_id':'E','family':'US_CPI','event_type':'US_CPI','scheduled_ms':3600000,
               'timing_status':'TEST'}
        raw=[[i*60000,'100','102','98','101','10',i*60000+59999,'0',1,'0','0','0'] for i in range(120)]
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'candles').mkdir()
            with patch('research.event_history_impact.public',return_value=raw),patch('research.event_history_impact.time.sleep'):
                r=window(event,'BTCUSDT',root)
        self.assertTrue(all(v['status']=='OBSERVED' for v in r['responses']))
        self.assertTrue(all(v['max_lower_wick_bps']==200 for v in r['responses']))

    def test_date_only_hour_gap_rejected(self):
        e={'scheduled_ms':0,'event_id':'E','event_type':'BOJ_RATE','local_date':'2025-01-01'}
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'candles').mkdir()
            with patch('research.event_history_impact.public',return_value=[]),patch('research.event_history_impact.time.sleep'):
                with self.assertRaises(ValueError):daily_window(e,'BTCUSDT',root)

    def test_missing_pre_window_keeps_unknown(self):
        r=row(0)
        for v in r['responses']:v['pre_return_bps']=None
        report=summarize([{}],[r])
        self.assertIsNone(report['statistics'][0]['median_abs_change_vs_pre_bps'])

    def test_archived_ppi_decline_keeps_negative_sign(self):
        r=extract('US_PPI','The Producer Price Index for final demand edged down 0.1 percent in August.')
        self.assertEqual(r['value'],-.1)

    def test_archived_nfp_edges_and_parenthetical_change(self):
        self.assertEqual(extract('US_NFP','Total nonfarm payroll employment edged down by 92,000')['value'],-92000)
        self.assertEqual(extract('US_NFP','Total nonfarm payroll employment was essentially unchanged in October (+12,000)')['value'],12000)

    def test_little_change_without_number_is_unknown(self):
        self.assertIsNone(extract('US_NFP','Total nonfarm payroll employment changed little.'))

    def test_jolts_level_is_not_a_monthly_change(self):
        r=extract('US_JOLTS','The number of job openings was little changed at 7.4 million.')
        self.assertEqual(r['metric'],'openings_level');self.assertEqual(r['unit'],'million_jobs')


if __name__=='__main__':unittest.main()
