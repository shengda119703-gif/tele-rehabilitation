"""Offline independent temporal references, never prediction-derived ground truth.

The existing video-score study is immutable. This separate review package grants
no model activation and imports only labels with two independent human records
and an explicit third-person professional resolution.
"""
from __future__ import annotations

from bisect import bisect_left
import copy
import json
import math
from pathlib import Path
import re
import shutil

from .common import ROOT, canonical_hash, file_hash, git, paths, utc_now, write_json

SCHEMA = 'rehab-professional-label-2'
BUNDLE = 'rehab-independent-review-bundle-1'
PROTOCOL = 'rehab-protocol-2.0'
BOUNDARIES = ('preparation_confirmed_s', 'outbound_start_s', 'endpoint_start_s',
              'endpoint_end_s', 'return_start_s', 'end_s')
TASKS = ('physical_completion', 'observable_completion')
EXERCISES = ('shoulder_abduction', 'sit_to_stand', 'rehab_squat')
MAX_BYTES = 8_000_000
MAX_ROWS = 64


def _fail(reason):
    raise ValueError(reason)


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _fail('duplicate_json_key')
        value[key] = item
    return value


def _json(text):
    return json.loads(text, object_pairs_hook=_object,
                      parse_constant=lambda _: _fail('nonfinite_json'))


