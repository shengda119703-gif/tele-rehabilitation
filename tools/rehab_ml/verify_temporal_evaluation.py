"""TEST metrics and real pending-reference refusal; never fabricated accuracy."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import file_hash, paths, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pending-bundle', type=Path, required=True)
    args = parser.parse_args()
    bundle = args.pending_bundle.resolve()
    if bundle.name != 'bundle.json' or not bundle.parent.is_relative_to(paths()['run']):
        raise ValueError('Explicit owned original annotation bundle required')
    frozen = {str(path): file_hash(path) for path in bundle.parent.iterdir() if path.is_file()}
    implementation = {str(path.relative_to(ROOT)): file_hash(path) for path in
        (Path(__file__), ROOT/'tools/rehab_ml/temporal_evaluation.py', ROOT/'tools/rehab_ml/cli.py',
         ROOT/'tests/rehab_backend/test_temporal_evaluation.py', ROOT/'tools/rehab_ml/verify_all.py',
         ROOT/'tools/rehab_ml/verify_storage_recheck.py')}
    root = paths()['run']/('temporal-evaluation-audit-'+uuid4().hex[:8])
    root.mkdir()
    summary = dict(scope='TEST_metric_contract_and_real_pending_reference_gate',
        bundle_sha256=file_hash(bundle), product_environment=sys.executable,
        implementation_sha256=implementation, commands=[], product_enabled=False,
        actual_professional_labels=0, actual_accuracy_evaluation_performed=False)
    cases = [
        ('help', ['tools/rehab_ml/cli.py', 'evaluate-annotations', '--help'], 0),
        ('storage-full-help', ['tools/rehab_ml/verify_storage_recheck.py', '--help'], 0),
        ('unit', ['-m', 'unittest', 'discover', '-s', 'tests/rehab_backend',
                  '-p', 'test_temporal_evaluation.py', '-v'], 0),
        ('pending-real-reference-refused', ['tools/rehab_ml/cli.py', 'evaluate-annotations',
            '--reference', str(bundle), '--predictions', str(root/'no-invented-predictions.json'),
            '--split', 'test', '--output-dir', str(root/'must-not-evaluate')], 1),
        ('scope', ['tools/rehab_ml/cli.py', 'verify-scope', '--baseline',
                   'reports/rehab_backend/protected_files.json'], 0),
    ]
    for name, arguments, expected in cases:
        log = root/(name+'.txt')
        started = perf_counter()
        with log.open('x', encoding='utf-8') as stream:
            result = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments], cwd=ROOT,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT)),
                stdout=stream, stderr=subprocess.STDOUT, timeout=60)
        summary['commands'].append(dict(name=name, arguments=arguments, exit_code=result.returncode,
            expected_exit=expected, elapsed_s=perf_counter()-started, log=str(log), log_sha256=file_hash(log)))
        write_json(root/'summary.json', summary)
    summary['passed'] = all(row['exit_code'] == row['expected_exit'] for row in summary['commands'])
    refusal = (root/'pending-real-reference-refused.txt').read_text(encoding='utf-8')
    summary['independent_reference_refusal_confirmed'] = 'blocked_missing_independent_professional_supervision' in refusal
    summary['evaluation_output_not_created'] = not (root/'must-not-evaluate').exists()
    summary['original_annotation_bundle_unchanged'] = all(file_hash(path) == expected for path, expected in frozen.items())
    summary['implementation_unchanged'] = all(file_hash(ROOT/path) == expected for path, expected in implementation.items())
    summary['passed'] = summary['passed'] and all(summary[key] for key in
        ('independent_reference_refusal_confirmed', 'evaluation_output_not_created',
         'original_annotation_bundle_unchanged', 'implementation_unchanged'))
    write_json(root/'summary.json', summary)
    summary.update(artifact=str(root/'summary.json'), summary_sha256=file_hash(root/'summary.json'))
    write_json(ROOT/'reports/rehab_backend/temporal_evaluation_verification.json', summary)
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
