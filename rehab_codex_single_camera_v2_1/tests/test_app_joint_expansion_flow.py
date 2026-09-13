"""Full controller/SQLite flows using explicitly synthetic landmark packets."""
import copy
import math
import time
import queue

import numpy as np
import pytest

from app.assessment import build_body_profile, build_training_reference
from app.camera_manager import CameraManager
from app.domain import FramePacket, utc_now
from app.exercises import exercise_spec
from app.landmark_schemas import BACKEND_SCHEMAS, SCHEMAS
from app.reports import export_session, render_report
from app.scene_controller import SceneController
from app.settings import default_setup
from app.storage import Storage
from app.landmark_backend import landmark_python
from app.settings import ROOT
from test_app_landmarks import frame


class SyntheticSession:
    def __init__(self, directory, eid, side):
        self.store = Storage(directory/'fixture.sqlite3')
        self.controller = SceneController(self.store, CameraManager(), test_mode=True)
        self.eid, self.side = eid, side
        self.source = {'kind': 'SYNTHETIC', 'ref': 'synthetic-flow', 'usage_context': 'TEST'}
        self.open()

    def open(self, reference=None):
        self.setup = default_setup(exercise=self.eid)
        self.setup['plan']['side'] = self.side
        self.setup['participant_confirmed'] = True
        if reference:
            self.setup['plan'].update(submode='training', assessment_reference=reference, training_plan_confirmed=True)
        self.controller.open(self.source, self.setup)
        self.t, self.seq = 0., 0
        self.history = []

    def feed(self, angle, count=20):
        c = self.controller
        spec = exercise_spec(self.eid)
        for _ in range(count):
            self.seq += 1
            pose = frame(BACKEND_SCHEMAS[spec['backend']], context=c.context,
                         side=self.side, angle=angle, seq=self.seq, t=self.t)
            if spec['joint'] == 'finger':
                names = SCHEMAS[pose.schema_id]
                finger, joint, _ = self.eid.split('_')
                i = names.index(finger+'_'+joint)
                before = 0 if joint == 'mcp' and finger != 'thumb' else i-1
                pose.people[0].xy[before] = [250., 300.]
                pose.people[0].xy[i] = [300., 300.]
                pose.people[0].xy[i+1] = [300+50*math.cos(math.radians(angle)), 300+50*math.sin(math.radians(angle))]
                pose.target_kind = 'hand'
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            packet = FramePacket(c.context, self.seq, self.t, time.monotonic(), utc_now(), image,
                                 time_basis='synthetic_test_time')
            c.consume(packet, pose)
            if c.latest_observation:
                self.history.append(c.latest_observation)
            self.t += .1

    def calibrate(self):
        c = self.controller
        self.feed(0.)
        c.record_joint_baseline(self.history, 'rest')
        self.history = []
        if exercise_spec(self.eid)['directional_calibration']:
            self.feed(25.)
            c.record_joint_baseline(self.history, 'direction')
            self.history = []
        self.feed(0.)
        self.setup = copy.deepcopy(c.setup)
        self.setup['participant_confirmed'] = True
        c.confirm(self.setup)

    def close(self):
        self.controller.stop('test_end')
        self.store.close()


@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('eid', ['wrist_flexion', 'wrist_extension', 'wrist_radial_deviation', 'wrist_ulnar_deviation',
                                'ankle_dorsiflexion', 'ankle_plantarflexion', 'index_pip_flexion', 'thumb_ip_flexion'])
