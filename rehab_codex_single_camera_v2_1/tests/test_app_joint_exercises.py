"""Synthetic geometry/state-machine evidence only; no camera or model access."""
import copy
import json
import math
from pathlib import Path

import pytest
import yaml

from app.domain import Context, EXERCISES, Metric, Observation, PoseFrame, PosePerson, RULE_VERSION, dumps
from app.exercises import exercise_spec
from app.quality import PoseAnalyzer
from app.rehab import RehabEngine
from app.settings import default_plan, default_setup


JOINT_CASES = [
    ('shoulder_abduction', 0., 70.),
    ('shoulder_flexion', 0., 80.),
    ('elbow_flexion', 0., 100.),
    ('knee_extension', 90., 20.),
    ('hip_abduction', 0., 35.),
]


def engine_for(exercise, **overrides):
    plan = default_plan(exercise)
    plan.update(overrides)
    return RehabEngine(plan)


def feed(engine, angle, n=15, *, status='VALID', track='one', extra=None):
    for _ in range(n):
        t = 0. if engine.last_t is None else engine.last_t + .1
        metrics = {engine.primary_metric: Metric.of(angle)}
        metrics.update({key: Metric.of(value) for key, value in (extra or {}).items()})
        engine.process(Observation(t, track, status, metrics))


def hip_pose(side='left', degrees=0., t=0.):
    xy = [[550., 100.] for _ in range(17)]
    xy[5], xy[6] = [450., 200.], [650., 200.]
    xy[11], xy[12] = [450., 350.], [650., 350.]
    xy[7], xy[9] = [600., 200.], [700., 200.]
    xy[8], xy[10] = [800., 200.], [900., 200.]
    xy[13], xy[14] = [450., 500.], [650., 500.]
    xy[15], xy[16] = [450., 650.], [650., 650.]
    hi, knee = (11, 13) if side == 'left' else (12, 14)
    outward = -1 if side == 'left' else 1
    xy[knee] = [xy[hi][0]+outward*150*math.sin(math.radians(degrees)),
                xy[hi][1]+150*math.cos(math.radians(degrees))]
    return PoseFrame(Context(1, 'rehab', 'fixture', 'SYNTHETIC', 'TEST'), round(t*10)+1,
                     t, (1280, 720), [PosePerson('one', [200., 50., 1000., 700.], xy, [1.]*17)])


def test_registry_matches_config_and_preserves_existing_names():
    required = {'label', 'joint', 'view', 'metric', 'metric_label', 'required_metrics',
                'rep_value_key', 'target_direction', 'guide', 'ready_hint'}
    config = yaml.safe_load((Path(__file__).resolve().parents[1]/'configs/exercises.yaml').read_text(encoding='utf-8'))
    assert set(EXERCISES) == set(config['exercises'])
    assert {c[0] for c in JOINT_CASES} | {'sit_to_stand'} <= set(EXERCISES)
    assert len(EXERCISES) == 53
    assert EXERCISES['shoulder_abduction'] == '肩外展'
    assert EXERCISES['sit_to_stand'] == '居家坐站'
    assert config['rule_version'] == RULE_VERSION == 'rules-0.3.0'
    for exercise, label in EXERCISES.items():
        spec = exercise_spec(exercise)
        assert required <= spec.keys()
        assert spec['label'] == label
        assert spec['metric'] in spec['required_metrics']
        assert spec['target_direction'] in ('increase', 'decrease')
        assert spec['rep_value_key'] == ('min_angle_deg' if spec['target_direction'] == 'decrease' else 'peak_angle_deg')
        assert '二维投影' in spec['metric_label']
        assert spec['measurement_type'] == '2d_projection' and spec['clinical_rom'] is False
        assert default_plan(exercise)['view'] == default_setup(exercise=exercise)['view'] == spec['view']
        assert default_plan(exercise)['target_angle_deg'] is None


@pytest.mark.parametrize('exercise', ['unknown', '', None, ['shoulder_abduction']])
def test_unknown_actions_are_rejected_at_all_engine_entry_points(exercise):
    for create in (exercise_spec, default_plan, lambda e: default_setup(exercise=e),
                   lambda e: RehabEngine(dict(default_plan(), exercise_id=e))):
        with pytest.raises(ValueError, match='未知康复动作'):
            create(exercise)


