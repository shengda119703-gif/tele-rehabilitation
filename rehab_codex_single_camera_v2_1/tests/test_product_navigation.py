import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import queue

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.domain import Context
from app.assessment import build_body_profile
from app.ui.main_window import MainWindow


class PassiveRuntime:
    def __init__(self):
        self.messages, self.views, self.calls = queue.Queue(), queue.Queue(), []

    def command(self, name, **kwargs):
        self.calls.append((name, kwargs))


@pytest.fixture
def desktop():
    app = QApplication.instance() or QApplication([])
    runtime = PassiveRuntime()
    window = MainWindow(runtime=runtime)
    window.show()
    app.processEvents()
    yield window, runtime, app
    window._allow_close = True
    window.close()
    window.deleteLater()
    app.processEvents()


def test_initial_catalog_and_real_card_open_correct_action_without_camera(desktop):
    w, runtime, app = desktop
    assert w.pages.currentWidget() is w.catalog
    assert w.scene_buttons['rehab'].isChecked()
    assert w.notice.isHidden()
    w.catalog.select_joint('wrist')
    app.processEvents()
    QTest.mouseClick(w.catalog.cards['wrist_extension'].open_button, Qt.MouseButton.LeftButton)
    assert w.pages.currentIndex() == 0
    assert w.exercise.currentData() == 'wrist_extension'
    assert w.view.currentData() == 'sagittal'
    assert '手背' in w.movement_steps.text()
    assert '实验性' in w.task_meta.text()
    assert runtime.calls == []


