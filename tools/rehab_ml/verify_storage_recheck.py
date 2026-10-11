"""Recheck storage-blocked TEST workflows on a real, explicitly spacious volume.

No disk-usage mocks, threshold edits, data relocation or user-file cleanup. The
failed whole regression is retained; this subset is not a replacement full run.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import file_hash, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--failed-summary', type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    failed = args.failed_summary.resolve()
    if (root.exists() or root == Path(root.anchor) or len(root.parts) < 3
            or root.is_relative_to(ROOT) or not failed.is_relative_to(ROOT/'.runtime/rehab_ml/run')):
        raise ValueError('Explicit new external TEST output and owned failed evidence required')
    parent = root.parent
    while not parent.exists():
        parent = parent.parent
    available = shutil.disk_usage(parent).free
    if available < 1_073_741_824:
        raise ValueError('Real scratch volume requires at least 1 GiB free')
    previous = read_json(failed)
    if previous.get('passed') is not False:
        raise ValueError('Explicit failed regression expected; do not replace passing evidence')
    for row in previous['commands']:
        if file_hash(row['log']) != row['log_sha256']:
            raise ValueError('Original failure log changed')
    root.mkdir(parents=True, exist_ok=False)
    for name in ('run', 'model', 'temp'):
        (root/name).mkdir()
    environment = dict(os.environ, REHAB_RUN_ROOT=str(root/'run'), REHAB_MODEL_ROOT=str(root/'model'),
        TEMP=str(root/'temp'), TMP=str(root/'temp'), PYTHONDONTWRITEBYTECODE='1',
        PYTHONPATH=str(ROOT/'rehab_codex_single_camera_v2_1')+os.pathsep+str(ROOT))
    summary = dict(scope='storage_blocked_TEST_subset_on_different_actual_volume',
        whole_regression_passed=False, source_failed_summary=str(failed),
        source_failed_summary_sha256=file_hash(failed), scratch_root=str(root),
        actual_free_bytes_before=available, disk_usage_mocked=False, storage_threshold_changed=False,
        raw_data_relocated=False, user_files_removed=False, product_environment=sys.executable,
        product_enabled=False, clinical_accuracy=None, commands=[])
    cases = [
        ('pose_training', ['-m', 'unittest', 'discover', '-s', 'tests/rehab_backend',
                           '-p', 'test_pose_training.py', '-v']),
        ('legacy_mobile', ['-m', 'pytest', 'mobile_rehab/tests/test_mobile.py', '-q',
                           '-p', 'no:cacheprovider', '--basetemp', str(root/'pytest-temporary')]),
        ('scope', ['tools/rehab_ml/cli.py', 'verify-scope', '--baseline',
                   'reports/rehab_backend/protected_files.json']),
    ]
    for name, arguments in cases:
        log = root/(name+'.txt')
        started = time.perf_counter()
        with log.open('x', encoding='utf-8') as stream:
            try:
                result = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments], cwd=ROOT,
                    env=environment, stdout=stream, stderr=subprocess.STDOUT, timeout=150)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = None
        summary['commands'].append(dict(name=name, arguments=arguments, exit_code=code,
            elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log),
            tail=log.read_text(encoding='utf-8')[-350:]))
        write_json(root/'summary.json', summary)
    summary['passed'] = all(row['exit_code'] == 0 for row in summary['commands'])
    summary['actual_free_bytes_after'] = shutil.disk_usage(root).free
    summary['original_failure_evidence_unchanged'] = file_hash(failed) == summary['source_failed_summary_sha256']
    write_json(root/'summary.json', summary)
    summary.update(artifact=str(root/'summary.json'), summary_sha256=file_hash(root/'summary.json'))
    write_json(ROOT/'reports/rehab_backend/storage_recheck_verification.json', summary)
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    return 0 if summary['passed'] and summary['original_failure_evidence_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