def test_extended_assessment_save_profile_training_and_reopen(tmp_path, eid, side):
    task = SyntheticSession(tmp_path, eid, side)
    c = task.controller
    try:
        task.calibrate()
        c.start()
        task.feed(0.)
        task.feed(30.)
        task.feed(0.)
        assert c.engine.completed == 1
        sid = c.session['id']
        c.stop('user_stop')
        saved = task.store.get_session(sid)
        assert saved['source_kind'] == 'SYNTHETIC' and saved['usage_context'] == 'TEST'
        assert saved['schema_id'] == BACKEND_SCHEMAS[exercise_spec(eid)['backend']]
        assert len(saved['joint_order']) == len(SCHEMAS[saved['schema_id']])
        assert saved['config_snapshot']['plan']['joint_baseline']['provenance']['side'] == side
        assert 'poses' not in saved
        assert saved['summary']['motion_range']['range_deg'] > 25
        assert '舒适起点记录' in render_report(saved)
        export_session(saved, tmp_path/'export')
        assert not list((tmp_path/'export').glob('*pose*'))
        profile = build_body_profile(task.store.list_sessions(), 'participant-local', 'SYNTHETIC', 'TEST')
        reference = build_training_reference(profile, eid, side)
        assert reference['status'] == 'ASSESSED'
        assert reference['experimental'] is True
        other = build_training_reference(profile, eid, 'right' if side == 'left' else 'left')
        assert other['status'] == 'NOT_ASSESSED'
        task.open(reference)
        task.calibrate()
        c.start()
        assert c.session['assessment_reference']['session_id'] == sid
        assert c.session['config_snapshot']['plan']['target_angle_deg'] is None
        task.feed(0.)
        task.feed(30.)
        assert '人工目标' not in c.summary()['message']
        training_id = c.session['id']
        c.stop('user_stop')
        task.store.close()
        task.store = Storage(tmp_path/'fixture.sqlite3')
        c.storage = task.store
        assert task.store.get_session(training_id)['assessment_reference']['session_id'] == sid
    finally:
        task.close()


def test_saved_or_changed_calibration_does_not_block_a_new_preview(tmp_path):
    task = SyntheticSession(tmp_path, 'ankle_dorsiflexion', 'left')
    try:
        task.calibrate()
        previous = copy.deepcopy(task.controller.setup)
        forged = copy.deepcopy(previous)
        forged['plan']['joint_baseline']['rest_value'] += 10
        task.controller.confirm(forged)
        assert task.controller.confirmed
        task.open()
        task.feed(0.)
        task.controller.confirm(previous)
        assert task.controller.confirmed
        assert task.store.list_sessions() == []
    finally:
        task.close()


def test_manual_zero_motion_is_rejected_but_missing_direction_does_not_block_start(tmp_path):
    task = SyntheticSession(tmp_path, 'wrist_flexion', 'left')
    try:
        task.feed(0.)
        task.controller.record_joint_baseline(task.history, 'rest')
        setup = copy.deepcopy(task.controller.setup)
        setup['participant_confirmed'] = True
        task.history = []
        task.feed(0.)
        with pytest.raises(ValueError, match='不能区分'):
            task.controller.record_joint_baseline(task.history, 'direction')
        task.controller.confirm(setup)
        task.controller.start()
        assert task.controller.session['readiness_policy'] == 'nonblocking-observation-1'
    finally:
        task.close()


@pytest.mark.parametrize('eid', ['ankle_dorsiflexion', 'index_pip_flexion', 'wrist_flexion'])
@pytest.mark.skipif(not landmark_python().is_file() or not (ROOT/'assets/models/pose_landmarker_full.task').is_file()
                    or not (ROOT/'assets/models/hand_landmarker.task').is_file(), reason='Optional official models not prepared')
def test_runtime_routes_single_blank_replay_to_selected_real_backend(tmp_path, eid):
    import cv2
    from app.runtime import Runtime
    video = tmp_path/'synthetic-blank.avi'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320,240))
    assert writer.isOpened()
    for _ in range(20):
        writer.write(np.zeros((240,320,3), dtype=np.uint8))
    writer.release()
    runtime = Runtime(tmp_path/'data')
    try:
        assert runtime.ready.wait(5)
        runtime.command('open', source={'kind': 'REPLAY_FILE', 'ref': 'synthetic-blank-fixture',
                                      'usage_context': 'TEST', 'file': str(video)}, setup=default_setup(exercise=eid))
        deadline = time.monotonic()+15
        while time.monotonic() < deadline and runtime.controller.latest_pose is None:
            time.sleep(.02)
        pose = runtime.controller.latest_pose
        assert pose is not None
        assert pose.schema_id == BACKEND_SCHEMAS[exercise_spec(eid)['backend']]
        assert pose.people == []
        assert runtime.controller.latest_observation.status == 'NO_PERSON_DETECTED'
        assert runtime.controller.session is None
        assert runtime.store.list_sessions() == []
    finally:
        runtime.command('shutdown')
        runtime.thread.join(10)
        assert not runtime.thread.is_alive()
