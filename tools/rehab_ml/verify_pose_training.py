"""Real original YOLO multi-epoch engineering audit; no patient supervision."""
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


def actual_cancel(root, reference, environment):
    """Exact live child handle plus observed phase; no lock-file liveness claim."""
    from tools.rehab_ml.pose_training import VERSION, request_cancel
    from tools.rehab_ml.mediapipe_video import release_owned
    from test_pose_training import test_config
    output = root/'cancel-run'
    output.mkdir()
    config_path, config = test_config(output, reference)
    config.update(output_dir=str(output), max_epochs=50, patience=50)
    write_json(config_path, config)
    write_json(output/'resolved-config.json', config)
    request = write_json(output/'request.json', dict(version=VERSION, config=str(config_path),
        config_sha256=file_hash(config_path), reference_sha256=file_hash(reference), output_dir=str(output),
        resolved_config_sha256=file_hash(output/'resolved-config.json')))
    for name in ('ultralytics-config', 'process-temp'):
        (output/name).mkdir()
    env = dict(environment, YOLO_CONFIG_DIR=str(output/'ultralytics-config'), YOLO_AUTOINSTALL='false',
               YOLO_OFFLINE='true', TEMP=str(output/'process-temp'), TMP=str(output/'process-temp'))
    arguments = [str(sys.executable), '-X', 'utf8', '-B', 'tools/rehab_ml/pose_training.py', '--child-request', request]
    started, observed = time.perf_counter(), None
    log = root/'native_cancel.txt'
    with log.open('wb') as stream:
        child = subprocess.Popen(arguments, cwd=ROOT, env=env, stdout=stream, stderr=stream,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while child.poll() is None and time.perf_counter()-started < 30:
                status = output/'status.json'
                if status.is_file():
                    state = read_json(status)
                    if state['phase'] == 'validation' and state['optimizer_steps'] > 0:
                        observed = state
                        break
                time.sleep(.02)
            if observed is None or child.poll() is not None:
                raise RuntimeError('live_child_validation_phase_not_observed')
            response = request_cancel(output)
            code = child.wait(timeout=15)
        except BaseException:
            if not release_owned(child):
                raise RuntimeError('audit_owned_cancel_child_release_unconfirmed')
            raise
    failure = read_json(output/'failure.json')
    if (code == 0 or failure['status'] != 'cancelled' or (output/'result.json').exists()
            or not (output/'last.pt').is_file()):
        raise RuntimeError('real_cancel_must_preserve_checkpoint_and_have_no_success_result')
    return dict(name='native_cancel', arguments=arguments[1:], exit_code=code, expected_exit_code=1, passed=code == 1,
        elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log),
        live_handle_confirmed_before_request=True, observed_phase=observed, response=response,
        owned_exit_confirmed=child.poll() is not None, checkpoint_retained_sha256=file_hash(output/'last.pt'),
        result_absent=True, failure=failure)