def test_registry_and_running_plan_are_detached_snapshots():
    spec = exercise_spec('knee_extension')
    spec.update(target_direction='increase', required_metrics=('hip_y',), label='changed')
    plan = default_plan('knee_extension')
    engine = RehabEngine(plan)
    plan.update(exercise_id='sit_to_stand', target_angle_deg=180, rest_deg=0)
    plan['calibration']['standing_knee'] = 0
    assert engine.spec['target_direction'] == 'decrease'
    assert engine.plan['target_angle_deg'] is None
    assert engine.plan['calibration'] == {}


@pytest.mark.parametrize('exercise', list(EXERCISES))
def test_wrong_view_cannot_enter_engine(exercise):
    with pytest.raises(ValueError, match='机位'):
        engine_for(exercise, view='fixed')


@pytest.mark.parametrize('target', [float('nan'), float('inf'), -1, 181])
def test_invalid_personal_target_is_rejected(target):
    with pytest.raises(ValueError, match='人工角度目标'):
        engine_for('knee_extension', target_angle_deg=target)


@pytest.mark.parametrize('exercise,rest,peak', JOINT_CASES)
def test_joint_round_trip_counts_only_after_observed_return(exercise, rest, peak):
    engine = engine_for(exercise)
    feed(engine, rest)
    feed(engine, peak, n=25)
    assert engine.completed == 0
    assert engine.phase in ('RAISING', 'PEAK_OR_HOLD')
    feed(engine, rest, n=2)
    assert engine.completed == 0
    feed(engine, rest)
    assert engine.completed == 1
    rep = engine.repetitions[0]
    assert rep['completion_status'] == 'COMPLETE' and rep['target_status'] == 'NOT_SET'
    assert rep['min_angle_deg'] == min(rest, peak)
    assert rep['peak_angle_deg'] == max(rest, peak)
    assert rep['range_deg'] == abs(peak-rest)
    assert rep['primary_metric'] == engine.spec['metric']
    assert rep['rise_time_s'] is None
    assert 'max_raise_projection_deg' in rep and 'min_knee_flexion_projection_deg' in rep
    assert rep['motion_range'] == engine.summary()['motion_range']
    feed(engine, peak)
    feed(engine, rest)
    assert engine.completed == 2


@pytest.mark.parametrize('exercise,rest,peak', JOINT_CASES)
@pytest.mark.parametrize('met', [True, False])
def test_manual_target_is_separate_from_completion_and_uses_correct_direction(exercise, rest, peak, met):
    direction = 1 if exercise_spec(exercise)['target_direction'] == 'increase' else -1
    target = peak-direction*5 if met else peak+direction*5
    engine = engine_for(exercise, target_angle_deg=target)
    feed(engine, rest)
    feed(engine, peak)
    feed(engine, rest)
    assert engine.completed == 1
    assert engine.repetitions[0]['target_status'] == ('MET' if met else 'NOT_MET')
    assert engine.summary()['target_met'] == int(met)


@pytest.mark.parametrize('exercise,rest,peak', JOINT_CASES)
def test_starting_in_outbound_pose_does_not_inherit_preview_half_cycle(exercise, rest, peak):
    engine = engine_for(exercise)
    feed(engine, peak)
    feed(engine, rest)
    assert engine.completed == 0 and engine.repetitions == []


@pytest.mark.parametrize('exercise,rest,peak', JOINT_CASES)
def test_stopping_before_return_retains_interrupted_attempt(exercise, rest, peak):
    engine = engine_for(exercise, target_angle_deg=peak)
    feed(engine, rest)
    feed(engine, peak)
    engine.finish('user_stop')
    assert engine.completed == 0
    assert engine.repetitions[0]['completion_status'] == 'INTERRUPTED'
    assert engine.repetitions[0]['target_status'] == 'UNASSESSABLE'
    before = copy.deepcopy(engine.summary())
    feed(engine, rest)
    assert engine.summary() == before


