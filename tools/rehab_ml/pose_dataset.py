"""Offline, consent-scoped RGB pose conversion and independent reference audit.

No inference is ground truth. Unknown joints retain masks; YOLO export refuses
partial annotation because the locked stock loss supervises missingness too.
Outputs live only in new dedicated ignored experiment directories, never SQL.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil

from .common import ROOT, canonical_hash, file_hash, paths, write_json

VERSION = 'rehab-rgb-pose-tools-1'
REFERENCE_VERSION = 'rehab-rgb-pose-reference-1'
PREDICTION_VERSION = 'rehab-rgb-pose-predictions-1'
JOINTS = ('nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear', 'left_shoulder',
          'right_shoulder', 'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist',
          'left_hip', 'right_hip', 'left_knee', 'right_knee', 'left_ankle', 'right_ankle')
FLIP = (0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15)
MAX_JSON_BYTES = 8*1024*1024
MAX_IMAGE_BYTES = 20*1024*1024
MAX_TOTAL_BYTES = 512*1024*1024
MAX_SAMPLES = 4000


def _fail(reason):
    raise ValueError(reason)


def _number(value, low=0., high=math.inf):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _identifier(value):
    return (isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) is not None
            and re.fullmatch(r'(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])', value) is None)


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _json(source):
    source = Path(source).resolve()
    if not source.is_file() or not 0 < source.stat().st_size <= MAX_JSON_BYTES:
        _fail('bounded_json_file_required')
    def constant(_):
        _fail('nonfinite_json_not_allowed')
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fail('duplicate_json_key')
            result[key] = value
        return result
    with source.open('rb') as stream:
        payload = stream.read(MAX_JSON_BYTES+1)
    if not 0 < len(payload) <= MAX_JSON_BYTES:
        _fail('bounded_json_file_required')
    value = json.loads(payload.decode('utf-8'), parse_constant=constant, object_pairs_hook=object_pairs)
    if not isinstance(value, dict):
        _fail('json_object_required')
    return source, value, hashlib.sha256(payload).hexdigest()


def _file(root, reference, expected_sha, maximum):
    if not isinstance(reference, str) or '\\' in reference or ':' in reference:
        _fail('relative_posix_evidence_path_required')
    parts = PurePosixPath(reference)
    if parts.is_absolute() or not parts.parts or any(p in ('.', '..') for p in parts.parts):
        _fail('evidence_path_escape')
    source = (root/reference).resolve()
    if not source.is_relative_to(root) or not source.is_file():
        _fail('evidence_file_missing_or_outside_reference_root')
    if not _sha(expected_sha) or not 0 < source.stat().st_size <= maximum:
        _fail('evidence_hash_or_size_invalid')
    if file_hash(source) != expected_sha:
        _fail('evidence_file_hash_mismatch')
    return source


def _contract(value):
    if (value.get('schema_id') != 'coco17-v1'
            or value.get('coordinate_space') != 'raw_image_pixels'
            or value.get('keypoint_order') != list(JOINTS)):
        _fail('explicit_coco17_anatomical_pixel_contract_required')


def load_reference(source, *, training=False):
    """Verify declared evidence and alignment; not a legal/clinical attestation."""
    from PIL import Image
    source, value, fingerprint = _json(source)
    if value.get('schema_version') != REFERENCE_VERSION:
        _fail('rgb_reference_version_mismatch')
    _contract(value)
    if not _identifier(value.get('dataset_id')) or value.get('usage_context') not in ('RESEARCH', 'TEST'):
        _fail('research_or_explicit_test_context_required')
    permissions = value.get('permissions') or {}
    if (not isinstance(permissions, dict) or permissions.get('analysis') is not True
            or (training and permissions.get('training') is not True)
            or not _identifier(permissions.get('verified_by'))):
        _fail('explicit_verified_analysis_or_training_permission_required')
    _file(source.parent, permissions.get('evidence_ref'), permissions.get('evidence_sha256'), MAX_JSON_BYTES)
    samples = value.get('samples')
    if not isinstance(samples, list) or not 1 <= len(samples) <= MAX_SAMPLES:
        _fail('bounded_nonempty_pose_samples_required')
    seen, groups, recordings, images, frames = set(), {}, {}, {}, set()
    recording_people, recording_times = {}, defaultdict(list)
    counts, total = Counter(), 0
    for row in samples:
        if not isinstance(row, dict):
            _fail('reference_sample_object_required')
        for key in ('sample_id', 'subject_group', 'recording_id'):
            if not _identifier(row.get(key)):
                _fail('pseudonymous_reference_identifiers_required')
        sid, split = row['sample_id'], row.get('split')
        if sid.casefold() in seen or split not in ('train', 'val', 'test'):
            _fail('duplicate_sample_or_invalid_split')
        seen.add(sid.casefold())
        for lookup, key in ((groups, row['subject_group']), (recordings, row['recording_id']),
                            (images, row.get('image_sha256'))):
            if key in lookup and lookup[key] != split:
                _fail('subject_recording_or_image_split_leakage')
            lookup[key] = split
        identity = (row['recording_id'], row.get('frame_seq'))
        if (type(row.get('frame_seq')) is not int or row['frame_seq'] < 0 or identity in frames
                or not _number(row.get('source_time_s'))
                or row.get('time_basis') not in ('media_pts', 'capture_monotonic', 'synthetic_test_time')):
            _fail('unique_aligned_frame_identity_and_time_required')
        frames.add(identity)
        if (row['recording_id'] in recording_people
                and recording_people[row['recording_id']] != row['subject_group']):
            _fail('recording_subject_identity_mismatch')
        recording_people[row['recording_id']] = row['subject_group']
        recording_times[row['recording_id']].append((row['frame_seq'], row['source_time_s']))
        if (row.get('exercise_id') not in ('shoulder_abduction', 'sit_to_stand', 'rehab_squat')
                or row.get('side') not in ('left', 'right') or row.get('view') not in ('front', 'side')):
            _fail('pilot_action_side_and_view_required')
        size = row.get('frame_size')
        if (not isinstance(size, list) or len(size) != 2
                or any(type(n) is not int or not 32 <= n <= 4096 for n in size)):
            _fail('bounded_original_frame_size_required')
        image = _file(source.parent, row.get('image_ref'), row.get('image_sha256'), MAX_IMAGE_BYTES)
        total += image.stat().st_size
        if total > MAX_TOTAL_BYTES:
            _fail('dataset_image_byte_budget_exceeded')
        with Image.open(image) as picture:
            if (picture.format not in ('JPEG', 'PNG') or picture.size != tuple(size)
                    or getattr(picture, 'n_frames', 1) != 1 or picture.getexif().get(274, 1) != 1):
                _fail('original_unrotated_single_rgb_frame_required')
        # PNG EXIF inspection can load/close its decoder. Verification needs a
        # fresh handle immediately after open, not that already-inspected one.
        with Image.open(image) as picture:
            picture.verify()
        box = row.get('bbox_xyxy_px')
        if (not isinstance(box, list) or len(box) != 4 or not all(_number(n) for n in box)
                or not 0 <= box[0] < box[2] <= size[0] or not 0 <= box[1] < box[3] <= size[1]):
            _fail('independent_full_person_bbox_required')
        annotation = row.get('annotations') or {}
        if not isinstance(annotation, dict):
            _fail('annotation_metadata_object_required')
        fixture = annotation.get('origin') == 'synthetic_fixture'
        if (annotation.get('origin') not in ('human', 'synthetic_fixture')
                or fixture and value['usage_context'] != 'TEST'
                or annotation.get('independently_reviewed') is not True
                or any(not _identifier(annotation.get(k)) for k in ('annotator', 'reviewer', 'version'))
                or annotation['annotator'] == annotation['reviewer']
                or row.get('bbox_origin') != ('fixture_box' if fixture else 'human_full_person_box')):
            _fail('independent_reviewed_annotation_and_bbox_origin_required')
        for key in ('xy', 'visibility', 'annotation_mask'):
            if not isinstance(row.get(key), list) or len(row[key]) != 17:
                _fail('all_coco17_slots_and_masks_required')
        for point, visible, mask in zip(row['xy'], row['visibility'], row['annotation_mask']):
            if type(mask) is not bool:
                _fail('boolean_independent_annotation_mask_required')
            if not mask:
                if point is not None or visible is not None:
                    _fail('unannotated_joint_must_remain_null')
            elif type(visible) is not int or visible not in (0, 1, 2):
                _fail('independent_integer_visibility_required_not_model_confidence')
            elif visible == 0:
                if point is not None:
                    _fail('explicit_not_locatable_joint_has_no_coordinate')
            elif (not isinstance(point, list) or len(point) != 2
                  or not _number(point[0], 0, size[0]) or not _number(point[1], 0, size[1])):
                _fail('annotated_pixel_coordinate_required')
        counts[split] += 1
    if set(counts) != {'train', 'val', 'test'}:
        _fail('nonempty_group_isolated_train_val_test_required')
    for times in recording_times.values():
        ordered = sorted(times)
        if any(current[1] <= previous[1] for previous, current in zip(ordered, ordered[1:])):
            _fail('recording_frame_time_must_increase_with_sequence')
    if file_hash(source) != fingerprint:
        _fail('reference_changed_during_validation')
    return source, value, fingerprint


def _new_output(output):
    output = Path(output).resolve()
    roots = paths()
    if not any(output != roots[k] and output.is_relative_to(roots[k]) for k in ('data', 'run')):
        _fail('new_output_must_be_inside_dedicated_ignored_data_or_run_root')
    output.mkdir(parents=True, exist_ok=False)
    return output


def convert(source, output, *, output_format='masked'):
    if output_format not in ('masked', 'yolo_pose'):
        _fail('unknown_pose_export_format')
    source, reference, fingerprint = load_reference(source, training=output_format == 'yolo_pose')
    if output_format == 'yolo_pose' and any(not all(row['annotation_mask']) for row in reference['samples']):
        _fail('partial_annotation_cannot_enter_stock_yolo_coordinate_and_objectness_loss')
    output = _new_output(output)
    rows = copy.deepcopy(reference['samples'])
    for row in rows:
        row['coordinate_loss_mask'] = [mask and v in (1, 2) for mask, v in
                                      zip(row['annotation_mask'], row['visibility'])]
        row['visibility_loss_mask'] = list(row['annotation_mask'])
        if output_format == 'yolo_pose':
            split, sid = row['split'], row['sample_id']
            image = (source.parent/row['image_ref']).resolve()
            target = output/'images'/split/(sid+image.suffix.lower())
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(image, target)
            if file_hash(target) != row['image_sha256']:
                _fail('copied_image_hash_mismatch')
            width, height = row['frame_size']
            x1, y1, x2, y2 = row['bbox_xyxy_px']
            label = [0, (x1+x2)/(2*width), (y1+y2)/(2*height), (x2-x1)/width, (y2-y1)/height]
            for point, visibility in zip(row['xy'], row['visibility']):
                label.extend([0, 0, 0] if visibility == 0 else [point[0]/width, point[1]/height, visibility])
            path = output/'labels'/split/(sid+'.txt')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(' '.join(str(n) for n in label)+'\n', encoding='utf-8')
    if output_format == 'yolo_pose':
        import yaml
        (output/'dataset.yaml').write_text(yaml.safe_dump(dict(path=str(output), train='images/train',
            val='images/val', test='images/test', kpt_shape=[17, 3], flip_idx=list(FLIP), names={0: 'person'}),
            sort_keys=False), encoding='utf-8')
    if file_hash(source) != fingerprint:
        _fail('reference_changed_during_conversion')
    result = dict(version=VERSION, output_format=output_format, reference_sha256=fingerprint,
                  reference=reference, converted_samples=rows, partial_annotation_preserved=True,
                  labels_format_ready=output_format == 'yolo_pose', fine_tuning_qualified=False,
                  no_training_or_product_activation=True, permission_document_content_not_legally_attested=True,
                  remaining=['baseline_error_and_coverage_evaluation', 'verified_experiment_training_eligibility'])
    path = write_json(output/'conversion.json', result)
    return dict(path=path, samples=len(rows), output_format=output_format,
                labels_format_ready=result['labels_format_ready'], fine_tuning_qualified=False,
                artifact_sha256=file_hash(path))


def _summary(rows):
    labeled = sum(row['coordinate_reference'] for row in rows)
    errors = [row['error_px'] for row in rows if row['error_px'] is not None]
    normalized = [row['normalized_error'] for row in rows if row['normalized_error'] is not None]
    successes = sum(row['pck_pass'] is True for row in rows)
    absent = sum(row['known_not_locatable'] for row in rows)
    return dict(slots=len(rows), unannotated=sum(row['unannotated'] for row in rows),
                coordinate_reference_count=labeled, covered_coordinate_count=len(errors),
                coordinate_coverage=len(errors)/labeled if labeled else None,
                mean_euclidean_error_px=sum(errors)/len(errors) if errors else None,
                mean_bbox_diagonal_normalized_error=sum(normalized)/len(normalized) if normalized else None,
                pck_all_coordinate_references=successes/labeled if labeled else None,
                pck_on_covered_coordinates=successes/len(errors) if errors else None,
                known_not_locatable_count=absent,
                predicted_present_on_not_locatable=sum(row['absent_predicted_present'] for row in rows),
                left_right_suspected_swaps=sum(row['swap_suspected'] is True for row in rows),
                left_right_assessable=sum(row['swap_suspected'] is not None for row in rows))


def evaluate(source, predictions, output, *, split='test', confidence_min=.5, pck_threshold=.05):
    if split not in ('val', 'test') or not _number(confidence_min, 0, 1) or not _number(pck_threshold, .001, 1):
        _fail('explicit_split_and_bounded_pose_metric_parameters_required')
    source, reference, fingerprint = load_reference(source)
    prediction_path, prediction, prediction_fingerprint = _json(predictions)
    if prediction.get('schema_version') != PREDICTION_VERSION or prediction.get('reference_sha256') != fingerprint:
        _fail('prediction_reference_version_or_hash_mismatch')
    _contract(prediction)
    model = prediction.get('model') or {}
    if (not isinstance(model, dict) or not _identifier(model.get('model_id')) or not _sha(model.get('weights_sha256'))
            or type(model.get('trained_on_reference')) is not bool):
        _fail('explicit_prediction_model_provenance_required')
    if model['trained_on_reference']:
        for key, group_split in (('training_subject_groups', 'train'), ('selection_subject_groups', 'val')):
            declared = model.get(key)
            allowed = {r['subject_group'] for r in reference['samples'] if r['split'] == group_split}
            if (not isinstance(declared, list) or any(not _identifier(group) for group in declared)
                    or not set(declared) <= allowed):
                _fail('model_training_or_selection_subject_leakage')
        if not model['training_subject_groups']:
            _fail('nonempty_candidate_training_group_provenance_required')
    samples = prediction.get('samples')
    if not isinstance(samples, list) or len(samples) > MAX_SAMPLES:
        _fail('bounded_pose_prediction_samples_required')
    by_id, reference_by_id = {}, {r['sample_id']: r for r in reference['samples']}
    for row in samples:
        if not isinstance(row, dict):
            _fail('prediction_sample_object_required')
        sid = row.get('sample_id')
        if sid in by_id or sid not in reference_by_id:
            _fail('duplicate_or_unknown_prediction_sample')
        target = reference_by_id[sid]
        for key in ('image_sha256', 'frame_size', 'frame_seq', 'source_time_s', 'subject_group', 'recording_id'):
            if row.get(key) != target[key] or type(row.get(key)) is not type(target[key]):
                _fail('prediction_original_frame_alignment_mismatch')
        if row.get('status') not in ('matched', 'no_person', 'ambiguous', 'failed'):
            _fail('explicit_prediction_observation_status_required')
        if not isinstance(row.get('xy'), list) or len(row['xy']) != 17 or not isinstance(row.get('conf'), list) or len(row['conf']) != 17:
            _fail('prediction_coco17_slots_required')
        for point, conf in zip(row['xy'], row['conf']):
            if conf is not None and not _number(conf, 0, 1):
                _fail('finite_prediction_confidence_required')
            if point is not None and (not isinstance(point, list) or len(point) != 2
                                     or not all(_number(n, -4096, 8192) for n in point)):
                _fail('finite_prediction_pixel_coordinate_required')
            if row['status'] != 'matched' and (point is not None or conf is not None):
                _fail('unmatched_prediction_cannot_supply_joint_evidence')
        by_id[sid] = row
    rows, states, durations = [], Counter(), []
    for sample in reference['samples']:
        if sample['split'] != split:
            continue
        predicted = by_id.get(sample['sample_id'])
        states[predicted['status'] if predicted else 'prediction_missing'] += 1
        duration = predicted.get('roundtrip_ms') if predicted else None
        if duration is not None:
            if not _number(duration):
                _fail('finite_inference_roundtrip_required')
            durations.append(duration)
        box, size = sample['bbox_xyxy_px'], sample['frame_size']
        diagonal = math.hypot(box[2]-box[0], box[3]-box[1])
        for index, joint in enumerate(JOINTS):
            point = predicted['xy'][index] if predicted else None
            conf = predicted['conf'][index] if predicted else None
            observed = (predicted is not None and predicted['status'] == 'matched' and point is not None
                        and conf is not None and conf >= confidence_min
                        and 0 <= point[0] <= size[0] and 0 <= point[1] <= size[1])
            mask, visibility, truth = sample['annotation_mask'][index], sample['visibility'][index], sample['xy'][index]
            available = mask and visibility in (1, 2)
            error = math.dist(point, truth) if observed and available else None
            normalized = error/diagonal if error is not None else None
            other = FLIP[index]
            swap = None
            if error is not None and other != index and sample['annotation_mask'][other] and sample['visibility'][other] in (1, 2):
                swap = math.dist(point, sample['xy'][other]) < error
            rows.append(dict(sample_id=sample['sample_id'], subject_group=sample['subject_group'],
                exercise_id=sample['exercise_id'], view=sample['view'], joint=joint, visibility=visibility,
                unannotated=not mask, coordinate_reference=available, known_not_locatable=mask and visibility == 0,
                absent_predicted_present=mask and visibility == 0 and observed, error_px=error,
                normalized_error=normalized, pck_pass=normalized <= pck_threshold if normalized is not None else None,
                swap_suspected=swap))
    groups = {}
    for key in ('joint', 'subject_group', 'exercise_id', 'view', 'visibility'):
        grouped = defaultdict(list)
        for row in rows:
            grouped[str(row[key])].append(row)
        groups[key] = {name: _summary(values) for name, values in sorted(grouped.items())}
    durations.sort()
    latency = {name: durations[max(0, math.ceil(q*len(durations))-1)] if durations else None
               for name, q in (('p50', .5), ('p95', .95))}
    if file_hash(source) != fingerprint or file_hash(prediction_path) != prediction_fingerprint:
        _fail('reference_or_predictions_changed_during_evaluation')
    output = _new_output(output)
    result = dict(version=VERSION, reference_sha256=fingerprint, prediction_sha256=prediction_fingerprint,
        model=model, split=split, confidence_min=confidence_min, pck_bbox_diagonal_threshold=pck_threshold,
        summary=_summary(rows), grouped=groups, observation_states=dict(states), per_joint_evidence=rows,
        roundtrip_ms=dict(latency, count=len(durations)), reference_usage_context=reference['usage_context'],
        evidence_scope=('synthetic_tool_verification_not_target_accuracy' if reference['usage_context'] == 'TEST'
                        else 'independent_reference_offline_2d_pose_evaluation'),
        group_scope='declared_experiment_groups_checked_not_proof_of_upstream_pretraining_exclusion',
        missing_predictions_count_in_coverage=True, clinical_accuracy=None, anatomical_rom_accuracy=None,
        uncertainty='No clinical confidence or bootstrap claim; inspect per-subject results and sample counts.')
    path = write_json(output/'evaluation.json', result)
    return dict(path=path, artifact_sha256=file_hash(path), evidence_scope=result['evidence_scope'], summary=result['summary'])
