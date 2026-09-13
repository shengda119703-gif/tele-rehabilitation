from dataclasses import replace
import queue
import time
from unittest.mock import Mock

import pytest

from app.domain import FramePacket
from app.dual_camera import make_dual_source, FramePairer, secondary_context, other_view
from app.runtime import Runtime
from app.scene_controller import SceneController
from app.storage import Storage
from test_dual_camera import manager, REFS, frame
from test_dual_controller import DualFixture


@pytest.fixture
def runtime(tmp_path, manager):
    r = Runtime.__new__(Runtime)
    r.store = Storage(tmp_path/'dual-runtime.sqlite3')
    r.camera = manager
    r.controller = SceneController(r.store, manager)
    r.audio, r.vision = Mock(), Mock()
    r.vision.device = 'cpu'
    r.messages, r.views = queue.Queue(), queue.Queue(maxsize=1)
    r.capture_settings = {}
    r.camera_test, r.camera_test_frames = False, 0
    r.preview_history = []
    r.connect_started_wall = r.last_frame_wall = None
    yield r
    manager.stop()
    r.store.close()


def current_pair(context, primary='frontal', seq=1):
    t = time.monotonic()-.1
    other = other_view(primary)
    front = frame(context, seq, t)
    side = frame(secondary_context(context, other), seq+100, t+.02)
    p = FramePairer(context, primary)
    p.add(primary, front)
    p.add(other, side)
    return p.take()


@pytest.mark.parametrize('primary', ['frontal', 'sagittal'])
def test_raw_pair_test_opens_two_sources_and_never_submits_a_model_or_saves_a_session(runtime, primary):
    r = runtime
    r._execute('camera_test', dict(source=make_dual_source(REFS, primary, 'TEST')))
    assert len([w for w in r.camera.worker.workers.values() if w]) == 2
    data = current_pair(r.controller.context, primary)
    r._receive_packet(data, r.camera.worker)
    view = r.views.get_nowait()
    assert view['camera_test'] and view['packet'].paired_frame is not None
    assert view['dual_camera']['primary_view'] == primary and view['pose'] is None
    assert view['dual_camera']['auxiliary_metrics'] == {} and not view['confirmed']
    r.vision.submit.assert_not_called()
    assert r.store.list_sessions() == []
    r._execute('stop_camera_test', {})
    assert r.camera.worker is None and not r.camera_test


def test_bad_or_duplicate_pair_does_not_refresh_watchdog_or_reuse_auxiliary_frame(runtime):
    r = runtime
    r._execute('camera_test', dict(source=make_dual_source(REFS, 'frontal', 'TEST')))
    frame = current_pair(r.controller.context)
    r._receive_packet(frame, r.camera.worker)
    accepted = r.last_frame_wall
    for bad in (frame, replace(frame, paired_frame=None),
                replace(frame, paired_frame=replace(frame.paired_frame, received_monotonic=time.monotonic()-5))):
        r._receive_packet(bad, r.camera.worker)
        assert r.last_frame_wall == accepted and r.camera_test_frames == 1


def test_preferences_persist_roles_without_current_indices_or_patient_mutations(runtime, tmp_path):
    r = runtime
    devices = {view: dict(ref, index=99) for view, ref in REFS.items()}
    r._execute('remember_camera_pair', dict(devices=devices))
    preferred = r.store.get_camera_pair_preference()
    assert set(preferred) == {'frontal', 'sagittal'}
    assert all('index' not in d for d in preferred.values())
    assert r.store.list_sessions() == [] and r.camera.worker is None
    r.store.close()
    r.store = Storage(tmp_path/'dual-runtime.sqlite3')
    assert r.store.get_camera_pair_preference() == preferred
    with pytest.raises(ValueError):
        r.store.save_camera_pair_preference(dict(REFS, sagittal=REFS['frontal']))
    assert r.store.get_camera_pair_preference() == preferred


def test_preview_suppresses_auxiliary_warning_and_keeps_main_measurement_ready(tmp_path):
    f = DualFixture(tmp_path)
    r = Runtime.__new__(Runtime)
    r.controller = f.c
    r.views = queue.Queue(maxsize=1)
    r.camera_test = False
    try:
        f.emit(.3, auxiliary_missing=True)
        r._view(f.c.latest_packet, f.c.latest_pose)
        view = r.views.get_nowait()
        assert view['measurement_hint'] is None
        assert view['observation_status'] == 'VALID'
        assert view['current_measurement_valid']
        assert view['guidance']['status'] == '辅助指标：本项无法评价'
        assert view['dual_camera']['auxiliary_status'] == 'UNKNOWN'
    finally:
        f.close()


def test_required_primary_missing_is_not_masked_by_an_unrelated_valid_metric(tmp_path):
    f = DualFixture(tmp_path)
    r = Runtime.__new__(Runtime)
    r.controller, r.views, r.camera_test = f.c, queue.Queue(maxsize=1), False
    try:
        f.start()
        packet, pose = f.emit(1., return_input=True)
        pose.people[0].conf[5] = .01
        f.c.consume(packet, pose)
        r._view(packet, pose)
        data = r.views.get_nowait()
        assert data['observation_status'] == 'VALID'  # Another, non-required metric still exists.
        assert not data['current_measurement_valid'] and data['guidance']['phase'] is None
        assert data['guidance']['level'] == 'status'
        assert f.c.engine.completed == 0
    finally:
        f.close()


def test_failed_paired_inference_finishes_the_session_and_preserves_save_gate(tmp_path):
    f = DualFixture(tmp_path)
    r = Runtime.__new__(Runtime)
    r.controller, r.audio, r.vision = f.c, Mock(), Mock()
    r.messages, r.views = queue.Queue(), queue.Queue(maxsize=1)
    r.camera_test = False
    try:
        ctx = f.start()
        f.emit(1.)
        r._inference_failed(f.c.latest_packet, 'fixture auxiliary model error')
        assert f.c.session is None and f.c.context is None
        saved = f.store.get_session(ctx.run_id)
        assert saved['stop_reason'] == 'dual_view_inference_error' and saved['dual_camera']['summary']['paired_observations'] == 1
        view = r.views.get_nowait()
        assert view['packet'] is None and view['error'] == 'fixture auxiliary model error'
    finally:
        f.close()
