"""V27 reproducible dependency audit and constrained experiment registration.
No live orders, no auto-promotion, no fitting to previously reviewed data.
"""
from __future__ import annotations
import ast, argparse, hashlib, json, math, sys
from pathlib import Path

FINDING_TO_EXPERIMENT = {
 'PRICE_DIRECTION': ('closed_bar_regime_probe','test frozen regime/threshold alternatives on independently later data'),
 'EXECUTION_FRICTION': ('friction_sensitivity_probe','test extra 5/10/20 bps costs without claiming fills'),
 'SMALL_SAMPLE': ('sample_accrual_probe','collect unseen non-overlapping observations without threshold refitting'),
 'ORDER_FEASIBILITY_UNKNOWN': ('venue_metadata_probe','verify actual symbol-specific lot/tick/min-notional from read-only source'),
 'ORDER_FEASIBILITY_REJECTED': ('size_filter_probe','enforce verified trade limits; abstain if $10 cannot meet limits'),
 'LOSS_CONCENTRATION': ('tail_risk_probe','freeze loss thresholds and quantify tails on later data'),
 'NO_TRADES': ('abstention_probe','preserve no-trade baseline and await independent data')
}
PROTECTED = {'self_evolution_v20','dendritic_v19','frozen_portfolio_v24','account_forensics_v25',
             'dendritic_diagnostics_v26','continuous_lab_v21','evidence_audit_v22','evidence_stress_v23'}

def digest(v):
 return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def dependency_audit(repository):
 repo=Path(repository); pkg=repo/'cqwe'; tests=repo/'tests'
 if not pkg.is_dir() or not tests.is_dir(): raise ValueError('REPOSITORY_STRUCTURE_MISSING')
 mods={p.stem:p for p in pkg.glob('*.py') if p.stem!='__init__'}
 names=set(mods); references={n:set() for n in names}; parse_errors=[]
 for folder in (pkg,tests):
  for path in sorted(folder.glob('*.py')):
   try: tree=ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
   except (SyntaxError,UnicodeError) as exc:
    parse_errors.append(path.relative_to(repo).as_posix()+':'+str(exc));continue
   for node in ast.walk(tree):
    if isinstance(node,ast.Import):
     for alias in node.names:
      parts=alias.name.split('.')
      if parts[0]=='cqwe' and len(parts)>1 and parts[1] in names:
       references[parts[1]].add(path.relative_to(repo).as_posix())
    elif isinstance(node,ast.ImportFrom):
     module=(node.module or '').split('.')
     if node.level and path.parent==pkg and module and module[0] in names:
      references[module[0]].add(path.relative_to(repo).as_posix())
     if module and module[0]=='cqwe' and len(module)>1 and module[1] in names:
      references[module[1]].add(path.relative_to(repo).as_posix())
     # from cqwe import x / from . import x
     if (node.level and path.parent==pkg and not node.module) or node.module=='cqwe':
      for alias in node.names:
       if alias.name in names:references[alias.name].add(path.relative_to(repo).as_posix())
 if parse_errors:raise ValueError('DEPENDENCY_PARSE_FAILURE: '+'; '.join(parse_errors))
 modules=[]
 for name,path in sorted(mods.items()):
  refs=sorted(references[name]);special=(name in PROTECTED or name in ('__main__','cli'))
  modules.append({'module':name,'path':path.relative_to(repo).as_posix(),'static_references':refs,
   'disposition':'RETAIN_ACTIVE_OR_SAFETY_CRITICAL' if refs or special else 'REVIEW_ONLY_UNPROVEN_UNUSED',
   'delete_approved':False})
 return {'modules':modules,'protected':sorted(PROTECTED),'scanned_modules':len(modules),
         'unproven_unused':sum(m['disposition']=='REVIEW_ONLY_UNPROVEN_UNUSED' for m in modules),
         'deletions_performed':0,
         'limitations':['AST import analysis misses dynamic imports, CLI entry points and third-party integrations.',
           'No existing module is deleted without dynamic usage evidence and a migration test.']}

