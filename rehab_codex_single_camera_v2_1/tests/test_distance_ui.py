import copy
from dataclasses import replace
import time
from unittest.mock import Mock

import numpy as np
import pytest
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest

from app.domain import Context
from app.settings import default_plan, default_setup
from app.exercises import EXERCISE_IDS, exercise_spec
from app.exercise_instructions import exercise_instructions
from app.exercise_guides import guide_steps
from app.ui.distance_coach import DistanceCoach
from app.ui.widgets import VideoCanvas
from test_product_navigation import desktop
from test_camera_selection import camera
from test_clarity_ui import enumerate_result, drain_commands
from test_camera_test_runtime import packet


def state(eid='shoulder_abduction', phase='RAISING', stage=None):
    data = dict(state='ONLINE', context=None, confirmed=True, observation_status='VALID',
                summary=dict(phase=phase, completed=2, metrics={exercise_spec(eid)['metric']: dict(valid=True, value=35)}))
    if stage:
        data['summary']['training'] = dict(stage=stage, set_number=1, target_sets=2, target_reps=5, set_reps=2,
                                          can_pause=stage == 'ACTIVE', can_resume=stage == 'PAUSED', can_next_set=stage == 'RESTING')
    return data


@pytest.fixture
def coach(desktop, tmp_path):
    w, runtime, app = desktop
    coach = DistanceCoach(w, root=tmp_path)
    coach.show()
    app.processEvents()
    yield coach, app
    coach.close()


def render(coach, data, plan=None, **kwargs):
    coach.render(data, plan or default_plan(), mirror=True, source_kind='SYNTHETIC', usage_context='TEST', **kwargs)


@pytest.mark.parametrize('eid', EXERCISE_IDS)
def test_all_existing_actions_keep_exact_step_text_in_large_guidance(coach, eid):
    c, app = coach
    plan = default_plan(eid)
    info = exercise_instructions(eid)
    for phase, key, step in [('WAIT_READY', 'start', 0), ('REST', 'move', 1),
                             ('RAISING', 'move', 1), ('LOWERING', 'return', 2)]:
        render(c, state(eid, phase), plan)
        assert c.presentation.currentWidget() is c.guide
        assert c.guide.instruction.text() == info[key] and c.guide.step_index == step
        assert '待补充' in c.guide.picture.text()
    app.processEvents()
    assert c.guide.instruction.font().pixelSize() >= 32


@pytest.mark.parametrize('status', ['OFFLINE', 'ERROR', 'SAVE_FAILED', 'PRIVACY_PAUSED'])
def test_interrupted_input_hides_previous_motion_picture_and_text(coach, status):
    c, app = coach
    render(c, state())
    render(c, dict(state=status))
    assert c.presentation.currentWidget() is c.hold
    assert '暂停' in c.hold.text() and not c.finish.isEnabled()
    assert c.canvas.image is None


@pytest.mark.parametrize('stage', ['PAUSED', 'RESTING', 'COMPLETE', 'FINISHED'])
def test_training_nonactive_states_do_not_keep_prompting_movement(coach, stage):
    c, app = coach
    plan = dict(default_plan(), submode='training')
    render(c, state(stage='ACTIVE'), plan)
    render(c, state(stage=stage), plan)
    assert c.presentation.currentWidget() is c.hold
    assert c.guide.isHidden() and c.finish.isEnabled()


@pytest.mark.parametrize('observation', ['UNKNOWN', 'MULTI_PERSON', 'NO_PERSON_DETECTED', None])
def test_missing_evidence_holds_large_guidance_not_bad_motion(coach, observation):
    c, app = coach
    data = state()
    data['observation_status'] = observation
    render(c, data)
    assert c.presentation.currentWidget() is c.hold and '暂停' in c.hold.text()
    assert '错误动作' not in c.feedback.text()


def test_main_metric_invalid_blocks_guidance_even_if_person_is_visible(coach):
    c, app = coach
    data = state()
    data['summary']['metrics']['raise_deg']['valid'] = False
    render(c, data)
    assert c.presentation.currentWidget() is c.hold


