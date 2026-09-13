"""Synthetic regressions for reported setup failures, not clinical validation."""
import copy
import math

import pytest

from app.exercises import exercise_spec
from app.landmark_schemas import SCHEMAS
from app.quality import PoseAnalyzer
from app.rehab import RehabEngine
from app.settings import default_plan
from test_app_joint_exercises import feed
from test_axial_and_extension import axial_pose, FunctionalSession
from test_app_joint_expansion_flow import SyntheticSession
from app.assessment import build_body_profile, build_training_reference


@pytest.mark.parametrize('eid', ['neck_flexion', 'neck_extension'])
@pytest.mark.parametrize('side', ['left', 'right'])
def test_side_neck_requires_only_near_eye_and_ear(eid, side):
    pose = axial_pose(eid, 25., side)
    names = SCHEMAS[pose.schema_id]
    required = {side+'_'+part for part in ('eye', 'ear')}
    for index, name in enumerate(names):
        if name not in required:
            pose.people[0].conf[index] = .01
    observation = PoseAnalyzer(side=side, exercise_id=eid).analyze(pose)
    assert observation.value('head_pitch_raw_deg') is not None
    assert observation.value('trunk_tilt_deg') is None


@pytest.mark.parametrize('eid', ['neck_flexion', 'neck_extension'])
@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('part', ['eye', 'ear'])
def test_neck_names_the_actual_missing_near_point(eid, side, part):
    from app.measurement_guidance import measurement_hint
    pose = axial_pose(eid, side=side)
    pose.people[0].conf[SCHEMAS[pose.schema_id].index(side+'_'+part)] = .01
    plan = default_plan(eid)
    plan['side'] = side
    observation = PoseAnalyzer(side=side, exercise_id=eid).analyze(pose)
    hint = measurement_hint(observation, plan, pose.schema_id, preview=True)
    name = ('左' if side == 'left' else '右')+{'eye': '眼', 'ear': '耳'}[part]
    assert name in hint and '未看清' in hint
    assert '双肩' not in hint


@pytest.mark.parametrize('part', ['shoulder', 'hip'])
def test_neck_measurement_does_not_require_shoulder_or_hip(part):
    pose = axial_pose('neck_flexion')
    names = SCHEMAS[pose.schema_id]
    pose.people[0].conf[names.index('left_'+part)] = .01
    observation = PoseAnalyzer(exercise_id='neck_flexion').analyze(pose)
    assert observation.value('head_pitch_raw_deg') is not None


@pytest.mark.parametrize('side', ['left', 'right'])
def test_foreshortened_neck_reference_is_not_guessed(side):
    from app.measurement_guidance import measurement_hint
    pose = axial_pose('neck_flexion', side=side)
    names = SCHEMAS[pose.schema_id]
    ear = pose.people[0].xy[names.index(side+'_ear')]
    pose.people[0].xy[names.index(side+'_eye')] = [ear[0]+1, ear[1]]
    plan = default_plan('neck_flexion')
    plan['side'] = side
    observation = PoseAnalyzer(side=side, exercise_id='neck_flexion').analyze(pose)
    assert observation.value('head_pitch_raw_deg') is None
    assert '参考线' in measurement_hint(observation, plan, pose.schema_id, preview=True)


def test_shoulder_does_not_accept_unusable_hanging_arm_baseline():
    from app.joint_calibration import validate_start_value
    plan = default_plan('shoulder_adduction')
    with pytest.raises(ValueError, match='侧抬臂'):
        validate_start_value(plan, 4.)
    validate_start_value(plan, 55.)


def test_low_adduction_baseline_cannot_bypass_engine_gate():
    plan = default_plan('shoulder_adduction')
    plan['joint_baseline'] = {'rest_value': 4.}
    with pytest.raises(ValueError, match='侧抬臂'):
        RehabEngine(plan)


def test_adduction_ready_and_wrong_direction_messages_explain_start():
    plan = default_plan('shoulder_adduction')
    plan['joint_baseline'] = {'rest_value': 55.}
    engine = RehabEngine(plan)
    feed(engine, 5.)
    assert engine.phase == 'WAIT_READY'
    assert '侧抬臂起点' in engine.summary()['message'] and '55' in engine.summary()['message']
    feed(engine, 55.)
    feed(engine, 100.)
    assert engine.completed == 0 and engine.phase == 'REST'
    assert '向外抬臂' in engine.summary()['message']
    feed(engine, 55.)
    feed(engine, 15.)
    assert engine.completed == 0
    assert '回到侧抬臂起点' in engine.summary()['message']
    feed(engine, 55.)
    assert engine.completed == 1
    assert engine.repetitions[0]['min_angle_deg'] == pytest.approx(15.)


