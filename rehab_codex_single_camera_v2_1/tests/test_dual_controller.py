import copy
from dataclasses import replace
import math

import numpy as np
import pytest

from app.camera_manager import CameraManager
from app.domain import FramePacket, PoseFrame, PosePerson
from app.dual_camera import make_dual_source, FramePairer, secondary_context, other_view
from app.scene_controller import SceneController
from app.settings import default_setup
from app.storage import Storage


DEVICES = {view: dict(name=view+' synthetic device', path=view+'-synthetic-path', backend=700)
           for view in ('frontal', 'sagittal')}


class DualFixture:
    def __init__(self, tmp_path, exercise='shoulder_abduction'):
        self.store = Storage(tmp_path/'two-view.sqlite3')
        self.camera = CameraManager()
        self.c = SceneController(self.store, self.camera, test_mode=True)
        self.setup = default_setup(exercise=exercise)
        self.setup.update(participant_confirmed=True,
                          dual_camera=dict(same_participant_confirmed=True, primary_view=self.setup['view']))
        self.source = make_dual_source(DEVICES, self.setup['view'], 'TEST')
        self.source['kind'] = 'SYNTHETIC'
        self.seq = 0
        self.open()

    def open(self):
        self.c.open(self.source, self.setup)
        self.emit(0., 0.)

    def emit(self, t, angle=0., *, auxiliary_missing=False, auxiliary_people=1,
             auxiliary_track='1', auxiliary_size=(1280, 720), malformed=None, return_input=False):
        self.seq += 1
        ctx = self.c.context
        primary_view = self.source['dual_camera']['primary_view']
        secondary_view = other_view(primary_view)
        raw = np.zeros((720, 1280, 3), np.uint8)
        packet = FramePacket(ctx, self.seq, t, t, '', raw)
        auxiliary = FramePacket(secondary_context(ctx, secondary_view), self.seq+1000, t+.02, t+.02, '',
                                np.zeros((auxiliary_size[1], auxiliary_size[0], 3), np.uint8))
        pairer = FramePairer(ctx, primary_view)
        pairer.add(primary_view, packet, now=t+.03)
        pairer.add(secondary_view, auxiliary, now=t+.03)
        pair = pairer.take()
        points = [[120., 100.] for _ in range(17)]
        points[5], points[6], points[11], points[12] = [200., 150.], [300., 150.], [200., 300.], [300., 300.]
        rad = math.radians(angle)
        points[7], points[9] = [200+100*math.sin(rad), 150+100*math.cos(rad)], [200+150*math.sin(rad), 150+150*math.cos(rad)]
        points[13], points[15] = [200., 400.], [200., 500.]
        main_pose = PoseFrame(ctx, self.seq, t, (1280, 720),
                              [PosePerson(ctx.epoch+':1', [100, 50, 500, 600], points, [1.]*17)],
                              model_manifest_id='primary-synthetic-model')
        aux_points = copy.deepcopy(points)
        aux_points[5] = [400., 150.]  # Distinct auxiliary projection must not alter primary shoulder angle.
        aux_people = [PosePerson(auxiliary.context.epoch+':'+auxiliary_track, [100, 50, 500, 600],
                                 aux_points, ([0.]*17 if auxiliary_missing else [1.]*17)) for _ in range(auxiliary_people)]
        auxiliary_pose = PoseFrame(auxiliary.context, auxiliary.seq, auxiliary.time_s, auxiliary_size, aux_people,
                                   model_manifest_id='secondary-synthetic-model')
        main_pose.paired_pose = auxiliary_pose
        if malformed == 'foreign_context':
            auxiliary_pose.context = ctx
        elif malformed == 'different_seq':
            auxiliary_pose.seq += 9
        elif malformed == 'missing_pose':
            main_pose.paired_pose = None
        if return_input:
            return pair, main_pose
        return self.c.consume(pair, main_pose)

    def start(self):
        self.c.confirm(self.setup)
        return self.c.start()

    def cycle(self):
        t = 1.
        for angle in (0., 90., 0.):
            for _ in range(20):
                self.emit(t, angle)
                t += .1

    def close(self):
        if self.c.pending:
            self.c.retry_save()
        self.c.stop('fixture_end')
        self.store.close()


@pytest.fixture
def dual(tmp_path):
    f = DualFixture(tmp_path)
    yield f
    f.close()


def test_dual_preview_does_not_require_manual_identity_or_visible_joints(dual):
    bad = copy.deepcopy(dual.setup)
    bad['dual_camera']['same_participant_confirmed'] = False
    setup = dual.c.confirm(bad)
    assert dual.c.confirmed
    assert setup['dual_camera']['confirmed_sizes'] == {'frontal': [1280, 720], 'sagittal': [1280, 720]}
    assert not setup['dual_camera']['same_participant_confirmed']


