"""Known-coordinate and saved-flow tests, not human/clinical accuracy evidence."""
import copy
import math
import time

import numpy as np
import pytest

from app.assessment import build_body_profile, build_training_reference
from app.domain import FramePacket, utc_now
from app.exercises import exercise_spec, EXERCISE_IDS
from app.landmark_schemas import SCHEMAS
from app.quality import PoseAnalyzer, angle_delta
from app.geometry import compatible_reports
from app.rehab import RehabEngine
from app.reports import render_report
from app.settings import default_plan
from test_app_landmarks import frame, settled
from test_app_joint_expansion_flow import SyntheticSession
from test_app_joint_exercises import feed


AXIAL = ['neck_lateral_flexion', 'neck_flexion', 'neck_extension',
         'trunk_lateral_flexion', 'trunk_flexion', 'trunk_extension']
EXTENSION = [f'{finger}_{joint}_extension'
             for finger, joints in [('thumb', ['mcp', 'ip']), ('index', ['mcp', 'pip', 'dip']),
                                   ('middle', ['mcp', 'pip', 'dip']), ('ring', ['mcp', 'pip', 'dip']),
                                   ('pinky', ['mcp', 'pip', 'dip'])] for joint in joints]


def test_measurement_contract_mismatch_blocks_historical_comparison():
    keys = ('scene_id', 'exercise_id', 'side', 'profile_id', 'profile_version',
            'source_ref', 'source_kind', 'usage_context', 'rule_version', 'model_manifest_id',
            'preprocess_version', 'preprocessing_hash', 'plan_hash', 'participant_id')
    first = {k: 'synthetic-fixture' for k in keys}
    first['measurement_contract'] = 'whole-segment-projection-1'
    assert compatible_reports(first, copy.deepcopy(first))
    assert not compatible_reports(first, dict(first, measurement_contract='other-definition'))
    assert not compatible_reports(first, dict(first, measurement_contract=None))


def axial_pose(eid, angle=0., side='left', **kwargs):
    pose = frame('coco17-v1', side=side, **kwargs)
    names, xy = SCHEMAS[pose.schema_id], pose.people[0].xy
    def put(name, x, y):
        xy[names.index(name)] = [x, y]
    r = math.radians(angle)
    if eid == 'neck_lateral_flexion':
        put('left_shoulder', 450., 280.)
        put('right_shoulder', 650., 280.)
        put('left_eye', 550.-30*math.cos(r), 150.-30*math.sin(r))
        put('right_eye', 550.+30*math.cos(r), 150.+30*math.sin(r))
    elif eid.startswith('neck_'):
        put(side+'_hip', 500., 480.)
        put(side+'_shoulder', 500., 280.)
        put(side+'_ear', 500., 160.)
        put(side+'_eye', 500.+60*math.cos(r), 160.+60*math.sin(r))
    elif eid == 'trunk_lateral_flexion':
        put('left_hip', 450., 480.)
        put('right_hip', 650., 480.)
        put('left_shoulder', 450.+200*math.sin(r), 480.-200*math.cos(r))
        put('right_shoulder', 650.+200*math.sin(r), 480.-200*math.cos(r))
    else:
        put(side+'_hip', 500., 480.)
        put(side+'_shoulder', 500.+200*math.sin(r), 480.-200*math.cos(r))
    return pose


@pytest.mark.parametrize('eid', AXIAL)
@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('angle', [-30., 0., 25.])
def test_axial_known_projected_change_with_anatomical_side(eid, side, angle):
    spec = exercise_spec(eid)
    rest = settled(axial_pose(eid, side=side), side=side, exercise_id=eid).value(spec['raw_metric'])
    value = settled(axial_pose(eid, angle, side), side=side, exercise_id=eid).value(spec['raw_metric'])
    assert angle_delta(value, rest) == pytest.approx(angle)
    assert spec['experimental'] and spec['clinical_rom'] is False
    pose = axial_pose(eid, angle, side)
    pose.people[0].xy = [[x*.8+100, y*.8+40] for x,y in pose.people[0].xy]
    scaled = settled(pose, side=side, exercise_id=eid).value(spec['raw_metric'])
    assert scaled == pytest.approx(value)


@pytest.mark.parametrize('eid', AXIAL)
def test_mirror_requires_new_calibration_not_reversing_anatomical_labels(eid):
    spec = exercise_spec(eid)
    values = []
    for angle in (0., 25.):
        pose = axial_pose(eid, angle)
        pose.people[0].xy = [[1280-x, y] for x,y in pose.people[0].xy]
        values.append(settled(pose, exercise_id=eid).value(spec['raw_metric']))
    assert angle_delta(values[1], values[0]) == pytest.approx(-25)


@pytest.mark.parametrize('eid', ['neck_lateral_flexion', 'trunk_lateral_flexion'])
def test_rigid_rotation_does_not_become_relative_head_or_pelvis_motion(eid):
    spec = exercise_spec(eid)
    original = axial_pose(eid, 20.)
    before = settled(original, exercise_id=eid).value(spec['raw_metric'])
    r = math.radians(15)
    original.people[0].xy = [[x*math.cos(r)-y*math.sin(r)+200,
                              x*math.sin(r)+y*math.cos(r)] for x,y in original.people[0].xy]
    after = settled(original, exercise_id=eid).value(spec['raw_metric'])
    assert after == pytest.approx(before)


def test_head_pitch_uses_the_fixed_screen_reference_without_requiring_the_hip():
    spec = exercise_spec('neck_flexion')
    original = axial_pose('neck_flexion', 20.)
    before = settled(original, exercise_id='neck_flexion').value(spec['raw_metric'])
    r = math.radians(15)
    original.people[0].xy = [[x*math.cos(r)-y*math.sin(r)+200,
                              x*math.sin(r)+y*math.cos(r)] for x, y in original.people[0].xy]
    after = settled(original, exercise_id='neck_flexion').value(spec['raw_metric'])
    assert angle_delta(after, before) == pytest.approx(15.)