def _read(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        _fail('annotation_file_quota')
    return _json(path.read_text(encoding='utf-8'))


def read_rows(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        _fail('annotation_file_quota')
    rows = [_json(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not 1 <= len(rows) <= MAX_ROWS or not all(isinstance(row, dict) for row in rows):
        _fail('annotation_row_quota_or_type')
    return rows


def repetition_template():
    return dict(rep_id=None, boundaries={key: None for key in BOUNDARIES},
                physical_completion=None, observable_completion=None,
                physical_reference=None,
                label_masks={**{key: False for key in TASKS},
                             'phase': {key: False for key in BOUNDARIES}},
                quality_problems=[], cue_opportunities=[])


def record_template(sample=None, role='A'):
    return dict(schema_version=SCHEMA, sample_id=None if sample is None else sample['sample_id'],
                source=None if sample is None else copy.deepcopy(sample), side=None,
                conditions=dict(acceptable_variation_conditions=None, support='unknown',
                                target_range_deg=None), repetitions=[],
                observable_count=None, observable_count_mask=False,
                annotation=dict(role=role, annotator=None, annotation_version=None,
                                origin='human', independently_performed=False,
                                video_reviewed=False, inventory_complete=False, status='pending'),
                review=dict(status='pending', input_digests=None, reviewer_qualification=None,
                            disagreement_paths=None, final_resolution=None))


def _new_output(path):
    path = Path(path).resolve()
    if path == paths()['run'] or not path.is_relative_to(paths()['run']) or path.exists():
        _fail('explicit_new_owned_output_directory_required')
    if shutil.disk_usage(paths()['run']).free < 32_000_000:
        _fail('annotation_disk_reserve')
    path.mkdir(parents=True, exist_ok=False)
    return path


def _rows_write(path, rows):
    # New package only; editable forms are never overwritten by a subsequent run.
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')


def _source_samples(receipt_path):
    from .mobiphysio_pose import verified_download
    receipt_path, receipt, plan_path, plan = verified_download(receipt_path)
    if plan['license'].get('rightsIdentifier') != 'CC0-1.0':
        _fail('independent_annotation_license_not_reviewed')
    files = {row['file_id']: row for row in receipt['files']}
    samples = [dict(sample_id='mobi3-e01-'+row['subject_id'], subject_group=row['subject_id'],
                    exercise_id='shoulder_abduction', view='frontal', protocol_version=PROTOCOL,
                    split=row['split'], video_ref=str(plan_path.parent/row['filename']),
                    video_sha256=files[row['file_id']]['sha256'], video_bytes=row['bytes'],
                    dataset='mobiphysio', dataset_version='3.0', camera_id='AF',
                    affected_side=None) for row in plan['samples']]
    proof = dict(receipt_ref=str(receipt_path), receipt_sha256=file_hash(receipt_path),
                 plan_sha256=file_hash(plan_path), license='CC0-1.0',
                 source_scope='offline_video_eaaq_research',
                 source_training_heads=['whole_video_eaaq'],
                 review_scope='independent_human_temporal_annotation',
                 training_enabled=False, product_enabled=False)
    return proof, samples


def _media_timeline(source):
    import av
    from .mobiphysio_pose import container_timeline
    with av.open(str(source)) as container:
        if len(container.streams.video) != 1:
            _fail('single_video_stream_required')
        frames = container.streams.video[0].frames
    stamps, discarded, origin = container_timeline(source, frames)
    return dict(time_basis='stream_relative_media_pts', origin_s=origin,
                presentation_s=stamps, discarded_packets=discarded)


def build_bundle(receipt_path, output_dir):
    """Recheck licensed bytes, then create score-free forms and actual PTS maps."""
    proof, samples = _source_samples(receipt_path)
    output = _new_output(output_dir)
    summary = dict(status='building', bundle=str(output/'bundle.json'),
                   product_enabled=False, training_performed=False, completed_samples=0)
    write_json(output/'summary.json', summary)
    try:
        # Serialize the fillable rules/templates before processing any media.
        guide = ROOT/'docs/development/REHAB_PROFESSIONAL_ANNOTATION.md'
        shutil.copyfile(guide, output/'GUIDE.md')
        template = dict(schema_version=SCHEMA, record=record_template(),
                        repetition=repetition_template(),
                        quality_problem=dict(problem_id=None, state='unknown', assessable=None,
                            state_mask=False, assessability_mask=False, start_s=None, end_s=None,
                            acceptable_variation_conditions=None),
                        cue_opportunity=dict(start_s=None, end_s=None, category=None, priority=None,
                            label_mask=False, actually_received=None, later_improved=None,
                            intervention_evidence=None))
        write_json(output/'templates.json', template)
        for sample in samples:
            source = Path(sample['video_ref'])
            media = _media_timeline(source)
            stamps = media['presentation_s']
            timeline = output/(sample['sample_id']+'-pts.json')
            write_json(timeline, media)
            sample.update(time_basis='stream_relative_media_pts', duration_s=stamps[-1],
                          timeline_ref=timeline.name, timeline_sha256=file_hash(timeline))
            if file_hash(source) != sample['video_sha256']:
                _fail('source_changed_during_package')
            summary['completed_samples'] += 1
            write_json(output/'summary.json', summary)
        _rows_write(output/'annotator-A.jsonl', [record_template(row, 'A') for row in samples])
        _rows_write(output/'annotator-B.jsonl', [record_template(row, 'B') for row in samples])
        _rows_write(output/'review.jsonl', [record_template(row, 'REVIEW') for row in samples])
        manifest = dict(schema_version=BUNDLE, source_proof=proof, samples=samples,
                        forms={role: filename for role, filename in
                               (('A', 'annotator-A.jsonl'), ('B', 'annotator-B.jsonl'), ('REVIEW', 'review.jsonl'))},
                        frozen_assets={name: file_hash(output/name) for name in ('GUIDE.md', 'templates.json')},
                        prediction_or_score_prefill=False, original_videos_copied=False,
                        independent_review_status='pending_human_review',
                        created_at=utc_now(), git_commit=git('rev-parse', 'HEAD'),
                        implementation_sha256=file_hash(__file__))
        manifest['manifest_digest'] = canonical_hash(manifest)
        write_json(output/'bundle.json', manifest)
        summary.update(status='pending_human_review', samples=len(samples),
                       split_counts={key: sum(row['split'] == key for row in samples)
                                     for key in ('train', 'val', 'test')},
                       labeled_repetitions=0, reference_generated=False,
                       bundle_sha256=file_hash(output/'bundle.json'),
                       artifacts=[str(output/name) for name in ('bundle.json', 'GUIDE.md', 'templates.json',
                                   'annotator-A.jsonl', 'annotator-B.jsonl', 'review.jsonl')])
        write_json(output/'summary.json', summary)
        return summary
    except Exception as exc:
        write_json(output/'failure.json', dict(status='failed', error_type=type(exc).__name__,
                                              error=str(exc), completed_samples=summary['completed_samples']))
        raise


def _bundle(path):
    path = Path(path).resolve()
    if path.name != 'bundle.json' or not path.parent.is_relative_to(paths()['run']):
        _fail('owned_explicit_bundle_required')
    value = _read(path)
    digest = value.pop('manifest_digest', None)
    if value.get('schema_version') != BUNDLE or canonical_hash(value) != digest:
        _fail('bundle_digest_changed')
    proof, source_rows = _source_samples(value['source_proof']['receipt_ref'])
    if proof != value['source_proof'] or len(source_rows) != len(value['samples']):
        _fail('bundle_source_qualification_changed')
    for source, sample in zip(source_rows, value['samples']):
        if (set(sample) != set(source) | {'time_basis', 'duration_s', 'timeline_ref', 'timeline_sha256'}
                or any(sample.get(key) != item for key, item in source.items())):
            _fail('bundle_source_or_split_changed')
        timeline = (path.parent/sample['timeline_ref']).resolve()
        if (timeline.parent != path.parent or file_hash(timeline) != sample['timeline_sha256']
                or sample['time_basis'] != 'stream_relative_media_pts'):
            _fail('source_timeline_changed')
        media = _read(timeline)
        # A self-declared hash is not evidence of media time. Re-derive PTS
        # from the verified original even if an attacker rewrites both hashes.
        if media != _media_timeline(source['video_ref']):
            _fail('timeline_does_not_match_verified_original')
        times = media['presentation_s']
        if (not 1 <= len(times) <= 18000 or any(type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in times)
                or any(a >= b for a, b in zip(times, times[1:])) or times[-1] != sample['duration_s']):
            _fail('invalid_source_timeline')
    for name, expected in value['frozen_assets'].items():
        asset = (path.parent/name).resolve()
        if asset.parent != path.parent or file_hash(asset) != expected:
            _fail('bundle_guide_or_template_changed')
    expected_forms = {'A': 'annotator-A.jsonl', 'B': 'annotator-B.jsonl', 'REVIEW': 'review.jsonl'}
    if value['forms'] != expected_forms:
        _fail('bundle_form_identity_changed')
    return path, value


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[\w.-]{1,100}', value) is not None


def _text(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 2000


def _time(value, sample, times):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= sample['duration_s']:
        _fail('annotation_time_outside_source')
    index = bisect_left(times, value)
    if not any(abs(times[k]-value) <= .0002 for k in (index-1, index) if 0 <= k < len(times)):
        _fail('annotation_boundary_not_media_frame')


def validate_record(row, sample, times, role):
    """Unknown state is never a negative; all masks and frame times are explicit."""
    expected = set(record_template())
    if set(row) != expected or row['schema_version'] != SCHEMA or row['sample_id'] != sample['sample_id']:
        _fail('annotation_record_schema_or_identity')
    if row['source'] != sample or sample['exercise_id'] not in EXERCISES:
        _fail('annotation_source_contract_changed')
    if row['side'] not in (None, 'left', 'right'):
        _fail('annotation_side_invalid')
    if set(row['conditions']) != set(record_template()['conditions']):
        _fail('annotation_conditions_schema')
    if row['conditions']['support'] not in ('unknown', 'none', 'allowed', 'not_allowed'):
        _fail('annotation_support_invalid')
    target = row['conditions']['target_range_deg']
    if target is not None and (type(target) not in (int, float) or not math.isfinite(target) or not 0 <= target <= 180):
        _fail('annotation_target_invalid')
    meta = row['annotation']
    if (set(meta) != set(record_template()['annotation']) or meta['role'] != role
            or meta['origin'] != 'human' or meta['status'] not in ('pending', 'completed')
            or any(type(meta[k]) is not bool for k in ('video_reviewed', 'inventory_complete', 'independently_performed'))):
        _fail('independent_human_annotation_metadata_required')
    completed = meta['status'] == 'completed'
    if role != 'REVIEW' and row['review'] != record_template()['review']:
        _fail('annotators_cannot_self_approve')
    if completed and (not _identifier(meta['annotator']) or not _identifier(meta['annotation_version'])
                      or not meta['video_reviewed'] or not meta['inventory_complete']
                      or not meta['independently_performed']):
        _fail('whole_recording_independent_review_required')
    if not isinstance(row['repetitions'], list) or len(row['repetitions']) > 500:
        _fail('repetition_quota')
    ids, last_end, known = set(), None, 0
    for rep in row['repetitions']:
        if set(rep) != set(repetition_template()) or not _identifier(rep['rep_id']) or rep['rep_id'] in ids:
            _fail('unique_repetition_schema_required')
        ids.add(rep['rep_id'])
        masks, boundaries = rep['label_masks'], rep['boundaries']
        if set(masks) != {*TASKS, 'phase'} or set(boundaries) != set(BOUNDARIES) or set(masks['phase']) != set(BOUNDARIES):
            _fail('per_task_and_boundary_masks_required')
        for task in TASKS:
            if type(masks[task]) is not bool or (type(rep[task]) is not bool if masks[task] else rep[task] is not None):
                _fail('completion_value_mask_mismatch')
            known += masks[task]
        finite = []
        for key in BOUNDARIES:
            if type(masks['phase'][key]) is not bool or (boundaries[key] is None) == masks['phase'][key]:
                _fail('phase_value_mask_mismatch')
            if masks['phase'][key]:
                _time(boundaries[key], sample, times)
                finite.append(boundaries[key])
                known += 1
        if any(a > b for a, b in zip(finite, finite[1:])):
            _fail('phase_boundaries_out_of_order')
        start, end = boundaries['outbound_start_s'], boundaries['end_s']
        if start is not None and last_end is not None and start < last_end:
            _fail('repetitions_overlap')
        if end is not None:
            last_end = end
        if masks['observable_completion'] and rep['observable_completion']:
            needed = ('preparation_confirmed_s', 'outbound_start_s', 'endpoint_start_s')
            if sample['exercise_id'] != 'sit_to_stand':
                needed += ('return_start_s', 'end_s')
            if any(not masks['phase'][key] for key in needed):
                _fail('observable_completion_requires_visible_lifecycle')
            confirmed = [boundaries[key] for key in needed]
            if any(a >= b for a, b in zip(confirmed, confirmed[1:])):
                _fail('observable_completion_requires_distinct_ordered_evidence')
        if masks['physical_completion']:
            ref = rep['physical_reference']
            if (not isinstance(ref, dict) or set(ref) != {'kind', 'evidence_sha256', 'alignment_note'}
                    or not re.fullmatch('[0-9a-f]{64}', str(ref['evidence_sha256'])) or not _text(ref['alignment_note'])):
                _fail('physical_reference_required')
            if ref['kind'] != 'same_video_visible' or ref['evidence_sha256'] != sample['video_sha256']:
                _fail('external_physical_reference_requires_separate_qualification')
            if not masks['observable_completion'] or rep['physical_completion'] != rep['observable_completion']:
                _fail('hidden_physical_completion_not_proven_by_same_video')
        elif rep['physical_reference'] is not None:
            _fail('unmasked_physical_reference')
        if any(not isinstance(rep[k], list) or len(rep[k]) > 32 for k in ('quality_problems', 'cue_opportunities')):
            _fail('quality_and_cue_list_quota')
        for problem in rep['quality_problems']:
            if set(problem) != {'problem_id', 'state', 'assessable', 'state_mask', 'assessability_mask',
                                'start_s', 'end_s', 'acceptable_variation_conditions'}:
                _fail('quality_problem_schema')
            if (not _identifier(problem['problem_id']) or type(problem['state_mask']) is not bool
                    or type(problem['assessability_mask']) is not bool
                    or problem['state'] not in ('present', 'absent', 'unknown')):
                _fail('quality_problem_mask_or_state')
            if (type(problem['assessable']) is not bool if problem['assessability_mask'] else problem['assessable'] is not None):
                _fail('quality_assessability_value_mask_mismatch')
            if problem['state_mask']:
                if (not problem['assessability_mask'] or problem['assessable'] is not True
                        or problem['state'] == 'unknown' or not _text(problem['acceptable_variation_conditions'])):
                    _fail('negative_or_positive_quality_requires_assessable_review')
            elif problem['state'] != 'unknown':
                _fail('unlabeled_quality_not_negative')
            if (problem['state_mask'] or problem['assessability_mask']
                    or problem['start_s'] is not None or problem['end_s'] is not None):
                _interval(problem, sample, times)
            known += problem['state_mask'] + problem['assessability_mask']
        for cue in rep['cue_opportunities']:
            if (set(cue) != {'start_s', 'end_s', 'category', 'priority', 'label_mask',
                            'actually_received', 'later_improved', 'intervention_evidence'}
                    or type(cue['label_mask']) is not bool):
                _fail('cue_opportunity_schema')
            if cue['label_mask']:
                if not _identifier(cue['category']) or type(cue['priority']) is not int or not 0 <= cue['priority'] <= 100:
                    _fail('reviewed_cue_category_and_priority_required')
                _interval(cue, sample, times)
                known += 1
            elif any(cue[k] is not None for k in ('start_s', 'end_s', 'category', 'priority')):
                _fail('unmasked_cue_opportunity')
            if any(cue[k] is not None for k in ('actually_received', 'later_improved', 'intervention_evidence')):
                _fail('intervention_receipt_requires_separately_qualified_evidence')
    if type(row['observable_count_mask']) is not bool:
        _fail('observable_count_boolean_mask_required')
    if row['observable_count_mask']:
        # An empty unreviewed list is not a negative. A separately asserted,
        # independently reviewed full inventory may legitimately contain zero.
        count = row['observable_count']
        if (not completed or type(count) is not int or not 0 <= count <= 500
                or any(rep['label_masks']['observable_completion'] is not True for rep in row['repetitions'])
                or count != sum(rep['observable_completion'] is True for rep in row['repetitions'])):
            _fail('observable_count_requires_complete_explicit_reviewed_inventory')
        known += 1
    elif row['observable_count'] is not None:
        _fail('unmasked_observable_count_not_zero_truth')
    if known and (not completed or row['side'] is None):
        _fail('known_labels_require_independent_completed_annotation_and_side')
    return known


def _interval(value, sample, times):
    _time(value['start_s'], sample, times)
    _time(value['end_s'], sample, times)
    if value['start_s'] > value['end_s']:
        _fail('annotation_interval_reversed')


def differences(a, b, prefix=''):
    """Exact disagreement locators, including masks; no silent averaging."""
    if type(a) is not type(b):
        return [prefix]
    if isinstance(a, dict):
        return sorted(path for key in sorted(set(a) | set(b))
                      for path in ([prefix+'/'+key] if key not in a or key not in b
                                   else differences(a[key], b[key], prefix+'/'+key)))
    if isinstance(a, list):
        if len(a) != len(b):
            return [prefix]
        return [path for i, (left, right) in enumerate(zip(a, b))
                for path in differences(left, right, prefix+'/'+str(i))]
    return [] if a == b else [prefix]


def _label_payload(row):
    return {key: row[key] for key in ('side', 'conditions', 'repetitions',
                                    'observable_count', 'observable_count_mask')}


def audit_bundle(bundle_path):
    path, bundle = _bundle(bundle_path)
    forms = {role: read_rows(path.parent/name) for role, name in bundle['forms'].items()}
    expected_ids = [row['sample_id'] for row in bundle['samples']]
    for rows in forms.values():
        if [row.get('sample_id') for row in rows] != expected_ids:
            _fail('complete_frozen_cohort_and_order_required')
    approved, pending, excluded, disagreements = [], [], [], []
    for index, sample in enumerate(bundle['samples']):
        rows = {role: values[index] for role, values in forms.items()}
        times = _read(path.parent/sample['timeline_ref'])['presentation_s']
        counts = {role: validate_record(row, sample, times, role) for role, row in rows.items()}
        delta = differences(_label_payload(rows['A']), _label_payload(rows['B']))
        disagreements.append(dict(sample_id=sample['sample_id'], paths=delta))
        review = rows['REVIEW']['review']
        if set(review) != set(record_template()['review']) or review['status'] not in ('pending', 'approved', 'excluded'):
            _fail('professional_resolution_schema')
        if review['status'] == 'pending':
            pending.append(sample['sample_id'])
            continue
        people = [row['annotation']['annotator'] for row in rows.values()]
        if (any(row['annotation']['status'] != 'completed' for row in rows.values())
                or len(set(people)) != 3 or not _text(review['reviewer_qualification'])
                or not _text(review['final_resolution']) or review['disagreement_paths'] != delta
                or review['input_digests'] != {role: canonical_hash(rows[role]) for role in ('A', 'B')}):
            _fail('two_independent_annotators_and_bound_professional_resolution_required')
        if review['status'] == 'excluded':
            if counts['REVIEW']:
                _fail('excluded_sample_cannot_contribute_supervision')
            excluded.append(sample['sample_id'])
        elif counts['REVIEW']:
            approved.append(copy.deepcopy(rows['REVIEW']))
        else:
            _fail('approved_reference_requires_nonempty_independent_supervision')
    result = dict(status=('qualified_partial' if pending else 'qualified') if approved else 'pending_human_review',
                  samples=len(expected_ids), approved=len(approved), excluded=len(excluded), pending=len(pending),
                  pending_sample_ids=pending, excluded_sample_ids=excluded,
                  known_labels=sum(validate_record(row, row['source'],
                                   _read(path.parent/row['source']['timeline_ref'])['presentation_s'], 'REVIEW')
                                   for row in approved),
                  disagreements=disagreements, product_enabled=False, pose_labels_available=False,
                  forms_sha256={role: file_hash(path.parent/name) for role, name in bundle['forms'].items()},
                  bundle_sha256=file_hash(path), approved_rows=approved)
    return result


def validate_bundle(bundle_path, output_dir):
    audit = audit_bundle(bundle_path)
    output = _new_output(output_dir)
    audit.pop('approved_rows')
    audit['artifact'] = str(output/'validation.json')
    write_json(output/'validation.json', audit)
    return audit


def import_reviewed(bundle_path, output_dir):
    audit = audit_bundle(bundle_path)
    if audit['status'] not in ('qualified', 'qualified_partial'):
        _fail('blocked_missing_independent_professional_supervision')
    output = _new_output(output_dir)
    bundle = Path(bundle_path).resolve()
    # Revalidate bytes and roles after collection, before emitting any reference.
    again = audit_bundle(bundle)
    if again != audit:
        _fail('annotations_changed_during_import')
    reference = dict(schema_version='rehab-reviewed-temporal-reference-1', origin='independent_human_review',
                     bundle_ref=str(bundle), bundle_sha256=audit['bundle_sha256'],
                     forms_sha256=audit['forms_sha256'], samples=audit.pop('approved_rows'),
                     cohort=_read(bundle)['samples'], pending_sample_ids=audit['pending_sample_ids'],
                     excluded_sample_ids=audit['excluded_sample_ids'],
                     all_source_samples=audit['samples'], excluded_samples=audit['excluded'],
                     training_scope='offline_temporal_research_only', pose_supervision=False,
                     product_enabled=False, diagnosis_or_dosage_allowed=False,
                     created_at=utc_now(), implementation_sha256=file_hash(__file__))
    write_json(output/'reference.json', reference)
    audit.update(artifact=str(output/'reference.json'), reference_sha256=file_hash(output/'reference.json'))
    write_json(output/'summary.json', audit)
    return audit