def test_absent_auxiliary_does_not_prevent_confirmation_and_start(dual):
    dual.emit(.2, auxiliary_people=0)
    dual.c.confirm(dual.setup)
    dual.c.start()
    assert dual.c.state == 'ONLINE'


def test_additional_auxiliary_person_does_not_prevent_confirmation(dual):
    dual.emit(.2, auxiliary_people=2)
    dual.c.confirm(dual.setup)
    dual.c.start()
    assert dual.c.state == 'ONLINE'


def test_independent_projections_count_once_and_persist_both_sources_without_images_or_unauthorized_poses(dual):
    ctx = dual.start()
    dual.cycle()
    assert dual.c.engine.completed == 1
    dual.c.stop('user_stop')
    saved = dual.store.get_session(ctx.run_id)
    assert saved['source_kind'] == 'SYNTHETIC' and saved['usage_context'] == 'TEST'
    assert 'poses' not in saved and 'raw_frames' not in saved
    paired = saved['dual_camera']
    assert paired['version'] == 'dual-2d-1' and paired['primary_view'] == 'frontal'
    assert paired['streams']['frontal']['model_manifest_id'] == 'primary-synthetic-model'
    assert paired['streams']['sagittal']['model_manifest_id'] == 'secondary-synthetic-model'
    assert paired['summary']['paired_observations'] == 60
    assert paired['summary']['max_receive_delta_s'] == pytest.approx(.02)
    first = paired['observations'][0]
    assert first['primary_time_s'] != first['secondary_time_s'] and first['primary_seq'] != first['secondary_seq']
    assert first['auxiliary_metrics']['aux_trunk_sagittal_deg']['value'] > 40
    assert first['primary_metrics']['raise_deg']['value'] == pytest.approx(0.)


def test_explicit_pose_consent_covers_both_views_and_preserves_contexts(dual):
    dual.setup['poses_consent'] = True
    ctx = dual.start()
    dual.emit(1., 0.)
    dual.c.stop('user_stop')
    saved = dual.store.get_session(ctx.run_id)
    primary = saved['poses'][0]['pose']
    assert primary['paired_pose']['context']['source_ref'] != primary['context']['source_ref']
    assert primary['paired_pose']['seq'] != primary['seq']


def test_auxiliary_metric_loss_keeps_evidenced_primary_cycle_and_marks_main_only(dual):
    dual.start()
    for i in range(20):
        dual.emit(1+i*.1, 0.)
    for i in range(20):
        dual.emit(3+i*.1, 90., auxiliary_missing=True)
    for i in range(20):
        dual.emit(5+i*.1, 0.)
    assert dual.c.engine.completed == 1
    missing = dual.c.session['dual_camera']['observations'][20]
    assert missing['primary_metrics']['raise_deg']['valid']
    assert not missing['jointly_valid'] and missing['auxiliary_status'] == 'UNKNOWN'
    assert missing['identity_confirmed'] and missing['primary_used'] and missing['main_measurement_usable']
    assert all(m['observation_status'] == 'VALID' for m in dual.c.session['metrics'])


def test_auxiliary_geometry_is_optional_for_confirmation_but_manual_identity_is_required(dual):
    dual.emit(.2, auxiliary_missing=True)
    dual.start()
    assert dual.c.state == 'ONLINE'


@pytest.mark.parametrize('view', ['primary', 'auxiliary'])
def test_reacquired_tracking_keeps_the_acknowledgement_without_user_interruption(dual, view):
    dual.c.confirm(dual.setup)
    packet, pose = dual.emit(.2, return_input=True)
    (pose if view == 'primary' else pose.paired_pose).people[0].track_key = 'another-person'
    dual.c.consume(packet, pose)
    assert dual.c.confirmed and not dual.c.confirmation_withdrawn
    dual.c.start()


@pytest.mark.parametrize('view', ['primary', 'auxiliary'])
def test_acknowledgement_survives_when_the_participant_temporarily_leaves(dual, view):
    dual.c.confirm(dual.setup)
    for t in (.2, 1., 2.4):
        packet, pose = dual.emit(t, return_input=True)
        if view == 'primary':
            pose.people = []
        else:
            pose.paired_pose.people = []
        dual.c.consume(packet, pose)
    assert dual.c.confirmed and not dual.c.confirmation_withdrawn
    dual.c.start()


@pytest.mark.parametrize('view', ['primary', 'auxiliary'])
def test_acknowledgement_stays_valid_when_a_carer_is_visible(dual, view):
    dual.c.confirm(dual.setup)
    packet, pose = dual.emit(.2, return_input=True)
    if view == 'primary':
        pose.people = pose.people*2
    else:
        pose.paired_pose.people = pose.paired_pose.people*2
    dual.c.consume(packet, pose)
    assert dual.c.confirmed and not dual.c.confirmation_withdrawn


def test_auxiliary_geometry_fluctuation_does_not_repeat_the_final_confirmation(dual):
    dual.c.confirm(dual.setup)
    dual.emit(.2, auxiliary_missing=True)
    assert dual.c.confirmed
    dual.c.start()