def test_navigation_reflects_current_page_and_preserves_running_task(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w.state = 'ONLINE'
    w._show_catalog()
    assert w.pages.currentIndex() == 0
    assert not runtime.calls
    assert not w.notice.isHidden()
    w.state = 'UNSELECTED'
    w._history()
    assert w.history_nav.isChecked()
    assert not w.scene_buttons['rehab'].isChecked()
    w._handle_message({'kind': 'command_done', 'command': 'history'})
    w._show_body()
    assert w.body_nav.isChecked()
    assert not w.history_nav.isChecked()


def test_advanced_settings_are_collapsed_but_operable(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    app.processEvents()
    assert not w.backend.isVisible()
    assert not w.usage.isVisible()
    assert w.source_options.toggle.isVisible()
    QTest.mouseClick(w.source_options.toggle, Qt.MouseButton.LeftButton)
    assert w.backend.isVisible() and w.usage.isVisible()
    assert not w.poses.isVisible() and not w.poses.isChecked()
    w.more_setup.toggle.setChecked(True)
    assert not w.poses.isHidden()
    assert runtime.calls == []


def test_synthetic_demo_source_cannot_open_a_fake_camera_session(desktop):
    w, runtime, app = desktop
    w.source_kind.setCurrentIndex(w.source_kind.findData('SYNTHETIC'))
    app.processEvents()
    assert w.usage.currentData() == 'TEST'
    assert w.replay_row.isHidden()
    assert not w.preview_button.isEnabled()
    assert '仅用于查看自动计划' in w.next_step_hint.text()


def test_training_hub_demo_switches_to_isolated_scope_and_opens_generated_plan(desktop):
    from app.demo_training_plan import DEMO_SCOPE, demo_participant
    w, runtime, app = desktop
    w._show_training_hub()
    w.training_hub.demo.click()
    assert runtime.calls[-1] == ('create_demo_training_plan', {})
    profile = dict(demo_participant(), revision=1)
    w._handle_message({'kind': 'demo_training_plan_created', 'scope': DEMO_SCOPE,
                       'participant': profile, 'proposal': {}, 'plan': {}})
    w._handle_message({'kind': 'command_done', 'command': 'create_demo_training_plan'})
    app.processEvents()
    assert w._body_scope_key() == DEMO_SCOPE
    assert w.participant_records[DEMO_SCOPE['participant_id']]['display_name'].startswith('演示患者')
    assert w.automatic_dialog is not None and w.automatic_dialog.demo_only
    assert runtime.calls[-1] == ('automatic_proposal', {'scope': DEMO_SCOPE})
    w.automatic_dialog.set_busy(False)
    w.automatic_dialog.reject()


@pytest.mark.parametrize('state,tone', [('PREVIEW', 'preview'), ('ONLINE', 'active'),
                                      ('OFFLINE', 'error'), ('SAVE_FAILED', 'error')])
def test_status_and_save_failure_controls_are_visible(desktop, state, tone):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w._render_view({'state': state, 'context': None, 'confirmed': False, 'summary': {}})
    assert w.status_badge.property('tone') == tone
    if state == 'SAVE_FAILED':
        assert not w.retry_button.isHidden()
        assert not w.backup_button.isHidden()
        assert not w.discard_button.isHidden()
        assert not w.start_button.isEnabled()
        assert not w.catalog.isEnabled()
        assert '打开' not in w.canvas.subcaption
        assert '待保存' in w.feedback.text()


def test_offline_message_is_not_replaced_by_last_person_observation(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w._render_view({'state': 'OFFLINE', 'context': None, 'confirmed': False,
                    'observation_status': 'NO_PERSON_DETECTED', 'summary': {}})
    assert '中断' in w.feedback.text()
    assert '断开' in w.canvas.caption


def test_confirmed_camera_does_not_claim_unconfirmed_training_can_start(desktop):
    w, runtime, app = desktop
    w._select_rehab('training')
    w._handle_message({'kind': 'confirmed', 'setup': w.setup})
    assert '可以开始' not in w.notice.text()
    assert '确认训练计划' in w.notice.text()


def test_disconnected_view_does_not_show_old_packet_as_live(desktop):
    import numpy as np
    from app.domain import FramePacket
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    context = Context(1, 'rehab', 'synthetic-ui', 'SYNTHETIC', 'TEST')
    packet = FramePacket(context, 1, 0, 0, '', np.zeros((200, 320, 3), dtype=np.uint8))
    w._accept_context_frames = True
    w._render_view({'state': 'OFFLINE', 'context': context, 'confirmed': False,
                    'packet': packet, 'summary': {'completed': 2, 'message': 'OLD'}})
    assert w.canvas.image is None
    assert 'OLD' not in w.feedback.text()


def test_selecting_unavailable_body_row_cannot_train_on_other_valid_row(desktop):
    w, runtime, app = desktop
    profile = build_body_profile([], **w._body_scope_key())
    profile['items'][0].update(status='ASSESSED', session_id='synthetic-1',
                               motion_range={'min_deg': 0, 'max_deg': 60, 'range_deg': 60})
    profile['items'][1].update(status='UNAVAILABLE', session_id='synthetic-2')
    w._handle_message({'kind': 'body_profile', 'profile': profile, 'html': 'SYNTHETIC TEST'})
    assert w.body_train.isEnabled()
    w.body_overview.table.selectRow(1)
    assert not w.body_train.isEnabled()
    w._train_from_body()
    assert not w.setup['plan'].get('assessment_reference')
    w._open_body_report()
    assert runtime.calls[-1] == ('report', {'id': 'synthetic-2'})


@pytest.mark.parametrize('size', [(1100, 730), (1360, 900), (1600, 1000)])
def test_layout_keeps_requested_window_size_and_footer_accessible(desktop, size):
    w, runtime, app = desktop
    w.resize(*size)
    app.processEvents()
    assert (w.width(), w.height()) == size
    w._choose_catalog_exercise('index_dip_flexion')
    app.processEvents()
    assert (w.width(), w.height()) == size
    # Qt retains obsolete geometry for hidden widgets. Check each action in
    # the actual lifecycle state that puts it in the footer layout.
    for state, confirmed, button in (('UNSELECTED', False, w.preview_button),
                                     ('PREVIEW', False, w.confirm_button),
                                     ('PREVIEW', True, w.start_button),
                                     ('ONLINE', True, w.stop_button)):
        w.state, w._confirmed = state, confirmed
        w._buttons()
        app.processEvents()
        assert button.isVisible()
        position = button.mapTo(w, button.rect().bottomRight())
        assert position.x() < w.width() and position.y() < w.height()
        assert button.height() >= 36
    assert w.setup_panel.widget().minimumSizeHint().width() <= w.setup_panel.width()