class NearSideSession(FunctionalSession):
    # Keep the real controller/calibration/storage path; erase far-side points
    # at the analyzer input instead of supplying precomputed valid angles.
    def __init__(self, directory, eid, side):
        super().__init__(directory, eid, side)
        original = self.controller.consume
        def consume(packet, pose):
            required = {side+'_'+part for part in ('eye', 'ear')}
            for index, name in enumerate(SCHEMAS[pose.schema_id]):
                if name not in required:
                    pose.people[0].conf[index] = .01
            return original(packet, pose)
        self.controller.consume = consume


@pytest.mark.parametrize('eid', ['neck_flexion', 'neck_extension'])
@pytest.mark.parametrize('side', ['left', 'right'])
def test_neck_single_side_assessment_saves_without_opposite_shoulder(tmp_path, eid, side):
    task = NearSideSession(tmp_path, eid, side)
    try:
        task.calibrate()
        task.controller.start()
        for angle in (task.rest, task.peak, task.rest):
            task.feed(angle)
        assert task.controller.engine.completed == 1
        sid = task.controller.session['id']
        task.controller.stop('user_stop')
        assert task.store.get_session(sid)['summary']['completed'] == 1
        profile = build_body_profile(task.store.list_sessions(), 'participant-local', 'SYNTHETIC', 'TEST')
        task.open(build_training_reference(profile, eid, side))
        task.calibrate()
        task.controller.start()
        for angle in (task.rest, task.peak, task.rest):
            task.feed(angle)
        assert task.controller.engine.completed == 1
    finally:
        task.close()


class ShoulderSession(SyntheticSession):
    def __init__(self, directory, side):
        super().__init__(directory, 'shoulder_adduction', side)
        original = self.controller.consume
        def consume(packet, pose):
            names, person = SCHEMAS[pose.schema_id], pose.people[0]
            x, y = person.xy[names.index(side+'_shoulder')]
            r = math.radians(self.angle)
            person.xy[names.index(side+'_elbow')] = [x+(-1 if side == 'left' else 1)*150*math.sin(r), y+150*math.cos(r)]
            for index, name in enumerate(names):
                if name not in {side+'_'+p for p in ('shoulder', 'elbow')}:
                    person.conf[index] = .01
            return original(packet, pose)
        self.controller.consume = consume

    def feed(self, angle, count=20):
        self.angle = angle
        super().feed(angle, count)

    def calibrate(self):
        self.feed(55.)
        self.controller.record_joint_baseline(self.history, 'rest')
        self.setup = copy.deepcopy(self.controller.setup)
        self.setup['participant_confirmed'] = True
        self.controller.confirm(self.setup)


@pytest.mark.parametrize('side', ['left', 'right'])
def test_shoulder_calibrates_counts_saves_and_trains_with_only_required_points(tmp_path, side):
    task = ShoulderSession(tmp_path, side)
    try:
        for training in (False, True):
            if training:
                profile = build_body_profile(task.store.list_sessions(), 'participant-local', 'SYNTHETIC', 'TEST')
                task.open(build_training_reference(profile, task.eid, side))
            task.calibrate()
            task.controller.start()
            for angle in (55., 15., 55.):
                task.feed(angle)
            assert task.controller.engine.completed == 1
            assert task.controller.latest_observation.value('trunk_tilt_deg') is None
            sid = task.controller.session['id']
            task.controller.stop('user_stop')
            saved = task.store.get_session(sid)
            assert saved['summary']['completed'] == 1
            assert saved['measurement_contract'] == exercise_spec(task.eid)['measurement_contract']
    finally:
        task.close()


def test_invalid_low_start_is_refused_before_saving_calibration(tmp_path):
    task = ShoulderSession(tmp_path, 'left')
    try:
        task.feed(4.)
        with pytest.raises(ValueError, match='侧抬臂'):
            task.controller.record_joint_baseline(task.history, 'rest')
        assert not task.controller.live_joint_baseline
    finally:
        task.close()


def test_runtime_allows_neck_preparation_without_hip(tmp_path):
    import queue
    from app.runtime import Runtime
    task = NearSideSession(tmp_path, 'neck_flexion', 'left')
    try:
        task.feed(0.)
        c = task.controller
        c.latest_pose.people[0].conf[11] = .01
        c.latest_pose.time_s += .1
        c.latest_observation = c.analyzer.analyze(c.latest_pose)
        c.record_joint_baseline(task.history, 'rest')
        runtime = Runtime.__new__(Runtime)
        runtime.controller, runtime.views = c, queue.Queue(maxsize=1)
        runtime.camera_test = False
        runtime._view(c.latest_packet, c.latest_pose)
        view = runtime.views.get_nowait()
        assert '髋' not in (view['measurement_hint'] or '') and view['summary'] == {}
        assert task.store.list_sessions() == []
        runtime.camera_test = True
        runtime._view(c.latest_packet, c.latest_pose)
        assert runtime.views.get_nowait()['measurement_hint'] is None
    finally:
        task.close()
