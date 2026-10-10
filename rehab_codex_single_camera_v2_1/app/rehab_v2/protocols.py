from __future__ import annotations

import copy
import math

from . import PROTOCOL_VERSION

PROTOCOLS = {
    'shoulder_abduction': dict(
        exercise_id='shoulder_abduction', metric='raise_deg', unit='degree',
        metric_version='upper-arm-image-vertical-2', view='frontal',
        required_joints=['{side}_shoulder', '{side}_elbow'],
        optional_quality_metrics={'elbow_flexion_deg': ['{side}_shoulder', '{side}_elbow', '{side}_wrist'],
                                  'trunk_tilt_deg': ['left_shoulder', 'right_shoulder', 'left_hip', 'right_hip']},
        start_posture='arm_at_comfortable_side', ready_max_deg=20., excursion_min_deg=10.,
        phases=['WAIT_READY', 'REST', 'RAISING', 'PEAK_OR_HOLD', 'LOWERING'],
        completion='observed_departure_turn_and_return', baseline_reference='image_down_vertical',
        eligibility_rule_ref='existing-general-activity-rules-1-no-dosage-change'),
    'sit_to_stand': dict(
        exercise_id='sit_to_stand', metric='knee_flexion_deg', unit='degree',
        metric_version='knee-180-minus-internal-2', view='sagittal',
        required_joints=['{side}_hip', '{side}_knee', '{side}_ankle'],
        optional_quality_metrics={}, start_posture='verified_seated',
        seated_min_deg=60., standing_max_deg=25., excursion_min_deg=15.,
        phases=['WAIT_READY', 'SEATED_READY', 'RISING', 'STANDING_REACHED', 'LOWERING'],
        completion='observed_seated_to_standing_then_seated_rearm',
        baseline_reference='verified_seated_knee', standard_chair_test=False,
        eligibility_rule_ref='existing-general-activity-rules-1-with-recorded-support'),
    'rehab_squat': dict(
        exercise_id='rehab_squat', metric='knee_flexion_deg', unit='degree',
        metric_version='knee-180-minus-internal-2', view='sagittal',
        required_joints=['{side}_hip', '{side}_knee', '{side}_ankle'],
        optional_quality_metrics={}, start_posture='standing', ready_max_deg=25.,
        excursion_min_deg=10.,
        phases=['WAIT_READY', 'REST', 'RAISING', 'PEAK_OR_HOLD', 'LOWERING'],
        completion='observed_knee_flexion_turn_and_standing_return',
        baseline_reference='verified_standing_knee', fixed_fitness_depth=False,
        eligibility_rule_ref='existing-plan-eligibility-no-new-prescription'),
}


def protocol(exercise_id, side='left', view=None):
    if exercise_id not in PROTOCOLS or side not in ('left', 'right'):
        raise ValueError('unsupported_exercise_or_side')
    value = copy.deepcopy(PROTOCOLS[exercise_id])
    if view is not None and view != value['view']:
        raise ValueError('unsupported_camera_view')
    value.update(protocol_version=PROTOCOL_VERSION, side=side,
                 required_joints=[j.format(side=side) for j in value['required_joints']],
                 required_metric=value['metric'], missing_policy='pause_evidence_keep_short_context',
                 quality_version='explicit-observed-constraints-2',
                 target_definition=('personal_prescribed_knee_flexion_reduction' if exercise_id == 'sit_to_stand'
                                    else 'personal_prescribed_projected_metric_maximum'),
                 validity='current_observed_or_causally_filtered_required_joints_only')
    value['optional_quality_metrics'] = {name: [j.format(side=side) for j in joints]
                                         for name, joints in value['optional_quality_metrics'].items()}
    return value


def number(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + ': finite number required')
    if not minimum <= value <= maximum:
        raise ValueError(name + ': out of bounds')
    return float(value)


def validated_plan(value):
    plan = copy.deepcopy(value)
    spec = protocol(plan['exercise_id'], plan.get('side', 'left'), plan.get('view'))
    plan.update(side=spec['side'], view=spec['view'])
    for key, default, lo, hi in (
        ('ready_s', 1., .1, 5.), ('dwell_s', .18, .05, 2.),
        ('max_gap_s', .5, .1, 2.), ('max_age_ms', 500., 10., 2000.),
        ('return_tolerance_deg', 8., 1., 15.), ('turn_delta_deg', 5., 1., 10.),
        ('issue_hold_s', .5, .1, 3.), ('feedback_cooldown_s', 8., 1., 60.)):
        plan[key] = number(plan.get(key, default), key, lo, hi)
    for key in ('target_angle_deg', 'allowed_elbow_flexion_deg', 'allowed_trunk_tilt_deg'):
        if plan.get(key) is not None:
            plan[key] = number(plan[key], key, 0., 180.)
        else:
            plan[key] = None
    # No automatic repetitions, sets, target or support prescription is created here.
    plan.setdefault('submode', 'training')
    plan.setdefault('use_of_hands', 'not_recorded')
    return plan, spec