def test_training_resume_and_next_set_keep_manual_confirm_and_busy_gates(coach):
    c, app = coach
    plan = dict(default_plan(), submode='training')
    calls = []
    c.control_requested.connect(lambda action, confirmed: calls.append((action, confirmed)))
    render(c, state(stage='PAUSED'), plan)
    assert not c.training.pause.isEnabled()
    c.training.confirm.setChecked(True)
    c.training.pause.click()
    assert calls == [('resume', True)]
    render(c, state(stage='RESTING'), plan)
    assert not c.training.confirm.isChecked() and not c.training.next_set.isEnabled()
    c.training.confirm.setChecked(True)
    c.set_controls(False)
    assert not c.training.next_set.isEnabled()
    assert c.finish.isEnabled() and c.privacy.isEnabled()  # Stop remains available while other commands are busy.
    c.set_controls(True)
    c.training.next_set.click()
    assert calls[-1] == ('next_set', True)
    resting = state(stage='RESTING')
    resting['summary']['training'].update(rest_remaining_s=8.2, can_next_set=False)
    render(c, resting, plan)
    assert '9 秒' in c.hold.text() and not c.training.next_set.isEnabled()


def test_sit_to_stand_recovery_shows_return_without_changing_count(coach):
    c, app = coach
    data = state('sit_to_stand', 'STANDING_REACHED', 'RECOVERY')
    before = copy.deepcopy(data)
    render(c, data, dict(default_plan('sit_to_stand'), submode='training'))
    assert c.guide.step_index == 2 and '回坐' in c.guide.instruction.text()
    assert data == before


def test_images_use_exact_side_and_stage_and_do_not_follow_camera_mirroring(coach, tmp_path):
    c, app = coach
    path = guide_steps('shoulder_abduction', 'left', root=tmp_path)[1]['image_path']
    path.parent.mkdir(parents=True)
    picture = QImage(320, 240, QImage.Format.Format_RGB32)
    picture.fill(0xff223344)
    picture.setPixel(0, 0, 0xffff0000)
    assert picture.save(str(path))
    render(c, state())
    assert c.guide.image_available and c.guide._pixmap.toImage().pixel(0, 0) == 0xffff0000
    c.resize(1100, 730)
    app.processEvents()
    assert c.guide.picture.pixmap().width() <= c.guide.picture.width()
    assert c.guide.picture.pixmap().height() <= c.guide.picture.height()
    render(c, state(), dict(default_plan(), side='right'))
    assert not c.guide.image_available


def test_live_watchdog_hides_old_motion_when_no_new_view_arrives(coach):
    c, app = coach
    context = Context(5, 'rehab', 'live-fixture', 'LIVE_CAMERA', 'TEST', run_id='test')
    frame = packet(context)
    data = dict(state(), context=context, packet=frame)
    render(c, data)
    assert c.presentation.currentWidget() is c.guide and c.canvas.image is not None
    c._check_freshness(now=frame.received_monotonic+3.1)
    assert c.presentation.currentWidget() is c.hold and '超时' in c.hold.text()
    assert c.canvas.image is None
    render(c, dict(data, packet=packet(context, 2)))
    assert c.presentation.currentWidget() is c.guide
    quality = dict(data, packet=packet(context, 3))
    quality['summary'] = dict(quality['summary'], training=state(stage='ACTIVE')['summary']['training'],
                              current_issues=[dict(rule_id='elbow_flexion')], message='可见屈肘超出已设范围')
    render(c, quality, dict(default_plan(), submode='training'))
    assert c.hold.text() == quality['summary']['message']
    c._check_freshness(now=quality['packet'].received_monotonic+4)
    assert '超时' in c.hold.text()  # Do not leave stale quality corrections on screen either.
    c.reject()
    assert not c.freshness_timer.isActive()


def test_live_old_packet_cannot_resume_guidance(coach):
    c, app = coach
    context = Context(2, 'rehab', 'live-fixture', 'LIVE_CAMERA', 'TEST')
    frame = replace(packet(context), received_monotonic=time.monotonic()-4)
    render(c, dict(state(), context=context, packet=frame))
    assert c.presentation.currentWidget() is c.hold and c.canvas.image is None


