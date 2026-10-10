"""Actual isolated CLI smoke plus TEST gradient/assignment/fault validation."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rehab_ml.common import ROOT, file_hash, paths, read_json, write_json


def main():
    root = paths()['run']/('pose-masked-audit-'+uuid4().hex[:8])
    root.mkdir()
    # This helper generates only labelled TEST fixtures, not human supervision.
    sys.path.insert(0, str(ROOT/'tests/rehab_backend'))
    from test_pose_masked_loss import fixture
    source, reference = fixture(root)
    unauthorized = copy.deepcopy(reference)
    unauthorized['permissions']['training'] = False
    rejected = Path(write_json(root/'not-authorized.json', unauthorized))
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
        PYTHONPATH=os.pathsep.join((str(ROOT/'tests/rehab_backend'), str(ROOT/'rehab_codex_single_camera_v2_1'), str(ROOT))))
    temporary = root/'process-temp'
    temporary.mkdir()
    environment.update(TEMP=str(temporary), TMP=str(temporary))
    steps = [('unit', ['-m', 'unittest', '-v', 'test_pose_masked_loss'], 0),
        ('native_smoke', ['tools/rehab_ml/cli.py', 'smoke-pose-masked', '--reference', str(source),
                         '--output-dir', str(root/'native-smoke')], 0),
        ('reject_without_training_permission', ['tools/rehab_ml/cli.py', 'smoke-pose-masked', '--reference',
                         str(rejected), '--output-dir', str(root/'must-not-exist')], 1)]
    summary = dict(run_id=root.name, evidence_scope='synthetic_engineering_loss_not_human_finetuning', commands=[],
        human_training_performed=False, fine_tuning_qualified=False, product_enabled=False, clinical_accuracy=None)
    summary['implementation_sha256'] = {p: file_hash(ROOT/p) for p in (
        'tools/rehab_ml/pose_masked_loss.py', 'tools/rehab_ml/pose_masked_smoke.py',
        'tools/rehab_ml/verify_pose_masked_loss.py', 'tools/rehab_ml/cli.py', 'tests/rehab_backend/test_pose_masked_loss.py')}
    try:
        for name, arguments, expected in steps:
            started = time.perf_counter()
            process = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments], cwd=ROOT, env=environment,
                                     capture_output=True, text=True, encoding='utf-8', timeout=140)
            log = root/(name+'.txt')
            log.write_text(process.stdout+process.stderr, encoding='utf-8')
            summary['commands'].append(dict(name=name, arguments=arguments, exit_code=process.returncode,
                expected_exit_code=expected, passed=process.returncode == expected, elapsed_s=time.perf_counter()-started,
                log=str(log), log_sha256=file_hash(log), tail=(process.stdout+process.stderr)[-700:]))
            if process.returncode != expected:
                raise RuntimeError('pose_masked_loss_step_failed:'+name)
        native = read_json(root/'native-smoke/result.json')
        if (native['human_training_performed'] is not False or native['engineering_optimizer_steps'] != 1
                or native['gradient_audit']['unknown_joint_gradient_max'] != 0.
                or native['reload_prediction_max_abs_difference'] > 1e-6 or (root/'must-not-exist').exists()):
            raise RuntimeError('pose_masked_native_audit_assertion_failed')
        summary['native_result'] = native
        summary['artifact_sha256'] = {p: file_hash(root/p) for p in (
            'reference.json', 'native-smoke/result.json', 'native-smoke/provenance.json',
            'native-smoke/child.log', 'native-smoke/TEST-engineering-checkpoint.pt')}
        summary['passed'] = True
    except Exception as error:
        summary.update(passed=False, failure_type=type(error).__name__, failure=str(error))
    write_json(root/'verification.json', summary)
    report = write_json(ROOT/'reports/rehab_backend/pose_masked_loss_verification.json', summary)
    print(json.dumps(dict(path=report, run_id=root.name, passed=summary['passed'], human_training_performed=False,
                         clinical_accuracy=None), ensure_ascii=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
