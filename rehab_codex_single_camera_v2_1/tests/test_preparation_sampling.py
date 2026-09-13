"""Synthetic state sequences; no camera or human-accuracy claim."""
import queue
from dataclasses import replace
from unittest.mock import Mock

import pytest

from app.runtime import Runtime
from test_dual_controller import DualFixture


@pytest.fixture
def sampling(tmp_path, monkeypatch):
    fixture = DualFixture(tmp_path)
    runtime = Runtime.__new__(Runtime)
    runtime.controller, runtime.store, runtime.camera = fixture.c, fixture.store, fixture.camera
    runtime.messages, runtime.views = queue.Queue(), queue.Queue(maxsize=1)
    runtime.preview_history, runtime.preparation = [], None
    runtime.camera_test = False
    runtime.audio, runtime.vision = Mock(), Mock()
    clock = [0.]
    monkeypatch.setattr('app.runtime.time.monotonic', lambda: clock[0])
    yield fixture, runtime, clock
    fixture.close()


def hold(fixture, runtime, start=1., *, missing=False):
    for i in range(11):
        fixture.emit(start+i*.1, 0., auxiliary_missing=missing)
        runtime.preview_history.append(fixture.c.latest_observation)


def test_countdown_discards_earlier_frames_and_records_only_new_stable_suffix(sampling):
    f, r, clock = sampling
    hold(f, r)
    assert len(r.preview_history) == 11
    r._begin_preparation('joint_baseline', 'rest')
    assert not r.preview_history and not f.c.confirmed
    hold(f, r, 2.1)
    clock[0] = 3.
    r._tick_preparation()
    assert not r.preview_history and not f.c.live_joint_baseline
    # Merely waiting cannot turn the previous image into a stable sampled baseline.
    clock[0] = 3.2
    r._tick_preparation()
    assert r.preparation is not None and not f.c.live_joint_baseline
    hold(f, r, 3.2)
    clock[0] = 4.3
    r._tick_preparation()
    assert r.preparation is None and f.c.live_joint_baseline['rest_value'] == pytest.approx(0.)
    assert f.c.state == 'PREVIEW' and not f.c.confirmed and f.c.session is None


@pytest.mark.parametrize('change', ['size', 'context', 'stop', 'cancel'])
def test_sampling_cancels_instead_of_relabelling_changed_context(sampling, change):
    f, r, clock = sampling
    r._begin_preparation('joint_baseline', 'rest')
    if change in ('stop', 'cancel'):
        r._execute('stop' if change == 'stop' else 'cancel_preparation', {})
    else:
        packet, pose = f.emit(.2, return_input=True)
        if change == 'size':
            pose.paired_pose.size = (640, 480)
            # A fresh size change is normally captured in the next pair; here bind the new observed size directly.
            f.c.latest_pose = pose
        else:
            f.c.context = replace(f.c.context, generation=f.c.context.generation+1)
        r._tick_preparation()
    assert r.preparation is None and not f.c.live_joint_baseline
    assert not r.preview_history


def test_reacquired_tracking_keeps_sampling_without_asking_again(sampling):
    f, r, clock = sampling
    r._begin_preparation('joint_baseline', 'rest')
    clock[0] = 3.
    r._tick_preparation()
    hold(f, r, 3.1)
    packet, pose = f.emit(4.3, 0., return_input=True)
    pose.people[0].track_key = 'changed-person'
    pose.paired_pose.people[0].track_key = 'changed-secondary'
    f.c.consume(packet, pose)
    r.preview_history.append(f.c.latest_observation)
    clock[0] = 4.4
    r._tick_preparation()
    # Spatial focus stays stable when only the detector's id changes, so the
    # participant is not asked to repeat a completed hold.
    assert r.preparation is None and f.c.live_joint_baseline['rest_value'] == pytest.approx(0.)
    assert f.c.live_joint_baseline['provenance']['track_key'] == f.c.latest_observation.track_key


def test_additional_people_do_not_cancel_preparation_sampling(sampling):
    f, r, clock = sampling
    r._begin_preparation('joint_baseline', 'rest')
    f.c.latest_observation = replace(f.c.latest_observation, status='MULTI_PERSON')
    clock[0] = 2.
    r._tick_preparation()
    assert r.preparation is not None


def test_short_dropout_is_absorbed_but_persistent_absence_stops_sampling(sampling):
    f, r, clock = sampling
    r._begin_preparation('joint_baseline', 'rest')
    f.c.latest_observation = replace(f.c.latest_observation, status='NO_PERSON_DETECTED')
    clock[0] = .3
    r._tick_preparation()
    assert r.preparation is not None
    clock[0] = 2.
    r._tick_preparation()
    assert r.preparation is None
    assert '取景' in list(r.messages.queue)[-1]['text']


def test_missing_geometry_can_recover_but_failed_window_never_samples_old_data(sampling):
    f, r, clock = sampling
    r._begin_preparation('joint_baseline', 'rest')
    clock[0] = 3.
    r._tick_preparation()
    for i in range(9):
        packet, pose = f.emit(1+i*.1, return_input=True)
        pose.people[0].conf = [0.]*17
        f.c.consume(packet, pose)
        r.preview_history.append(f.c.latest_observation)
    clock[0] = 3.+Runtime.sampling_window_s+.1
    r._tick_preparation()
    assert r.preparation is None and not f.c.live_joint_baseline
    messages = list(r.messages.queue)
    assert messages[-1]['kind'] == 'preparation' and '再试一次' in messages[-1]['text']


def test_replay_requests_new_media_after_countdown_without_using_wall_time_as_pose_time(sampling):
    f, r, clock = sampling
    f.c.source['kind'] = 'REPLAY_FILE'
    r.camera.worker = Mock()
    r._begin_preparation('joint_baseline', 'rest')
    assert not r.camera.worker.preview_segment.called
    clock[0] = 3.
    r._tick_preparation()
    r.camera.worker.preview_segment.assert_called_once_with(1.2)
    assert not f.c.live_joint_baseline
    r.camera.worker = None


def test_old_preview_command_cannot_start_sampling_in_new_context(sampling):
    f, r, clock = sampling
    stale = replace(f.c.context, generation=f.c.context.generation-1)
    with pytest.raises(ValueError, match='预览已变化'):
        r._execute('prepare_sample', dict(sample='joint_baseline', position='rest', expected_context=stale))
    assert r.preparation is None


def test_inference_results_captured_before_sampling_are_not_counted_when_they_arrive_late(sampling):
    f, r, clock = sampling
    r._begin_preparation('joint_baseline', 'rest')
    clock[0] = 3.
    r._tick_preparation()
    for i in range(11):
        f.emit(1+i*.1)
        r._collect_preview_observation(f.c.latest_packet)
    assert r.preview_history == []
    r._tick_preparation()
    assert not f.c.live_joint_baseline
    for i in range(11):
        f.emit(3.1+i*.1)
        r._collect_preview_observation(f.c.latest_packet)
    clock[0] = 4.2
    r._tick_preparation()
    assert r.preparation is None and f.c.live_joint_baseline
