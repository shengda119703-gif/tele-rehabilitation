"""Original YOLO deterministic CPU resume audit; engineering fixtures only."""
from __future__ import annotations

import argparse
import json
import copy
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.rehab_ml.common import ROOT, canonical_hash, file_hash, paths, read_json, write_json


def boundary_child(request):
    """Controlled TEST cancellation after an actual validated native boundary.

    No optimizer, data, inference or selection replacement. This is not an
    externally timed crash; its injection point is intentionally repeatable.
    """
    from tools.rehab_ml import pose_resume
    from tools.rehab_ml.pose_training import run_child, request_cancel, record_child_failure
    actual = pose_resume.save_boundary
    def save_then_request_cancel(output, *args, **kwargs):
        result = actual(output, *args, **kwargs)
        request_cancel(output)
        return result
    pose_resume.save_boundary = save_then_request_cancel
    try:
        run_child(request)
    except Exception as error:
        record_child_failure(request, error)
        raise


def tensor_state(path):
    import torch
    from tools.rehab_ml.pose_masked_smoke import _tensor_digest
    value = torch.load(path, map_location='cpu', weights_only=True)
    tensors = [(f'{key}.{name}', tensor) for key, state in sorted(value['optimizer_state']['state'].items())
               for name, tensor in sorted(state.items())]
    return dict(model=_tensor_digest(value['state_dict'].items()), optimizer=_tensor_digest(tensors),
                groups=canonical_hash(value['optimizer_state']['param_groups']))


def state_difference(first, second):
    """Diagnostic only. Does not relax the bitwise verification gate."""
    import torch
    left = torch.load(first, map_location='cpu', weights_only=True)
    right = torch.load(second, map_location='cpu', weights_only=True)
    model = [(name, (tensor.double()-right['state_dict'][name].double()).abs().max().item())
             for name, tensor in left['state_dict'].items() if not torch.equal(tensor, right['state_dict'][name])]
    optimizer = [(str(key), name, (tensor.double()-right['optimizer_state']['state'][key][name].double()).abs().max().item())
                 for key, values in left['optimizer_state']['state'].items() for name, tensor in values.items()
                 if not torch.equal(tensor, right['optimizer_state']['state'][key][name])]
    return dict(model_changed_tensors=len(model), model_max_abs=max((row[1] for row in model), default=0.),
                optimizer_changed_tensors=len(optimizer), optimizer_max_abs=max((row[2] for row in optimizer), default=0.),
                diagnostic_not_acceptance_tolerance=True)


def crash_child(request):
    """TEST actual exit after native step two, before its validation/commit.

    The actual explicit CPU AdamW step runs first. The previous full epoch boundary is
    left intact; no failure/status cleanup runs. This is not a random-timed
    operating-system fault, nor a native deadlock simulation.
    """
    import torch
    from tools.rehab_ml.pose_cpu_gradients import CPUAdamW
    from tools.rehab_ml.pose_training import run_child, configuration, qualified_reference
    config = configuration(read_json(request)['config'])[1]
    reference = qualified_reference(config)[1]
    steps_per_epoch = math.ceil(sum(row['split'] == 'train' for row in reference['samples'])/config['batch_size'])
    actual = CPUAdamW.step
    steps = 0
    def step_then_exit(optimizer, *args, **kwargs):
        nonlocal steps
        result = actual(optimizer, *args, **kwargs)
        steps += 1
        if steps == steps_per_epoch+1:
            os._exit(27)
        return result
    CPUAdamW.step = step_then_exit
    run_child(request)
    raise RuntimeError('TEST_crash_injection_not_reached')


def crash_driver(config):
    """Actual production parent owns, waits and records the TEST crash child."""
    from unittest.mock import patch
    from tools.rehab_ml.pose_training import configuration, train_pose
    _, resolved, _ = configuration(config)
    if resolved['mode'] != 'engineering_test':
        raise ValueError('TEST_crash_driver_forbids_human_training')
    actual = subprocess.Popen
    def launch(arguments, **kwargs):
        # Mutate the passed list so the parent's receipt reports the actual
        # arguments. This test-only launch injection is not a public config.
        arguments[4] = str(Path(__file__).resolve())
        arguments[5] = '--crash-child'
        return actual(arguments, **kwargs)
    with patch('tools.rehab_ml.pose_training.subprocess.Popen', side_effect=launch):
        try:
            train_pose(config)
        except RuntimeError as error:
            if str(error) != 'offline_pose_training_failed_no_success_claim':
                raise
        else:
            raise RuntimeError('TEST_crash_parent_wrongly_returned_success')
    source = Path(resolved['output_dir'])
    receipt = read_json(source/'provenance.json')
    if receipt['exit_code'] != 27 or receipt['owned_exit_confirmed'] is not True:
        raise RuntimeError('TEST_crash_parent_exit_not_confirmed')
    print(json.dumps(dict(source=str(source), actual_owned_exit_code=27, owned_exit_confirmed=True)))