@pytest.mark.parametrize('phase,message', [('PEAK_OR_HOLD', '按舒适幅度完成出程后，缓慢回位'),
                                          ('RAISING', '已观察到目标范围；缓慢回位；当前 40°')])
def test_training_return_feedback_never_shows_opposite_outbound_picture(coach, phase, message):
    c, app = coach
    data = state(phase=phase, stage='ACTIVE')
    data['summary']['message'] = message
    render(c, data, dict(default_plan(), submode='training'))
    assert c.guide.step_index == 2 and '放下' in c.guide.instruction.text()
    original = c.guide.select_step
    c.guide.select_step = Mock(wraps=original)
    render(c, data, dict(default_plan(), submode='training'))
    c.guide.select_step.assert_not_called()  # Repeated return frames do not decode two images each time.


def test_existing_quality_feedback_takes_priority_over_motion_picture(coach):
    c, app = coach
    data = state(stage='ACTIVE')
    data['summary'].update(current_issues=[dict(rule_id='elbow_flexion')], message='本次上举时可见屈肘超出已设范围')
    render(c, data, dict(default_plan(), submode='training'))
    assert c.presentation.currentWidget() is c.hold
    assert c.hold.text() == data['summary']['message']


def test_long_error_never_pushes_stop_controls_off_screen(coach):
    c, app = coach
    c.resize(1100, 730)
    data = dict(state(), error='测试错误详细信息。'*100)
    render(c, data)
    app.processEvents()
    assert (c.width(), c.height()) == (1100, 730)
    assert c.feedback.toolTip() == data['error']
    assert c.rect().contains(c.finish.mapTo(c, c.finish.rect().bottomRight()))


def test_default_mirror_and_replay_preferences_remain_display_only(desktop):
    w, runtime, app = desktop
    assert default_setup()['mirror'] and w.mirror.isChecked() and w.canvas.mirror
    assert runtime.calls == []
    w._choose_catalog_exercise('elbow_flexion')
    assert w._read_setup()['mirror'] and w.setup['plan']['side'] == 'left'
    w.mirror.setChecked(False)
    w._select_scene('activity')
    assert not w.canvas.mirror
    w.source_kind.setCurrentIndex(w.source_kind.findData('REPLAY_FILE'))
    assert not w.canvas.mirror
    w.mirror.setChecked(True)
    w.source_kind.setCurrentIndex(w.source_kind.findData('LIVE_CAMERA'))
    assert not w.canvas.mirror
    w.source_kind.setCurrentIndex(w.source_kind.findData('REPLAY_FILE'))
    assert w.canvas.mirror
    assert not any(name in ('open', 'start', 'camera_test') for name, _ in runtime.calls)


def test_camera_test_mirror_toggle_is_shared_without_reopening_input(desktop):
    w, runtime, app = desktop
    enumerate_result(w, [camera()])
    w._start_camera_test()
    dialog = w.camera_test_dialog
    assert dialog.canvas.mirror and dialog.mirror_toggle.isChecked()
    before = list(runtime.calls)
    dialog.mirror_toggle.setChecked(False)
    assert not dialog.canvas.mirror and not w.canvas.mirror and not w.mirror.isChecked()
    assert runtime.calls == before
    w._handle_message(dict(kind='camera_test_stopped'))
    drain_commands(w)
    w._choose_catalog_exercise('knee_extension')
    assert not w._read_setup()['mirror']


