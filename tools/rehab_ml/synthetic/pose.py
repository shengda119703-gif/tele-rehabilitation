"""Independent frozen CPU pose backends on one verified synthetic frame inventory.

YOLO reuses the product's owned worker and ByteTrack, without business rules.
MediaPipe runs in the existing isolated landmark environment and reuses its
image-pixel mapping. Neither backend's predictions are independent references.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.rehab_ml.common import ROOT, canonical_hash, file_hash, utc_now
from tools.rehab_ml.synthetic.video import (_new_json, _read, iter_selected_rgb,
                                             validate_frame_manifest)

SCHEMA = 'rehab_synthetic_pose/v1'
MODEL_HASHES = {
    'yolo17': '869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0',
    'mediapipe33': '5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1',
}


def _core():
    path = str(ROOT / 'rehab_codex_single_camera_v2_1')
    if path not in sys.path:
        sys.path.insert(0, path)


def _finite(value):
    try:
        return float(value) if value is not None and math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _model_contract(backend):
    if backend not in MODEL_HASHES:
        raise ValueError('backend_must_be_yolo17_or_mediapipe33')
    core = ROOT / 'rehab_codex_single_camera_v2_1'
    path = core / 'assets/models' / ('yolo11n-pose.pt' if backend == 'yolo17' else 'pose_landmarker_full.task')
    if not path.is_file() or file_hash(path) != MODEL_HASHES[backend]:
        raise ValueError('frozen_original_pose_model_sha256_mismatch_no_download')
    result = dict(path=str(path), sha256=MODEL_HASHES[backend], device='cpu', frozen=True)
    if backend == 'yolo17':
        manifest = _read(path.with_name('manifest.json'))
        if manifest.get('sha256') != result['sha256'] or manifest.get('schema_id') != 'coco17-v1':
            raise ValueError('original_yolo_manifest_mismatch')
        spec = importlib.util.find_spec('ultralytics')
        tracker = Path(spec.origin).parent / 'cfg/trackers/bytetrack.yaml' if spec else None
        if tracker is None or not tracker.is_file():
            raise ValueError('existing_original_bytetrack_required_no_install')
        result.update(tracker='ByteTrack', tracker_path=str(tracker), tracker_sha256=file_hash(tracker),
                      ultralytics_version=importlib.metadata.version('ultralytics'),
                      schema_id='coco17-v1', confidence_kind='ultralytics_keypoint_confidence',
                      detector_confidence=.35, imgsz=640, identity_kind='session_track_not_biometric')
    else:
        from tools.rehab_ml.mediapipe_video import model_contract
        verified, contract = model_contract()
        if verified.resolve() != path.resolve() or contract['weights_sha256'] != result['sha256']:
            raise ValueError('original_mediapipe_manifest_mismatch')
        result.update(schema_id='mediapipe33-v1', confidence_kind='min_presence_visibility',
                      identity_kind='spatial_session_only_not_biometric', options=contract)
    return result


def _base_frame(row):
    return {key: row[key] for key in ('frame_index', 'pts', 'time_base', 'timestamp_s',
                                     'decoded_rgb_sha256', 'sample_grid_time_s', 'sample_age_s')}


def _missing(row, reason, *, status='missing', elapsed_ms=None):
    return dict(_base_frame(row), pose_detected=False, track_id=None, joints={},
                people_count=0, status=status, missing_reason=reason, elapsed_ms=elapsed_ms)


def _jpeg_input(image):
    """Same original-size JPEG90 pixels for both backends; no stretch or crop."""
    import cv2
    from mobile_rehab.rehab_v2.pose_worker import JPEG_CAPACITY
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok or encoded.nbytes > JPEG_CAPACITY:
        raise ValueError('original_size_jpeg_exceeds_owned_worker_capacity_no_resize')
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if decoded is None or decoded.shape != image.shape:
        raise ValueError('jpeg_original_size_decode_failed')
    rgb = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
    data = encoded.tobytes()
    return data, dict(jpeg_sha256=hashlib.sha256(data).hexdigest(),
                      inference_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest())


def _yolo_frame(pose, row, elapsed_ms):
    _core()
    from app.landmark_schemas import COCO17
    people = []
    for person in pose.people:
        if len(person.xy) != 17 or len(person.conf) != 17:
            raise ValueError('original_coco17_output_shape_changed')
        joints = {}
        for name, xy, confidence in zip(COCO17, person.xy, person.conf):
            if len(xy) != 2:
                raise ValueError('original_coco17_xy_pair_required')
            x, y, confidence = _finite(xy[0]), _finite(xy[1]), _finite(confidence)
            # Ultralytics masks low-confidence xy to (0,0). Retain confidence,
            # but do not turn that missing-location sentinel into a corner label.
            zero_mask = x == 0. and y == 0.
            if x is None or y is None or zero_mask:
                x = y = None
            joints[name] = dict(x=x, y=y, confidence=confidence, visibility=None, presence=None,
                                coordinate_missing_reason='ultralytics_zero_coordinate_mask' if zero_mask else
                                    'nonfinite_coordinate' if x is None else None)
        people.append(dict(track_id=person.track_key, bbox=list(person.bbox), joints=joints))
    if len(people) != 1:
        return dict(_missing(row, 'no_person' if not people else 'multiple_people', elapsed_ms=elapsed_ms),
                    people_count=len(people), people=people)
    return dict(_base_frame(row), pose_detected=True, track_id=people[0]['track_id'],
                joints=people[0]['joints'], people_count=1, people=people,
                status='completed', missing_reason=None, elapsed_ms=elapsed_ms)


def _yolo_predictions(video, manifest, sample_id, model, timeout_s):
    _core()
    from app.domain import Context
    from mobile_rehab.rehab_v2.pose_worker import IsolatedPoseWorker, offline_pose_process
    worker = IsolatedPoseWorker(target=offline_pose_process, startup_timeout_s=20.,
                                cold_timeout_s=60., frame_timeout_s=20., release_timeout_s=2.)
    runtime = SimpleNamespace(context=Context(1, 'rehab', manifest['source_sha256'],
                                               'SYNTHETIC', 'TEST', sample_id),
                              engine=SimpleNamespace(spec={'side':'left'}))
    rows = []
    deadline = time.monotonic() + timeout_s
    try:
        for frame, rgb in iter_selected_rgb(video, manifest):
            if time.monotonic() >= deadline:
                raise TimeoutError('yolo_video_budget_exceeded_between_bounded_frame_calls')
            started = time.perf_counter()
            try:
                encoded, fingerprints = _jpeg_input(rgb)
                pose, stages = worker.infer(dict(sid=sample_id, seq=frame['frame_index']+1,
                    source_time_s=frame['timestamp_s'], encoded=encoded), runtime)
                if (list(pose.size) != manifest['source_size'] or pose.model_manifest_id != model['sha256']
                        or pose.schema_id != 'coco17-v1' or pose.coordinate_space != 'raw_image_pixels'
                        or pose.keypoint_order_version != 'coco17-anatomical-lr-v1'):
                    raise ValueError('original_yolo_coordinate_or_model_contract_changed')
                row = _yolo_frame(pose, frame, 1000*(time.perf_counter()-started))
                row.update(fingerprints, stages_ms=stages, backend_inference_ms=pose.inference_ms)
            except Exception as error:
                row = dict(_missing(frame, str(error)[:300], status='failed',
                                    elapsed_ms=1000*(time.perf_counter()-started)),
                           failure_type=type(error).__name__)
            rows.append(row)
    finally:
        worker.close()
        release = worker.last_release or dict(confirmed=worker.process is None, reason='worker_not_started')
        if release.get('confirmed') is not True:
            raise RuntimeError('owned_yolo_release_not_confirmed')
    return rows, dict(worker_contract=worker.contract, owned_release=release)


def _mediapipe_frame(result, row, context, previous, fingerprint, size, elapsed_ms):
    # Reuse the original mapping, including its spatial-session continuity rule.
    from tools.rehab_ml.mediapipe_video import encode_pose
    _core()
    from app.landmark_schemas import POSE33
    pose, previous, raw = encode_pose(result, context, row['frame_index']+1,
                                     row['timestamp_s'], tuple(size), fingerprint, elapsed_ms, previous)
    if not pose.people:
        return _missing(row, 'no_person', elapsed_ms=elapsed_ms), previous
    values = raw[0]
    joints = {name:dict(x=xy[0], y=xy[1], confidence=confidence,
                      visibility=visibility, presence=presence, image_z=image_z)
              for name, xy, confidence, visibility, presence, image_z in zip(
                  POSE33, values['xy'], pose.people[0].conf, values['visibility'],
                  values['presence'], values['image_z'])}
    return dict(_base_frame(row), pose_detected=True, track_id=pose.people[0].track_key,
                joints=joints, people_count=1, bbox=pose.people[0].bbox,
                status='completed', missing_reason=None, elapsed_ms=elapsed_ms), previous


def _mediapipe_child(request_path):
    request_path = Path(request_path).resolve()
    # A venv launcher can have a native child. On Windows the parent first
    # contains the exact Popen handle/tree using the existing HostJob contract.
    # A parent that dies before admission cannot leave model work running.
    admitted = request_path.parent/'child-admitted'
    deadline = time.monotonic() + 20.
    while not admitted.is_file():
        if time.monotonic() >= deadline:
            raise RuntimeError('mediapipe_child_not_admitted')
        time.sleep(.02)
    import cv2
    import mediapipe as mp
    import numpy as np
    from tools.rehab_ml.resource_gate import heavy_compute
    _core()
    from app.domain import Context
    from tools.rehab_ml.mediapipe_video import VideoClock
    request = _read(request_path)
    model = request['model']
    if file_hash(model['path']) != MODEL_HASHES['mediapipe33'] or model['sha256'] != MODEL_HASHES['mediapipe33']:
        raise ValueError('frozen_mediapipe_model_changed')
    if importlib.metadata.version('mediapipe') != model['options']['python_sdk_required']:
        raise ValueError('existing_mediapipe_sdk_version_mismatch')
    context = Context(1, 'rehab', request['source_sha256'], 'SYNTHETIC', 'TEST', request['sample_id'])
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_buffer=Path(model['path']).read_bytes(),
                                         delegate=mp.tasks.BaseOptions.Delegate.CPU),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=1,
        min_pose_detection_confidence=.5, min_pose_presence_confidence=.5, min_tracking_confidence=.5)
    clock, previous, rows = VideoClock(), None, []
    with heavy_compute(), mp.tasks.vision.PoseLandmarker.create_from_options(options) as task:
        for frame in request['frames']:
            started = time.perf_counter()
            path = request_path.parent / frame['jpeg_file']
            try:
                if path.resolve().parent != (request_path.parent/'input_frames').resolve():
                    raise ValueError('owned_mediapipe_input_frame_required')
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != frame['jpeg_sha256']:
                    raise ValueError('mediapipe_input_jpeg_sha256_mismatch')
                bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB) if bgr is not None else None
                if (rgb is None or list(rgb.shape[1::-1]) != request['source_size']
                        or hashlib.sha256(rgb.tobytes()).hexdigest() != frame['inference_rgb_sha256']):
                    raise ValueError('mediapipe_input_pixel_fingerprint_or_size_mismatch')
                milliseconds = clock.accept(frame['timestamp_s'])
                if milliseconds is None:
                    raise ValueError('nonnegative_shared_frame_timestamp_required')
                result = task.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), milliseconds)
                row, previous = _mediapipe_frame(result, frame, context, previous,
                    model['sha256'], request['source_size'], 1000*(time.perf_counter()-started))
                row.update(jpeg_sha256=frame['jpeg_sha256'], inference_rgb_sha256=frame['inference_rgb_sha256'],
                           mediapipe_timestamp_ms=milliseconds)
            except Exception as error:
                previous = None
                row = dict(_missing(frame, str(error)[:300], status='failed',
                           elapsed_ms=1000*(time.perf_counter()-started)), failure_type=type(error).__name__)
            rows.append(row)
    if file_hash(model['path']) != model['sha256']:
        raise ValueError('mediapipe_model_changed_during_inference')
    _new_json(request_path.parent/'child-poses.json', dict(rows=rows,
              environment=dict(mediapipe=importlib.metadata.version('mediapipe'),
                               opencv=cv2.__version__, python=sys.version), model_sha256=model['sha256']))


def _mediapipe_predictions(video, manifest, sample_id, model, output, timeout_s):
    core = ROOT / 'rehab_codex_single_camera_v2_1'
    python = core / ('.venv-landmarks/Scripts/python.exe' if os.name == 'nt' else '.venv-landmarks/bin/python')
    if not python.is_file():
        raise ValueError('existing_landmark_environment_required_no_auto_install')
    spool = output/'input_frames'
    spool.mkdir()
    frames = []
    for frame, rgb in iter_selected_rgb(video, manifest):
        data, fingerprints = _jpeg_input(rgb)
        filename = f'input_frames/frame-{frame["frame_index"]:06d}.jpg'
        (output/filename).write_bytes(data)
        frames.append(dict(frame, **fingerprints, jpeg_file=filename))
    request = output/'mediapipe-request.json'
    _new_json(request, dict(source_sha256=manifest['source_sha256'], source_size=manifest['source_size'],
                           model=model, sample_id=sample_id, frames=frames))
    args = [str(python), '-X', 'utf8', '-B', str(Path(__file__).resolve()), '--mediapipe-child', str(request)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', MPLBACKEND='Agg',
               MPLCONFIGDIR=str(output/'mpl'), TEMP=str(output), TMP=str(output))
    from tools.rehab_ml.mediapipe_video import release_owned
    from mobile_rehab.rehab_v2.host_lifetime import HostJob, lifetime_contract
    job = HostJob() if os.name == 'nt' else None
    with (output/'child.log').open('xb') as log:
        process = None
        try:
            process = subprocess.Popen(args, cwd=ROOT, env=env, stdout=log, stderr=log,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if job is not None:
                # HostJob takes a retained native process handle, never PID
                # discovery. Popen owns this Windows handle until it is closed.
                exact = SimpleNamespace(pid=process.pid, is_alive=lambda:process.poll() is None,
                                        sentinel=process._handle)
                job.assign(exact)
            (output/'child-admitted').write_text('owned parent admitted\n', encoding='utf-8')
            code = process.wait(timeout=timeout_s)
        except BaseException:
            if job is not None:
                job.close()
            if process is not None and not release_owned(process):
                raise RuntimeError('owned_mediapipe_release_unconfirmed')
            raise
        finally:
            if job is not None:
                job.close()
    if code != 0:
        raise RuntimeError('mediapipe_child_failed_see_preserved_child_log')
    result = _read(output/'child-poses.json')
    if result.get('model_sha256') != model['sha256']:
        raise ValueError('mediapipe_child_model_fingerprint_mismatch')
    return result['rows'], dict(environment=result['environment'], arguments=args,
                               owned_exit_confirmed=process.poll() is not None,
                               host_lifetime=lifetime_contract(),
                               child_log_sha256=file_hash(output/'child.log'))


def validate_pose(value, *, frame_manifest=None, verify_model=True):
    """Check source/row/model binding; never assess human motion correctness."""
    result = _read(value)
    if result.get('schema_version') != SCHEMA or result.get('backend') not in MODEL_HASHES:
        raise ValueError('unsupported_synthetic_pose_schema')
    if (not isinstance(result.get('frames'), list) or not result['frames']
            or not isinstance(result.get('source_size'), list) or len(result['source_size']) != 2
            or any(type(n) is not int or n < 32 for n in result['source_size'])):
        raise ValueError('nonempty_pose_frames_and_original_source_size_required')
    model = result.get('model', {})
    if model.get('sha256') != MODEL_HASHES[result['backend']]:
        raise ValueError('synthetic_pose_model_fingerprint_mismatch')
    if verify_model and (not Path(model['path']).is_file() or file_hash(model['path']) != model['sha256']):
        raise ValueError('synthetic_pose_model_file_changed')
    if frame_manifest is not None:
        manifest = validate_frame_manifest(frame_manifest)
        if (result.get('source_sha256') != manifest['source_sha256']
                or result.get('source_size') != manifest['source_size']
                or result.get('frame_manifest_sha256') != canonical_hash(manifest)
                or len(result.get('frames', [])) != len(manifest['frames'])):
            raise ValueError('synthetic_pose_shared_frame_binding_mismatch')
        for row, source in zip(result['frames'], manifest['frames']):
            if any(row.get(key) != value for key, value in _base_frame(source).items()):
                raise ValueError('synthetic_pose_frame_pts_or_pixel_binding_mismatch')
    previous, previous_index = -math.inf, -1
    _core()
    from app.landmark_schemas import COCO17, POSE33
    names = set(COCO17 if result['backend'] == 'yolo17' else POSE33)
    for row in result.get('frames', []):
        if (not isinstance(row.get('pose_detected'), bool) or _finite(row.get('timestamp_s')) is None
                or row.get('timestamp_s', -1) <= previous or row['timestamp_s'] < 0
                or type(row.get('frame_index')) is not int or row['frame_index'] <= previous_index
                or type(row.get('pts')) is not int
                or not isinstance(row.get('time_base'), list) or len(row['time_base']) != 2
                or any(type(n) is not int or n <= 0 for n in row['time_base'])
                or row.get('status') not in ('completed','missing','failed')):
            raise ValueError('ordered_pose_frame_or_detection_mask_required')
        previous, previous_index = row['timestamp_s'], row['frame_index']
        if row['status'] == 'failed' and row['pose_detected']:
            raise ValueError('failed_frame_cannot_claim_successful_pose')
        if not row['pose_detected'] and (row.get('joints') != {} or row.get('track_id') is not None):
            raise ValueError('missing_pose_must_not_contain_fabricated_joints_or_track')
        if row['pose_detected'] and set(row.get('joints', {})) != names:
            raise ValueError('complete_backend_named_joint_schema_required')
        for joint in row.get('joints', {}).values():
            if not all(key in joint for key in ('x','y','confidence','visibility','presence')):
                raise ValueError('explicit_coordinate_and_backend_confidence_fields_required')
            for key in ('x', 'y', 'confidence', 'visibility', 'presence'):
                value = joint.get(key)
                if value is not None and (_finite(value) is None
                        or key in ('confidence','visibility','presence') and not 0 <= value <= 1):
                    raise ValueError('finite_pixel_or_backend_probability_required')
            if (joint.get('x') is None) != (joint.get('y') is None):
                raise ValueError('partial_xy_pair_not_supported')
    return result


def extract_pose(video, frame_manifest, output_dir, *, sample_id, backend='yolo17', timeout_s=600.):
    """Run one frozen CPU backend; callers schedule generation/training separately.

    This creates a new output directory and retains failures. Sources and model
    hashes are checked before and after inference; unavailable joints stay null.
    """
    if not isinstance(sample_id, str) or re.fullmatch(r'[A-Za-z0-9_-]{1,96}', sample_id) is None:
        raise ValueError('safe_sample_id_required')
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 5 <= timeout_s <= 1800:
        raise ValueError('bounded_pose_inference_timeout_required')
    manifest = validate_frame_manifest(frame_manifest, video=video, verify_decode=True)
    model = _model_contract(backend)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    _new_json(output/'frame-manifest.json', manifest)
    started = time.perf_counter()
    result = dict(schema_version=SCHEMA, sample_id=sample_id, backend=backend,
                  source_path=str(Path(video).resolve()), source_sha256=manifest['source_sha256'],
                  source_size=manifest['source_size'], model=model,
                  frame_manifest_sha256=canonical_hash(manifest),
                  frame_manifest_path=str(output/'frame-manifest.json'),
                  time_basis=manifest['time_basis'], sampling_hz=manifest['sampling_hz'],
                  preprocessing=dict(resize=False, crop=False, flip=False, original_coordinates=True,
                                     internal_model_preprocessing='original_backend_unchanged',
                                     shared_input='original_size_jpeg90_decode_rgb24', jpeg_quality=90,
                                     source_pixel_fingerprint='decoded_rgb_sha256',
                                     backend_input_pixel_fingerprint='inference_rgb_sha256'),
                  is_ground_truth=False, independent_reference=False, product_enabled=False,
                  status='running', started_at=utc_now(), frames=[])
    _new_json(output/'request.json', dict(sample_id=sample_id, backend=backend, video=str(Path(video).resolve()),
                                        source_sha256=manifest['source_sha256'], model=model,
                                        frame_manifest_sha256=canonical_hash(manifest)))
    try:
        if backend == 'yolo17':
            rows, execution = _yolo_predictions(video, manifest, sample_id, model, timeout_s)
        else:
            rows, execution = _mediapipe_predictions(video, manifest, sample_id, model, output, timeout_s)
        result.update(frames=rows, execution=execution)
        if file_hash(video) != manifest['source_sha256'] or _model_contract(backend) != model:
            raise ValueError('source_model_or_tracker_configuration_changed_during_inference')
        validate_pose(result, frame_manifest=manifest)
        failures = sum(row['status'] == 'failed' for row in rows)
        result.update(status='failed' if failures == len(rows) else 'completed_with_failures' if failures else 'completed',
                      inference_failures=failures, detected_frames=sum(row['pose_detected'] for row in rows),
                      processed_frames=len(rows))
    except Exception as error:
        result.update(status='failed', failure_type=type(error).__name__, failure=str(error)[:500])
        if not result['frames']:
            result['frames'] = [_missing(row, 'backend_not_completed', status='failed') for row in manifest['frames']]
    result.update(elapsed_s=time.perf_counter()-started, completed_at=utc_now())
    _new_json(output/'pose.json', result)
    return {**result, 'result_path':str(output/'pose.json'), 'result_sha256':file_hash(output/'pose.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mediapipe-child', type=Path, required=True)
    _mediapipe_child(parser.parse_args().mediapipe_child)