def main(*, multibatch=False):
    root = paths()['run']/('pose-resume-audit-'+uuid4().hex[:8])
    root.mkdir()
    sys.path.insert(0, str(ROOT/'tests/rehab_backend'))
    from test_pose_masked_loss import fixture
    from test_pose_training import test_config
    from tools.rehab_ml.pose_training import VERSION
    from tools.rehab_ml.pose_resume import IMPLEMENTATIONS
    from tools.rehab_ml.resource_gate import heavy_compute
    reference, reference_value = fixture(root)
    if multibatch:
        from PIL import Image, ImageDraw
        template = reference_value['samples'][0]
        for index in range(1, 5):
            picture = Image.new('RGB', (96, 64), (80+index*15, 110+index*10, 160+index*7))
            ImageDraw.Draw(picture).rectangle((index*5, 8, 70, 45), fill=(170, 120+index, 90))
            path = root/f'TEST-train-{index}.png'
            picture.save(path)
            reference_value['samples'].append(dict(copy.deepcopy(template), sample_id=f'TEST-train-{index}',
                recording_id=f'TEST-recording-train-{index}', image_ref=path.name, image_sha256=file_hash(path)))
        reference_value['dataset_id'] = 'TEST-resume-multibatch'
        write_json(reference, reference_value)
    config_path, config = test_config(root, reference)
    config.update(max_epochs=3, patience=3, output_dir=str(root/'uninterrupted'))
    if multibatch:
        config.update(threads=4, image_size=160)
    steps_per_epoch = math.ceil(sum(row['split'] == 'train' for row in reference_value['samples'])/config['batch_size'])
    write_json(config_path, config)
    source = root/'cancelled-source'
    source.mkdir()
    source_config = dict(config, output_dir=str(source))
    source_config_path = write_json(root/'source-config.json', source_config)
    write_json(source/'resolved-config.json', source_config)
    source_request = write_json(source/'request.json', dict(version=VERSION, config=source_config_path,
        config_sha256=file_hash(source_config_path), reference_sha256=file_hash(reference), output_dir=str(source),
        resolved_config_sha256=file_hash(source/'resolved-config.json')))
    for name in ('process-temp', 'ultralytics-config'):
        (source/name).mkdir()
    resume_config = write_json(root/'resume-config.json', dict(config, output_dir=str(root/'resumed')))
    rejected_config = write_json(root/'reject-config.json', dict(config, output_dir=str(root/'must-not-exist')))
    crashed = root/'crashed-source'
    crash_config = write_json(root/'crash-config.json', dict(config, output_dir=str(crashed)))
    crash_resume_config = write_json(root/'crash-resume-config.json', dict(config, output_dir=str(root/'crash-resumed')))
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
        TEMP=str(source/'process-temp'), TMP=str(source/'process-temp'),
        YOLO_CONFIG_DIR=str(source/'ultralytics-config'), YOLO_OFFLINE='true', YOLO_AUTOINSTALL='false',
        CUBLAS_WORKSPACE_CONFIG=':4096:8',
        PYTHONPATH=os.pathsep.join((str(ROOT/'tests/rehab_backend'), str(ROOT/'rehab_codex_single_camera_v2_1'), str(ROOT))))
    summary = dict(run_id=root.name, scope='synthetic_native_epoch_resume_not_human_accuracy', commands=[],
        audit_case='multibatch_cpu4_160_batch2_train5' if multibatch else 'singlebatch_cpu2_128_batch2_train1',
        human_training_performed=False, clinical_accuracy=None, product_enabled=False,
        implementation_sha256={name: file_hash(ROOT/name) for name in (*IMPLEMENTATIONS,
            'tools/rehab_ml/cli.py', 'tests/rehab_backend/test_pose_resume.py',
            'tests/rehab_backend/test_pose_cpu_gradients.py', 'tools/rehab_ml/verify_pose_resume.py')})

    def command(name, arguments, expected=0):
        started = time.perf_counter()
        completed = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments], cwd=ROOT, env=environment,
            capture_output=True, text=True, encoding='utf-8', timeout=145.)
        log = root/(name+'.txt')
        log.write_text(completed.stdout+completed.stderr, encoding='utf-8')
        summary['commands'].append(dict(name=name, arguments=arguments, exit_code=completed.returncode,
            expected_exit_code=expected, elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log),
            tail=(completed.stdout+completed.stderr)[-1200:]))
        if completed.returncode != expected:
            raise RuntimeError('pose_resume_command_failed:'+name)

    try:
        with heavy_compute():
            pass  # Never close a user's formal session or unrelated task.
        command('unit', ['-m', 'unittest', 'test_pose_resume', 'test_pose_training', 'test_pose_cpu_gradients', '-v'])
        command('uninterrupted', ['tools/rehab_ml/cli.py', 'train-pose', '--config', str(config_path)])
        command('native_boundary_cancel', ['tools/rehab_ml/verify_pose_resume.py', '--boundary-child', source_request], 1)
        source_hashes = {str(path.relative_to(source)): file_hash(path) for path in source.rglob('*') if path.is_file()}
        manifest = read_json(source/'resume-manifest.json')
        if (manifest['epoch'] != 1 or manifest['optimizer_steps'] != steps_per_epoch
                or read_json(source/'failure.json')['status'] != 'cancelled' or (source/'test-started.json').exists()):
            raise RuntimeError('actual_native_cancel_did_not_leave_pretest_epoch_one_boundary')
        command('resume', ['tools/rehab_ml/cli.py', 'train-pose', '--config', resume_config, '--resume-run', str(source)])
        uninterrupted, resumed = read_json(root/'uninterrupted/result.json'), read_json(root/'resumed/result.json')
        with heavy_compute():
            full_state, resumed_state = tensor_state(root/'uninterrupted/last.pt'), tensor_state(root/'resumed/last.pt')
        full_order = [json.loads(line) for line in (root/'uninterrupted/train-order.jsonl').read_text(encoding='utf-8').splitlines()]
        resumed_order = [json.loads(line) for line in (root/'resumed/train-order.jsonl').read_text(encoding='utf-8').splitlines()]
        if (resumed['resumed_from_epoch'] != 1 or resumed['current_attempt_optimizer_steps'] != 2*steps_per_epoch
                or resumed['optimizer_steps'] != 3*steps_per_epoch or resumed['epochs_completed'] != 3
                or resumed['best_epoch'] != uninterrupted['best_epoch'] or resumed['human_training_performed']
                or resumed['test_used_for_selection'] or resumed['product_enabled']):
            raise RuntimeError('native_resume_epoch_step_selection_or_safety_contract_mismatch')
        after_hashes = {str(path.relative_to(source)): file_hash(path) for path in source.rglob('*') if path.is_file()}
        if source_hashes != after_hashes:
            raise RuntimeError('resume_changed_original_cancelled_run')
        command('reject_completed_test', ['tools/rehab_ml/cli.py', 'train-pose', '--config', rejected_config,
                                          '--resume-run', str(root/'uninterrupted')], 1)
        if (root/'must-not-exist').exists():
            raise RuntimeError('invalid_resume_created_output')
        summary.update(native=dict(source_manifest=manifest, source_file_count=len(source_hashes),
            source_files_unchanged=True, actual_cancelled_child_exit_code=1,
            cancellation='controlled_request_after_actual_epoch_validation_not_external_crash',
            model_and_optimizer_bitwise_equal=full_state == resumed_state, full_tensor_digests=full_state,
            resumed_tensor_digests=resumed_state,
            resumed_order_losses_gradients_equal=resumed_order == [row for row in full_order if row['epoch'] > 1],
            total_epochs=3, total_optimizer_steps=3*steps_per_epoch, current_attempt_steps=2*steps_per_epoch,
            steps_per_epoch=steps_per_epoch, best_epoch=resumed['best_epoch'],
            baseline_validation_inherited=resumed['baseline_validation_inherited'],
            training_numerical_environment=resumed['training_numerical_environment'],
            candidate_test_summary=resumed['candidate_test_summary']))
        with heavy_compute():
            summary['native']['state_difference'] = state_difference(root/'uninterrupted/last.pt', root/'resumed/last.pt')
        command('native_mid_epoch_crash', ['tools/rehab_ml/verify_pose_resume.py', '--crash-driver', crash_config])
        crash_manifest = read_json(crashed/'resume-manifest.json')
        crash_status = read_json(crashed/'status.json')
        crash_receipt = read_json(crashed/'provenance.json')
        if (crash_manifest['epoch'] != 1 or crash_manifest['optimizer_steps'] != steps_per_epoch
                or crash_status['phase'] != 'training' or crash_status['epoch'] != 2
                or crash_receipt['exit_code'] != 27 or crash_receipt['owned_exit_confirmed'] is not True
                or (crashed/'failure.json').exists() or (crashed/'test-started.json').exists()):
            raise RuntimeError('native_crash_did_not_leave_exact_pretest_previous_boundary')
        crash_before = {str(path.relative_to(crashed)): file_hash(path) for path in crashed.rglob('*') if path.is_file()}
        command('resume_after_native_crash', ['tools/rehab_ml/cli.py', 'train-pose', '--config', crash_resume_config,
                                              '--resume-run', str(crashed)])
        crash_result = read_json(root/'crash-resumed/result.json')
        if (crash_result['resumed_from_epoch'] != 1 or crash_result['current_attempt_optimizer_steps'] != 2*steps_per_epoch
                or crash_result['optimizer_steps'] != 3*steps_per_epoch or crash_result['epochs_completed'] != 3
                or crash_result['resume_source']['terminal_receipt_sha256'] != file_hash(crashed/'provenance.json')
                or crash_result['test_used_for_selection'] or crash_result['product_enabled']
                or crash_result['human_training_performed']):
            raise RuntimeError('native_crash_resume_contract_mismatch')
        if crash_before != {str(path.relative_to(crashed)): file_hash(path) for path in crashed.rglob('*') if path.is_file()}:
            raise RuntimeError('native_crash_source_changed_by_resume')
        with heavy_compute():
            crash_state = tensor_state(root/'crash-resumed/last.pt')
            crash_difference = state_difference(root/'uninterrupted/last.pt', root/'crash-resumed/last.pt')
        crash_order = [json.loads(line) for line in (root/'crash-resumed/train-order.jsonl').read_text(encoding='utf-8').splitlines()]
        summary['native_crash'] = dict(actual_owned_exit_code=27, owned_exit_confirmed=True,
            injection='after_actual_first_AdamW_step_of_epoch_two_before_commit',
            actual_step_before_exit=steps_per_epoch+1, source_manifest=crash_manifest,
            source_status=crash_status, terminal_receipt_sha256=file_hash(crashed/'provenance.json'),
            previous_boundary_resumed=True, source_files_unchanged=True, total_epochs=3,
            total_optimizer_steps=3*steps_per_epoch, current_attempt_steps=2*steps_per_epoch, tensor_digests=crash_state,
            state_difference=crash_difference, model_and_optimizer_bitwise_equal=full_state == crash_state,
            resumed_order_losses_gradients_equal=crash_order == [row for row in full_order if row['epoch'] > 1])
        weights = ROOT/'rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt'
        from tools.rehab_ml.pose_masked_smoke import BASE_SHA256
        if file_hash(weights) != BASE_SHA256:
            raise RuntimeError('original_weight_changed')
        summary['original_weight_sha256'] = file_hash(weights)
        if (full_state != resumed_state or full_state != crash_state
                or resumed_order != [row for row in full_order if row['epoch'] > 1]
                or crash_order != [row for row in full_order if row['epoch'] > 1]):
            raise RuntimeError('native_resume_not_equal_to_uninterrupted_optimizer_and_order')
        summary['passed'] = True
    except Exception as error:
        summary.update(passed=False, failure_type=type(error).__name__, failure=str(error))
    write_json(root/'verification.json', summary)
    filename = 'pose_resume_verification_multibatch.json' if multibatch else 'pose_resume_verification.json'
    output = write_json(ROOT/'reports/rehab_backend'/filename, summary)
    print(json.dumps(dict(path=output, run_id=root.name, passed=summary['passed'], failure=summary.get('failure')), ensure_ascii=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--boundary-child', type=Path)
    parser.add_argument('--crash-child', type=Path)
    parser.add_argument('--crash-driver', type=Path)
    parser.add_argument('--multibatch', action='store_true', help='TEST five-image, three-batch, four-thread native case')
    arguments = parser.parse_args()
    if arguments.boundary_child is not None:
        boundary_child(arguments.boundary_child)
    elif arguments.crash_child is not None:
        crash_child(arguments.crash_child)
    elif arguments.crash_driver is not None:
        crash_driver(arguments.crash_driver)
    else:
        raise SystemExit(main(multibatch=arguments.multibatch))
