import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from app.assessment import build_body_profile
from test_camera_selection import camera
from test_product_navigation import desktop


def enumerate_result(w, devices, backend=700):
    w._handle_message(dict(kind='devices', devices=devices, backend=backend))


def drain_commands(w):
    for name, count in list(w.pending_commands.items()):
        for _ in range(count):
            w._handle_message(dict(kind='command_done', command=name))


def test_startup_restore_selects_saved_backend_and_current_index_without_open(desktop):
    w, runtime, app = desktop
    w._handle_message(dict(kind='ready', preferred_camera=camera(backend=1400, index=0)))
    assert w.backend.currentData() == 1400
    assert runtime.calls[-1] == ('enumerate', {'backend': 1400})
    enumerate_result(w, [camera(backend=1400, index=19)], 1400)
    drain_commands(w)
    assert w.device.currentData()['index'] == 19
    assert w.device.isVisible()  # Already selected on the entry screen.
    assert not any(name in ('open', 'confirm', 'start') for name, _ in runtime.calls)
    assert not w.manual.isChecked() and not w.start_button.isEnabled()


def test_first_unique_camera_reused_across_all_scenes_modes_and_replay(desktop):
    w, runtime, app = desktop
    enumerate_result(w, [camera()])
    for scene in ('activity', 'bedroom_demo', 'safety_demo', 'rehab'):
        w._select_scene(scene)
        assert w.device.currentData() == camera()
    for mode in ('training', 'assessment'):
        w._select_rehab(mode)
        assert w.device.currentData() == camera()
    w.source_kind.setCurrentIndex(1)
    w.source_kind.setCurrentIndex(0)
    w._choose_catalog_exercise('knee_extension')
    assert w.device.currentData() == camera()
    assert not any(name in ('open', 'confirm', 'start') for name, _ in runtime.calls)


def test_manual_choice_is_remembered_and_refresh_does_not_clear_it(desktop):
    w, runtime, app = desktop
    enumerate_result(w, [camera(), camera('second')])
    assert w.device.currentData() is None
    w.device.setCurrentIndex(2)
    assert w.notice.isHidden()
    assert runtime.calls[-1] == ('remember_camera', {'device': camera('second')})
    enumerate_result(w, [camera('second', index=18), camera()])
    assert w.device.currentData()['index'] == 18
    assert len(runtime.calls) == 1


@pytest.mark.parametrize('page,title', [(1, '历史记录'), (2, '身体档案')])
def test_global_camera_change_keeps_page_title(desktop, page, title):
    w, runtime, app = desktop
    w.pages.setCurrentIndex(page)
    enumerate_result(w, [camera(), camera('second')])
    w.device.setCurrentIndex(1)
    assert w.pages.currentIndex() == page and w.title.text() == title


def test_successful_camera_refresh_does_not_clear_other_notices(desktop):
    w, runtime, app = desktop
    w.notice.setText('其他操作尚未保存')
    enumerate_result(w, [camera()])
    assert w.notice.text() == '其他操作尚未保存'


def test_missing_saved_device_stays_unselected_until_it_returns_or_user_rebinds(desktop):
    w, runtime, app = desktop
    enumerate_result(w, [camera()])
    enumerate_result(w, [camera('second')])
    assert w.device.currentData() is None
    enumerate_result(w, [camera('second')])
    assert w.device.currentData() is None
    enumerate_result(w, [camera(index=22)])
    assert w.device.currentData()['index'] == 22
    assert runtime.calls == []


def test_missing_device_revokes_confirmation_without_switching_or_opening_capture(desktop):
    w, runtime, app = desktop
    enumerate_result(w, [camera()])
    w._choose_catalog_exercise('shoulder_abduction')
    w.state, w._confirmed = 'PREVIEW', True
    enumerate_result(w, [camera('second')])
    assert not w._confirmed and not w.start_button.isEnabled()
    assert runtime.calls == [('unconfirm', {})]


def test_backend_change_clears_stale_selection_and_ignores_old_reply(desktop):
    w, runtime, app = desktop
    enumerate_result(w, [camera()])
    w.backend.setCurrentIndex(1)
    assert w.device.currentData() is None
    enumerate_result(w, [camera()])
    assert w.device.count() == 1 and w.device.currentData() is None
    enumerate_result(w, [camera(backend=1400)], 1400)
    assert w.device.currentData() is None
    w.device.setCurrentIndex(1)
    assert w.device.currentData()['backend'] == 1400


