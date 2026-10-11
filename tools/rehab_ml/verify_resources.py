"""Owned-process compute admission audit; TEST inputs, no user services."""
from __future__ import annotations

from io import BytesIO
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.rehab_ml.common import ROOT, file_hash, paths, read_json, write_json
from tools.rehab_ml.resource_gate import heavy_compute


def prepare_child(root, reference, name, *, epochs=50):
    from tools.rehab_ml.pose_training import VERSION
    from test_pose_training import test_config
    output = root/name
    output.mkdir()
    config_path, config = test_config(output, reference)
    config.update(output_dir=str(output), max_epochs=epochs, patience=epochs)
    write_json(config_path, config)
    write_json(output/'resolved-config.json', config)
    request = write_json(output/'request.json', dict(version=VERSION, config=str(config_path),
        config_sha256=file_hash(config_path), reference_sha256=file_hash(reference), output_dir=str(output),
        resolved_config_sha256=file_hash(output/'resolved-config.json')))
    for name in ('ultralytics-config', 'process-temp'):
        (output/name).mkdir()
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', YOLO_AUTOINSTALL='false', YOLO_OFFLINE='true',
        TEMP=str(output/'process-temp'), TMP=str(output/'process-temp'), YOLO_CONFIG_DIR=str(output/'ultralytics-config'))
    arguments = [sys.executable, '-X', 'utf8', '-B', 'tools/rehab_ml/pose_training.py', '--child-request', request]
    return output, environment, arguments


def control_probe(service, owner, sid, count=40):
    values = []
    for index in range(count):
        operation = 'pause' if index % 2 == 0 else 'resume'
        revision = service.get(owner, sid)['revision']
        started = time.perf_counter()
        service.control(owner, sid, operation,
                        dict(idempotency_key='TEST-control-'+str(index), expected_revision=revision))
        values.append(1000*(time.perf_counter()-started))
    values.sort()
    return dict(requests=count, p50_ms=values[math.ceil(.5*count)-1],
                p95_ms=values[math.ceil(.95*count)-1], maximum_ms=values[-1],
                scope='internal_TEST_control_not_camera_or_multi_user_pressure')


def wait_heavy_admission(timeout_s=20.):
    """Prove both OS handles are available, allowing independent reports to end."""
    from app.rehab_v2.resources import ResourceBusy
    started = time.perf_counter()
    while True:
        try:
            with heavy_compute():
                return time.perf_counter()-started
        except ResourceBusy:
            if time.perf_counter()-started >= timeout_s:
                raise RuntimeError('actual_heavy_admission_still_busy_after_finalization') from None
            time.sleep(.02)