def main():
    root = paths()['run']/('pose-training-audit-'+uuid4().hex[:8])
    root.mkdir()
    sys.path.insert(0, str(ROOT/'tests/rehab_backend'))
    from test_pose_masked_loss import fixture
    from test_pose_training import test_config
    reference, value = fixture(root)
    config, _ = test_config(root, reference)
    rejected = copy.deepcopy(value)
    rejected['permissions']['training'] = False
    rejected_ref = write_json(root/'not-authorized.json', rejected)
    rejected_config = dict(read_json(config), reference=rejected_ref, output_dir=str(root/'must-not-exist'))
    rejected_config_path = write_json(root/'not-authorized-config.json', rejected_config)
    early_config = dict(read_json(config), output_dir=str(root/'early-stop-run'), max_epochs=4, patience=1)
    early_config_path = write_json(root/'early-stop-config.json', early_config)
    (root/'process-temp').mkdir()
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TEMP=str(root/'process-temp'), TMP=str(root/'process-temp'),
        PYTHONPATH=os.pathsep.join((str(ROOT/'tests/rehab_backend'), str(ROOT/'rehab_codex_single_camera_v2_1'), str(ROOT))))
    commands = [('unit', ['-m', 'unittest', '-v', 'test_pose_training'], 0),
        ('native_multi_epoch', ['tools/rehab_ml/cli.py', 'train-pose', '--config', str(config)], 0),
        ('native_early_stopping', ['tools/rehab_ml/cli.py', 'train-pose', '--config', early_config_path], 0),
        ('reject_training_permission', ['tools/rehab_ml/cli.py', 'train-pose', '--config', rejected_config_path], 1)]
    summary = dict(run_id=root.name, evidence_scope='synthetic_multi_epoch_engineering_not_human_accuracy',
        commands=[], human_training_performed=False, product_enabled=False, clinical_accuracy=None,
        implementation_sha256={p: file_hash(ROOT/p) for p in ('tools/rehab_ml/pose_training.py',
            'tools/rehab_ml/pose_masked_loss.py', 'tools/rehab_ml/cli.py', 'tools/rehab_ml/verify_pose_training.py',
            'tests/rehab_backend/test_pose_training.py')})
    try:
        for name, arguments, expected in commands:
            started = time.perf_counter()
            process = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments], cwd=ROOT, env=environment,
                                     capture_output=True, text=True, encoding='utf-8', timeout=145)
            log = root/(name+'.txt')
            log.write_text(process.stdout+process.stderr, encoding='utf-8')
            summary['commands'].append(dict(name=name, arguments=arguments, exit_code=process.returncode,
                expected_exit_code=expected, passed=process.returncode == expected, elapsed_s=time.perf_counter()-started,
                log=str(log), log_sha256=file_hash(log), tail=(process.stdout+process.stderr)[-1000:]))
            if process.returncode != expected:
                raise RuntimeError('pose_training_verification_step_failed:'+name)
        result = read_json(root/'training/result.json')
        history = read_json(root/'training/history.json')
        if (result['epochs_completed'] != 2 or result['optimizer_steps'] != 2 or len(history) != 2
                or result['human_training_performed'] or result['product_enabled']
                or result['test_used_for_selection'] or result['validation_test_used_for_optimization']
                or not result['selected_checkpoint_strictly_reloaded'] or (root/'must-not-exist').exists()):
            raise RuntimeError('actual_multi_epoch_training_result_scope_or_count_mismatch')
        summary['native_result'] = result
        early = read_json(root/'early-stop-run/result.json')
        if early['stop_reason'] != 'validation_patience' or early['epochs_completed'] != 2 or early['best_epoch'] != 1:
            raise RuntimeError('actual_validation_early_stopping_not_proved')
        summary['native_early_stopping'] = dict(epochs_completed=early['epochs_completed'], best_epoch=early['best_epoch'],
            stop_reason=early['stop_reason'], optimizer_steps=early['optimizer_steps'],
            result_sha256=file_hash(root/'early-stop-run/result.json'))
        summary['commands'].append(actual_cancel(root, reference, environment))
        summary['training_history'] = history
        summary['artifact_sha256'] = {p: file_hash(root/p) for p in ('reference.json', 'config.json',
            'training/result.json', 'training/history.json', 'training/train-order.jsonl', 'training/model-card.json',
            'training/resource-budget.json', 'training/provenance.json', 'training/child.log', 'training/best.pt', 'training/last.pt',
            'early-stop-run/result.json', 'cancel-run/failure.json', 'cancel-run/status.json', 'cancel-run/last.pt')}
        summary['passed'] = True
    except Exception as error:
        summary.update(passed=False, failure_type=type(error).__name__, failure=str(error))
    write_json(root/'verification.json', summary)
    report = write_json(ROOT/'reports/rehab_backend/pose_training_verification.json', summary)
    print(json.dumps(dict(path=report, run_id=root.name, passed=summary['passed'], human_training_performed=False), ensure_ascii=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