def test_selection_does_not_reuse_measured_baseline_or_confirmation(desktop):
    w, runtime, app = desktop
    enumerate_result(w, [camera()])
    w._choose_catalog_exercise('shoulder_abduction')
    w.state, w._confirmed = 'PREVIEW', True
    w.setup['plan']['joint_baseline'] = {'rest_value': 20}
    w._select_scene('activity')
    assert w.device.currentData() == camera()
    assert not w._confirmed and not w.setup['plan']['joint_baseline']
    assert any(name == 'switch' for name, _ in runtime.calls)
    assert not any(name == 'open' for name, _ in runtime.calls)


@pytest.mark.parametrize('state,confirmed,expected', [
    ('UNSELECTED', False, 'preview_button'), ('PREVIEW', False, 'confirm_button'),
    ('PREVIEW', True, 'start_button'), ('ONLINE', True, 'stop_button'),
    ('OFFLINE', False, 'preview_button'), ('SAVE_FAILED', False, 'retry_button'),
])
def test_only_current_primary_action_is_shown_and_errors_keep_recovery(desktop, state, confirmed, expected):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w._render_view(dict(state=state, context=None, confirmed=confirmed, summary={}))
    primary = [b for b in (w.preview_button, w.confirm_button, w.start_button, w.stop_button, w.retry_button)
               if not b.isHidden() and b.objectName() == 'primary']
    assert primary == [getattr(w, expected)]
    assert not w.privacy_button.isHidden() if state in ('PREVIEW', 'ONLINE') else w.privacy_button.isHidden()
    if state == 'SAVE_FAILED':
        assert not w.backup_button.isHidden() and not w.discard_button.isHidden()


def test_short_pages_keep_actions_text_guides_and_details_accessible(desktop):
    w, runtime, app = desktop
    assert not w.subtitle.isVisible()
    assert w.catalog.cards['shoulder_abduction'].minimumHeight() <= 170
    w._choose_catalog_exercise('wrist_flexion')
    assert '掌侧' in w.exercise_guide.steps[1]['text']
    w.setup_tabs.setCurrentIndex(1)
    app.processEvents()
    assert w.joint_baselines.isHidden() and w.optional_baseline.isHidden()
    w._choose_catalog_exercise('shoulder_abduction')
    w.setup_tabs.setCurrentIndex(1)
    app.processEvents()
    assert w.optional_baseline.isHidden() and w.joint_baselines.isHidden()
    QTest.mouseClick(w.measurement_details.toggle, Qt.MouseButton.LeftButton)
    assert not w.action_guide.isHidden() and w.action_guide.text()


@pytest.mark.parametrize('state', ['PREVIEW', 'ONLINE', 'OFFLINE', 'SAVE_FAILED'])
def test_small_window_feedback_and_visible_actions_stay_on_screen(desktop, state):
    w, runtime, app = desktop
    w.resize(1100, 730)
    w._choose_catalog_exercise('wrist_flexion')
    w._render_view(dict(state=state, context=None, confirmed=False, summary={}))
    app.processEvents()
    assert w.feedback.isVisible()
    widgets = [w.feedback, w.privacy_button, w.preview_button, w.confirm_button,
               w.start_button, w.stop_button, w.retry_button, w.backup_button, w.discard_button]
    for widget in widgets:
        if widget.isVisible():
            bottom = widget.mapTo(w, widget.rect().bottomRight())
            assert bottom.y() < w.height() and bottom.x() < w.width()


def test_global_source_change_clears_visible_old_body_results(desktop):
    w, runtime, app = desktop
    profile = build_body_profile([], **w._body_scope_key())
    w._handle_message(dict(kind='body_profile', profile=profile, html='test'))
    w.pages.setCurrentIndex(2)
    w.source_kind.setCurrentIndex(1)
    assert w.body_profile is None and not w.body_train.isEnabled()
    assert any(name == 'body_profile' and kw['source_kind'] == 'REPLAY_FILE' for name, kw in runtime.calls)
