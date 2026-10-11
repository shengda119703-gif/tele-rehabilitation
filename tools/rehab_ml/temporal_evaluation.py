"""Independent reviewed temporal references versus declared backend exports.

Offline evaluation only. Unknown reference boundaries are not negatives, missing
predictions remain in coverage, and no result activates a model or changes dose.
"""
from __future__ import annotations

import math
from pathlib import Path
import re
from statistics import mean, median

from .common import canonical_hash, file_hash, write_json
from .professional_annotations import (BOUNDARIES, _read, _new_output, _time,
                                       audit_bundle)

POLICY = dict(schema_version='rehab-temporal-evaluation-policy-1',
              event_tolerance_s=.25, matching='ordered_maximum_cardinality_minimum_absolute_error',
              unknown_reference='unassessable_not_negative', missing_prediction='retain_in_coverage',
              completed_count='explicit_observable_inventory_only')
PREDICTION_SCHEMA = 'rehab-temporal-predictions-1'


def _fail(reason):
    raise ValueError(reason)


def match_events(reference, prediction, tolerance_s):
    """Ordered one-to-one matching: maximize matches, then minimize total error.

    A nearest-first greedy matcher can lose a valid match. Each DP cell keeps
    (matched count, negative absolute error); only traceback is quadratic memory.
    """
    if (type(tolerance_s) not in (int, float) or not math.isfinite(tolerance_s)
            or not 0 < tolerance_s <= 1):
        _fail('invalid_predeclared_event_tolerance')
    for values in (reference, prediction):
        if (len(values) > 500 or any(type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in values)
                or any(a > b for a, b in zip(values, values[1:]))):
            _fail('ordered_finite_bounded_event_times_required')
    n, m = len(reference), len(prediction)
    trace = [bytearray(m+1) for _ in range(n+1)]
    previous = [(0, 0.)]*(m+1)
    for i in range(1, n+1):
        current = [(0, 0.)]*(m+1)
        for j in range(1, m+1):
            best, direction = previous[j], 1
            if current[j-1] > best:
                best, direction = current[j-1], 2
            error = abs(prediction[j-1]-reference[i-1])
            if error <= tolerance_s:
                candidate = (previous[j-1][0]+1, previous[j-1][1]-error)
                if candidate >= best:
                    best, direction = candidate, 3
            current[j], trace[i][j] = best, direction
        previous = current
    result, i, j = [], n, m
    while i and j:
        direction = trace[i][j]
        if direction == 3:
            result.append((i-1, j-1))
            i, j = i-1, j-1
        elif direction == 1:
            i -= 1
        else:
            j -= 1
    return list(reversed(result))


def _errors(values):
    if not values:
        return dict(n=0, mean_absolute_s=None, median_absolute_s=None, bias_s=None, p95_absolute_s=None)
    absolute = sorted(abs(value) for value in values)
    position = .95*(len(absolute)-1)
    low = int(position)
    high = min(low+1, len(absolute)-1)
    p95 = absolute[low]+(absolute[high]-absolute[low])*(position-low)
    return dict(n=len(values), mean_absolute_s=mean(absolute), median_absolute_s=median(absolute),
                bias_s=mean(values), p95_absolute_s=p95)


def verified_reference(path):
    """Bind imported labels back to unchanged originals and professional review."""
    value = _read(path)
    if value.get('schema_version') == 'rehab-independent-review-bundle-1':
        audit = audit_bundle(path)
        if audit['status'] not in ('qualified', 'qualified_partial'):
            _fail('blocked_missing_independent_professional_supervision')
        _fail('explicit_imported_temporal_reference_required')
    required = {'schema_version', 'origin', 'bundle_ref', 'bundle_sha256', 'forms_sha256', 'samples',
                'cohort', 'pending_sample_ids', 'excluded_sample_ids', 'all_source_samples',
                'excluded_samples', 'training_scope', 'pose_supervision', 'product_enabled',
                'diagnosis_or_dosage_allowed', 'created_at', 'implementation_sha256'}
    if (set(value) != required or value['schema_version'] != 'rehab-reviewed-temporal-reference-1'
            or value['origin'] != 'independent_human_review'
            or value['training_scope'] != 'offline_temporal_research_only'
            or any(value[key] is not False for key in ('pose_supervision', 'product_enabled', 'diagnosis_or_dosage_allowed'))):
        _fail('independent_imported_temporal_reference_required')
    audit = audit_bundle(value['bundle_ref'])
    if audit['status'] not in ('qualified', 'qualified_partial'):
        _fail('blocked_missing_independent_professional_supervision')
    bundle = _read(value['bundle_ref'])
    expected = dict(bundle_sha256=audit['bundle_sha256'], forms_sha256=audit['forms_sha256'],
                    samples=audit['approved_rows'], cohort=bundle['samples'],
                    pending_sample_ids=audit['pending_sample_ids'], excluded_sample_ids=audit['excluded_sample_ids'],
                    all_source_samples=audit['samples'], excluded_samples=audit['excluded'])
    if any(value[key] != item for key, item in expected.items()):
        _fail('reference_no_longer_matches_professional_resolution')
    return value


