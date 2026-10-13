import copy,json,tempfile,unittest
from pathlib import Path
from cqwe.mutation_governor_v27 import dependency_audit,register,run,digest

class V27Tests(unittest.TestCase):
 def fixture(self):
  from cqwe.dendritic_diagnostics_v26 import EXPERIMENTS
  p={'version':'CQWE_V26_DENDRITIC_POSTMORTEM','research_only':True,'profit_claim':False,
    'decision':'RESEARCH_ONLY_NO_PROMOTION','source_sha256':'a'*64,
    'proposals':[{'finding':'PRICE_DIRECTION',**EXPERIMENTS['PRICE_DIRECTION'],'status':'PROPOSAL_ONLY_NOT_PROMOTED'}]}
  p['audit_sha256']=digest(p);return p
 def audit(self):return {'deletions_performed':0}
 def test_registered_block(self):
  x=register(self.fixture(),self.audit());self.assertFalse(x['auto_promotion']);self.assertEqual(x['experiments'][0]['candidate_status'],'REGISTERED_NOT_RUN')
 def test_hash_tamper(self):
  p=self.fixture();p['profit_claim']=True
  with self.assertRaises(ValueError):register(p,self.audit())
 def test_tamper_proposal(self):
  p=self.fixture();p['proposals'][0]['finding']='SMALL_SAMPLE'
  with self.assertRaisesRegex(ValueError,'HASH'):register(p,self.audit())
 def test_duplicates(self):
  p=self.fixture();p['proposals']*=2;p['audit_sha256']=digest({k:v for k,v in p.items() if k!='audit_sha256'})
  with self.assertRaisesRegex(ValueError,'INVALID_FINDING'):register(p,self.audit())
 def test_no_source(self):
  p=self.fixture();p.pop('source_sha256')
  with self.assertRaisesRegex(ValueError,'UNBOUND_SOURCE'):register(p,self.audit())
 def test_invalid_audit(self):
  with self.assertRaisesRegex(ValueError,'INVALID_DEPENDENCY'):register(self.fixture(),{'deletions_performed':1})
 def test_unknown_finding(self):
  p=self.fixture();p['proposals'][0]['finding']='UNKNOWN';p['audit_sha256']=digest({k:v for k,v in p.items() if k!='audit_sha256'})
  with self.assertRaisesRegex(ValueError,'INVALID_FINDING'):register(p,self.audit())
 def test_no_mutation(self):
  p=self.fixture();a=self.audit();before=copy.deepcopy((p,a));register(p,a);self.assertEqual((p,a),before)
 def test_dep_scan(self):
  repo=Path(__file__).resolve().parents[1];out=dependency_audit(repo)
  names={v['module']:v for v in out['modules']}
  self.assertIn('self_evolution_v20',names);self.assertFalse(names['self_evolution_v20']['delete_approved'])
  self.assertIn('cqwe/dendritic_diagnostics_v26.py',names['account_forensics_v25']['static_references'])
 def test_report_roundtrip(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=Path(tmp);p=r/'input.json';p.write_text(json.dumps(self.fixture()));out=r/'report.json'
   x=run(p,Path(__file__).resolve().parents[1],out);self.assertEqual(x,json.loads(out.read_text()));self.assertIn('registry_sha256',x)
 def test_repeat(self):self.assertEqual(register(self.fixture(),self.audit()),register(self.fixture(),self.audit()))
 def test_stale_schema(self):
  p=self.fixture();p['version']='V25';p['audit_sha256']=digest({k:v for k,v in p.items() if k!='audit_sha256'})
  with self.assertRaisesRegex(ValueError,'INVALID_POSTMORTEM'):register(p,self.audit())
if __name__=='__main__':unittest.main()
