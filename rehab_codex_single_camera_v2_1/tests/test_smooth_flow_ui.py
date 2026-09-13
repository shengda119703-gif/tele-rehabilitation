"""Native workflow checks for the calmer flow. Offscreen Qt, no camera."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.guidance import GuidancePolicy
from app.guided import prompt_state
from app.journey import SCENE_ROIS, current_scene_step, scene_steps
from test_product_navigation import desktop
from test_distance_ui import coach, render


def preview(w, valid=True, **extra):
    data = dict(state='PREVIEW', context=None, confirmed=False, observation_status='VALID' if valid else 'UNKNOWN',
                current_measurement_valid=valid, summary={}, **extra)
    w._render_view(data)
    return data


def test_a_steady_picture_advances_framing_without_an_extra_click(desktop, monkeypatch):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    clock = [100.]
    monkeypatch.setattr('app.ui.main_window.time.monotonic', lambda: clock[0])
    preview(w, valid=False)
    assert not w._journey_framed and w._journey_step().key == 'framing'
    preview(w, valid=True)
    assert not w._journey_framed  # One good frame is not yet a steady picture.
    clock[0] += 1.3
    preview(w, valid=True)
    assert w._journey_framed and w._journey_step().key == 'confirm'


def test_a_brief_dropout_does_not_undo_framing_or_ask_again(desktop, monkeypatch):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    clock = [100.]
    monkeypatch.setattr('app.ui.main_window.time.monotonic', lambda: clock[0])
    preview(w, valid=True)
    clock[0] += 1.3
    preview(w, valid=True)
    assert w._journey_framed
    for _ in range(4):
        clock[0] += .2
        preview(w, valid=False)
        assert w._journey_framed and w._journey_step().key == 'confirm'


def test_countdown_delays_the_start_and_can_be_cancelled(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w.state = 'PREVIEW'
    w._journey_framed = True
    w._confirmed = True
    w._buttons()
    assert w._journey_step().key == 'start'
    w.start_button.click()
    assert w._start_countdown == 3 and not any(name == 'start' for name, _ in runtime.calls)
    assert w.journey.countdown.isVisible() and not w.start_button.isEnabled()
    w.journey.cancel_countdown.click()
    assert w._start_countdown == 0 and not any(name == 'start' for name, _ in runtime.calls)
    assert w.start_button.isEnabled()
    w.countdown_enabled.setChecked(False)
    w.start_button.click()
    assert runtime.calls[-1][0] == 'start'


def test_countdown_reaches_start_only_after_the_last_tick(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w.state, w._journey_framed, w._confirmed = 'PREVIEW', True, True
    w._buttons()
    w.start_button.click()
    for expected in (2, 1):
        w._tick_start_countdown()
        assert w._start_countdown == expected
        assert not any(name == 'start' for name, _ in runtime.calls)
    w._tick_start_countdown()
    assert w._start_countdown == 0 and runtime.calls[-1][0] == 'start'


def test_guided_switch_marks_setup_without_reintroducing_baseline_steps(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('neck_flexion')
    w.state, w._journey_framed = 'PREVIEW', True
    w._buttons()
    assert w._journey_step().key == 'confirm'
    assert w.journey.guided.isVisible()
    w.journey.guided.setChecked(True)
    assert w._guided and w.guided_toggle.isChecked()
    assert w._read_setup()['continuation_mode'] == 'guided'
    assert w._journey_step().key == 'confirm'
    assert w.joint_baselines.isHidden() and not w.guided_note.isHidden()
    assert runtime.calls[-1][0] == 'unconfirm'
    w.guided_toggle.setChecked(False)
    assert not w._guided and not w.journey.guided.isChecked()
    assert w._read_setup()['continuation_mode'] == 'auto'
    assert w._journey_step().key == 'confirm'


def test_a_failed_sampling_offers_the_guided_path_instead_of_a_dead_end(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('neck_flexion')
    w.state, w._journey_framed = 'PREVIEW', True
    w._handle_message(dict(kind='preparation', active=False,
                           text='尚未取得连续稳定画面。可以再试一次，也可以改用引导计时练习。'))
    assert w._preparation_failed and w.preparation_retry.isVisible()
    assert w.journey.offer.isVisible() and '引导计时' in w.journey.offer.text()
    w._handle_message(dict(kind='preparation', active=False, text='已记录。准备好后核对并确认本次准备。'))
    assert not w._preparation_failed


def test_a_long_gap_offers_the_guided_path_quietly(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    policy = GuidancePolicy()
    data = None
    for i in range(40):
        data = dict(state='PREVIEW', context=None, confirmed=False, observation_status='UNKNOWN',
                    current_measurement_valid=False, adjustment='请让测试部位清楚进入画面。', summary={})
        data['guidance'] = policy.render(data, w.setup['plan'], now=i*.5)
        w._render_view(data)
    assert data['guidance']['offer'] == 'guided'
    assert w.journey.offer.isVisible() and w.journey.offer.text() == data['guidance']['offer_text']
    assert w.notice.isHidden()


def test_self_report_control_appears_only_while_running(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w.state = 'PREVIEW'
    w._buttons()
    assert w.self_report_button.isHidden()
    w._render_view(dict(state='ONLINE', context=None, confirmed=True, observation_status='VALID',
                        current_measurement_valid=True, self_reported=0, summary=dict(phase='RAISING', completed=0, metrics={})))
    assert w.self_report_button.isVisible() and w.self_report_button.isEnabled()
    w.self_report_button.click()
    assert runtime.calls[-1][0] == 'self_report'
    w._handle_message(dict(kind='self_report', count=2, context=None))
    assert '已记 2 次' in w.self_report_button.text()
    w._render_view(dict(state='UNSELECTED', context=None, confirmed=False, summary={}))
    assert w.self_report_button.isHidden() and w._self_reported == 0


def test_guided_run_shows_the_prompt_in_both_views(desktop, coach):
    w, runtime, app = desktop
    c, _ = coach
    w._choose_catalog_exercise('shoulder_abduction')
    w._set_guided_mode(True)
    policy = GuidancePolicy()
    data = dict(state='ONLINE', context=None, confirmed=True, observation_status='UNKNOWN',
                current_measurement_valid=False, continuation_mode='guided', self_reported=1,
                guided_prompt=prompt_state(4., 'shoulder_abduction'),
                summary=dict(phase=None, completed=0, metrics={}))
    data['guidance'] = policy.render(data, w.setup['plan'], now=1.)
    w._render_view(data)
    render(c, data)
    assert data['guidance']['level'] == 'status'
    assert w.exercise_guide.instruction.text() == data['guidance']['instruction']
    assert '做动作' in w.exercise_guide.status.text()
    assert c.presentation.currentWidget() is c.guide
    assert '引导计时' in c.count.text() and '自己记录 1 次' in c.count.text()
    assert c.self_report.isVisible()


def test_preparation_reuse_is_reported_once(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('sit_to_stand')
    data = dict(state='PREVIEW', context=None, confirmed=False, observation_status='VALID',
                current_measurement_valid=True, summary={},
                preparation_reuse=dict(reused=['calibration'], reasons=[]))
    w._render_view(data)
    assert '已沿用上次的坐站基线' in w.notice.text()
    w.notice.clear()
    w._render_view(data)
    assert w.notice.isHidden()
    data['preparation_reuse'] = dict(reused=[], reasons=['坐站基线的输入、画面尺寸、侧别或机位已变化，需要重新记录'])
    w._render_view(data)
    assert '需要重新记录' in w.notice.text()


def test_mirror_change_keeps_the_preview_and_only_asks_for_a_new_acknowledgement(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w.state, w._confirmed = 'PREVIEW', True
    runtime.calls.clear()
    w.mirror.setChecked(False)
    assert not w._confirmed and w.state == 'PREVIEW'
    assert [name for name, _ in runtime.calls] == ['unconfirm']


def test_companion_scenes_now_have_the_same_short_step_list(desktop):
    w, runtime, app = desktop
    for scene in ('activity', 'bedroom_demo', 'safety_demo'):
        w._select_scene(scene)
        assert w.setup_tabs.isTabVisible(2)
        step = w._journey_step()
        assert step.key == 'camera' and step.number == 1
        w.state = 'PREVIEW'
        w._buttons()
        assert w._journey_step().key == 'regions'
        w._journey_next()
        assert '还需要圈定' in w.journey.message.text()
        w.setup['rois'] = {name: [.1, .1, .5, .5] for name, _ in SCENE_ROIS[scene]}
        w._buttons()
        expected = 'permission' if scene == 'activity' else 'confirm'
        assert w._journey_step().key == expected
        if scene == 'activity':
            w._journey_next()
            assert w.permission.isChecked()
            assert w._journey_step().key == 'confirm'
        w.state = 'UNSELECTED'
        w.setup['rois'] = {}
        w.permission.setChecked(False)


def test_scene_step_list_is_complete_and_ordered():
    for scene in ('activity', 'bedroom_demo', 'safety_demo'):
        keys = [step[0] for step in scene_steps(scene)]
        assert keys[0] == 'camera' and keys[-4:] == ['confirm', 'start', 'active', 'result']
        assert ('permission' in keys) == (scene == 'activity')
        assert len(keys) == len(set(keys))
        assert all(all(isinstance(value, str) and value for value in step) for step in scene_steps(scene))
        assert current_scene_step(scene, 'SAVE_FAILED').key == 'save_failed'
        assert current_scene_step(scene, 'ONLINE').key == 'active'
        assert current_scene_step(scene, 'UNSELECTED', saved=True).key == 'result'


def test_completion_summary_states_what_was_and_was_not_measured(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w._latest_report_id = 'run-1'
    w.state = 'UNSELECTED'
    snapshot = dict(id='run-1', measurement_mode='auto_observed',
                    summary=dict(completed=3, motion_range=dict(min_deg=8., max_deg=91., range_deg=83.),
                                 self_reported_reps=1))
    w._handle_message(dict(kind='report', snapshot=snapshot, html='<p>x</p>'))
    app.processEvents()
    step = w._journey_step()
    assert step.key == 'result'
    text = w._completion_summary(step)
    assert '3 次' in text and '8° ～ 91°' in text and '自己记录的完成次数：1 次' in text
    assert w.journey.next_actions.isVisible()
    guided = dict(id='run-1', measurement_mode='guided_timed',
                  summary=dict(completed=0, motion_range=None, motion_range_valid=False,
                               approximate_range=dict(min_deg=10., max_deg=30., range_deg=20., approximate=True),
                               self_reported_reps=2))
    w._latest_snapshot = guided
    text = w._completion_summary(w._journey_step())
    assert '引导计时' in text and '近似角度范围' in text and '不作为训练所需的评估依据' in text
    for dialog in w.report_windows:
        dialog.close()


def test_result_step_next_actions_are_wired(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w._latest_report_id = 'run-2'
    w.state = 'UNSELECTED'
    w._buttons()
    assert w._journey_step().key == 'result'
    QTest.mouseClick(w.journey.another, Qt.MouseButton.LeftButton)
    assert w.pages.currentWidget() is w.catalog
    w._latest_report_id = 'run-2'
    w.state = 'UNSELECTED'
    w._buttons()
    QTest.mouseClick(w.journey.detail, Qt.MouseButton.LeftButton)
    assert ('report', {'id': 'run-2'}) in runtime.calls