@pytest.mark.parametrize('exercise,rest,peak', JOINT_CASES)
@pytest.mark.parametrize('interrupt', ['missing', 'stream_gap', 'identity', 'multi_person'])
def test_interruption_never_completes_unseen_return(exercise, rest, peak, interrupt):
    engine = engine_for(exercise, target_angle_deg=peak)
    feed(engine, rest)
    feed(engine, peak)
    if interrupt == 'missing':
        before = engine.valid_s
        feed(engine, None, n=8)
        assert engine.valid_s == before
    elif interrupt == 'stream_gap':
        engine.process(Observation(engine.last_t+1., 'one', 'VALID', {engine.primary_metric: Metric.of(rest)}))
    elif interrupt == 'identity':
        feed(engine, rest, n=1, track='other')
    else:
        feed(engine, rest, n=1, status='MULTI_PERSON')
    feed(engine, rest, track='other' if interrupt == 'identity' else 'one')
    assert engine.completed == 0
    assert engine.repetitions[0]['completion_status'] == 'UNASSESSABLE'
    assert engine.repetitions[0]['target_status'] == 'UNASSESSABLE'


def test_recovery_frame_checks_total_missing_duration_not_just_last_frame_gap():
    engine = engine_for('knee_extension')
    feed(engine, 90)
    feed(engine, 20)
    last_good = engine.last_t
    engine.process(Observation(last_good+.4, 'one', 'UNKNOWN', {}))
    engine.process(Observation(last_good+.6, 'one', 'VALID', {'knee_flexion_deg': Metric.of(90)}))
    feed(engine, 90)
    assert engine.completed == 0
    assert engine.repetitions[0]['completion_status'] == 'UNASSESSABLE'


def test_short_missing_observation_is_retained_without_invented_duration():
    engine = engine_for('elbow_flexion')
    feed(engine, 0)
    feed(engine, 80)
    before = engine.valid_s
    feed(engine, None, n=1)
    feed(engine, 80, n=1)
    assert engine.valid_s == before
    feed(engine, 0)
    assert engine.completed == 1
    rep = engine.repetitions[0]
    assert rep['observation_status'] == 'PARTIAL_OBSERVABLE'
    assert rep['metric_validity']['elbow_flexion_deg']['partial_observation']


@pytest.mark.parametrize('exercise,rest,peak', JOINT_CASES)
def test_insufficient_or_disconnected_samples_do_not_produce_range(exercise, rest, peak):
    engine = engine_for(exercise)
    assert engine.summary()['motion_range'] is None
    feed(engine, peak, n=2)
    assert engine.summary()['motion_range'] is None
    feed(engine, None, n=1)
    feed(engine, peak, n=1)
    assert engine.summary()['valid_sample_count'] == 3
    assert engine.summary()['motion_range'] is None
    feed(engine, peak, n=2)
    assert engine.summary()['motion_range'] == {'min_deg': peak, 'max_deg': peak, 'range_deg': 0.}


@pytest.mark.parametrize('exercise,rest,peak', JOINT_CASES)
def test_noise_spike_does_not_set_target_or_report_extreme(exercise, rest, peak):
    direction = 1 if exercise_spec(exercise)['target_direction'] == 'increase' else -1
    target = peak+direction*10
    engine = engine_for(exercise, target_angle_deg=target)
    feed(engine, rest)
    feed(engine, peak)
    feed(engine, peak+direction*15, n=1)
    feed(engine, peak)
    feed(engine, rest)
    rep = engine.repetitions[0]
    assert rep['target_status'] == 'NOT_MET'
    assert rep[engine.spec['rep_value_key']] == peak
    assert engine.summary()['motion_range']['range_deg'] == abs(peak-rest)


def test_knee_extension_needs_no_hip_height_or_sitstand_calibration():
    engine = engine_for('knee_extension')
    assert engine.plan['calibration'] == {}
    assert engine.spec['required_metrics'] == ('knee_flexion_deg',)
    feed(engine, 90)
    feed(engine, 20)
    assert engine.completed == 0
    feed(engine, 90)
    assert engine.completed == 1
    assert engine.repetitions[0]['min_knee_flexion_projection_deg'] == 20.