def test_mirrored_pixels_and_roi_round_trip_leave_raw_frame_unchanged(desktop):
    w, runtime, app = desktop
    canvas = VideoCanvas()
    canvas.resize(640, 400)
    canvas.show()
    ctx = Context(1, 'rehab', 'fixture', 'SYNTHETIC', 'TEST')
    frame = packet(ctx)
    frame.image[:, :80] = [255, 0, 0]
    frame.image[:, 80:] = [0, 0, 255]
    original = frame.image.copy()
    canvas.set_frame(frame)
    app.processEvents()
    rect = canvas.image_rect()
    position = QPointF(rect.left()+rect.width()*.25, rect.center().y())
    canvas.mirror = False
    canvas.update()
    app.processEvents()
    assert canvas.grab().toImage().pixelColor(position.toPoint()).blue() == 255
    canvas.mirror = True
    canvas.update()
    app.processEvents()
    assert canvas.grab().toImage().pixelColor(position.toPoint()).red() == 255
    for x, y in ((.1, .25), (.75, .9)):
        shown = canvas.map_raw(x, y)
        assert canvas.to_raw(shown) == pytest.approx((x, y))
    assert np.array_equal(frame.image, original)
    assert canvas.image.pixelColor(0, 0).blue() == 255
    canvas.close()


def start_large_view(w):
    w._choose_catalog_exercise('shoulder_abduction')
    w._accept_context_frames = True
    context = Context(20, 'rehab', 'fixture', 'SYNTHETIC', 'TEST', run_id='test-run')
    w._render_view(dict(state(), context=context, packet=packet(context)))
    return context


def test_real_run_view_opens_large_guidance_once_and_escape_does_not_stop(desktop):
    w, runtime, app = desktop
    assert w.distance_coach is None
    ctx = start_large_view(w)
    c = w.distance_coach
    assert c and c.isVisible() and c.canvas.mirror and c.guide.step_index == 1
    before = list(runtime.calls)
    QTest.keyClick(c, Qt.Key.Key_Escape)
    assert not c.isVisible() and runtime.calls == before and w.state == 'ONLINE'
    w._render_view(dict(state(), context=ctx, packet=packet(ctx, 2)))
    assert not c.isVisible()
    w._open_distance_coach()
    assert c.isVisible()
    c.privacy.click()
    assert runtime.calls[-1] == ('privacy', {'reason': 'privacy_pause'})


def test_auto_large_view_can_be_disabled_and_never_starts_recording(desktop):
    w, runtime, app = desktop
    w.auto_distance.setChecked(False)
    start_large_view(w)
    assert w.distance_coach is None
    assert not any(name in ('open', 'start') for name, _ in runtime.calls)


def test_pending_save_returns_to_recovery_controls_and_blocks_large_view(desktop):
    w, runtime, app = desktop
    start_large_view(w)
    w._render_view(dict(state='SAVE_FAILED', context=None, confirmed=False, summary={}, error='保存失败'))
    assert not w.distance_coach.isVisible()
    assert w.retry_button.isVisible() and not w.distance_button.isEnabled()
    w._open_distance_coach()
    assert not w.distance_coach.isVisible()


def test_saved_after_unexpected_disconnect_keeps_large_warning(desktop):
    w, runtime, app = desktop
    start_large_view(w)
    w._handle_message(dict(kind='saved', id='fixture-saved'))
    w._render_view(dict(state='OFFLINE', context=None, confirmed=False, summary={}, error='输入断开'))
    assert w.distance_coach.isVisible() and '暂停' in w.distance_coach.hold.text()
    assert w.distance_coach.canvas.image is None


@pytest.mark.parametrize('size', [(1100, 730), (1360, 900), (1600, 1000)])
@pytest.mark.parametrize('font_size', [32, 36, 40, 48])
def test_big_text_and_stop_controls_fit_supported_sizes(coach, size, font_size):
    c, app = coach
    c.resize(*size)
    c.font_choice.setCurrentIndex(c.font_choice.findData(font_size))
    plan = default_plan('index_pip_flexion')
    render(c, state('index_pip_flexion'), plan)
    app.processEvents()
    assert (c.width(), c.height()) == size
    for child in (c.finish, c.privacy, c.back, c.guide.instruction, c.guide.picture, c.safety):
        top = child.mapTo(c, child.rect().topLeft())
        bottom = child.mapTo(c, child.rect().bottomRight())
        assert c.rect().contains(top) and c.rect().contains(bottom)
    needed = c.guide.instruction.heightForWidth(c.guide.instruction.width())
    assert c.guide.instruction.height() >= needed
