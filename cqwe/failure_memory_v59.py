"""V59 immutable failure records with reason fingerprints; no autonomous promotion."""
import hashlib,json

def analyze_trials(trials):
    seen=set(); failures=[]; promotions=[]
    for t in trials:
        if not isinstance(t,dict) or set(t)!={'id','candidate','window','score','baseline_score','evidence_sha256'}:raise ValueError('INVALID_TRIAL')
        if t['id'] in seen:raise ValueError('DUPLICATE_TRIAL')
        seen.add(t['id'])
        for k in ('score','baseline_score'):
            v=t[k]
            if not isinstance(v,(float,int)) or isinstance(v,bool) or not __import__('math').isfinite(v):raise ValueError('INVALID_SCORE')
        if not isinstance(t['window'],str) or not t['window']:raise ValueError('MISSING_WINDOW')
        if not isinstance(t['candidate'],str) or not t['candidate']:raise ValueError('MISSING_CANDIDATE')
        h=t['evidence_sha256']
        if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):raise ValueError('MISSING_TRIAL_PROOF')
        if t['score']<=t['baseline_score']:
            failures.append({'candidate':t['candidate'],'trial_id':t['id'],'reason':'NO_INDEPENDENT_UPLIFT','evidence_sha256':h})
    return {'trial_count':len(trials),'failed_trials':failures,'automatic_promotions':promotions,'promotion_allowed':False}
