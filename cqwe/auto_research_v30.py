"""CQWE V30: collect then run one immutable first-240-bar research evaluation.
No trading, credentials, model promotion, repeated candidate selection or claimed profit.
Scheduler calls this module; only published closed bars enter the frozen snapshot.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from .public_data_v29 import collect, SYMBOLS, PERIOD, _digest
from .continuous_lab_v21 import verify_saved, read_markets
from .forward_experiment_v28 import evaluate

FIRST_WINDOW = 240

def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _atomic(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    os.replace(tmp, p)

def _verify_finished(root, checkpoint):
    receipt_path = root / 'receipt_v30.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt.get('receipt_sha256') != _digest({k:v for k,v in receipt.items() if k!='receipt_sha256'}):
        raise ValueError('RECEIPT_TAMPERED')
    if receipt['checkpoint_tip_sha256'] != checkpoint['tip_sha256']:
        raise ValueError('CHECKPOINT_CHANGED')
    if receipt['snapshot_start_ms'] != checkpoint['last_seen_ms'] + PERIOD:
        raise ValueError('SNAPSHOT_CHECKPOINT_MISMATCH')
    for name, expected in receipt['artifact_sha256'].items():
        if name not in {'forward_v28.json', *(f'snapshot/{sym}_5m.json' for sym in SYMBOLS)}:
            raise ValueError('BAD_RECEIPT_FILENAME')
        path = root/name
        if not path.is_file() or _sha(path) != expected:
            raise ValueError('IMMUTABLE_ARTIFACT_CHANGED: '+name)
    report = json.loads((root/'forward_v28.json').read_text(encoding='utf-8'))
    if report.get('audit_sha256') != _digest({k:v for k,v in report.items() if k!='audit_sha256'}):
        raise ValueError('FORWARD_REPORT_TAMPERED')
    if report['future_first_ms'] != receipt['snapshot_start_ms'] or report['future_last_ms'] != receipt['snapshot_end_ms']:
        raise ValueError('REPORT_WINDOW_MISMATCH')
    if any(not v['ledger_balanced'] for v in report['variants']):
        raise ValueError('UNBALANCED_LEDGER')
    return {'status':'ALREADY_VERIFIED','bars':FIRST_WINDOW,'receipt_sha256':receipt['receipt_sha256'],'research_only':True}

def run_cycle(store='reports/v21_evidence', output_dir='data/future', registry='reports/v27_mutation_registry.json',
              evidence_dir='reports/v30_forward_first240', *, do_collect=True, collector=collect, evaluator=evaluate):
    root = Path(evidence_dir)
    root.mkdir(parents=True,exist_ok=True)
    lock = root/'.cycle_lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError('CYCLE_ALREADY_RUNNING_OR_STALE_LOCK: review before removing') from None
    try:
        checkpoint = verify_saved(store)
        if (root/'receipt_v30.json').exists():
            # Validate frozen study first; continue accumulating public closed-bar data.
            status = _verify_finished(root, checkpoint)
            if do_collect:
                latest = collector(store, output_dir)
                status['latest_collected_bars'] = latest['bars_per_symbol']
            return status
        if any(root.iterdir()) and {p.name for p in root.iterdir()} != {'.cycle_lock'}:
            raise RuntimeError('INCOMPLETE_EVIDENCE_DIR: manual review required, no automatic overwrite')
        if do_collect:
            collected = collector(store, output_dir)
        else:
            manifest = Path(output_dir)/'manifest_v29.json'
            if not manifest.is_file():raise FileNotFoundError('COLLECTION_MANIFEST_MISSING')
            collected = json.loads(manifest.read_text(encoding='utf-8'))
        if collected.get('manifest_sha256') != _digest({k:v for k,v in collected.items() if k!='manifest_sha256'}):
            raise ValueError('COLLECTION_MANIFEST_INVALID')
        bar_count = collected['bars_per_symbol']
        if not collected['forward_ready'] or bar_count < FIRST_WINDOW:
            return {'status':'WAIT_FOR_CLOSED_BARS','bars':bar_count,'needed':max(0,FIRST_WINDOW-bar_count),'research_only':True}
        if collected['checkpoint_tip_sha256'] != checkpoint['tip_sha256']:
            raise ValueError('COLLECTOR_CHECKPOINT_MISMATCH')
        inputs = [Path(output_dir)/(s+'_5m.json') for s in SYMBOLS]
        for sym,p in zip(SYMBOLS, inputs):
            if _sha(p) != collected['source_sha256'][sym]:raise ValueError('COLLECTED_DATA_CHANGED')
        times, market, _ = read_markets(inputs)
        if len(times) != bar_count or times[0] != checkpoint['last_seen_ms']+PERIOD:
            raise ValueError('BAD_FORWARD_BOUNDARY')
        if len(times)<FIRST_WINDOW:raise ValueError('INSUFFICIENT_ALIGNED_WINDOW')
        # No look-ahead beyond first 240 bars: evidence remains frozen once ready.
        snapshot = root/'snapshot'
        snapshot.mkdir()
        snapshot_paths = []
        for sym in SYMBOLS:
            p = snapshot/(sym+'_5m.json')
            _atomic(p, market[sym][:FIRST_WINDOW])
            snapshot_paths.append(p)
        result_path = root/'forward_v28.json'
        try:
            result = evaluator(registry, store, snapshot_paths, str(result_path))
            if not result_path.is_file():raise RuntimeError('EVALUATOR_DID_NOT_WRITE_REPORT')
            if result.get('decision') != 'EXPLORATORY_ONLY_NO_PROMOTION' or result.get('no_orders') is not True:
                raise ValueError('UNTRUSTED_FORWARD_RESULT')
            if any(not v.get('ledger_balanced') for v in result['variants']):raise ValueError('UNBALANCED_LEDGER')
            if result['future_first_ms']!=times[0] or result['future_last_ms']!=times[FIRST_WINDOW-1]:
                raise ValueError('EVALUATION_WINDOW_CHANGED')
            artifacts = {str(p.relative_to(root)).replace('\\','/'): _sha(p) for p in snapshot_paths}
            artifacts['forward_v28.json'] = _sha(result_path)
            receipt = {'version':'CQWE_V30_FROZEN_RESEARCH_RECEIPT','research_only':True,'no_orders':True,
                       'auto_promotion':False,'checkpoint_tip_sha256':checkpoint['tip_sha256'],
                       'snapshot_start_ms':times[0],'snapshot_end_ms':times[FIRST_WINDOW-1],
                       'bars_per_symbol':FIRST_WINDOW,'artifact_sha256':artifacts}
            receipt['receipt_sha256']=_digest(receipt)
            _atomic(root/'receipt_v30.json',receipt)
            return {'status':'FORWARD_VERIFIED','bars':FIRST_WINDOW,'receipt_sha256':receipt['receipt_sha256'],'research_only':True}
        except Exception:
            # fail-closed: preserve partial evidence for forensic analysis
            raise
    finally:
        lock.rmdir()

def main():
    p=argparse.ArgumentParser(description='CQWE V30 hourly read-only collection + one frozen research experiment')
    p.add_argument('--store',default='reports/v21_evidence')
    p.add_argument('--output-dir',default='data/future')
    p.add_argument('--registry',default='reports/v27_mutation_registry.json')
    p.add_argument('--evidence-dir',default='reports/v30_forward_first240')
    a=p.parse_args()
    result=run_cycle(a.store,a.output_dir,a.registry,a.evidence_dir)
    print('CQWE_V30_CYCLE_PASS '+json.dumps(result,ensure_ascii=False,sort_keys=True))
    print('READ ONLY | ONE FROZEN STUDY | NO ORDERS | NO AUTO PROMOTION | NO REAL PROFIT CLAIM')
if __name__=='__main__':main()
