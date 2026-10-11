"""Original YOLO on verified CC0 videos; predictions are not 2D ground truth."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import numpy as np

from .common import ROOT, file_hash, paths, read_json, utc_now, write_json
from .mobiphysio_rgb import load_plan

FEATURE_SCHEMA = 'mobiphysio-front-rgb2d-causal69-1'
PERIOD_S = .25
CONFIDENCE_MIN = .5
MAX_DURATION_S = 180.
MAX_DECODED_FRAMES = 18000
LONG_EDGE = 640
PTS_TOLERANCE_S = .0002  # decoder rounding only; no invented clock or interpolation


def presentation_timeline(packets, advertised_frames):
    """Account for explicit container discard packets, not a relaxed count tolerance."""
    packets = list(packets)
    if not 1 <= len(packets) <= MAX_DECODED_FRAMES or len(packets) != advertised_frames:
        raise ValueError('Container packet inventory disagrees with frame header or quota')
    stamps, discarded = [], 0
    for row in packets:
        if row['corrupt'] or not np.isfinite(row['pts_s']):
            raise ValueError('Corrupt packet or missing presentation time')
        if row['discard']:
            discarded += 1
        else:
            stamps.append(float(row['pts_s']))
    stamps.sort()
    if not stamps or not (np.diff(stamps) > 0).all() or stamps[-1] > MAX_DURATION_S:
        raise ValueError('Invalid presentable timeline or duration quota')
    return stamps, discarded


def container_timeline(source, advertised_frames):
    import av
    with av.open(str(source)) as container:
        if len(container.streams.video) != 1:
            raise ValueError('Exactly one video stream required')
        stream = container.streams.video[0]
        if stream.start_time is None or stream.time_base is None:
            raise ValueError('Missing explicit stream timeline origin')
        origin = float(stream.start_time*stream.time_base)
        if not np.isfinite(origin):
            raise ValueError('Nonfinite stream origin')
        packets = []
        for packet in container.demux(stream):
            if not packet.size:
                continue  # empty decoder flush packet, not a video sample
            if packet.pts is None or packet.time_base is None:
                raise ValueError('Missing packet presentation timestamp')
            # Retain explicit stream-relative presentation time; no FPS-generated clock.
            packets.append(dict(pts_s=float(packet.pts*packet.time_base)-origin,
                                corrupt=packet.is_corrupt, discard=packet.is_discard))
            if len(packets) > MAX_DECODED_FRAMES:
                raise ValueError('Container packet quota exceeded')
    stamps, discarded = presentation_timeline(packets, round(advertised_frames))
    return stamps, discarded, origin


def frame_features(xy, confidence, size, dt):
    """Current frame only, shoulder-width scale; masks accompany every zero placeholder."""
    xy = np.asarray(xy, dtype=np.float64)
    confidence = np.asarray(confidence, dtype=np.float64)
    if xy.shape != (17, 2) or confidence.shape != (17,) or not np.isfinite(dt) or dt < 0:
        raise ValueError('COCO17 prediction and nonnegative source dt required')
    width, height = size
    if width <= 0 or height <= 0:
        raise ValueError('Valid frame size required')
    finite = np.isfinite(confidence) & np.isfinite(xy).all(1)
    usable = finite & (confidence >= CONFIDENCE_MIN) & (confidence <= 1)
    usable &= (xy[:, 0] >= 0) & (xy[:, 0] < width) & (xy[:, 1] >= 0) & (xy[:, 1] < height)
    normalized = np.zeros((17, 2), dtype=np.float64)
    anchor_valid = bool(usable[5] and usable[6])
    scale = float(np.linalg.norm(xy[5]-xy[6])) if anchor_valid else 0.
    if scale < 1.:
        usable[:] = False
        anchor_valid = False
    if anchor_valid:
        normalized[usable] = (xy[usable]-(xy[5]+xy[6])/2)/scale
    known_conf = np.where(np.isfinite(confidence) & (confidence >= 0) & (confidence <= 1), confidence, 0.)
    features = np.concatenate((normalized.reshape(-1), usable.astype(float), known_conf, [dt]))
    if not np.isfinite(features).all():
        raise ValueError('Nonfinite features cannot be serialized or trained')
    return features.astype(np.float32), usable, anchor_valid


def verified_download(receipt_path):
    receipt_path = Path(receipt_path).resolve()
    if not re.fullmatch(r'download-[0-9a-f]{8}\.json', receipt_path.name):
        raise ValueError('Explicit download receipt required')
    receipt = read_json(receipt_path)
    plan_path, plan = load_plan(receipt['plan'])
    if (receipt_path.parent != plan_path.parent or receipt.get('schema_version') != 'mobiphysio-rgb-download-1'
            or receipt.get('status') != 'verified_rgb_download' or receipt.get('plan_sha256') != file_hash(plan_path)
            or receipt.get('verified_file_bytes') != plan['expected_bytes'] or len(receipt['files']) != len(plan['samples'])):
        raise ValueError('Partial or changed download cannot become the full RGB experiment')
    by_id = {row['file_id']: row for row in receipt['files']}
    if len(by_id) != len(receipt['files']):
        raise ValueError('Duplicate download file ID')
    for sample in plan['samples']:
        row = by_id.get(sample['file_id'])
        source = plan_path.parent / sample['filename']
        if (row is None or Path(row['path']).resolve() != source.resolve() or source.stat().st_size != sample['bytes']
                or row['bytes'] != sample['bytes'] or row['subject_id'] != sample['subject_id']
                or row['split'] != sample['split'] or file_hash(source, 'md5') != sample['md5']
                or file_hash(source) != row['sha256']):
            raise ValueError('Verified RGB bytes, source identity or group split changed')
    return receipt_path, receipt, plan_path, plan


def extract_cohort(receipt_path):
    import cv2
    import av
    receipt_path, receipt, plan_path, plan = verified_download(receipt_path)
    sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
    from app.domain import Context
    from mobile_rehab.rehab_v2.pose_worker import IsolatedPoseWorker, JPEG_CAPACITY, offline_pose_process
    weights = ROOT/'rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt'
    weight_hash = file_hash(weights)
    contract = read_json(weights.with_name('manifest.json'))
    if contract.get('sha256') != weight_hash or contract.get('schema_id') != 'coco17-v1':
        raise ValueError('Original weight contract changed')
    output = paths()['run'] / ('mobiphysio-pose-'+uuid4().hex[:8])
    output.mkdir()
    worker = IsolatedPoseWorker(target=offline_pose_process)
    summary = dict(schema_version='mobiphysio-pose-extraction-1', status='running', run_id=output.name,
        source_receipt=str(receipt_path), receipt_sha256=file_hash(receipt_path),
        plan=str(plan_path), plan_sha256=file_hash(plan_path), study=plan['study'], subject_splits=plan['subject_splits'],
        feature_schema=FEATURE_SCHEMA, model_sha256=weight_hash, samples=[],
        sampling=dict(period_s=PERIOD_S, source='actual_pyav_frame_pts_relative_to_explicit_stream_origin', interpolation=False,
                      initial_negative_pts='skip', nominal_fps_is_not_timestamps=True),
        completeness=dict(reference='PyAV demux packet PTS minus explicit stream start_time and discard flags',
                          decoder_pts_tolerance_s=PTS_TOLERANCE_S, frame_count_tolerance=0),
        preprocessing=dict(long_edge=LONG_EDGE, upscale=False, flip=False, crop=False, jpeg_quality=90,
                           coordinate_mapping='inference_pixels divided by explicit sx/sy to original image pixels'),
        prediction_confidence_min=CONFIDENCE_MIN, label_granularity='whole_video_eaaq',
        no_independent_keypoint_reference=True, clinical_accuracy=None, product_enabled=False, training_performed=False,
        worker_contract=worker.contract, source_sha256={str(path): file_hash(path) for path in
            (Path(__file__), ROOT/'tools/rehab_ml/mobiphysio_rgb.py', ROOT/'mobile_rehab/rehab_v2/pose_worker.py',
             ROOT/'rehab_codex_single_camera_v2_1/app/vision.py')}, started_at=utc_now())
    write_json(output/'summary.json', summary)
    by_id = {row['file_id']: row for row in receipt['files']}
    try:
        for epoch, sample in enumerate(plan['samples'], 1):
            summary['current_video'] = sample['video_name']
            write_json(output/'summary.json', summary)
            source = plan_path.parent / sample['filename']
            capture = av.open(str(source))
            if len(capture.streams.video) != 1:
                capture.close()
                raise ValueError('Exactly one verified video stream required')
            video_stream = capture.streams.video[0]
            advertised_frames = float(video_stream.frames)
            advertised_width, advertised_height = float(video_stream.width), float(video_stream.height)
            if (not np.isfinite([advertised_frames, advertised_width, advertised_height]).all()
                    or not 1 <= advertised_frames <= MAX_DECODED_FRAMES
                    or not 32 <= advertised_width <= 4096 or not 32 <= advertised_height <= 4096):
                capture.close()
                raise ValueError('Decoded RGB header is outside declared frame/dimension budgets')
            runtime = SimpleNamespace(context=Context(epoch, 'rehab', sample['subject_id'], 'REPLAY_FILE', 'RESEARCH', output.name),
                                      engine=SimpleNamespace(spec=dict(side='left')))
            # Side is only the existing worker's required YOLO invocation hint;
            # bilateral COCO17 is retained. It never becomes affected-side truth.
            frames, decoded, skipped_negative, prior, next_sample, prior_sample = [], 0, 0, None, None, None
            latencies, sequence, masks = [], [], []
            try:
                expected_pts, discarded_packets, stream_origin = container_timeline(source, advertised_frames)
                for decoded_frame in capture.decode(video_stream):
                    decoded += 1
                    if decoded > MAX_DECODED_FRAMES:
                        raise ValueError('Declared RGB frame budget exceeded')
                    if decoded_frame.pts is None or decoded_frame.time_base is None or decoded_frame.is_corrupt:
                        raise ValueError('Corrupt decoded frame or missing real frame PTS')
                    pts = float(decoded_frame.pts*decoded_frame.time_base)-stream_origin
                    if not np.isfinite(pts): raise ValueError('Nonfinite decoder PTS')
                    if decoded > len(expected_pts) or abs(pts-expected_pts[decoded-1]) > PTS_TOLERANCE_S:
                        raise ValueError('Decoded frame does not match container presentation PTS')
                    if pts < 0 and prior is None:
                        skipped_negative += 1
                        continue
                    if prior is not None and pts <= prior:
                        raise ValueError('Media PTS is not strictly monotonic; no nominal repair')
                    prior = pts
                    if decoded > MAX_DECODED_FRAMES or pts > MAX_DURATION_S:
                        raise ValueError('Declared RGB decode duration/frame budget exceeded')
                    if next_sample is not None and pts+1e-9 < next_sample: continue
                    next_sample = pts+PERIOD_S
                    image = decoded_frame.to_ndarray(format='bgr24')
                    height, width = image.shape[:2]
                    factor = min(1., LONG_EDGE/max(width, height))
                    resized = cv2.resize(image, (max(1, round(width*factor)), max(1, round(height*factor)))) if factor < 1 else image
                    infer_height, infer_width = resized.shape[:2]
                    encoded_ok, jpeg = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    if not encoded_ok or jpeg.size > JPEG_CAPACITY:
                        raise ValueError('Explicit research JPEG exceeds existing owned-worker capacity')
                    started = time.perf_counter()
                    pose, stages = worker.infer(dict(sid=sample['video_name'], seq=decoded, source_time_s=pts,
                                                    encoded=jpeg.tobytes()), runtime)
                    elapsed = (time.perf_counter()-started)*1000
                    if (pose.size != (infer_width, infer_height) or pose.model_manifest_id != weight_hash
                            or pose.schema_id != 'coco17-v1' or pose.coordinate_space != 'raw_image_pixels'
                            or pose.keypoint_order_version != 'coco17-anatomical-lr-v1'):
                        raise ValueError('Original pose output coordinate/model contract changed')
                    single = len(pose.people) == 1
                    xy = np.asarray(pose.people[0].xy, dtype=float) if single else np.full((17, 2), np.nan)
                    confidence = np.asarray(pose.people[0].conf, dtype=float) if single else np.zeros(17)
                    scales = np.asarray([infer_width/width, infer_height/height])
                    xy_source = xy/scales
                    dt = 0. if prior_sample is None else pts-prior_sample
                    feature, usable, anchor = frame_features(xy_source, confidence, (width, height), dt)
                    sequence.append(feature); masks.append(bool(single and anchor)); latencies.append(elapsed)
                    frames.append(dict(seq=decoded, pts=pts, raw_frame_size=[width, height],
                        inference_frame_size=[infer_width, infer_height], scale_xy=scales.tolist(),
                        raw_decoded_sha256=hashlib.sha256(image.tobytes()).hexdigest(),
                        jpeg_sha256=hashlib.sha256(jpeg.tobytes()).hexdigest(), predicted_people=len(pose.people),
                        xy_source_px=[[float(x), float(y)] if np.isfinite([x, y]).all() else None for x, y in xy_source],
                        conf=[float(value) if np.isfinite(value) else None for value in confidence],
                        usable_prediction_mask=usable.tolist(), body_scale_usable=anchor,
                        worker_ms=elapsed, stages_ms=stages))
                    prior_sample = pts
            finally:
                capture.close()
            if decoded != len(expected_pts):
                raise ValueError('Decoder ended before the full presentable timeline; no truncated-score training')
            if not frames or not any(masks): raise ValueError('No usable sampled body scale; no empty feature training')
            arrays = output/(sample['video_name']+'.npz')
            np.savez_compressed(arrays, features=np.asarray(sequence), time_s=np.asarray([row['pts'] for row in frames]),
                                prediction_mask=np.asarray(masks, dtype=bool))
            detail = output/(sample['video_name']+'.json')
            write_json(detail, dict(schema_version='mobiphysio-rgb-predictions-1', frames=frames, affected_side=None,
                                    label_is_video_level=True, independent_keypoint_reference=False))
            summary['samples'].append(dict(video_name=sample['video_name'], subject_id=sample['subject_id'], split=sample['split'],
                file_id=sample['file_id'], source_sha256=by_id[sample['file_id']]['sha256'], score=sample['label'],
                decoded_frames=decoded, sampled_frames=len(frames), usable_frames=sum(masks), skipped_negative_pts=skipped_negative,
                advertised_frames=advertised_frames, explicit_discard_packets=discarded_packets,
                container_stream_start_s=stream_origin,
                expected_presentable_frames=len(expected_pts), decoded_full_presentable_video=True,
                last_pts=prior, npz=str(arrays), npz_sha256=file_hash(arrays), detail=str(detail), detail_sha256=file_hash(detail),
                roundtrip_ms_p50=float(np.quantile(latencies, .5)), roundtrip_ms_p95=float(np.quantile(latencies, .95))))
            write_json(output/'summary.json', summary)
            print(f"Original YOLO completed {len(summary['samples'])}/{len(plan['samples'])}: {sample['video_name']}", flush=True)
        summary['status'] = 'completed_pose_extraction'
    except Exception as exc:
        summary.update(status='failed_pose_extraction', error_type=type(exc).__name__, error=str(exc))
    finally:
        try:
            worker.close()
            summary['owned_release'] = worker.last_release
        except Exception as exc:
            summary.update(status='failed_resource_release', release_error=str(exc))
        summary.update(completed_at=utc_now(), summary_path=str(output/'summary.json'))
        write_json(output/'summary.json', summary)
    return summary