def test_sitstand_still_requires_hip_height_but_auto_establishes_run_baseline():
    engine = engine_for('sit_to_stand')
    feed(engine, 90, extra={'hip_y': .65})
    feed(engine, 45., extra={'hip_y': .52})
    feed(engine, 5., extra={'hip_y': .4})
    assert engine.automatic_sitstand and engine.plan['calibration']['automatic']
    assert engine.completed == 1
    rep = engine.repetitions[0]
    assert rep['motion_range'] == {'min_deg': 5., 'max_deg': 90., 'range_deg': 85.}
    assert rep['rise_time_s'] > 0
    engine.finish('user_stop')
    assert engine.completed == 1 and rep['lowering_time_s'] is None


@pytest.mark.parametrize('exercise,rest,peak', JOINT_CASES)
def test_training_has_direction_target_and_return_but_assessment_only_measures(exercise, rest, peak):
    engine = engine_for(exercise, submode='training', target_angle_deg=peak)
    feed(engine, rest)
    assert engine.spec['outbound_hint'] in engine.summary()['message']
    assert ('≤' if engine.direction == -1 else '≥') in engine.summary()['message']
    feed(engine, peak)
    message = engine.summary()['message']
    assert '已观察到目标范围' in message and engine.spec['return_hint'] in message
    assert '当前' in message
    assessment = engine_for(exercise, submode='assessment', target_angle_deg=peak)
    feed(assessment, rest)
    feed(assessment, peak)
    assert '测量' in assessment.summary()['message']
    assert '人工目标' not in assessment.summary()['message']
    assert assessment.spec['return_hint'] not in assessment.summary()['message']


def test_training_return_guidance_and_quality_priority_after_plan_complete():
    engine = engine_for('knee_extension', submode='training', target_angle_deg=20., target_reps=1)
    feed(engine, 90.)
    feed(engine, 20.)
    feed(engine, 50., n=3)
    assert engine.phase == 'LOWERING'
    assert engine.spec['return_hint'] in engine.summary()['message']
    feed(engine, 90.)
    assert '已完成计划' in engine.summary()['message']
    feed(engine, None, n=1)
    assert '未计入' in engine.summary()['message']


def test_assessment_quality_evidence_does_not_become_live_coaching():
    engine = engine_for('shoulder_flexion', allowed_elbow_flexion_deg=10., allowed_trunk_tilt_deg=10.)
    feed(engine, 0.)
    feed(engine, 80., extra={'elbow_flexion_deg': 30., 'trunk_tilt_deg': 30.})
    assert len(engine.summary()['current_issues']) == 2
    assert '超出' not in engine.summary()['message']
    feed(engine, 0.)
    assert len(engine.repetitions[0]['issues']) == 2


@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('degrees', [-35., 0., 35.])
def test_hip_angle_is_signed_pelvis_relative_projection(side, degrees):
    observation = PoseAnalyzer(side=side).analyze(hip_pose(side, degrees))
    assert observation.value('hip_abduction_deg') == pytest.approx(degrees)


def test_hip_angle_does_not_change_when_only_trunk_tilts():
    frame = hip_pose(degrees=25.)
    first = PoseAnalyzer().analyze(frame)
    frame.people[0].xy[5][0] += 100
    frame.people[0].xy[6][0] += 100
    tilted = PoseAnalyzer().analyze(frame)
    assert tilted.value('trunk_tilt_deg') > first.value('trunk_tilt_deg')
    assert tilted.value('hip_abduction_deg') == pytest.approx(first.value('hip_abduction_deg'))


@pytest.mark.parametrize('side', ['left', 'right'])
def test_hip_angle_survives_common_pelvis_rotation_mirror_and_uniform_scale(side):
    frame = hip_pose(side, 35.)
    rotation = math.radians(25.)
    frame.people[0].xy = [[550+(x-550)*math.cos(rotation)-(y-350)*math.sin(rotation),
                           350+(x-550)*math.sin(rotation)+(y-350)*math.cos(rotation)]
                          for x, y in frame.people[0].xy]
    assert PoseAnalyzer(side=side).analyze(frame).value('hip_abduction_deg') == pytest.approx(35.)
    frame.people[0].xy = [[1280-x, y] for x, y in frame.people[0].xy]
    assert PoseAnalyzer(side=side).analyze(frame).value('hip_abduction_deg') == pytest.approx(35.)
    frame.people[0].xy = [[2*x, 2*y] for x, y in frame.people[0].xy]
    frame.size = (2560, 1440)
    assert PoseAnalyzer(side=side).analyze(frame).value('hip_abduction_deg') == pytest.approx(35.)