def test_absent_auxiliary_person_does_not_exclude_primary_or_break_cycle(dual):
    dual.start()
    for i in range(20):
        dual.emit(1+i*.1, 0.)
    for i in range(20):
        dual.emit(3+i*.1, 90., auxiliary_people=0)
    for i in range(20):
        dual.emit(5+i*.1, 0.)
    assert dual.c.engine.completed == 1
    row = dual.c.session['dual_camera']['observations'][20]
    assert row['primary_used'] and row['identity_confirmed']
    assert not row['auxiliary_focus_available']
    assert dual.c.session['metrics'][20]['metrics']['raise_deg']['valid']


@pytest.mark.parametrize('view', ['primary', 'auxiliary'])
def test_visible_person_without_detector_track_uses_spatial_focus(dual, view):
    dual.start()
    packet, pose = dual.emit(1., return_input=True)
    (pose if view == 'primary' else pose.paired_pose).people[0].track_key = None
    dual.c.consume(packet, pose)
    assert dual.c.session is not None and dual.c.state == 'ONLINE'
    row = dual.c.session['dual_camera']['observations'][-1]
    assert row['primary_used'] and row['identity_confirmed']


def test_additional_primary_person_does_not_stop_when_auxiliary_geometry_is_missing(dual):
    dual.start()
    pair, pose = dual.emit(1., auxiliary_missing=True, return_input=True)
    pose.people.append(copy.deepcopy(pose.people[0]))
    dual.c.consume(pair, pose)
    assert dual.c.session is not None and dual.c.context is not None
    row = dual.c.session['dual_camera']['observations'][-1]
    assert row['primary_status'] == 'VALID' and not row['jointly_valid']


def test_nested_capture_statistics_track_latest_primary_and_secondary_observation(dual):
    ctx = dual.start()
    packet, pose = dual.emit(1., return_input=True)
    packet.received_fps, packet.paired_frame.received_fps = 28., 19.
    pose.inference_ms, pose.paired_pose.inference_ms = 20., 24.
    dual.c.consume(packet, pose)
    dual.c.stop()
    saved = dual.store.get_session(ctx.run_id)
    streams = saved['dual_camera']['streams']
    assert streams['frontal']['actual_capture']['received_fps'] == 28.
    assert streams['sagittal']['actual_capture']['received_fps'] == 19.
    assert streams['frontal']['actual_capture']['inference_ms'] == 20.


@pytest.mark.parametrize('change', [dict(auxiliary_people=2), dict(auxiliary_track='other')])
def test_additional_person_or_tracker_change_does_not_end_the_task(dual, change):
    dual.start()
    dual.emit(1., 0.)
    dual.emit(1.2, 0., **change)
    assert dual.c.context is not None and dual.c.session is not None
    assert dual.c.state == 'ONLINE'


def test_secondary_resolution_change_stops_before_measuring_and_requires_new_setup(dual):
    ctx = dual.start()
    with pytest.raises(RuntimeError, match='尺寸'):
        dual.emit(1., auxiliary_size=(640, 480))
    assert dual.c.context is None
    assert dual.store.get_session(ctx.run_id)['stop_reason'] == 'secondary_frame_shape_changed'


@pytest.mark.parametrize('malformed', ['foreign_context', 'different_seq', 'missing_pose'])
def test_mismatched_auxiliary_pose_is_never_consumed_as_a_valid_pair(dual, malformed):
    dual.start()
    with pytest.raises(ValueError):
        dual.emit(1., malformed=malformed)
    assert dual.c.engine.completed == 0 and dual.c.session['dual_camera']['observations'] == []


def test_save_failure_keeps_complete_dual_snapshot_for_retry(dual, monkeypatch):
    ctx = dual.start()
    dual.cycle()
    original = dual.store.save_session
    monkeypatch.setattr(dual.store, 'save_session', lambda s: (_ for _ in ()).throw(OSError('fixture disk full')))
    with pytest.raises(RuntimeError, match='保存失败'):
        dual.c.stop('user_stop')
    assert dual.c.state == 'SAVE_FAILED' and dual.c.pending['dual_camera']['summary']['paired_observations'] == 60
    assert dual.camera.worker is None
    monkeypatch.setattr(dual.store, 'save_session', original)
    dual.c.retry_save()
    assert dual.store.get_session(ctx.run_id)['summary']['completed'] == 1


def test_dual_input_is_not_accepted_for_unrelated_monitoring_scenes(dual):
    with pytest.raises(ValueError, match='康复'):
        dual.c.open(dual.source, default_setup('activity'))


def test_stale_preview_pair_cannot_be_reused_after_start(dual):
    packet, pose = dual.emit(.2, return_input=True)
    dual.start()
    assert dual.c.consume(packet, pose) is False
    assert dual.c.session['dual_camera']['observations'] == []
