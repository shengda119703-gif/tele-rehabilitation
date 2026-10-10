from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

from .common import ROOT, file_hash, paths, write_json


def extract_pose(video, exercise, side):
    """Authorized local analysis only; not an implicit training consent grant."""
    sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
    from app.camera_manager import CameraManager
    from app.domain import Context, clean_json
    from app.vision import VisionWorker
    from app.quality import PoseAnalyzer
    from app.rehab import RehabEngine
    from app.settings import default_plan
    from app.rehab_v2.evidence import EvidenceAdapter
    from app.rehab_v2.engine import ProtocolEngine
    from mobile_rehab.replay_status import replay_ended
    source = Path(video).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    source_hash = file_hash(source)
    output = paths()['run'] / ('target-replay-'+source_hash[:12]+'-'+uuid4().hex[:8])
    output.mkdir()
    # SourceWorker deliberately pauses a preview after one frame. An offline
    # analysis needs an explicit run identity, not a preview context.
    context = Context(1, 'rehab', source_hash, 'REPLAY_FILE', 'TEST', output.name)
    camera, vision = CameraManager(), VisionWorker(start_thread=False)
    adapter = EvidenceAdapter(exercise, side)
    engine = ProtocolEngine(dict(exercise_id=exercise, side=side), source_epoch=context.epoch)
    legacy = None if exercise == 'rehab_squat' else RehabEngine(dict(default_plan(exercise), side=side))
    analyzer = PoseAnalyzer(side=side, exercise_id=exercise if legacy else None)
    timing = dict(basis='opencv_media_pts', skipped_leading_frames=0)
    last_seen, frames, observable = time.monotonic(), 0, 0
    latencies = []
    started = time.perf_counter()
    try:
        camera.open_replay(source, context, dict(speed=1000))
        with (output / 'pose-frames.jsonl').open('w', encoding='utf-8') as stream:
            while True:
                if replay_ended(camera.worker.read_status(), timing):
                    break
                packet = camera.worker.read_latest()
                if packet is None:
                    if time.monotonic()-last_seen > 30:
                        raise TimeoutError('Replay decoder stalled')
                    time.sleep(.005)
                    continue
                last_seen = time.monotonic()
                if packet.time_s > 120 or frames >= 15000 or max(packet.image.shape[:2]) > 4096:
                    raise ValueError('Replay resource limit exceeded')
                tick = time.perf_counter()
                pose = vision.infer(packet, backend='yolo', side=side)
                evidence = adapter.analyze(pose, processing_age_ms=0., time_basis='opencv_media_pts')
                engine.process(evidence)
                if legacy:
                    legacy.process(analyzer.analyze(pose))
                observable += engine.observation_state in ('observable', 'partially_observable')
                frames += 1
                latencies.append(1000*(time.perf_counter()-tick))
                stream.write(json.dumps(clean_json(dict(seq=pose.seq, time_s=pose.time_s,
                     schema_id=pose.schema_id, coordinate_space=pose.coordinate_space,
                     model_manifest_id=pose.model_manifest_id, size=pose.size,
                     people=pose.people, metrics=evidence.metrics)), ensure_ascii=False, allow_nan=False)+'\n')
                camera.worker.acknowledge(packet.seq)
        if frames < 3:
            raise ValueError('No usable decoded frames')
        engine.finish('user_stopped')
        if legacy:
            legacy.finish('user_stop')
        import numpy as np
        result = dict(kind='private_target_domain_backend_replay', video_sha256=source_hash,
                      exercise_id=exercise, side=side, frames=frames, observable_frames=observable,
                      observed_fraction=observable/frames, input_timing=timing,
                      elapsed_s=time.perf_counter()-started,
                      model_manifest_id=pose.model_manifest_id,
                      latency_ms=dict(p50=float(np.quantile(latencies, .5)), p95=float(np.quantile(latencies, .95))),
                      legacy_summary=legacy.summary() if legacy else None, v2_summary=engine.summary(),
                      pose_file_sha256=file_hash(output / 'pose-frames.jsonl'),
                      analysis_authorization='explicit_local_cli_analysis', training_authorized=False,
                      professional_labels_available=False, clinical_accuracy=None,
                      count_accuracy=None, target_domain_quality_accuracy=None,
                      time_limit_notes='Media PTS and decoder skip evidence retained; no exposure/clinical timing guarantee')
        write_json(output / 'result.json', clean_json(result))
        return dict(path=str(output / 'result.json'), video_sha256=source_hash, frames=frames,
                    v2_completed=engine.completed, legacy_completed=legacy.completed if legacy else None,
                    observable_frames=observable, elapsed_s=result['elapsed_s'], training_authorized=False)
    except Exception as exc:
        write_json(output / 'failure.json', dict(status='failed', error_type=type(exc).__name__,
            error=str(exc), decoded_frames=frames, video_sha256=source_hash,
            training_authorized=False))
        raise
    finally:
        try:
            camera.stop()
        finally:
            vision.close()


def label_template():
    return dict(schema_version='rehab-professional-label-1', sample_id=None, subject_group=None,
                exercise_id=None, side=None, view=None, protocol_version=None,
                raw_video_ref=None, raw_video_sha256=None, keypoints_ref=None, time_basis=None,
                permissions=dict(analysis=False, training=False, redistribution=False, license=None,
                                 consent_document_ref=None, consent_verified_by=None),
                boundaries=dict(preparation_confirmed_s=None, outbound_start_s=None,
                                endpoint_start_s=None, endpoint_end_s=None, return_start_s=None, end_s=None),
                physical_completion=None, observable_completion=None,
                quality_problems=[dict(problem_id=None, state='unknown', assessable=False,
                                       start_s=None, end_s=None, acceptable_variation_conditions=None)],
                cue_opportunities=[dict(start_s=None, end_s=None, category=None, priority=None,
                                        actually_received=None, later_improved=None)],
                annotations=dict(annotator=None, reviewer=None, annotation_version=None,
                                 independently_reviewed=False, disagreements=None, final_resolution=None),
                label_masks=dict(physical_completion=False, observable_completion=False,
                                 phase=False, error=False, cue_timing=False),
                note='Null/unknown is unannotated, never a negative label. No causal intervention claim without recorded intervention.')


def supervision_status():
    from .common import load_registry
    return dict(status='blocked_missing_supervision',
                existing_licensed_dataset='IRDS whole-repetition Kinect quality labels',
                unavailable=['qualified_target_RGB_training_data', 'verified_2d_joint_and_visibility_labels',
                             'professionally_reviewed_phase_and_observability_labels'],
                dataset_status={key: value['license_status'] for key, value in load_registry().items()},
                training_allowed=False, model_activated=False,
                next_required='Verified dataset eligibility/access or consented independently annotated target video')