def native_audit(root):
    from PIL import Image
    from app.domain import Context
    from app.rehab_v2.resources import ComputeLease, ResourceBusy
    from app.rehab_v2.sessions import SessionError
    from mobile_rehab.rehab_v2.service import SessionService
    from mobile_rehab.rehab_v2.pose_worker import IsolatedPoseWorker, offline_pose_process
    from tools.rehab_ml.pose_training import request_cancel
    from tools.rehab_ml.mediapipe_video import release_owned
    from test_pose_masked_loss import fixture
    from test_sessions import frozen_plan, request

    reference, _ = fixture(root)
    owner = 'TEST-coordination-owner'
    service = SessionService(root/'TEST-sessions.sqlite3', frozen_plan, internal_replay=True)
    pose_worker = IsolatedPoseWorker(target=offline_pose_process)
    child = None
    result = {}
    try:
        sid = service.create(owner, request())['session_id']
        output, environment, arguments = prepare_child(root, reference, 'blocked-by-formal')
        started = time.perf_counter()
        completed = subprocess.run(arguments, cwd=ROOT, env=environment, capture_output=True,
                                   text=True, encoding='utf-8', timeout=10.)
        log = root/'blocked-child.txt'
        log.write_text(completed.stdout+completed.stderr, encoding='utf-8')
        failure = read_json(output/'failure.json')
        if completed.returncode != 1 or failure['code'] != ResourceBusy.code or (output/'last.pt').exists():
            raise RuntimeError('actual_trainer_was_not_refused_before_optimization')
        result['formal_blocks_training'] = dict(exit_code=completed.returncode, failure=failure,
            elapsed_s=time.perf_counter()-started, checkpoint_absent=True,
            log_sha256=file_hash(log), request_sha256=file_hash(output/'request.json'))
        result['formal_controls'] = control_probe(service, owner, sid)
        receipt = service.finish(owner, sid, dict(idempotency_key='finish',
            expected_revision=service.get(owner, sid)['revision']))
        # Fact finalization releases formal capacity; a separately admitted
        # report may still be ending. Prove both real handles, not an ended label.
        result['heavy_admission_after_finalization_s'] = wait_heavy_admission()

        output, environment, arguments = prepare_child(root, reference, 'actual-trainer')
        log = root/'actual-trainer.txt'
        observed = None
        started = time.perf_counter()
        with log.open('wb') as stream:
            child = subprocess.Popen(arguments, cwd=ROOT, env=environment, stdout=stream, stderr=stream,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            while child.poll() is None and time.perf_counter()-started < 30.:
                if (output/'status.json').is_file():
                    state = read_json(output/'status.json')
                    if state['phase'] == 'validation' and state['optimizer_steps'] > 0:
                        observed = state
                        break
                time.sleep(.01)
            if observed is None or child.poll() is not None:
                raise RuntimeError('actual_live_native_optimizer_phase_not_observed')
            tick = time.perf_counter()
            try:
                service.create(owner, request('new-during-training'))
            except SessionError as error:
                if error.code != ResourceBusy.code or error.status != 503:
                    raise
            else:
                raise RuntimeError('formal_session_admitted_during_actual_native_training')
            denied_ms = 1000*(time.perf_counter()-tick)
            if service.create(owner, request())['session_id'] != sid:
                raise RuntimeError('historical_idempotent_read_lost_during_training')
            if service.commit(owner, sid)['receipt'] != receipt:
                raise RuntimeError('heavy_work_changed_committed_training_fact')
            cancel_receipt = request_cancel(output)
            exit_code = child.wait(timeout=15.)
        if exit_code != 1 or (output/'result.json').exists() or not (output/'last.pt').exists():
            raise RuntimeError('actual_cancel_exit_checkpoint_or_result_contract_failed')
        result['actual_training_blocks_formal'] = dict(observed_phase=observed,
            owned_pid=child.pid, owned_exit_confirmed=child.poll() is not None, exit_code=exit_code,
            formal_create_denied_ms=denied_ms, cancel_receipt=cancel_receipt,
            failure=read_json(output/'failure.json'), checkpoint_sha256=file_hash(output/'last.pt'),
            result_absent=True, elapsed_s=time.perf_counter()-started, log_sha256=file_hash(log))
        child = None  # Popen is already waited, no unrelated-process cleanup.
        after = service.create(owner, request('new-after-training'))['session_id']
        service.finish(owner, after, dict(idempotency_key='finish-after-training', expected_revision=0))
        result['formal_create_after_exit'] = True

        image = BytesIO()
        Image.new('RGB', (64, 64), 'white').save(image, format='JPEG')
        runtime = SimpleNamespace(context=Context(1, 'rehab', 'TEST-empty-image', 'REPLAY_FILE', 'TEST', 'TEST-research'),
                                  engine=SimpleNamespace(spec=dict(side='left')))
        pose, stages = pose_worker.infer(dict(sid='TEST-research', seq=0, source_time_s=0.,
                                            encoded=image.getvalue()), runtime)
        # Heavy lease must remain in this actual idle native child between
        # reference images. A parent-only preflight lock would not prove this.
        probe = ComputeLease('formal')
        try:
            try:
                probe.acquire()
            except ResourceBusy:
                pass
            else:
                raise RuntimeError('offline_native_child_did_not_keep_exclusive_lease')
        finally:
            probe.close()
        native_pid = pose_worker.process.pid
        if not pose_worker.process.is_alive():
            raise RuntimeError('offline_native_child_exit_not_expected_between_images')
        pose_worker.close()
        with ComputeLease('formal'):
            pass
        result['actual_offline_yolo'] = dict(pid=native_pid, predicted_people=len(pose.people),
            model_manifest_id=pose.model_manifest_id, stages_ms=stages,
            held_between_images=True, release=pose_worker.last_release,
            scope='empty_TEST_image_native_execution_not_human_accuracy')
        return result
    finally:
        if child is not None and not release_owned(child):
            raise RuntimeError('resource_audit_owned_child_release_unconfirmed')
        pose_worker.close()
        service.close(graceful=False)


def main():
    root = paths()['run']/('resource-audit-'+uuid4().hex[:8])
    root.mkdir()
    sys.path.insert(0, str(ROOT/'tests/rehab_backend'))
    summary = dict(run_id=root.name, clinical_accuracy=None, human_training_performed=False,
        product_enabled=False, scope='v2_formal_and_instrumented_offline_tasks_not_full_product_pressure',
        implementation_sha256={name: file_hash(ROOT/name) for name in (
            'rehab_codex_single_camera_v2_1/app/rehab_v2/resources.py',
            'mobile_rehab/rehab_v2/service.py', 'mobile_rehab/rehab_v2/pose_worker.py',
            'mobile_rehab/rehab_v2/owned_worker.py', 'tools/rehab_ml/resource_gate.py',
            'tools/rehab_ml/pose_training.py', 'tools/rehab_ml/training.py',
            'tools/rehab_ml/pose_masked_smoke.py', 'tools/rehab_ml/pose_inference.py',
            'tools/rehab_ml/mediapipe_video.py', 'tools/rehab_ml/target_domain.py',
            'tests/rehab_backend/test_resources.py',
            'tools/rehab_ml/verify_resources.py')})
    weights = ROOT/'rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt'
    before = file_hash(weights)
    try:
        # Refuse safely if an instrumented user's formal session is currently
        # active. This audit never closes somebody else's session or process.
        with heavy_compute():
            pass
        summary['native'] = native_audit(root)
        summary['original_weight_sha256'] = file_hash(weights)
        if summary['original_weight_sha256'] != before:
            raise RuntimeError('original_pose_weight_changed_during_resource_audit')
        summary['passed'] = True
    except Exception as error:
        summary.update(passed=False, failure_type=type(error).__name__, failure=str(error))
    write_json(root/'verification.json', summary)
    report = write_json(ROOT/'reports/rehab_backend/resource_verification.json', summary)
    print(json.dumps(dict(path=report, run_id=root.name, passed=summary['passed']), ensure_ascii=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
