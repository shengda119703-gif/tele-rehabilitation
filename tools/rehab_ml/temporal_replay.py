"""Original licensed RGB -> original pose worker -> unchanged v2 protocol.

Research predictions only; no human forms, video scores, patient store or UI are
consumed. The analyzed side is explicit, not an inferred affected-side label.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import math
from pathlib import Path
import sys
import time
from types import SimpleNamespace

from .common import ROOT, canonical_hash, file_hash, utc_now, write_json
from .professional_annotations import BOUNDARIES, _new_output, _source_samples
from .mobiphysio_pose import (LONG_EDGE, PERIOD_S, PTS_TOLERANCE_S,
                             container_timeline)
from .temporal_evaluation import PREDICTION_SCHEMA

VERSION = 'rehab-original-temporal-replay-1'
SUPPORTED = ('outbound_start_s', 'return_start_s', 'end_s')


def transition_events(before, after, seq, stamp):
    """Confirmation PTS, never an invented earlier motion/peak boundary.

    The initial ready calibration is not a per-repetition preparation event.
    Endpoint band boundaries belong to another retrospective timing definition;
    do not export them as human phase boundaries.
    """
    phase_before, phase_after = before['phase'], after['phase']
    events = []
    if phase_before in ('REST', 'SEATED_READY') and phase_after in ('RAISING', 'RISING'):
        events.append(('outbound_start_s', seq, stamp))
    if phase_before in ('RAISING', 'PEAK_OR_HOLD', 'STANDING_REACHED') and phase_after == 'LOWERING':
        events.append(('return_start_s', seq, stamp))
    for rep in after['repetitions'][len(before['repetitions']):]:
        if rep['completion_status'] == 'COMPLETE':
            if rep['end_time_s'] != stamp:
                raise ValueError('complete_event_must_have_current_observed_pts')
            events.append(('end_s', seq, stamp))
    return events


def event_inventory():
    # [] means this implemented event emitted none; None means not exported.
    return {key: [] if key in SUPPORTED else None for key in BOUNDARIES}


def append_events(inventory, transitions):
    for key, seq, stamp in transitions:
        if key not in SUPPORTED or type(seq) is not int or not math.isfinite(stamp) or stamp < 0:
            raise ValueError('observed_confirmation_event_required')
        entries = inventory[key]
        if len(entries) >= 500 or (entries and stamp <= entries[-1]['time_s']):
            raise ValueError('bounded_chronological_confirmation_events_required')
        entries.append(dict(event_id=f'{key}-{seq}', time_s=stamp, evidence_kind='filtered'))


def missing_row(source, side):
    return {**{key: source[key] for key in ('sample_id', 'video_sha256', 'exercise_id',
                                           'protocol_version', 'split', 'time_basis')},
            'side': side, 'status': 'unavailable', 'completed_count': None,
            'boundary_events': dict.fromkeys(BOUNDARIES)}


def source_fingerprints():
    core = ROOT/'rehab_codex_single_camera_v2_1/app'
    files = [Path(__file__), ROOT/'tools/rehab_ml/cli.py', ROOT/'tools/rehab_ml/mobiphysio_pose.py',
             ROOT/'tools/rehab_ml/mobiphysio_rgb.py', ROOT/'tools/rehab_ml/professional_annotations.py',
             ROOT/'tools/rehab_ml/common.py']
    files += list((core/'rehab_v2').glob('*.py'))
    files += [core/name for name in ('quality.py', 'geometry.py', 'domain.py', 'landmark_schemas.py',
                                     'movement_timing.py', 'vision.py', 'exercises.py')]
    files += [ROOT/'mobile_rehab/rehab_v2'/name for name in
              ('pose_worker.py', 'owned_worker.py', 'host_lifetime.py')]
    return {str(path.relative_to(ROOT)): file_hash(path) for path in sorted(set(files))}


def replay_video(source, output, runtime, worker, config, model_hash):
    import av
    import cv2
    from app.domain import clean_json
    from app.rehab_v2.evidence import EvidenceAdapter
    from mobile_rehab.rehab_v2.pose_worker import JPEG_CAPACITY
    engine = runtime.engine
    adapter = EvidenceAdapter(source['exercise_id'], config['analyzed_side'],
                              max_gap_s=engine.plan['max_gap_s'])
    events, decoded, sampled, observable = event_inventory(), 0, 0, 0
    next_sample, last_pts = None, None
    trace = output/(source['sample_id']+'-trace.jsonl')
    with av.open(source['video_ref']) as container, trace.open('x', encoding='utf-8') as stream:
        if len(container.streams.video) != 1:
            raise ValueError('single_original_video_stream_required')
        video = container.streams.video[0]
        stamps, discarded, origin = container_timeline(source['video_ref'], video.frames)
        if (not 32 <= video.width <= 4096 or not 32 <= video.height <= 4096
                or stamps[-1] > 180 or stamps[0] < 0):
            raise ValueError('original_video_outside_declared_resource_or_clock_contract')
        for frame in container.decode(video):
            decoded += 1
            if frame.pts is None or frame.time_base is None or frame.is_corrupt or decoded > len(stamps):
                raise ValueError('invalid_or_extra_decoded_frame')
            pts = float(frame.pts*frame.time_base)-origin
            if abs(pts-stamps[decoded-1]) > PTS_TOLERANCE_S or (last_pts is not None and pts <= last_pts):
                raise ValueError('decoded_pts_disagrees_with_original_presentation_inventory')
            last_pts = pts
            if next_sample is not None and pts+1e-9 < next_sample:
                continue
            next_sample = pts+config['sampling_period_s']
            image = frame.to_ndarray(format='bgr24')
            height, width = image.shape[:2]
            factor = min(1., LONG_EDGE/max(width, height))
            resized = cv2.resize(image, (max(1, round(width*factor)), max(1, round(height*factor)))) if factor < 1 else image
            ih, iw = resized.shape[:2]
            ok, jpeg = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok or jpeg.size > JPEG_CAPACITY:
                raise ValueError('original_worker_jpeg_capacity')
            started = time.perf_counter()
            pose, stages = worker.infer(dict(sid=source['sample_id'], seq=decoded,
                source_time_s=pts, encoded=jpeg.tobytes()), runtime)
            if (pose.size != (iw, ih) or pose.model_manifest_id != model_hash
                    or pose.schema_id != 'coco17-v1' or pose.coordinate_space != 'raw_image_pixels'
                    or pose.keypoint_order_version != 'coco17-anatomical-lr-v1'
                    or pose.seq != decoded or pose.time_s != pts or pose.context != runtime.context):
                raise ValueError('original_pose_response_contract_changed')
            sx, sy = iw/width, ih/height
            # Preserve all original people/bboxes/tracker output; no pseudo box or identity.
            people = [replace(person, xy=[[x/sx, y/sy] for x, y in person.xy],
                bbox=[person.bbox[0]/sx, person.bbox[1]/sy, person.bbox[2]/sx, person.bbox[3]/sy])
                for person in pose.people]
            source_pose = replace(pose, people=people, size=(width, height))
            # Unchanged adapter accepts mapped_source_seconds. The mapping here is
            # identity from explicit stream-relative PTS, not a receive clock/FPS.
            evidence = adapter.analyze(source_pose, processing_age_ms=0., time_basis='mapped_source_seconds')
            before = dict(phase=engine.phase, repetitions=list(engine.repetitions))
            if not engine.process(evidence):
                raise ValueError('unchanged_protocol_rejected_actual_source_frame')
            after = dict(phase=engine.phase, repetitions=list(engine.repetitions))
            transitions = transition_events(before, after, decoded, pts)
            append_events(events, transitions)
            observable += engine.observation_state in ('observable', 'partially_observable')
            sampled += 1
            stream.write(__import__('json').dumps(clean_json(dict(seq=decoded, time_s=pts,
                decoded_bgr_sha256=hashlib.sha256(image.tobytes()).hexdigest(),
                jpeg_sha256=hashlib.sha256(jpeg.tobytes()).hexdigest(), inference_size=[iw, ih],
                scale_xy=[sx, sy], pose=asdict(source_pose), metrics=asdict(evidence),
                phase_before=before['phase'], phase_after=after['phase'], completed=engine.completed,
                emitted_events=transitions, roundtrip_ms=(time.perf_counter()-started)*1000,
                stages_ms=stages)), ensure_ascii=False, allow_nan=False)+'\n')
        if decoded != len(stamps) or sampled < 3:
            raise ValueError('incomplete_original_decode_or_insufficient_samples')
    engine.finish('offline_original_video_ended')
    result_path = output/(source['sample_id']+'-result.json')
    write_json(result_path, clean_json(engine.summary()))
    row = missing_row(dict(source, time_basis='stream_relative_media_pts'), config['analyzed_side'])
    row.update(status='completed', completed_count=engine.completed, boundary_events=events)
    proof = dict(sample_id=source['sample_id'], decoded_presentable_frames=decoded,
        discarded_packets=discarded, sampled_frames=sampled, observable_frames=observable,
        source_origin_s=origin, trace=str(trace), trace_sha256=file_hash(trace),
        result=str(result_path), result_sha256=file_hash(result_path), completed_count=engine.completed)
    return row, proof


def replay(receipt_path, output_dir, *, split, side):
    if split not in ('val', 'test') or side not in ('left', 'right'):
        raise ValueError('explicit_split_and_analyzed_side_required')
    sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
    from app.domain import Context
    from app.rehab_v2.engine import ProtocolEngine
    from mobile_rehab.rehab_v2.pose_worker import IsolatedPoseWorker, offline_pose_process
    proof, all_sources = _source_samples(receipt_path)
    sources = [dict(row, time_basis='stream_relative_media_pts') for row in all_sources if row['split'] == split]
    if not sources:
        raise ValueError('empty_fixed_split')
    weights = ROOT/'rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt'
    model_hash = file_hash(weights)
    from .professional_annotations import _read
    contract = _read(weights.with_name('manifest.json'))
    if contract.get('sha256') != model_hash or contract.get('schema_id') != 'coco17-v1':
        raise ValueError('original_model_contract_changed')
    implementation = source_fingerprints()
    plan = ProtocolEngine(dict(exercise_id='shoulder_abduction', side=side), source_epoch='config-only').plan
    config = dict(schema_version=VERSION, split=split, analyzed_side=side, affected_side=None,
        side_selected_before_inference=True, sampling_period_s=PERIOD_S,
        preprocessing=dict(long_edge=LONG_EDGE, jpeg_quality=90, upscale=False, flip=False, crop=False),
        plan=plan, public_time_basis='stream_relative_media_pts', engine_time_basis='mapped_source_seconds',
        clock_mapping='identity_from_explicit_stream_relative_pts', offline_processing_age_ms=0.,
        live_latency_claim=False, supported_boundaries=list(SUPPORTED),
        event_definition='current_filtered_evidence_protocol_confirmation_not_physical_motion_onset',
        unavailable_boundaries=[key for key in BOUNDARIES if key not in SUPPORTED],
        clinical_accuracy=None, product_enabled=False, training_performed=False)
    output = _new_output(output_dir)
    write_json(output/'config.json', config)  # frozen before first media decode
    rows = [missing_row(row, side) for row in sources]
    summary = dict(schema_version=VERSION, status='running', started_at=utc_now(),
        source_proof=proof, implementation=implementation, config_sha256=canonical_hash(config),
        model_sha256=model_hash, samples=[], complete_requested_cohort=len(sources),
        reference_used_for_predictions=False, human_forms_read=False, therapist_scores_used=False,
        clinical_accuracy=None, affected_side=None, product_enabled=False, training_performed=False)
    worker = IsolatedPoseWorker(target=offline_pose_process)
    summary['worker_contract'] = worker.contract
    try:
        for index, source in enumerate(sources):
            context = Context(index+1, 'rehab', source['video_sha256'], 'REPLAY_FILE', 'RESEARCH', output.name)
            runtime = SimpleNamespace(context=context, engine=ProtocolEngine(plan, source_epoch=context.epoch,
                                                                            session_id=source['sample_id']))
            try:
                row, details = replay_video(source, output, runtime, worker, config, model_hash)
                rows[index] = row
            except Exception as exc:
                rows[index]['status'] = 'failed'  # never retain a partial count as completed
                details = dict(sample_id=source['sample_id'], status='failed',
                               error_type=type(exc).__name__, error=str(exc))
                partial = output/(source['sample_id']+'-trace.jsonl')
                if partial.exists():
                    details.update(partial_trace=str(partial), partial_trace_sha256=file_hash(partial))
            summary['samples'].append(details)
            write_json(output/'summary.json', summary)
            print(f"Original temporal replay {index+1}/{len(sources)}: {rows[index]['status']}", flush=True)
    finally:
        worker.close()
        summary['owned_release'] = worker.last_release
    # Reverify original source bytes/splits and exact implementation before publication.
    checked_proof, checked_sources = _source_samples(receipt_path)
    unchanged = (checked_proof == proof and checked_sources == all_sources
                 and source_fingerprints() == implementation and file_hash(weights) == model_hash
                 and _read(output/'config.json') == config)
    summary.update(implementation_and_sources_unchanged=unchanged,
        status='completed' if unchanged and worker.last_release.get('confirmed') is True
               and all(row['status'] == 'completed' for row in rows) else 'failed', completed_at=utc_now())
    manifest = dict(schema_version=PREDICTION_SCHEMA, origin='declared_backend_export',
        reference_used_for_predictions=False, implementation_sha256=canonical_hash(implementation),
        model_sha256=model_hash, config_sha256=canonical_hash(config), samples=rows)
    if not unchanged or worker.last_release.get('confirmed') is not True:
        # Invalid execution-level provenance invalidates the entire export.
        manifest['samples'] = [dict(missing_row(source, side), status='failed') for source in sources]
    write_json(output/'predictions.json', manifest)
    summary.update(predictions=str(output/'predictions.json'), predictions_sha256=file_hash(output/'predictions.json'))
    write_json(output/'summary.json', summary)
    return dict(status=summary['status'], artifact=str(output/'summary.json'), summary_sha256=file_hash(output/'summary.json'),
        predictions=summary['predictions'], predictions_sha256=summary['predictions_sha256'],
        cohort_videos=len(rows), completed_videos=sum(row['status'] == 'completed' for row in manifest['samples']),
        actual_professional_labels=0, clinical_accuracy=None, product_enabled=False)
