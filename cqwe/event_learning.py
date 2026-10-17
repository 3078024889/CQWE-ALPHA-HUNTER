"""Append-only event-resolution forecasts and delayed, category-specific learning.

No market price is used as the resolved outcome. No account/order capability.
Initial model equals the market reference; learned residuals are uncalibrated.
"""
import contextlib
import json
import math
import os
from pathlib import Path

from .copernican_experiment_v81_v85 import digest


def finite(value, lo, hi):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError('INVALID_BOUNDED_NUMBER')
    return float(value)


def source_hash(value):
    if not isinstance(value,str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('SOURCE_HASH_REQUIRED')
    return value


class EventLearner:
    def __init__(self):
        self.forecasts = {}
        self.resolved = set()
        self.models = {}
        self.scores = []
        self.last_ms = -1

    def model(self, category):
        if not isinstance(category,str) or not 1 <= len(category) <= 100:
            raise ValueError('INVALID_CATEGORY')
        return self.models.setdefault(category, {'weights':[0.]*4,'memory':[0.]*4,'updates':0})

    def _clock(self, at_ms):
        if type(at_ms) is not int or at_ms < self.last_ms:
            raise ValueError('EVENT_CLOCK_REVERSED')
        self.last_ms = at_ms

    def forecast(self, *, event_id, category, market_probability, features, source_sha256, at_ms):
        if not isinstance(event_id,str) or not event_id or len(event_id) > 100:
            raise ValueError('INVALID_EVENT_ID')
        if event_id in self.forecasts:
            raise ValueError('EVENT_ALREADY_FORECAST')
        p0 = finite(market_probability,.000001,.999999)
        if not isinstance(features,list) or len(features) != 4:
            raise ValueError('INVALID_FEATURE_DIMENSION')
        x = [finite(v,-1,1) for v in features]
        source_hash(source_sha256)
        m = self.model(category)
        u = [v+.1*mem for v,mem in zip(x,m['memory'])]
        branches = [math.tanh(sum(m['weights'][j]*u[j] for j in group)) for group in ((0,1),(2,3))]
        z = math.log(p0/(1-p0))+.5*sum(branches)
        p = 1/(1+math.exp(-z))
        self._clock(at_ms)
        row = {'event_id':event_id,'category':category,'market_probability':p0,
               'features':x,'source_sha256':source_sha256,'at_ms':at_ms,
               'predicted_probability':p,'model_before_sha256':digest(m),
               'model_updates_before_forecast':m['updates'],
               'cache':{'u':u,'branches':branches}}
        self.forecasts[event_id] = row
        return row

    def resolve(self, *, event_id, outcome, source_sha256, at_ms):
        if event_id not in self.forecasts or event_id in self.resolved:
            raise ValueError('UNKNOWN_OR_ALREADY_RESOLVED_EVENT')
        if type(outcome) is not int or outcome not in (0,1):
            raise ValueError('FINAL_BINARY_OUTCOME_REQUIRED')
        source_hash(source_sha256)
        f = self.forecasts[event_id]
        if type(at_ms) is not int or at_ms <= f['at_ms']:
            raise ValueError('OUTCOME_NOT_AFTER_FORECAST')
        self._clock(at_ms)
        p,p0 = f['predicted_probability'],f['market_probability']
        score = {'brier':(p-outcome)**2,'market_brier':(p0-outcome)**2,
                 'log_loss':-math.log(p if outcome else 1-p),
                 'market_log_loss':-math.log(p0 if outcome else 1-p0)}
        m = self.model(f['category'])
        # Delayed SGD uses the cache/prediction that was actually committed.
        for j in range(4):
            slope = .5*(1-f['cache']['branches'][j//2]**2)
            delta = .05*(outcome-p)*slope*f['cache']['u'][j]
            m['weights'][j] = max(-1.,min(1.,m['weights'][j]+delta))
            m['memory'][j] = .9*m['memory'][j]+.1*f['features'][j]*(2*outcome-1)
        m['updates'] += 1
        self.resolved.add(event_id)
        self.scores.append(score)
        return {'event_id':event_id,'outcome':outcome,'source_sha256':source_sha256,
                'at_ms':at_ms,'score':score,'model_after_sha256':digest(m)}

    def summary(self):
        n = len(self.scores)
        means = {k:sum(s[k] for s in self.scores)/n if n else None
                 for k in ('brier','market_brier','log_loss','market_log_loss')}
        return {'schema':'CQWE_EVENT_RESOLUTION_LEARNING_V1','forecasts':len(self.forecasts),
                'resolved_events':n,'pending_events':len(self.forecasts)-n,
                'category_models':self.models,'mean_scores':means,
                'probabilities_calibrated':False,'independent_event_alpha_proven':False,
                'real_orders':0,'realized_account_profit':None}


class EventJournal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)

    @contextlib.contextmanager
    def lock(self):
        lock = self.path.with_suffix(self.path.suffix+'.lock')
        with lock.open('x') as f:
            f.write(str(os.getpid()))
        try:
            yield
        finally:
            lock.unlink()

    def load(self):
        learner = EventLearner()
        previous = None
        sequence = 0
        if not self.path.exists():
            return learner,previous,sequence
        if self.path.stat().st_size > 30_000_000:
            raise ValueError('EVENT_JOURNAL_BUDGET')
        with self.path.open(encoding='utf-8') as f:
            for line in f:
                if len(line) > 200000 or sequence >= 10000:
                    raise ValueError('EVENT_RECORD_BUDGET')
                row = json.loads(line)
                if row.get('sequence') != sequence+1 or row.get('previous') != previous:
                    raise ValueError('EVENT_CHAIN_BROKEN')
                if row.get('sha256') != digest({k:v for k,v in row.items() if k != 'sha256'}):
                    raise ValueError('EVENT_RECORD_CHANGED')
                inputs = row['inputs']
                if row['kind'] == 'FORECAST':
                    actual = learner.forecast(**inputs)
                elif row['kind'] == 'RESOLVED':
                    actual = learner.resolve(**inputs)
                else:
                    raise ValueError('UNKNOWN_EVENT_OPERATION')
                if actual != row['result']:
                    raise ValueError('EVENT_LEARNING_REPLAY_MISMATCH')
                previous,sequence = row['sha256'],sequence+1
        return learner,previous,sequence

    def append(self, kind, **inputs):
        with self.lock():
            learner,previous,sequence = self.load()
            if kind == 'FORECAST':
                result = learner.forecast(**inputs)
            elif kind == 'RESOLVED':
                result = learner.resolve(**inputs)
            else:
                raise ValueError('UNKNOWN_EVENT_OPERATION')
            row = {'kind':kind,'inputs':inputs,'result':result,
                   'previous':previous,'sequence':sequence+1}
            row['sha256'] = digest(row)
            with self.path.open('a',encoding='utf-8') as f:
                f.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
                f.flush()
                os.fsync(f.fileno())
            return result
