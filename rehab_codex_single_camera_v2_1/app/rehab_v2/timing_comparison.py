"""Read-only comparison of observed durations, never a recovery conclusion.

Meaning/conditions are compared separately from the identity of each fact.
Each repetition freezes its own timing context: a later set's calibration or
model signature cannot reinterpret an earlier repetition. Old facts without
that context remain readable, but are not silently backfilled for comparison.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
from statistics import median

from ..domain import digest
from .timing import ALGORITHM_VERSION, TIMING_VERSION

CONTEXT_VERSION = 'rehab-timing-context-1'
COMPARISON_VERSION = 'rehab-timing-comparison-1'
METRICS = ('outbound_s', 'endpoint_dwell_s', 'return_s', 'target_hold_s')
PARAMETERS = ('ready_s', 'dwell_s', 'max_gap_s', 'max_age_ms',
              'return_tolerance_deg', 'turn_delta_deg')
TIME_FIELDS = ('outbound_min_s', 'outbound_max_s', 'return_min_s', 'return_max_s', 'hold_min_s')


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def freeze_context(plan, spec, baseline, signature, calibration_epoch, *, source_epoch):
    """Called once when a real repetition starts, before later recalibration."""
    signature = signature or ()
    domain = dict(schema_id=signature[1] if len(signature) == 5 else None,
                  model_manifest_id=signature[2] if len(signature) == 5 else None,
                  frame_size=list(signature[3]) if len(signature) == 5 else None,
                  time_basis=signature[4] if len(signature) == 5 else None,
                  coordinate_space='raw_image_pixels', preprocess_version='causal-ema-schema-0.3.0')
    start = ({key: deepcopy(baseline.get(key)) for key in ('raw_value', 'unit', 'reference')}
             if baseline else None)
    return dict(version=CONTEXT_VERSION, calibration_epoch=calibration_epoch,
        source_epoch=source_epoch, source_ref=signature[0] if len(signature) == 5 else None,
        participant_id=plan.get('participant_id'), submode=plan['submode'],
        protocol=deepcopy(spec), domain=domain, baseline=start,
        parameters={key: plan[key] for key in PARAMETERS}, target_angle_deg=plan['target_angle_deg'],
        timing_plan=deepcopy(plan['timing_plan']),
        support=dict(use_of_hands=plan['use_of_hands'], needs_companion=plan.get('needs_companion')),
        dose=(dict(target_reps=plan.get('target_reps'), target_sets=plan.get('target_sets'),
                   rest_between_sets_s=plan.get('rest_between_sets_s')) if plan['submode'] == 'training'
              else None))


def _contract(item, rep, metric):
    timing = rep.get('movement_timing')
    if not isinstance(timing, dict):
        return None, 'missing_observed_timing'
    context = timing.get('comparison_context')
    if not isinstance(context, dict) or context.get('version') != CONTEXT_VERSION:
        return None, 'missing_or_unsupported_per_rep_timing_context'
    if timing.get('version') != TIMING_VERSION or timing.get('algorithm_version') != ALGORITHM_VERSION:
        return None, 'unsupported_timing_algorithm'
    if timing.get('count_gate') is not False:
        return None, 'unsupported_timing_count_semantics'
    if (type(context.get('calibration_epoch')) is not int or context['calibration_epoch'] < 0
            or context['calibration_epoch'] != rep.get('calibration_epoch')):
        return None, 'timing_calibration_reference_mismatch'
    if not isinstance(context.get('source_epoch'), str) or not context['source_epoch']:
        return None, 'missing_or_mismatched_timing_evidence'
    domain = context.get('domain')
    spec = context.get('protocol')
    plan = item['frozen_plan']['plan']
    if not isinstance(domain, dict) or not isinstance(spec, dict):
        return None, 'missing_timing_measurement_contract'
    if spec != item['frozen_plan'].get('protocol'):
        return None, 'timing_protocol_binding_mismatch'
    if (not context.get('participant_id') or context['participant_id'] != plan.get('participant_id')
            or context.get('submode') != plan.get('submode')):
        return None, 'missing_or_mismatched_timing_scope'
    for field in ('schema_id', 'model_manifest_id', 'coordinate_space', 'preprocess_version', 'time_basis'):
        if not isinstance(domain.get(field), str) or not domain[field]:
            return None, 'missing_timing_measurement_contract'
    size = domain.get('frame_size')
    if not isinstance(size, list) or len(size) != 2 or any(type(v) is not int or v <= 0 for v in size):
        return None, 'missing_timing_measurement_contract'
    # Nominal frame-index time is not promoted to measured source-clock time.
    if domain['time_basis'] not in ('mapped_source_seconds', 'opencv_media_pts'):
        return None, 'unsupported_or_nominal_time_basis'
    if timing.get('time_basis') != domain['time_basis']:
        return None, 'timing_clock_reference_mismatch'
    refs = timing.get('evidence_refs')
    if not isinstance(refs, dict):
        return None, 'missing_or_mismatched_timing_evidence'
    for name in ('first', 'latest'):
        ref = refs.get(name)
        if (not isinstance(ref, dict) or ref.get('source_epoch') != context.get('source_epoch')
                or type(ref.get('seq')) is not int or ref['seq'] < 0
                or not _number(ref.get('time_s')) or ref['time_s'] < 0):
            return None, 'missing_or_mismatched_timing_evidence'
    if refs['latest']['seq'] < refs['first']['seq'] or refs['latest']['time_s'] < refs['first']['time_s']:
        return None, 'invalid_timing_evidence_order'
    parameters = context.get('parameters')
    goals = context.get('timing_plan')
    if (not isinstance(parameters, dict) or set(parameters) != set(PARAMETERS)
            or any(not _number(v) for v in parameters.values())
            or not isinstance(goals, dict) or set(goals) != set(TIME_FIELDS)
            or any(v is not None and not _number(v) for v in goals.values())):
        return None, 'missing_timing_parameters'
    if any(parameters[key] != plan.get(key) for key in PARAMETERS) or goals != plan.get('timing_plan'):
        return None, 'timing_parameter_binding_mismatch'
    if 'target_angle_deg' not in context or context['target_angle_deg'] != plan.get('target_angle_deg'):
        return None, 'timing_target_binding_mismatch'
    if context['target_angle_deg'] is not None and not _number(context['target_angle_deg']):
        return None, 'invalid_timing_target'
    support = context.get('support')
    expected_support = dict(use_of_hands=plan.get('use_of_hands'), needs_companion=plan.get('needs_companion'))
    if not isinstance(support, dict) or support != expected_support:
        return None, 'timing_support_binding_mismatch'
    if context['submode'] == 'training':
        dose = context.get('dose')
        if (not isinstance(dose, dict) or set(dose) != {'target_reps', 'target_sets', 'rest_between_sets_s'}
                or any(type(dose.get(k)) is not int or dose[k] < 1 for k in ('target_reps', 'target_sets'))
                or any(dose[k] != plan.get(k) for k in dose)
                or (dose['rest_between_sets_s'] is not None
                    and (not _number(dose['rest_between_sets_s']) or dose['rest_between_sets_s'] < 0))):
            return None, 'timing_dose_binding_mismatch'
    elif context['submode'] != 'assessment' or context.get('dose') is not None:
        return None, 'unsupported_timing_submode'
    baseline = context.get('baseline')
    if (not isinstance(baseline, dict) or not _number(baseline.get('raw_value'))
            or baseline.get('unit') != spec.get('unit') or baseline.get('reference') != spec.get('baseline_reference')):
        return None, 'missing_timing_baseline'
    seated = spec.get('exercise_id') == 'sit_to_stand'
    expected_method = 'protocol_standing_range_2' if seated else 'peak_band_3deg_median3'
    expected_mode = 'observed_standing_and_seated_rearm' if seated else 'after_observed_cycle'
    expected_anchor = ('protocol_standing_knee_range' if seated else
                       'prescribed_projected_metric' if context['target_angle_deg'] is not None else None)
    if timing.get('method') != expected_method or timing.get('phase_timing_mode') != expected_mode:
        return None, 'timing_phase_definition_mismatch'
    if metric == 'target_hold_s' and timing.get('hold_anchor') != expected_anchor:
        return None, 'timing_hold_definition_mismatch'
    source = item['source']
    if not source.get('source_kind') or not source.get('usage_context'):
        return None, 'missing_timing_source_scope'
    return dict(version=COMPARISON_VERSION, metric=metric, unit='second',
        participant_id=context['participant_id'], submode=context['submode'],
        source_kind=source['source_kind'], usage_context=source['usage_context'],
        protocol=spec, domain=domain, baseline=baseline, parameters=parameters,
        target_angle_deg=context['target_angle_deg'], timing_plan=goals, support=support,
        dose=context['dose'], timing_version=timing['version'], algorithm_version=timing['algorithm_version'],
        method=timing['method'], phase_timing_mode=timing['phase_timing_mode'],
        hold_anchor=expected_anchor if metric == 'target_hold_s' else None), None


def _summary(item, metric):
    reps = item['snapshot']['repetitions']
    reasons, contracts, values = Counter(), {}, []
    complete = 0
    for rep in reps:
        if rep.get('completion_status') != 'COMPLETE':
            reasons['repetition_not_complete'] += 1
            continue
        complete += 1
        contract, error = _contract(item, rep, metric)
        if error:
            reasons[error] += 1
            continue
        contracts[digest(contract)] = contract
        timing = rep['movement_timing']
        measured = timing.get(metric)
        if not isinstance(measured, dict) or measured.get('valid') is not True:
            reasons[(measured.get('reason') if isinstance(measured, dict) else None) or 'timing_metric_unavailable'] += 1
        elif not _number(measured.get('value')) or measured['value'] < 0:
            reasons['invalid_observed_duration'] += 1
        elif metric == 'target_hold_s' and (timing.get('partial_observation') is not False
                                           or timing.get('cycle_complete') is not True):
            reasons['partial_hold_is_observed_lower_bound'] += 1
        else:
            values.append(measured['value'])
    return dict(attempts=len(reps), complete_repetitions=complete, valid_complete_repetitions=len(values),
        excluded_repetitions=len(reps)-len(values), exclusion_reasons=dict(reasons),
        median_s=median(values) if values else None, distinct_condition_count=len(contracts)), contracts


def compare_timing(left, right):
    """Only compare homogeneous, complete, valid recorded durations.

    Invalid attempts remain in denominators/reasons; no missing value becomes
    zero. Independent repetitions are not paired by index. A median difference
    is descriptive, not a clinical improvement or a statistical significance.
    The service verifies ownership, finalization and visual digests first.
    """
    rows = {}
    for metric in METRICS:
        a, ac = _summary(left, metric)
        b, bc = _summary(right, metric)
        changed = []
        if not a['valid_complete_repetitions'] or not b['valid_complete_repetitions']:
            reason = 'no_valid_complete_timing_on_both_sides'
        elif len(ac) != 1 or len(bc) != 1:
            reason = 'heterogeneous_recorded_conditions'
        elif a['valid_complete_repetitions'] != a['complete_repetitions'] or b['valid_complete_repetitions'] != b['complete_repetitions']:
            reason = 'incomplete_timing_coverage'
        else:
            ca, cb = next(iter(ac.values())), next(iter(bc.values()))
            changed = [key for key in ca if ca[key] != cb[key]]
            reason = 'contract_changed' if changed else 'compatible_recorded_conditions'
        compatible = reason == 'compatible_recorded_conditions'
        rows[metric] = dict(comparable=compatible, reason=reason, changed_fields=changed, left=a, right=b,
            left_contract_digests=sorted(ac), right_contract_digests=sorted(bc),
            right_minus_left_median_s=(b['median_s']-a['median_s'] if compatible else None))
    return dict(version=COMPARISON_VERSION, unit='second', metrics=rows, read_only=True,
        scope='observed_source_clock_durations_under_recorded_conditions',
        clinical_comparable=False, improvement_assessed=False, significance_assessed=False,
        sampling_invariance_validated=False, frontend_not_connected=True)