@pytest.mark.parametrize('missing', [11, 12, 13])
def test_missing_pelvis_or_test_knee_invalidates_only_supported_measurements(missing):
    frame = hip_pose(degrees=35.)
    frame.people[0].conf[missing] = .1
    observation = PoseAnalyzer().analyze(frame)
    assert observation.value('hip_abduction_deg') is None
    assert observation.metrics['hip_abduction_deg'].reason
    assert observation.value('elbow_flexion_deg') is not None


def test_hip_does_not_require_shoulders_or_ankles():
    frame = hip_pose(degrees=35.)
    for i in (5, 6, 15, 16):
        frame.people[0].conf[i] = .1
    observation = PoseAnalyzer().analyze(frame)
    assert observation.value('hip_abduction_deg') == pytest.approx(35.)
    assert observation.value('trunk_tilt_deg') is None


@pytest.mark.parametrize('degenerate', ['pelvis', 'thigh', 'vertical_pelvis'])
def test_degenerate_hip_geometry_returns_null(degenerate):
    frame = hip_pose()
    points = frame.people[0].xy
    if degenerate == 'pelvis':
        points[12] = points[11][:]
    elif degenerate == 'thigh':
        points[13] = points[11][:]
    else:
        points[12] = [points[11][0], points[11][1]+100]
    assert PoseAnalyzer().analyze(frame).value('hip_abduction_deg') is None


def test_adduction_and_trunk_only_motion_do_not_count_as_hip_abduction():
    engine = engine_for('hip_abduction')
    feed(engine, 0.)
    feed(engine, -35.)
    feed(engine, 0.)
    assert engine.completed == 0
    analyzer = PoseAnalyzer()
    for seq in range(50):
        frame = hip_pose(t=5.+seq*.1)
        for index in (5, 6):
            frame.people[0].xy[index][0] += 80*math.sin(seq/5)
        engine.process(analyzer.analyze(frame))
    assert engine.completed == 0


def test_hip_geometry_drives_complete_round_trip_without_shoulder_or_sitstand_metrics():
    engine = engine_for('hip_abduction')
    analyzer = PoseAnalyzer()
    for seq, degrees in enumerate([0.]*20+[35.]*20+[0.]*20):
        frame = hip_pose(degrees=degrees, t=seq*.1)
        for index in (5, 6, 15, 16):
            frame.people[0].conf[index] = .1
        engine.process(analyzer.analyze(frame))
    assert engine.completed == 1
    assert engine.repetitions[0]['peak_angle_deg'] == pytest.approx(35., abs=.1)
    assert engine.summary()['clinical_rom'] is False


def test_elbow_and_knee_projection_formulas_have_known_angles():
    frame = hip_pose()
    points = frame.people[0].xy
    points[5], points[7], points[9] = [400., 200.], [400., 350.], [550., 350.]
    points[11], points[13], points[15] = [400., 350.], [400., 500.], [550., 500.]
    observation = PoseAnalyzer().analyze(frame)
    assert observation.value('elbow_flexion_deg') == pytest.approx(90.)
    assert observation.value('knee_flexion_deg') == pytest.approx(90.)
    points[15] = [400., 650.]
    assert PoseAnalyzer().analyze(frame).value('knee_flexion_deg') == pytest.approx(0.)


def test_summary_and_repetitions_are_json_safe_and_do_not_change_on_bad_time():
    engine = engine_for('elbow_flexion')
    feed(engine, 0.)
    feed(engine, 80.)
    feed(engine, 0.)
    before = copy.deepcopy(engine.summary())
    for time in (None, float('nan'), float('inf'), 0., engine.last_t):
        engine.process(Observation(time, 'one', 'VALID', {'elbow_flexion_deg': Metric.of(120.)}))
    assert engine.summary() == before
    saved = json.loads(dumps({'summary': engine.summary(), 'repetitions': engine.repetitions}))
    assert saved['summary']['motion_range'] == {'min_deg': 0., 'max_deg': 80., 'range_deg': 80.}