def validate_predictions(value, cohort, labels, bundle_dir):
    """Prediction provenance is declared, not automatically proof of execution."""
    if (set(value) != {'schema_version', 'origin', 'reference_used_for_predictions', 'implementation_sha256',
                       'model_sha256', 'config_sha256', 'samples'}
            or value['schema_version'] != PREDICTION_SCHEMA or value['origin'] != 'declared_backend_export'
            or value['reference_used_for_predictions'] is not False):
        _fail('backend_prediction_manifest_required_no_reference_prefill')
    for key in ('implementation_sha256', 'model_sha256', 'config_sha256'):
        if not isinstance(value[key], str) or re.fullmatch('[0-9a-f]{64}', value[key]) is None:
            _fail('declared_backend_source_model_config_hashes_required')
    rows = value['samples']
    if (not isinstance(rows, list) or len(rows) != len(cohort) or not all(isinstance(row, dict) for row in rows)
            or [row.get('sample_id') for row in rows] != [row['sample_id'] for row in cohort]):
        _fail('complete_requested_split_cohort_required')
    for source, row in zip(cohort, rows):
        required = {'sample_id', 'video_sha256', 'exercise_id', 'side', 'protocol_version', 'split',
                    'time_basis', 'status', 'completed_count', 'boundary_events'}
        if set(row) != required:
            _fail('prediction_sample_schema')
        if any(row[key] != source[key] for key in ('sample_id', 'video_sha256', 'exercise_id',
                                                  'protocol_version', 'split', 'time_basis')):
            _fail('prediction_source_protocol_split_or_clock_mismatch')
        if (row['side'] not in (None, 'left', 'right') or row['status'] not in ('completed', 'failed', 'unavailable')
                or (source['sample_id'] in labels and row['side'] != labels[source['sample_id']]['side'])):
            _fail('prediction_side_or_status_mismatch')
        count = row['completed_count']
        if count is not None and (type(count) is not int or not 0 <= count <= 500):
            _fail('explicit_finite_prediction_count_required')
        events = row['boundary_events']
        if not isinstance(events, dict) or set(events) != set(BOUNDARIES):
            _fail('independent_prediction_boundary_availability_required')
        if row['status'] != 'completed' and (count is not None or any(events[key] is not None for key in BOUNDARIES)):
            _fail('failed_prediction_is_missing_not_zero_or_negative')
        times = _read(Path(bundle_dir)/source['timeline_ref'])['presentation_s']
        for entries in events.values():
            if entries is None:
                continue
            if not isinstance(entries, list) or len(entries) > 500:
                _fail('prediction_event_quota')
            ids, previous = set(), -1.
            for event in entries:
                if (set(event) != {'event_id', 'time_s', 'evidence_kind'}
                        or not isinstance(event['event_id'], str) or re.fullmatch(r'[\w.-]{1,100}', event['event_id']) is None
                        or event['event_id'] in ids or event['evidence_kind'] not in ('observed', 'filtered')):
                    _fail('unique_observed_prediction_events_required')
                ids.add(event['event_id'])
                _time(event['time_s'], source, times)
                if event['time_s'] < previous:
                    _fail('prediction_events_not_chronological')
                previous = event['time_s']
    return rows


def score_sample(label, prediction, tolerance_s):
    """Only independently known tasks are scored; masks do not disappear."""
    count_known = label['observable_count_mask']
    available = prediction['completed_count'] is not None
    count_error = prediction['completed_count']-label['observable_count'] if count_known and available else None
    result = dict(sample_id=label['sample_id'], subject_group=label['source']['subject_group'],
                  exercise_id=label['source']['exercise_id'], side=label['side'], view=label['source']['view'],
                  count_reference_known=count_known, count_prediction_available=available,
                  reference_observable_count=label['observable_count'] if count_known else None,
                  prediction_count=prediction['completed_count'], count_error=count_error,
                  overcount=None if count_error is None else max(count_error, 0),
                  undercount=None if count_error is None else max(-count_error, 0), boundaries={})
    for key in BOUNDARIES:
        reps = label['repetitions']
        reference = [rep['boundaries'][key] for rep in reps if rep['label_masks']['phase'][key]]
        unknown = sum(not rep['label_masks']['phase'][key] for rep in reps)
        inventory_known = bool(reps) and unknown == 0
        entries = prediction['boundary_events'][key]
        predicted = [] if entries is None else [entry['time_s'] for entry in entries]
        matches = match_events(reference, predicted, tolerance_s)
        tp, unmatched = len(matches), len(predicted)-len(matches)
        false_positive = unmatched if inventory_known else 0
        unassessable = 0 if inventory_known else unmatched
        errors = [predicted[j]-reference[i] for i, j in matches]
        result['boundaries'][key] = dict(known_reference_events=len(reference), unknown_reference_boundaries=unknown,
            complete_boundary_inventory=inventory_known, prediction_available=entries is not None,
            prediction_events=None if entries is None else len(predicted), true_positive=tp,
            false_negative=len(reference)-tp, false_positive=false_positive,
            unmatched_prediction_unassessable=unassessable, matches=[dict(reference_index=i, prediction_index=j)
                for i, j in matches], matched_errors_s=errors, timing=_errors(errors))
    return result