def register(postmortem,audit):
 if not isinstance(postmortem,dict) or postmortem.get('version')!='CQWE_V26_DENDRITIC_POSTMORTEM' or not postmortem.get('research_only') or postmortem.get('decision')!='RESEARCH_ONLY_NO_PROMOTION' or postmortem.get('profit_claim') is not False:
  raise ValueError('INVALID_POSTMORTEM')
 if not isinstance(postmortem.get('source_sha256'),str) or len(postmortem['source_sha256'])!=64:raise ValueError('UNBOUND_SOURCE')
 if not isinstance(postmortem.get('audit_sha256'),str) or len(postmortem['audit_sha256'])!=64:raise ValueError('UNBOUND_AUDIT')
 copy=dict(postmortem);stamp=copy.pop('audit_sha256')
 if digest(copy)!=stamp:raise ValueError('POSTMORTEM_HASH_MISMATCH')
 if not isinstance(audit,dict) or audit.get('deletions_performed')!=0:raise ValueError('INVALID_DEPENDENCY_AUDIT')
 proposals=postmortem.get('proposals')
 if not isinstance(proposals,list) or not proposals:raise ValueError('EMPTY_PROPOSALS')
 seen=set();experiments=[]
 for proposal in proposals:
  if not isinstance(proposal,dict):raise ValueError('INVALID_PROPOSAL')
  finding=proposal.get('finding')
  if finding not in FINDING_TO_EXPERIMENT or finding in seen or proposal.get('status')!='PROPOSAL_ONLY_NOT_PROMOTED':raise ValueError('INVALID_FINDING')
  seen.add(finding);variant,question=FINDING_TO_EXPERIMENT[finding]
  experiments.append({'id':variant,'finding':finding,'hypothesis':question,
   'candidate_status':'REGISTERED_NOT_RUN',
   'required_evidence':['frozen rule and dataset SHA256', 'strictly later unseen sample',
    'costed next-bar account ledger', 'comparison with $10 zero-trade cash baseline',
    'symbol-specific venue metadata when asserting order feasibility'],
   'promotion':'BLOCKED_NO_INDEPENDENT_FORWARD_EVIDENCE'})
 return {'version':'CQWE_V27_MUTATION_REGISTRY','research_only':True,'no_orders':True,
         'input_postmortem_sha256':stamp,'source_forensics_sha256':postmortem['source_sha256'],
         'dependencies':audit,'experiments':experiments,
         'auto_promotion':False,'independent_forward_evidence':False,
         'decision':'HOLD_CASH_AND_COLLECT_FORWARD_EVIDENCE',
         'warning':'Historical diagnostic experiments do not provide new independent trading PnL.'}

def run(postmortem_path,repo,output):
 original=Path(postmortem_path).read_bytes();post=json.loads(original.decode('utf-8-sig'))
 result=register(post,dependency_audit(repo));result['input_file_sha256']=hashlib.sha256(original).hexdigest()
 result['registry_sha256']=digest(result)
 out=Path(output);out.parent.mkdir(parents=True,exist_ok=True)
 tmp=out.with_name(out.name+'.tmp');tmp.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');tmp.replace(out)
 return result

def main():
 parser=argparse.ArgumentParser(description='Read-only V27 dependency and registered mutation audit')
 parser.add_argument('--postmortem',required=True);parser.add_argument('--repo',default='.')
 parser.add_argument('--output',default='reports/v27_mutation_registry.json');args=parser.parse_args()
 result=run(args.postmortem,args.repo,args.output)
 print('V27 modules=',result['dependencies']['scanned_modules'],'review_candidates=',result['dependencies']['unproven_unused'],
       'removed=',result['dependencies']['deletions_performed'],'registered=',len(result['experiments']))
 print('CQWE_V27_REGISTRY_PASS | NO DELETIONS WITHOUT PROOF | NO PROMOTION | NO ORDERS')
if __name__=='__main__':main()
