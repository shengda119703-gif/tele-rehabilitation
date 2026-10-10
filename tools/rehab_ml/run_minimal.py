"""Run the complete real IRDS minimal experiment and invariant verification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import file_hash, paths, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=20261011)
    args = parser.parse_args()
    if args.seed != 20261011:
        parser.error('This fixed comparison uses seed 20261011; use separate explicit configs for other seeds')
    summary = dict(kind='real_licensed_grouped_IRDS_pipeline', seed=args.seed, stages=[], experiments=[],
                   product_enabled=False, clinical_accuracy=None)
    destination = ROOT / 'reports/rehab_backend/experiment_summary.json'
    def step(name, fn):
        started = time.perf_counter()
        value = fn()
        summary['stages'].append(dict(name=name, elapsed_s=time.perf_counter()-started, result=value))
        write_json(destination, summary)
        return value
    from tools.rehab_ml.download import resolve, fetch, verify
    from tools.rehab_ml.data import prepare, split
    from tools.rehab_ml.features import build_features
    from tools.rehab_ml.training import train, evaluate
    try:
        from tools.rehab_ml.inventory import doctor
        step('doctor', doctor)
        step('resolve_official_metadata', resolve)
        step('fetch_pinned_skeleton_only', lambda: fetch('intellirehabds'))
        step('verify_download', lambda: verify('intellirehabds'))
        adapted = step('prepare_named_joints_and_labels', lambda: prepare([4, 5]))
        step('split_people_before_features', lambda: split(args.seed))
        step('build_causal_kinect_features', lambda: build_features('kinect_3d'))
        summary['dataset_counts'] = adapted['counts']
        for name in ('baseline', 'tcn'):
            trained = step('train_'+name, lambda: train(ROOT / ('configs/rehab_ml/'+name+'.yaml')))
            # Always explicit run IDs; earlier experiments/test observations are not selection inputs.
            validation = step('evaluate_'+name+'_val', lambda: evaluate(trained['run_id'], 'val'))
            test = step('evaluate_'+name+'_test', lambda: evaluate(trained['run_id'], 'test'))
            run = Path(trained['path'])
            summary['experiments'].append(dict(train=trained, val=validation, test=test,
                provenance=read_json(run / 'provenance.json'), model_card=read_json(run / 'model-card.json'),
                artifact_hashes={p.name: file_hash(p) for p in run.iterdir() if p.is_file()}))
            write_json(destination, summary)
        for command in (['replay', '--suite', 'rehab_core'], ['verify-sessions', '--database-mode', 'isolated']):
            def run_check(command=command):
                result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'tools/rehab_ml/cli.py'), *command],
                                         cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=90)
                if result.returncode:
                    raise RuntimeError(result.stderr)
                return json.loads(result.stdout)
            step('check_'+command[0], run_check)
        summary['status'] = 'minimal_pipeline_passed_not_whole_task_complete'
        write_json(destination, summary)
        print(json.dumps(dict(ok=True, summary=str(destination),
                              run_ids=[e['train']['run_id'] for e in summary['experiments']]), ensure_ascii=False))
        return 0
    except Exception as exc:
        summary.update(status='failed', error_type=type(exc).__name__, error=str(exc))
        write_json(destination, summary)
        print(json.dumps(dict(ok=False, summary=str(destination), error=str(exc)), ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