def aggregate(rows, cohort_size):
    known = [row for row in rows if row['count_reference_known']]
    errors = [row['count_error'] for row in known if row['count_error'] is not None]
    result = dict(cohort_videos=cohort_size, approved_reference_videos=len(rows),
        approved_reference_coverage=None if not cohort_size else len(rows)/cohort_size,
        known_count_reference_coverage=None if not cohort_size else len(known)/cohort_size,
        known_count_reference_videos=len(known), available_count_predictions=len(errors),
        missing_count_predictions=len(known)-len(errors), count_mae=None if not errors else mean(abs(e) for e in errors),
        count_bias=None if not errors else mean(errors), exact_count_videos=sum(e == 0 for e in errors),
        count_coverage=None if not known else len(errors)/len(known), boundaries={})
    for key in BOUNDARIES:
        items = [row['boundaries'][key] for row in rows]
        totals = {field: sum(item[field] for item in items) for field in
                  ('known_reference_events', 'unknown_reference_boundaries', 'true_positive',
                   'false_positive', 'false_negative', 'unmatched_prediction_unassessable')}
        tp, fp, fn, unknown = (totals[key] for key in ('true_positive', 'false_positive', 'false_negative',
                                                     'unmatched_prediction_unassessable'))
        result['boundaries'][key] = dict(totals, prediction_available_videos=sum(item['prediction_available'] for item in items),
            prediction_missing_videos=sum(not item['prediction_available'] for item in items),
            recall=None if not tp+fn else tp/(tp+fn),
            precision_on_assessable=None if not tp+fp else tp/(tp+fp),
            precision_lower_bound=None if not tp+fp+unknown else tp/(tp+fp+unknown),
            timing=_errors([value for item in items for value in item['matched_errors_s']]))
    return result


def evaluate(reference_path, predictions_path, output_dir, *, split, tolerance_s=.25):
    if split not in ('val', 'test'):
        _fail('explicit_validation_or_test_split_required')
    policy = dict(POLICY, event_tolerance_s=tolerance_s)
    # Validate policy before any output and before viewing predictions.
    match_events([], [], tolerance_s)
    ref_hash = file_hash(reference_path)
    reference = verified_reference(reference_path)
    cohort = [row for row in reference['cohort'] if row['split'] == split]
    labels = {row['sample_id']: row for row in reference['samples'] if row['source']['split'] == split}
    if not labels:
        _fail('blocked_missing_independent_professional_supervision_for_requested_split')
    pred_hash = file_hash(predictions_path)
    predictions = validate_predictions(_read(predictions_path), cohort, labels, Path(reference['bundle_ref']).parent)
    rows = [score_sample(labels[row['sample_id']], row, tolerance_s)
            for row in predictions if row['sample_id'] in labels]
    summary = dict(schema_version='rehab-reviewed-temporal-evaluation-1', split=split,
        scope='offline_count_and_reviewed_boundary_evaluation', clinical_accuracy=None, product_enabled=False,
        prediction_provenance='declared_backend_export_not_proof_of_execution',
        source_reference_sha256=ref_hash, source_predictions_sha256=pred_hash,
        source_bundle_sha256=reference['bundle_sha256'], policy=policy, policy_sha256=canonical_hash(policy),
        pending_sample_ids=[row['sample_id'] for row in cohort if row['sample_id'] in reference['pending_sample_ids']],
        excluded_sample_ids=[row['sample_id'] for row in cohort if row['sample_id'] in reference['excluded_sample_ids']],
        aggregate=aggregate(rows, len(cohort)),
        cohort_prediction_status={row['sample_id']: row['status'] for row in predictions},
        by_subject={group: aggregate([item for item in rows if item['subject_group'] == group],
            sum(item['subject_group'] == group for item in cohort)) for group in sorted({row['subject_group'] for row in cohort})},
        samples=rows, unsupported_metrics=['2d_pose_error', 'physical_execution_without_qualified_sync_reference',
            'quality_classification', 'cue_effectiveness', 'disease_or_dose', 'phone_performance'],
        uncertainty='No frame-independent confidence interval; report per-subject counts and missing reference coverage.')
    if file_hash(reference_path) != ref_hash or file_hash(predictions_path) != pred_hash:
        _fail('evaluation_inputs_changed')
    # Recheck human references again; an old imported reference cannot outlive revised review.
    if verified_reference(reference_path) != reference:
        _fail('professional_reference_changed_during_evaluation')
    output = _new_output(output_dir)
    summary['artifact'] = str(output/'evaluation.json')
    write_json(output/'evaluation.json', summary)
    return summary
