"""Independent synthetic-source and honest human-reference contracts.

Validation records declarations, not proof of a person's qualifications. AI drafts
may be saved, but are never eligible supervision. No MobiPhysio gate is changed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

SCHEMA_VERSION = 'rehab_synthetic/v1'
PHASES = ('ready', 'outbound', 'endpoint_or_hold', 'return', 'rest_or_other')
SCENARIOS = tuple('ABCDEF')
SPLITS = ('train', 'val', 'test')


class SyntheticContractError(ValueError):
    pass


def _fail(reason):
    raise SyntheticContractError(reason)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 4096


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _number(value):
    return type(value) in (float, int) and math.isfinite(value)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _object(value, name):
    if not isinstance(value, dict):
        _fail(name+'_object_required')
    return value


def freeze_splits(formal_group_splits):
    """Freeze ten independent formal source groups BEFORE formal generation."""
    groups = _object(formal_group_splits, 'formal_group_splits')
    if (len(groups) != 10 or any(not _text(key) for key in groups)
            or any(not isinstance(split, str) or split not in SPLITS for split in groups.values())
            or Counter(groups.values()) != Counter(train=6, val=2, test=2)):
        _fail('formal_split_requires_ten_groups_6_2_2')
    return dict(frozen=True, formal_group_splits=copy.deepcopy(groups), sha256=canonical_hash(groups))


def _freeze(manifest):
    frozen = manifest.get('split_freeze')
    if frozen is None:
        return {}
    _object(frozen, 'split_freeze')
    expected = freeze_splits(frozen.get('formal_group_splits'))
    if frozen != expected:
        _fail('split_freeze_changed_or_not_frozen')
    return expected['formal_group_splits']


def validate_timeline(timeline, sample):
    """Validate the complete decoded PTS inventory, never FPS reconstruction."""
    _object(timeline, 'timeline')
    video = sample['video']
    if timeline.get('schema_version') != SCHEMA_VERSION:
        _fail('timeline_schema_mismatch')
    if (timeline.get('video_sha256') != video['sha256']
            or timeline.get('frame_count') != video['frame_count']
            or timeline.get('width') != video['width'] or timeline.get('height') != video['height']):
        _fail('timeline_source_or_geometry_mismatch')
    if timeline.get('time_basis') != 'stream_relative_media_pts':
        _fail('actual_media_pts_required')
    provenance = _object(timeline.get('provenance'), 'timeline_provenance')
    if (provenance.get('origin') != 'decoded_video' or not _text(provenance.get('decoder'))
            or not _integer(provenance.get('video_stream_index'))
            or not _number(provenance.get('stream_start_time_s'))):
        _fail('decoded_pts_provenance_required')
    times = timeline.get('presentation_s')
    if (not isinstance(times, list) or len(times) != video['frame_count']
            or any(not _number(t) or t < 0 for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        _fail('complete_strictly_increasing_media_pts_required')
    return tuple(times)


def _full_review(review, sample, *, require=False):
    _object(review, 'review')
    if type(review.get('full_video_watched')) is not bool:
        _fail('explicit_full_video_watched_required')
    watched = review['full_video_watched']
    if watched:
        if (review.get('reviewed_video_sha256') != sample['video']['sha256']
                or review.get('reviewed_frame_count') != sample['video']['frame_count']
                or not _text(review.get('watched_at'))):
            _fail('complete_review_bound_to_original_video_required')
    if require and not watched:
        _fail('full_video_review_required')
    return watched


def _sample(row):
    _object(row, 'sample')
    for key in ('sample_id', 'source_group_id', 'reference_group_id', 'exercise_id', 'side', 'view'):
        if not _text(row.get(key)):
            _fail('sample_'+key+'_required')
    if row['side'] not in ('left', 'right', 'bilateral', 'unknown'):
        _fail('explicit_anatomical_side_required')
    if row.get('split') not in SPLITS or row.get('stage') not in ('pilot', 'formal'):
        _fail('sample_split_and_stage_required')
    if row['stage'] == 'pilot' and row['split'] != 'train':
        _fail('pilot_sources_train_only')
    if row['stage'] == 'formal' and row.get('scenario') not in SCENARIOS:
        _fail('formal_scenario_A_through_F_required')
    lineage = row.get('lineage_ids')
    if (not isinstance(lineage, list) or not lineage or any(not _text(x) for x in lineage)
            or len(set(lineage)) != len(lineage)):
        _fail('nonempty_unique_lineage_ids_required')
    video = _object(row.get('video'), 'video')
    if (not _text(video.get('path')) or not _text(video.get('timeline_path'))
            or not _sha(video.get('sha256')) or not _sha(video.get('timeline_sha256'))
            or any(not _integer(video.get(key), 1) for key in ('width', 'height', 'frame_count'))):
        _fail('original_video_hash_geometry_and_pts_index_required')
    gen = _object(row.get('generation'), 'generation')
    if (not _text(gen.get('prompt_version')) or not _integer(gen.get('seed'))
            or any(not _sha(gen.get(key)) for key in ('model_sha256', 'workflow_sha256', 'prompt_sha256'))):
        _fail('generation_versions_and_hashes_required')
    status = row.get('status', 'pending')
    if status not in ('pending', 'accepted', 'excluded'):
        _fail('unknown_sample_status')
    if status == 'excluded' and not _text(row.get('exclusion_reason')):
        _fail('excluded_source_reason_required')
    if status == 'accepted':
        review = _object(row.get('acceptance'), 'acceptance')
        if review.get('reviewer_role') != 'human_operator' or not _text(review.get('reviewer_id')):
            _fail('accepted_source_requires_human_operator')
        _full_review(review, row, require=True)


def source_components(samples):
    """Conservative transitive closure across person, reference, motion and raw IDs.

    Identifiers share one origin namespace: callers cannot bypass a common source
    by relabeling its ID as a reference instead of a lineage. Duplicate raw hashes
    are joined even if filenames and claimed people differ.
    """
    parent = {}

    def find(key):
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    keys = []
    for row in samples:
        tokens = ['origin:'+x for x in [row['sample_id'], row['source_group_id'],
                  row['reference_group_id'], *row['lineage_ids']]]
        tokens.append('sha256:'+row['video']['sha256'])
        ref_sha = row.get('generation', {}).get('reference_sha256')
        if ref_sha is not None:
            if not _sha(ref_sha):
                _fail('reference_sha256_invalid')
            tokens.append('sha256:'+ref_sha)
        for token in tokens[1:]:
            union(tokens[0], token)
        keys.append(tokens[0])
    groups = defaultdict(list)
    for row, key in zip(samples, keys):
        groups[find(key)].append(row['sample_id'])
    return sorted((sorted(group) for group in groups.values()), key=lambda x: x[0])


def validate_manifest(manifest, timelines=None, *, require_formal_complete=False):
    """Pure structural/source validation; optional supplied PTS objects are checked.

    File verification belongs to load_manifest. Pending candidates are retained,
    and never counted as accepted formal source clips.
    """
    _object(manifest, 'manifest')
    if manifest.get('schema_version') != SCHEMA_VERSION or not _text(manifest.get('dataset_id')):
        _fail('synthetic_manifest_schema_and_dataset_id_required')
    rows = manifest.get('samples')
    if not isinstance(rows, list):
        _fail('samples_list_required')
    frozen = _freeze(manifest)
    for row in rows:
        _sample(row)
    ids = [row['sample_id'] for row in rows]
    if len(set(ids)) != len(ids):
        _fail('duplicate_sample_id')
    paths = {}
    for row in rows:
        path, sha = row['video']['path'], row['video']['sha256']
        if path in paths and paths[path] != sha:
            _fail('same_raw_path_conflicting_hashes')
        paths[path] = sha
        if row['stage'] == 'formal' and frozen.get(row['source_group_id']) != row['split']:
            _fail('formal_source_outside_frozen_split')
        if timelines is not None:
            if row['sample_id'] not in timelines:
                _fail('complete_pts_index_inventory_required')
            validate_timeline(timelines[row['sample_id']], row)
    components = source_components(rows)
    by_id = {row['sample_id']: row for row in rows}
    for component in components:
        selected = [by_id[key] for key in component]
        if len({row['split'] for row in selected}) != 1:
            _fail('transitive_source_leakage_between_splits')
        if any(row['stage'] == 'pilot' for row in selected) and selected[0]['split'] != 'train':
            _fail('pilot_related_sources_train_only')
        if len({row['source_group_id'] for row in selected if row['stage'] == 'formal'}) > 1:
            _fail('formal_source_groups_not_independent')
    if len({row['video']['sha256'] for row in rows}) != len(rows):
        _fail('duplicate_raw_video_cannot_be_another_source_sample')
    accepted = [row for row in rows if row['stage'] == 'formal' and row.get('status') == 'accepted']
    if require_formal_complete:
        expected = {(group, scenario) for group in frozen for scenario in SCENARIOS}
        actual = [(row['source_group_id'], row['scenario']) for row in accepted]
        if len(frozen) != 10 or len(actual) != 60 or set(actual) != expected:
            _fail('sixty_human_accepted_formal_sources_A_through_F_required')
    return dict(sample_count=len(rows), source_components=components,
                accepted_formal_count=len(accepted),
                accepted_formal_splits=dict(Counter(row['split'] for row in accepted)),
                pending_sample_ids=[row['sample_id'] for row in rows if row.get('status', 'pending') == 'pending'])


def _read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail('duplicate_json_key')
            result[key] = value
        return result
    def constant(_):
        _fail('nonfinite_json_number')
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=pairs,
                          parse_constant=constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SyntheticContractError('unreadable_json:'+str(path)) from exc


def _resolve(base, reference):
    path = Path(reference)
    return path.resolve() if path.is_absolute() else (base/path).resolve()


def _file_hash(path):
    digest = hashlib.sha256()
    try:
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                digest.update(block)
    except OSError as exc:
        raise SyntheticContractError('source_file_missing:'+str(path)) from exc
    return digest.hexdigest()


def load_manifest(path, *, require_formal_complete=False, verify_files=True):
    """Verify raw hashes and re-decode actual PTS; return the source manifest.

    ``verify_files=False`` is only a structural/tooling mode and cannot establish
    actual media evidence. Callers must not present that mode as dataset approval.
    """
    path = Path(path).resolve()
    manifest = _read_json(path)
    validate_manifest(manifest, require_formal_complete=require_formal_complete)
    if verify_files:
        timelines = {}
        for row in manifest['samples']:
            video = row['video']
            for ref_key, hash_key in (('path', 'sha256'), ('timeline_path', 'timeline_sha256')):
                source = _resolve(path.parent, video[ref_key])
                if _file_hash(source) != video[hash_key]:
                    _fail('source_file_hash_mismatch:'+row['sample_id']+':'+ref_key)
            timelines[row['sample_id']] = _read_json(_resolve(path.parent, video['timeline_path']))
        validate_manifest(manifest, timelines, require_formal_complete=require_formal_complete)
        # A self-consistent JSON index is not evidence of actual media PTS. Check
        # the immutable source itself, including packet/frame inventory matching.
        from .video import probe_video
        for row in manifest['samples']:
            try:
                decoded = probe_video(_resolve(path.parent, row['video']['path']))
            except (ValueError, OSError) as exc:
                raise SyntheticContractError('actual_video_decode_failed:'+row['sample_id']) from exc
            saved = timelines[row['sample_id']]
            if any(decoded[key] != saved[key] for key in
                   ('video_sha256', 'frame_count', 'width', 'height', 'time_basis', 'presentation_s')):
                _fail('stored_timeline_disagrees_with_actual_decode:'+row['sample_id'])
            if 'frames' in saved and decoded['frames'] != saved['frames']:
                _fail('stored_frame_fingerprints_disagree_with_actual_decode:'+row['sample_id'])
    return manifest


def repetition_template(rep_id=None):
    return dict(rep_id=rep_id, boundaries=dict.fromkeys(PHASES),
                boundary_masks=dict.fromkeys(PHASES, False),
                observable_completion=None, observable_completion_mask=False)


def prepare_review(sample, timeline, *, reviewer_id=None, reviewer_role='human_operator'):
    """Create an UNREVIEWED empty form. No count, phase or quality is inferred."""
    _sample(sample)
    validate_timeline(timeline, sample)
    if reviewer_role not in ('human_operator', 'ai_draft'):
        _fail('reviewer_role_invalid')
    return dict(schema_version=SCHEMA_VERSION, sample_id=sample['sample_id'],
        reviewer_id=reviewer_id, reviewer_role=reviewer_role,
        review=dict(full_video_watched=False, reviewed_video_sha256=None,
                    reviewed_frame_count=None, watched_at=None),
        side=None, side_mask=False, observable_count=None, observable_count_mask=False,
        phase_intervals=[], repetitions=[], quality=[])


def _masked(value, mask, predicate, name):
    if type(mask) is not bool:
        _fail(name+'_boolean_mask_required')
    if mask and not predicate(value):
        _fail(name+'_known_value_required')
    if not mask and value is not None:
        _fail(name+'_unknown_must_be_null')


def _at_pts(value, times):
    # Match decoded frame times, with only serialization rounding tolerance.
    return _number(value) and any(abs(float(value)-stamp) <= .0002 for stamp in times)


def _professional(value):
    if not isinstance(value, dict) or value.get('approved') is not True or value.get('independent') is not True:
        return False
    people = value.get('reviewers')
    if not isinstance(people, list) or len(people) != 3:
        return False
    roles = {'annotator_A', 'annotator_B', 'reviewer'}
    return (all(isinstance(p, dict) and _text(p.get('id')) and _text(p.get('qualification'))
                and _text(p.get('evidence_ref')) and _sha(p.get('evidence_sha256')) for p in people)
            and len({p['id'] for p in people}) == 3 and {p.get('role') for p in people} == roles)


def validate_annotation(row, sample, timeline):
    """Validate masks and real-PTS labels; report eligibility without inventing it."""
    _object(row, 'annotation')
    _sample(sample)
    times = validate_timeline(timeline, sample)
    if row.get('schema_version') != SCHEMA_VERSION or row.get('sample_id') != sample['sample_id']:
        _fail('annotation_schema_or_source_mismatch')
    role = row.get('reviewer_role')
    if role not in ('human_operator', 'ai_draft'):
        _fail('reviewer_role_invalid')
    watched = _full_review(row.get('review'), sample)
    if row.get('reviewer_id') is not None and not _text(row['reviewer_id']):
        _fail('reviewer_id_invalid')
    _masked(row.get('side'), row.get('side_mask'), lambda x: x in ('left', 'right', 'bilateral'), 'side')
    _masked(row.get('observable_count'), row.get('observable_count_mask'), _integer, 'observable_count')
    intervals = row.get('phase_intervals')
    if not isinstance(intervals, list):
        _fail('phase_intervals_list_required')
    previous = -math.inf
    for interval in intervals:
        _object(interval, 'phase_interval')
        if interval.get('phase') not in PHASES:
            _fail('unsupported_phase')
        known = interval.get('label_mask')
        _masked(interval.get('start_s'), known, lambda x: _at_pts(x, times), 'phase_start')
        _masked(interval.get('end_s'), known, lambda x: _at_pts(x, times), 'phase_end')
        if known:
            if interval['end_s'] <= interval['start_s'] or interval['start_s'] < previous:
                _fail('phase_intervals_must_be_ordered_nonoverlapping')
            previous = interval['end_s']
    repetitions = row.get('repetitions')
    if not isinstance(repetitions, list):
        _fail('repetitions_list_required')
    ids, previous = set(), -math.inf
    for rep in repetitions:
        _object(rep, 'repetition')
        if not _text(rep.get('rep_id')) or rep['rep_id'] in ids:
            _fail('unique_rep_id_required')
        ids.add(rep['rep_id'])
        boundaries, masks = rep.get('boundaries'), rep.get('boundary_masks')
        if (not isinstance(boundaries, dict) or not isinstance(masks, dict)
                or set(boundaries) != set(PHASES) or set(masks) != set(PHASES)):
            _fail('all_phase_boundary_values_and_masks_required')
        known = []
        for phase in PHASES:
            _masked(boundaries[phase], masks[phase], lambda x: _at_pts(x, times), 'boundary_'+phase)
            if masks[phase]:
                known.append(boundaries[phase])
        if any(b < a for a, b in zip(known, known[1:])) or (known and known[0] < previous):
            _fail('repetition_boundaries_out_of_order_or_overlapping')
        if known:
            previous = known[-1]
        _masked(rep.get('observable_completion'), rep.get('observable_completion_mask'),
                lambda x: type(x) is bool, 'observable_completion')
        if rep.get('observable_completion') is True and sample['exercise_id'] == 'shoulder_abduction':
            if not all(masks.values()):
                _fail('complete_shoulder_roundtrip_requires_all_boundaries')
            if not (boundaries['ready'] <= boundaries['outbound'] < boundaries['endpoint_or_hold']
                    < boundaries['return'] < boundaries['rest_or_other']):
                _fail('complete_shoulder_roundtrip_requires_positive_phase_durations')
    if row['observable_count_mask']:
        if any(not rep['observable_completion_mask'] for rep in repetitions):
            _fail('unknown_completion_inventory_cannot_set_count')
        if row['observable_count'] != sum(rep['observable_completion'] is True for rep in repetitions):
            _fail('count_must_match_explicit_observable_completions')
    quality = row.get('quality')
    if not isinstance(quality, list):
        _fail('quality_list_required')
    for label in quality:
        _object(label, 'quality_label')
        if not _text(label.get('problem_id')) or label.get('kind') not in ('observable_change', 'clinical_quality'):
            _fail('quality_problem_and_kind_required')
        _masked(label.get('assessable'), label.get('assessability_mask'), lambda x: type(x) is bool, 'quality_assessability')
        state, mask = label.get('state'), label.get('label_mask')
        if type(mask) is not bool or state not in ('present', 'absent', 'unknown'):
            _fail('quality_state_and_mask_required')
        if mask and (state == 'unknown' or label.get('assessable') is not True or label.get('assessability_mask') is not True):
            _fail('known_quality_requires_assessable_state')
        if not mask and state != 'unknown':
            _fail('unknown_quality_must_remain_unknown')
        if mask:
            if (not _at_pts(label.get('start_s'), times) or not _at_pts(label.get('end_s'), times)
                    or label['end_s'] < label['start_s']):
                _fail('quality_interval_requires_actual_pts')
            if label['kind'] == 'clinical_quality' and not _professional(label.get('professional_review')):
                _fail('clinical_quality_requires_independent_qualified_review')
        elif label.get('start_s') is not None or label.get('end_s') is not None:
            _fail('unknown_quality_interval_must_be_null')
    reasons = []
    if role != 'human_operator':
        reasons.append('ai_draft_not_human_reference')
    if not _text(row.get('reviewer_id')):
        reasons.append('human_reviewer_not_identified')
    if not watched:
        reasons.append('full_video_review_pending')
    if not row.get('side_mask'):
        reasons.append('anatomical_side_unconfirmed')
    elif row.get('side') not in ('left', 'right'):
        reasons.append('require_side_specific_temporal_reference')
    if sample.get('status', 'pending') != 'accepted':
        reasons.append('source_not_human_accepted')
    if not (row['observable_count_mask'] or any(x['label_mask'] for x in intervals)
            or any(any(x['boundary_masks'].values()) or x['observable_completion_mask'] for x in repetitions)):
        reasons.append('no_known_temporal_supervision')
    return dict(eligible_for_training=not reasons, reasons=reasons)


def load_eligible_annotations(rows, manifest, timelines):
    """Return only genuine reviewed rows; reject illegal records, retain unknowns.

    Drafts/pending rows remain available in the caller's source inventory and are
    excluded here, never converted to negatives or zero counts.
    """
    validate_manifest(manifest, timelines)
    if not isinstance(rows, list):
        _fail('annotation_rows_list_required')
    samples = {row['sample_id']: row for row in manifest['samples']}
    seen, result = set(), []
    for row in rows:
        if not isinstance(row, dict) or row.get('sample_id') not in samples or row['sample_id'] in seen:
            _fail('unknown_or_duplicate_annotation_sample')
        key = row['sample_id']
        seen.add(key)
        if validate_annotation(row, samples[key], timelines[key])['eligible_for_training']:
            result.append(copy.deepcopy(row))
    return result
