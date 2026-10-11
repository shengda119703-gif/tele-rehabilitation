"""Consent-scoped Python VIDEO approximation of the unchanged APK pose input.

Native decode/inference runs only in the existing landmark environment child.
No camera, model download, SQL, clinical truth or client activation is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.rehab_ml.common import ROOT, file_hash, paths, read_json, write_json
from tools.rehab_ml.pose_dataset import _new_output
from tools.rehab_ml.resource_gate import heavy_compute

VERSION = 'rehab-mediapipe-video-audit-1'
MAX_FRAMES = 15000
MAX_VIDEO_BYTES = 256*1024*1024
MAX_SECONDS = 120.


class VideoClock:
    """Keep media seconds exact; millisecond API cannot repair discontinuities."""
    def __init__(self):
        self.previous = self.previous_ms = None
        self.leading_skipped = 0
        self.last_skipped_raw_time_s = None

    def accept(self, stamp):
        if type(stamp) not in (float, int) or not math.isfinite(stamp):
            raise ValueError('finite_media_pts_required')
        if self.previous is None and -.25 <= stamp < 0 and self.leading_skipped < 4:
            self.leading_skipped += 1
            self.last_skipped_raw_time_s = stamp
            return None
        if stamp < 0 or self.previous is not None and stamp <= self.previous:
            raise ValueError('strictly_increasing_nonnegative_media_pts_required')
        milliseconds = round(stamp*1000)
        if self.previous_ms is not None and milliseconds <= self.previous_ms:
            raise ValueError('distinct_mediapipe_millisecond_timestamps_required')
        self.previous, self.previous_ms = float(stamp), milliseconds
        return milliseconds


def model_contract():
    """Verify original model and separately declare SDK/build differences."""
    core = ROOT/'rehab_codex_single_camera_v2_1'
    sys.path.insert(0, str(core))
    from app.landmark_backend import verified_model
    model, fingerprint = verified_model('mediapipe_pose')
    android = ROOT/'android_offline'
    lock = read_json(android/'package-lock.json')
    sdk = lock['packages']['node_modules/@mediapipe/tasks-vision']['version']
    built = android/'build/assets/models/pose_landmarker_full.task'
    return model, dict(weights_sha256=fingerprint, python_sdk_required='1.0.1',
        apk_javascript_sdk_locked=sdk, apk_build_model_sha256=file_hash(built) if built.is_file() else None,
        apk_build_weight_matches=built.is_file() and file_hash(built) == fingerprint,
        installed_apk_weights_not_verified=True, mode='VIDEO', delegate='CPU', num_poses=1,
        min_pose_detection_confidence=.5, min_pose_presence_confidence=.5, min_tracking_confidence=.5,
        options_basis='unchanged_android_offline/web/worker.js',
        sdk_platform_and_decoding_not_identical=True, phone_performance_not_measured=True)


def encode_pose(result, context, seq, stamp, size, fingerprint, elapsed, previous):
    """Preserve presence/visibility and original pixel geometry; no world mixing."""
    from app.domain import PoseFrame, PosePerson
    from app.landmark_schemas import ORDERS
    width, height = size
    if len(result.pose_landmarks) > 1:
        raise ValueError('single_pose_video_contract_required')
    people = []
    raw = []
    for landmarks in result.pose_landmarks:
        if len(landmarks) != 33:
            raise ValueError('mediapipe33_landmark_contract_required')
        def finite(value):
            return float(value) if value is not None and math.isfinite(value) else None
        xy = [[finite(p.x*width), finite(p.y*height)] for p in landmarks]
        visibility = [finite(p.visibility) for p in landmarks]
        presence = [finite(p.presence) for p in landmarks]
        conf = [min(a, b) if a is not None and b is not None else None
                for a, b in zip(visibility, presence)]
        valid = [p for p, c in zip(xy, conf) if c is not None and c >= .5
                 and all(v is not None for v in p) and 0 <= p[0] <= width and 0 <= p[1] <= height]
        center = (sum(p[0] for p in valid)/len(valid), sum(p[1] for p in valid)/len(valid)) if valid else None
        # No biological identity claim. Missing/large jump/gap breaks spatial ID.
        continuous = (center is not None and previous is not None and 0 < stamp-previous[0] <= .5
                      and math.dist(center, previous[1]) <= .15*math.hypot(width, height))
        track = previous[2] if continuous else f'mp-spatial:{seq}'
        previous = (stamp, center, track) if center is not None else None
        finite_points = [p for p in xy if all(v is not None for v in p)]
        bbox = ([min(p[0] for p in finite_points), min(p[1] for p in finite_points),
                 max(p[0] for p in finite_points), max(p[1] for p in finite_points)] if finite_points else [0.]*4)
        attributes = dict(confidence_kind='min_presence_visibility', raw_visibility=visibility,
            raw_presence=presence, image_z=[finite(p.z) for p in landmarks],
            identity_kind='spatial_session_only_not_biometric', detector_mode='VIDEO')
        people.append(PosePerson(track, bbox, xy, conf, attributes))
        raw.append(dict(xy=xy, visibility=visibility, presence=presence,
                        image_z=attributes['image_z'], track_key=track))
    return PoseFrame(context, seq, stamp, size, people, elapsed, schema_id='mediapipe33-v1',
        keypoint_order_version=ORDERS['mediapipe33-v1'], model_manifest_id=fingerprint,
        backend='mediapipe_pose'), previous if people else None, raw


def run_child(request_path):
    with heavy_compute():
        return _run_child(request_path)


def _run_child(request_path):
    """Bounded file-only inference; called by the existing landmark interpreter."""
    request = read_json(request_path)
    if request.get('analysis_consent') is not True:
        raise ValueError('explicit_local_video_analysis_consent_required')
    source, output = Path(request['video']).resolve(), Path(request_path).resolve().parent
    if file_hash(source) != request['video_sha256']:
        raise ValueError('source_changed_before_decode')
    model, contract = model_contract()
    model_bytes = model.read_bytes()
    if hashlib.sha256(model_bytes).hexdigest() != contract['weights_sha256']:
        raise ValueError('pose_model_changed_before_load')
    import cv2
    import mediapipe as mp
    import numpy as np
    if mp.__version__ != contract['python_sdk_required']:
        raise ValueError('locked_landmark_runtime_version_mismatch')
    from app.domain import Context, clean_json
    from app.rehab_v2.evidence import EvidenceAdapter
    from app.rehab_v2.engine import ProtocolEngine
    context = Context(1, 'rehab', request['video_sha256'], 'REPLAY_FILE', 'TEST', output.name)
    adapter = EvidenceAdapter(request['exercise_id'], request['side'])
    engine = ProtocolEngine(dict(exercise_id=request['exercise_id'], side=request['side']), source_epoch=context.epoch)
    clock, previous, frames, decoded, observable, latencies = VideoClock(), None, 0, 0, 0, []
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        cap.release()
        raise ValueError('local_video_decoder_open_failed')
    expected = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if not math.isfinite(expected) or expected < 3 or expected > MAX_FRAMES or expected != int(expected):
        cap.release()
        raise ValueError('bounded_declared_video_frame_count_required')
    width, height = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    if not 0 < width*height <= 1920*1080 or max(width, height) > 4096:
        cap.release()
        raise ValueError('video_pixel_budget_exceeded_no_implicit_resize')
    start = time.perf_counter()
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_buffer=model_bytes, delegate=mp.tasks.BaseOptions.Delegate.CPU),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=1,
        min_pose_detection_confidence=.5, min_pose_presence_confidence=.5, min_tracking_confidence=.5)
    try:
        with mp.tasks.vision.PoseLandmarker.create_from_options(options) as task, (output/'pose-frames.jsonl').open('w', encoding='utf-8') as stream:
            while True:
                ok, image = cap.read()
                if not ok:
                    if decoded != int(expected):
                        raise ValueError('decoder_stopped_before_declared_end')
                    break
                decoded += 1
                if (decoded > MAX_FRAMES or image is None or image.dtype != np.uint8 or image.ndim != 3
                        or image.shape[2] != 3 or image.shape[1::-1] != (int(width), int(height))):
                    raise ValueError('original_constant_rgb_frame_contract_required')
                stamp = float(cap.get(cv2.CAP_PROP_POS_MSEC))/1000
                if stamp > MAX_SECONDS:
                    raise ValueError('video_duration_budget_exceeded')
                timestamp = clock.accept(stamp)
                if timestamp is None:
                    continue
                frames += 1
                tick = time.perf_counter()
                result = task.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,
                    data=np.ascontiguousarray(image[:, :, ::-1])), timestamp)
                elapsed = (time.perf_counter()-tick)*1000
                pose, previous, raw = encode_pose(result, context, frames, stamp, (int(width), int(height)),
                    contract['weights_sha256'], elapsed, previous)
                evidence = adapter.analyze(pose, processing_age_ms=0., time_basis='opencv_media_pts')
                engine.process(evidence)
                observable += engine.observation_state in ('observable', 'partially_observable')
                latencies.append(elapsed)
                stream.write(json.dumps(clean_json(dict(seq=frames, decoded_frame_index=decoded,
                    time_s=stamp, mediapipe_timestamp_ms=timestamp, size=pose.size, schema_id=pose.schema_id,
                    decoded_bgr_sha256=hashlib.sha256(np.ascontiguousarray(image).tobytes()).hexdigest(),
                    coordinate_space=pose.coordinate_space, raw_pose=raw, metrics=evidence.metrics,
                    processing_age_is_offline_zero_not_realtime=True)), ensure_ascii=False, allow_nan=False)+'\n')
    finally:
        cap.release()
    if frames < 3 or file_hash(source) != request['video_sha256']:
        raise ValueError('usable_video_or_source_fingerprint_mismatch')
    engine.finish('user_stopped')
    latencies.sort()
    result = dict(version=VERSION, video_sha256=request['video_sha256'], exercise_id=request['exercise_id'],
        side=request['side'], frames=frames, decoded_frames=decoded, observable_frames=observable,
        observed_fraction=observable/frames, input_timing=dict(basis='opencv_media_pts',
            skipped_leading_frames=clock.leading_skipped, last_skipped_raw_time_s=clock.last_skipped_raw_time_s,
            video_api_timestamp='round(media_pts_seconds*1000)', timestamps_not_filled=True),
        runtime=dict(python=sys.version.split()[0], mediapipe=mp.__version__, opencv=cv2.__version__, numpy=np.__version__),
        model=contract, protocol=engine.spec, v2_summary=engine.summary(), elapsed_s=time.perf_counter()-start,
        inference_latency_ms={name:latencies[max(0, math.ceil(q*len(latencies))-1)] for name,q in [('p50',.5),('p95',.95)]},
        pose_file_sha256=file_hash(output/'pose-frames.jsonl'), training_authorized=False,
        analysis_authorization='explicit_local_video_analysis', independent_reference_available=False,
        clinical_accuracy=None, count_accuracy=None, phone_performance=None,
        world_landmarks_not_used=True, bbox_kind='derived_model_points_not_independent_full_person_bbox',
        status='python_video_approximation_not_apk_acceptance')
    write_json(output/'result.json', clean_json(result))


def extract_mediapipe(video, exercise, side, *, analysis_consent=False, output_dir=None, timeout_s=180.):
    if analysis_consent is not True or exercise not in ('shoulder_abduction','sit_to_stand','rehab_squat') or side not in ('left','right'):
        raise ValueError('explicit_video_analysis_and_pilot_action_required')
    if type(timeout_s) not in (float, int) or not math.isfinite(timeout_s) or not 5 <= timeout_s <= 300:
        raise ValueError('bounded_video_child_timeout_required')
    source = Path(video).resolve()
    if (not source.is_file() or source.suffix.lower() not in ('.mp4','.mov','.m4v','.avi')
            or not 0 < source.stat().st_size <= MAX_VIDEO_BYTES):
        raise ValueError('bounded_existing_video_file_required_not_camera_input')
    core = ROOT/'rehab_codex_single_camera_v2_1'
    python = core/'.venv-landmarks/Scripts/python.exe' if os.name == 'nt' else core/'.venv-landmarks/bin/python'
    if not python.is_file():
        raise ValueError('existing_landmark_environment_required_no_auto_install')
    fingerprint = file_hash(source)
    output = _new_output(output_dir or paths()['run']/('mediapipe-video-'+uuid4().hex[:8]))
    write_json(output/'request.json', dict(video=str(source), video_sha256=fingerprint,
        exercise_id=exercise, side=side, analysis_consent=True))
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', MPLBACKEND='Agg',
        MPLCONFIGDIR=str(output/'mpl'), TEMP=str(output), TMP=str(output))
    arguments = [str(python), '-X','utf8','-B',str(Path(__file__).resolve()),'--child-request',str(output/'request.json')]
    started = time.perf_counter()
    with (output/'child.log').open('wb') as log:
        process = subprocess.Popen(arguments, cwd=ROOT, env=environment, stdout=log, stderr=log,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            code = process.wait(timeout=timeout_s)
        except BaseException as error:
            confirmed = release_owned(process)
            write_json(output/'failure.json',dict(status=('release_unconfirmed' if not confirmed else
                'timeout' if isinstance(error,subprocess.TimeoutExpired) else 'cancelled_or_wait_failed'),
                pid=process.pid,owned_exit_confirmed=confirmed,training_authorized=False))
            if not confirmed:
                raise RuntimeError('owned_video_child_release_unconfirmed') from error
            if isinstance(error,subprocess.TimeoutExpired):
                raise TimeoutError('owned_mediapipe_video_timeout_no_result_claim') from error
            raise
    provenance = dict(arguments=arguments, exit_code=code, elapsed_s=time.perf_counter()-started,
        child_log_sha256=file_hash(output/'child.log'), owned_exit_confirmed=process.poll() is not None,
        source_hash_unchanged=file_hash(source)==fingerprint,
        implementation_sha256={name:file_hash(ROOT/name) for name in (
            'tools/rehab_ml/mediapipe_video.py','rehab_codex_single_camera_v2_1/app/rehab_v2/engine.py',
            'rehab_codex_single_camera_v2_1/app/rehab_v2/evidence.py','rehab_codex_single_camera_v2_1/app/quality.py')})
    write_json(output/'provenance.json',provenance)
    if code != 0 or not provenance['source_hash_unchanged']:
        raise RuntimeError('mediapipe_video_child_failed_or_source_changed_no_success_claim')
    result = read_json(output/'result.json')
    if result['video_sha256'] != fingerprint or file_hash(output/'pose-frames.jsonl') != result['pose_file_sha256']:
        raise ValueError('mediapipe_video_artifact_fingerprint_mismatch')
    return dict(path=str(output/'result.json'), video_sha256=fingerprint, frames=result['frames'],
        observable_frames=result['observable_frames'], v2_completed=result['v2_summary']['completed'],
        elapsed_s=result['elapsed_s'], training_authorized=False, phone_performance=None,
        result_sha256=file_hash(output/'result.json'), owned_exit_confirmed=True)


def release_owned(process):
    """Only the exact child handle; never broad process-name/PID discovery."""
    if process.poll() is not None:
        return True
    try:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    except (OSError,subprocess.TimeoutExpired):
        return process.poll() is not None
    return process.poll() is not None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--child-request',type=Path,required=True)
    args = parser.parse_args()
    try:
        run_child(args.child_request)
    except Exception as error:
        write_json(args.child_request.resolve().parent/'failure.json', dict(status='failed',
            error_type=type(error).__name__,code=str(error)[:160], training_authorized=False,
            clinical_accuracy=None))
        raise
