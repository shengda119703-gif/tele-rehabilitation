"""Fixed counterfactual sampling of authorized pose caches, not accuracy/training.

Each profile starts a fresh original causal filter and protocol. Cached filtered
metrics are deliberately ignored. No camera, model inference, SQL or UI is used.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import json
import math
from pathlib import Path
from statistics import median
import sys
from uuid import uuid4

from .common import ROOT, canonical_hash, file_hash, paths, write_json
from .pose_dataset import _json, _sha

VERSION = 'rehab-sampling-sensitivity-1'
MAX_FRAMES = 15000
MAX_CACHE_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = 256 * 1024
SOURCES = (
    'tools/rehab_ml/sampling_audit.py',
    'rehab_codex_single_camera_v2_1/app/domain.py',
    'rehab_codex_single_camera_v2_1/app/quality.py',
    'rehab_codex_single_camera_v2_1/app/geometry.py',
    'rehab_codex_single_camera_v2_1/app/landmark_schemas.py',
    'rehab_codex_single_camera_v2_1/app/exercises.py',
    'rehab_codex_single_camera_v2_1/app/rehab_v2/protocols.py',
    'rehab_codex_single_camera_v2_1/app/rehab_v2/engine.py',
    'rehab_codex_single_camera_v2_1/app/rehab_v2/evidence.py',
    'rehab_codex_single_camera_v2_1/app/rehab_v2/timing.py',
    'rehab_codex_single_camera_v2_1/app/rehab_v2/timing_comparison.py',
    'rehab_codex_single_camera_v2_1/app/movement_timing.py',
)


@dataclass(frozen=True)
class Profile:
    name: str
    stride: int = 1
    clock_offset_s: float = 0.
    jitter_s: float = 0.
    loss: str | None = None


# Predeclared before reading target clips; no search for a favorable cadence.
PROFILES = (
    Profile('reference'), Profile('sample_every_2', stride=2),
    Profile('sample_every_3', stride=3), Profile('sample_every_6', stride=6),
    Profile('clock_origin_plus_1000s', clock_offset_s=1000.),
    Profile('counterfactual_clock_jitter_12ms', jitter_s=.012),
    Profile('known_loss_every_20th', loss='periodic'),
    Profile('known_loss_middle_10pct', loss='middle'),
    Profile('known_loss_final_frame', loss='final'),
)


def _finite(value, low=-math.inf, high=math.inf):
    try:
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high
    except (OverflowError, ValueError):
        return False


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate_pose_cache_key')
        value[key] = item
    return value


def _constant(_):
    raise ValueError('nonfinite_pose_cache_json')


def load_cache(result_path):
    """Only explicit analysis-only original YOLO extraction, in the ignored root."""
    path = Path(result_path).resolve()
    run_root = paths()['run']
    if not path.is_relative_to(run_root) or path.name != 'result.json':
        raise ValueError('explicit_result_under_ignored_run_root_required')
    path, result, result_hash = _json(path)
    if (result.get('kind') != 'private_target_domain_backend_replay'
            or result.get('analysis_authorization') != 'explicit_local_cli_analysis'
            or result.get('training_authorized') is not False
            or result.get('professional_labels_available') is not False
            or not _sha(result.get('video_sha256'))
            or not _sha(result.get('model_manifest_id'))
            or result.get('exercise_id') not in ('shoulder_abduction', 'sit_to_stand', 'rehab_squat')
            or result.get('side') not in ('left', 'right')
            or not isinstance(result.get('input_timing'), dict)
            or result['input_timing'].get('basis') != 'opencv_media_pts'
            or type(result.get('frames')) is not int or not 3 <= result['frames'] <= MAX_FRAMES):
        raise ValueError('authorized_analysis_only_monotonic_media_cache_required')
    cache = (path.parent / 'pose-frames.jsonl').resolve()
    if (not cache.is_relative_to(path.parent) or not cache.is_file()
            or not 0 < cache.stat().st_size <= MAX_CACHE_BYTES
            or not _sha(result.get('pose_file_sha256'))
            or file_hash(cache) != result['pose_file_sha256']):
        raise ValueError('bounded_unchanged_pose_cache_required')
    rows, previous_seq, previous_time, size = [], -1, -1., None
    with cache.open('rb') as stream:
        while line := stream.readline(MAX_LINE_BYTES + 1):
            if len(line) > MAX_LINE_BYTES or not line.endswith(b'\n') or len(rows) >= MAX_FRAMES:
                raise ValueError('bounded_complete_pose_cache_line_required')
            row = json.loads(line, parse_constant=_constant, object_pairs_hook=_pairs)
            if not isinstance(row, dict):
                raise ValueError('pose_cache_frame_object_required')
            seq, stamp, dimensions = row.get('seq'), row.get('time_s'), row.get('size')
            if (type(seq) is not int or seq <= previous_seq
                    or not _finite(stamp, 0., 120.) or stamp <= previous_time
                    or not isinstance(dimensions, list) or len(dimensions) != 2
                    or any(type(v) is not int or not 1 <= v <= 4096 for v in dimensions)
                    or size is not None and size != dimensions
                    or row.get('schema_id') != 'coco17-v1'
                    or row.get('coordinate_space') != 'raw_image_pixels'
                    or row.get('model_manifest_id') != result['model_manifest_id']
                    or not _sha(row.get('decoded_bgr_sha256'))):
                raise ValueError('ordered_original_coco17_geometry_and_identity_required')
            people = row.get('people')
            if not isinstance(people, list) or len(people) > 32:
                raise ValueError('bounded_pose_candidates_required')
            for person in people:
                if (not isinstance(person, dict)
                        or person.get('track_key') is not None and (
                            not isinstance(person['track_key'], str) or len(person['track_key']) > 128)
                        or not isinstance(person.get('bbox'), list) or len(person['bbox']) != 4
                        or not all(_finite(v, -8192., 8192.) for v in person['bbox'])
                        or not isinstance(person.get('xy'), list) or len(person['xy']) != 17
                        or any(not isinstance(point, list) or len(point) != 2
                               or any(v is not None and not _finite(v, -8192., 8192.) for v in point)
                               for point in person['xy'])
                        or not isinstance(person.get('conf'), list) or len(person['conf']) != 17
                        or any(v is not None and not _finite(v, 0., 1.) for v in person['conf'])):
                    raise ValueError('bounded_original_pose_candidate_shape_required')
            rows.append(row)
            previous_seq, previous_time, size = seq, stamp, dimensions
    if len(rows) != result['frames']:
        raise ValueError('declared_pose_cache_frame_count_mismatch')
    if file_hash(cache) != result['pose_file_sha256'] or file_hash(path) != result_hash:
        raise ValueError('pose_cache_changed_during_read')
    return rows, result, dict(result_path=path, result_sha256=result_hash,
                            cache_path=cache, cache_sha256=result['pose_file_sha256'])


def select(profile, index, count):
    if profile not in PROFILES or type(index) is not int or not 0 <= index < count:
        raise ValueError('predeclared_profile_and_frame_index_required')
    if index % profile.stride:
        return False
    if profile.loss == 'periodic':
        return index % 20 != 19
    if profile.loss == 'middle':
        return not math.floor(.45 * count) <= index < math.ceil(.55 * count)
    if profile.loss == 'final':
        return index != count - 1
    return True


def transformed_time(profile, row, index):
    # Depends on this frame and index only. Never interpolates with a future pose.
    return row['time_s'] + profile.clock_offset_s + profile.jitter_s * (0., .5, 1., .5, 0.)[index % 5]


def replay(rows, exercise, side, profile, *, target_angle_deg=None):
    """Fresh raw-keypoint filter; no resampling of a previously filtered trace."""
    sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
    from app.domain import Context, PoseFrame, PosePerson
    from app.rehab_v2.engine import ProtocolEngine
    from app.rehab_v2.evidence import EvidenceAdapter
    if not rows or profile not in PROFILES:
        raise ValueError('nonempty_cache_and_predeclared_profile_required')
    context = Context(1, 'rehab', 'authorized-cache-replay', 'REPLAY_FILE', 'TEST', 'sampling-audit', 'sampling-epoch')
    engine = ProtocolEngine(dict(exercise_id=exercise, side=side, target_angle_deg=target_angle_deg),
                            source_epoch=context.epoch, session_id='sampling-audit')
    adapter = EvidenceAdapter(exercise, side)
    trace, phases, reasons = [], [], Counter()
    kept, lost, previous_time, last_phase, first_ready = 0, 0, None, None, None
    max_hold_s, missing_started, longest_missing_s = None, None, 0.
    for index, row in enumerate(rows):
        stamp = transformed_time(profile, row, index)
        if not _finite(stamp) or previous_time is not None and stamp <= previous_time:
            raise ValueError('counterfactual_clock_is_not_monotonic')
        previous_time = stamp
        if not select(profile, index, len(rows)):
            lost += 1
            if profile.loss:
                engine.note_input_gap(row['seq'], stamp, 'sampling_audit_known_frame_loss')
                if missing_started is None:
                    missing_started = stamp
            continue
        kept += 1
        people = [PosePerson(person['track_key'], deepcopy(person['bbox']),
                             deepcopy(person['xy']), deepcopy(person['conf'])) for person in row['people']]
        pose = PoseFrame(context, row['seq'], stamp, tuple(row['size']), people,
                         model_manifest_id=row['model_manifest_id'])
        evidence = adapter.analyze(pose, processing_age_ms=0., time_basis='opencv_media_pts')
        engine.process(evidence)
        valid = engine.observation_state in ('observable', 'partially_observable')
        metric = evidence.metrics[engine.spec['metric']]
        trace.append(dict(seq=row['seq'], original_time_s=row['time_s'], processed_time_s=stamp,
                          valid=valid, value=metric.value if valid else None, phase=engine.phase))
        if valid:
            if missing_started is not None:
                longest_missing_s = max(longest_missing_s, stamp - missing_started)
                missing_started = None
        else:
            reasons[metric.reason or 'missing_primary_metric'] += 1
            if missing_started is None:
                missing_started = stamp
        if engine.baseline is not None and first_ready is None:
            first_ready = stamp
        live = engine.timing_live()
        if live is not None and _finite(live['hold_elapsed_s'], 0.):
            max_hold_s = max(max_hold_s or 0., live['hold_elapsed_s'])
        if engine.phase != last_phase:
            phases.append(dict(seq=row['seq'], time_s=stamp, phase=engine.phase))
            last_phase = engine.phase
    if missing_started is not None:
        longest_missing_s = max(longest_missing_s, previous_time - missing_started)
    engine.finish('user_stopped')
    summary = deepcopy(engine.summary())
    complete = [r for r in summary['repetitions'] if r['completion_status'] == 'COMPLETE']
    timing = {}
    for name in ('outbound_s', 'endpoint_dwell_s', 'return_s', 'target_hold_s'):
        valid_values, excluded = [], Counter()
        for rep in complete:
            recorded, metric = rep['movement_timing'], rep['movement_timing'][name]
            if name == 'target_hold_s' and (recorded['partial_observation'] or not recorded['cycle_complete']):
                excluded['partial_hold_is_observed_lower_bound'] += 1
            elif metric['valid']:
                valid_values.append(metric['value'])
            else:
                excluded[metric['reason'] or 'invalid_time_metric'] += 1
        timing[name] = dict(complete_denominator=len(complete), valid_complete=len(valid_values),
                            excluded_complete_reasons=dict(excluded),
                            median_s=median(valid_values) if valid_values else None)
    primary_valid = sum(item['valid'] for item in trace)
    value = dict(profile=profile.name, retained_frames=kept, discarded_frames=lost,
                 original_frames=len(rows), valid_primary_frames=primary_valid,
                 retained_frame_coverage=primary_valid / kept if kept else None,
                 original_frame_retention_coverage=primary_valid / len(rows),
                 longest_explicit_missing_span_s=longest_missing_s,
                 baseline_observed=summary['baseline'] is not None,
                 first_ready_relative_s=first_ready-transformed_time(profile, rows[0], 0) if first_ready is not None else None,
                 completed=summary['completed'], attempted=len(summary['repetitions']),
                 partial_or_unassessable=sum(r['completion_status'] != 'COMPLETE' for r in summary['repetitions']),
                 invalid_primary_reasons=dict(reasons), diagnostics=summary['diagnostics'],
                 phase_transition_count=len(phases), timing=timing,
                 max_observed_live_target_hold_s=max_hold_s,
                 counterfactual_clock=bool(profile.jitter_s or profile.clock_offset_s),
                 declared_known_loss=profile.loss is not None,
                 sampling_semantics='known_missing_input' if profile.loss else 'intentional_analysis_cadence',
                 trace=trace, phases=phases, summary=summary)
    return value


def comparison(reference, candidate):
    """Same retained source-seq disagreement, not independent reference error."""
    ref = {item['seq']: item for item in reference['trace']}
    values = [abs(item['value'] - ref[item['seq']]['value']) for item in candidate['trace']
              if item['valid'] and ref[item['seq']]['valid']]
    values.sort()
    shared = len(values)
    return dict(reference_profile=reference['profile'], completed_delta=candidate['completed']-reference['completed'],
                baseline_observed_changed=candidate['baseline_observed'] != reference['baseline_observed'],
                shared_valid_source_frames=shared,
                metric_absolute_disagreement_deg=dict(mean=sum(values)/shared if shared else None,
                    p95=values[max(0, math.ceil(.95*shared)-1)] if shared else None,
                    maximum=values[-1] if shared else None),
                interpretation='same_model_sampling_disagreement_not_gold_standard_error',
                clinical_accuracy=None, count_accuracy=None, timing_accuracy=None)


def run_audit(result_paths, *, publish=False):
    result_paths = list(result_paths)
    if not 1 <= len(result_paths) <= 10:
        raise ValueError('one_to_ten_explicit_analysis_results_required')
    inputs = [load_cache(p) for p in result_paths]
    hashes = {p: file_hash(ROOT/p) for p in SOURCES}
    root = paths()['run']/('sampling-audit-'+uuid4().hex[:8])
    root.mkdir()
    report = dict(version=VERSION, run_id=root.name, implementation_sha256=hashes,
                  profiles=[p.__dict__ for p in PROFILES], results=[],
                  primary_time_basis='opencv_media_pts', source_pixels_redecoded=False,
                  original_models_changed=False, training_performed=False, training_authorized=False,
                  private_RGB_and_keypoints_published=False, independent_reference_available=False,
                  clinical_accuracy=None, count_accuracy=None, timing_accuracy=None,
                  population_sampling_invariance_validated=False, network_or_phone_tested=False,
                  cached_filtered_metrics_used=False, protocol_parameters_tuned=False)
    for rows, metadata, identity in inputs:
        results = [replay(rows, metadata['exercise_id'], metadata['side'], profile) for profile in PROFILES]
        reference = results[0]
        public_rows = []
        for value in results:
            public = {k: v for k, v in value.items() if k not in ('trace', 'phases', 'summary')}
            public['comparison'] = comparison(reference, value)
            public_rows.append(public)
        item = dict(video_sha256=metadata['video_sha256'], model_manifest_id=metadata['model_manifest_id'],
                    result_file_sha256=identity['result_sha256'], pose_file_sha256=identity['cache_sha256'],
                    exercise_id=metadata['exercise_id'], side=metadata['side'],
                    original_frames=len(rows), input_timing=metadata['input_timing'],
                    original_duration_s=rows[-1]['time_s']-rows[0]['time_s'],
                    original_interval_s=dict(minimum=min(b['time_s']-a['time_s'] for a,b in zip(rows, rows[1:])),
                        median=median(b['time_s']-a['time_s'] for a,b in zip(rows, rows[1:])),
                        maximum=max(b['time_s']-a['time_s'] for a,b in zip(rows, rows[1:]))),
                    historical_extraction_completed=metadata['v2_summary']['completed'],
                    historical_extraction_observable=metadata['observable_frames'],
                    current_reference_matches_historical_count=reference['completed']==metadata['v2_summary']['completed'],
                    current_reference_matches_historical_coverage=reference['valid_primary_frames']==metadata['observable_frames'],
                    explicit_target_not_supplied=True, profiles=public_rows)
        # Full per-frame/private evidence stays inside the newly owned ignored run.
        detail_path = root/(metadata['video_sha256'][:12]+'-details.json')
        if detail_path.exists():
            raise ValueError('duplicate_video_result_in_audit')
        write_json(detail_path, dict(input_result=str(identity['result_path']), results=results))
        item['private_detail_sha256'] = file_hash(detail_path)
        report['results'].append(item)
    report['inputs_unchanged'] = all(file_hash(i['result_path'])==i['result_sha256']
        and file_hash(i['cache_path'])==i['cache_sha256'] for _,_,i in inputs)
    report['implementation_unchanged'] = hashes=={p:file_hash(ROOT/p) for p in SOURCES}
    if not report['inputs_unchanged'] or not report['implementation_unchanged']:
        raise ValueError('audit_input_or_implementation_changed')
    report['profile_contract_sha256'] = canonical_hash(report['profiles'])
    write_json(root/'summary.json', report)
    if publish:
        write_json(ROOT/'reports/rehab_backend/sampling_sensitivity.json', report)
    return dict(run_id=root.name, summary=str(root/'summary.json'), summary_sha256=file_hash(root/'summary.json'),
                videos=len(inputs), profile_runs=len(inputs)*len(PROFILES),
                clinical_accuracy=None, training_performed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', action='append', required=True, type=Path)
    parser.add_argument('--publish', action='store_true', help='Publish aggregate statistics, never private trace/keypoints')
    args = parser.parse_args()
    print(json.dumps(run_audit(args.result, publish=args.publish), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