@pytest.mark.parametrize('eid,necessary', [('neck_lateral_flexion', 'left_eye'), ('neck_flexion', 'left_ear'),
                                         ('neck_extension', 'left_eye'), ('trunk_lateral_flexion', 'right_hip'),
                                         ('trunk_flexion', 'left_shoulder'), ('trunk_extension', 'left_hip')])
def test_missing_necessary_points_are_not_zero_or_replaced_by_other_side(eid, necessary):
    pose = axial_pose(eid, 25.)
    names = SCHEMAS[pose.schema_id]
    pose.people[0].conf[names.index(necessary)] = .01
    spec = exercise_spec(eid)
    assert settled(pose, exercise_id=eid).value(spec['raw_metric']) is None
    pose = axial_pose(eid, 25.)
    pose.people[0].conf[names.index('left_wrist')] = .01
    assert settled(pose, exercise_id=eid).value(spec['raw_metric']) is not None


@pytest.mark.parametrize('eid,a,b', [('neck_lateral_flexion', 'left_eye', 'right_eye'),
                                   ('neck_flexion', 'left_ear', 'left_eye'),
                                   ('trunk_lateral_flexion', 'left_hip', 'right_hip'),
                                   ('trunk_flexion', 'left_hip', 'left_shoulder')])
def test_short_or_collapsed_reference_lines_refuse_measurement(eid, a, b):
    pose = axial_pose(eid)
    names, xy = SCHEMAS[pose.schema_id], pose.people[0].xy
    xy[names.index(b)] = [xy[names.index(a)][0]+1, xy[names.index(a)][1]]
    assert settled(pose, exercise_id=eid).value(exercise_spec(eid)['raw_metric']) is None


@pytest.mark.parametrize('eid', EXTENSION)
def test_finger_extension_starts_flexed_and_has_decreasing_target(eid):
    spec = exercise_spec(eid)
    assert spec['metric'] == eid.replace('_extension', '_flexion_deg')
    plan = default_plan(eid)
    plan.update(joint_baseline={'rest_value': 70.}, target_angle_deg=25.)
    engine = RehabEngine(plan)
    feed(engine, 10.)
    assert engine.phase == 'WAIT_READY' and engine.completed == 0
    feed(engine, 70.)
    feed(engine, 20.)
    assert engine.completed == 0
    feed(engine, 70.)
    assert engine.completed == 1 and engine.repetitions[0]['target_status'] == 'MET'
    assert engine.repetitions[0]['min_angle_deg'] == 20.


class FunctionalSession(SyntheticSession):
    def feed(self, angle, count=20):
        if self.eid not in AXIAL:
            return super().feed(angle, count)
        for _ in range(count):
            self.seq += 1
            pose = axial_pose(self.eid, angle, self.side, context=self.controller.context, seq=self.seq, t=self.t)
            packet = FramePacket(self.controller.context, self.seq, self.t, time.monotonic(), utc_now(),
                                 np.zeros((720, 1280, 3), dtype=np.uint8), time_basis='synthetic_test_time')
            self.controller.consume(packet, pose)
            if self.controller.latest_observation:
                self.history.append(self.controller.latest_observation)
            self.t += .1

    def calibrate(self):
        self.rest, self.peak = (70., 20.) if self.eid in EXTENSION else (0., -25. if 'extension' in self.eid else 25.)
        c = self.controller
        self.feed(self.rest)
        c.record_joint_baseline(self.history, 'rest')
        self.history = []
        if self.eid in AXIAL:
            self.feed(self.peak)
            c.record_joint_baseline(self.history, 'direction')
            self.history = []
        self.feed(self.rest)
        self.setup = copy.deepcopy(c.setup)
        self.setup['participant_confirmed'] = True
        c.confirm(self.setup)


@pytest.mark.parametrize('eid', AXIAL+EXTENSION)
@pytest.mark.parametrize('side', ['left', 'right'])
def test_new_actions_assess_save_summarize_and_execute_two_training_sets(tmp_path, eid, side):
    task = FunctionalSession(tmp_path, eid, side)
    c = task.controller
    try:
        task.calibrate()
        c.start()
        for angle in (task.rest, task.peak, task.rest):
            task.feed(angle)
        assert c.engine.completed == 1
        sid = c.session['id']
        c.stop('user_stop')
        saved = task.store.get_session(sid)
        assert saved['source_kind'] == 'SYNTHETIC' and saved['usage_context'] == 'TEST'
        assert saved['measurement_contract'] == exercise_spec(eid)['measurement_contract']
        profile = build_body_profile(task.store.list_sessions(), 'participant-local', 'SYNTHETIC', 'TEST')
        ref = build_training_reference(profile, eid, side)
        assert ref['status'] == 'ASSESSED' and ref['motion_range']['range_deg'] > 20
        assert exercise_spec(eid)['label'] in render_report(saved)
        task.open(ref)
        c.setup['plan'].update(target_reps=1, target_sets=2)
        task.calibrate()
        c.start()
        for group in range(2):
            for angle in (task.rest, task.peak, task.rest):
                task.feed(angle)
            if group == 0:
                assert c.engine.stage == 'RESTING'
                c.training_control('next_set', setup_confirmed=True)
        assert c.engine.completed == 2 and c.engine.stage == 'COMPLETE'
        training_id = c.session['id']
        c.stop('user_stop')
        assert task.store.get_session(training_id)['summary']['completed_sets'] == 2
        assert c.camera.worker is None
    finally:
        task.close()
