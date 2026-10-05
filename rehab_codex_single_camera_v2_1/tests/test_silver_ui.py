import queue
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt

from app.silver_service import execute
from app.silver_store import SilverStore
from app.storage import Storage
from app.runtime import Runtime
from test_product_navigation import desktop
from test_dual_ui import select_pair


def test_help_works_without_camera_even_during_pending_refresh_and_returns_saved_record(desktop, tmp_path):
    w, runtime, app = desktop
    care, clinical = SilverStore(tmp_path/'support.sqlite3'), Storage(tmp_path/'clinical.sqlite3')
    try:
        w._show_silver()
        d = w.silver_dialog
        assert d.pending
        w.silver_help.click()
        command, kw = runtime.calls[-1]
        assert command == 'silver' and kw['operation'] == 'request' and kw['kind'] == 'help'
        result = execute(care, clinical, None, **kw)
        w._handle_message(dict(kind='silver', data=result))
        assert d.requests.count() == 1 and result['requests'][0]['remote_delivery'] == 'NOT_CONNECTED'
        assert not any(name in ('open', 'start', 'camera_test') for name, _ in runtime.calls)
        assert not d.pending and d._help_request_id is None
        assert d.tabs.currentIndex() == 2 and d.requests.currentRow() == 0
        d.role.setCurrentIndex(1)
        result_error = '未获共享授权'
        w._handle_message(dict(kind='error', command='silver', text=result_error))
        assert result_error in d.error.text() and not d.requests.count()
        assert '未知' in d.coverage.text()
    finally:
        clinical.close()


def test_ui_calls_real_local_response_transitions_and_revoke_hides_family_data(desktop, tmp_path):
    w, runtime, app = desktop
    care, clinical = SilverStore(tmp_path/'support.sqlite3'), Storage(tmp_path/'clinical.sqlite3')
    try:
        w._show_silver()
        d = w.silver_dialog
        def respond():
            _, kw = runtime.calls[-1]
            w._handle_message(dict(kind='silver', data=execute(care, clinical, None, **kw)))
        respond()
        d.recipient.setText('女儿')
        d.grants['requests'].setChecked(True)
        d.save_policy.click()
        respond()
        d.contact.click()
        respond()
        d.role.setCurrentIndex(1)
        respond()
        assert not d.help_button.isEnabled() and not d.training.isEnabled()
        d.requests.setCurrentRow(0)
        d.ack.click()
        respond()
        assert d.items[0][1]['status'] == 'ACKNOWLEDGED'
        d.claim.click()
        respond()
        assert d.items[0][1]['status'] == 'CLAIMED'
        scope = w._body_scope_key()
        care.consent(scope, '', [], care.policy(scope)['revision'])
        d.refresh()
        _, kw = runtime.calls[-1]
        with pytest.raises(ValueError):
            execute(care, clinical, None, **kw)
    finally:
        clinical.close()


def test_second_camera_navigation_does_not_open_cameras_and_restores_rehab_pair(desktop):
    w, runtime, app = desktop
    select_pair(w, app)
    front, side = w.device.currentData(), w.secondary_device.currentData()
    w._show_silver()
    w._silver_navigate('activity', 'secondary')
    assert w.scene == 'activity' and w.device.currentData() == side
    assert not any(name in ('open', 'camera_test', 'start') for name, _ in runtime.calls)
    w._silver_navigate('safety_demo', 'secondary')
    assert w.scene == 'safety_demo' and w.device.currentData() == side
    w._silver_navigate('bedroom_demo', 'primary')
    assert w.scene == 'bedroom_demo' and w.device.currentData() == front
    w._select_scene('rehab')
    assert w.device.currentData() == front and w.secondary_device.currentData() == side
    w.state = 'ONLINE'
    w._silver_navigate('safety_demo', 'secondary')
    assert w.scene == 'rehab'
    assert '先停止' in w.silver_dialog.error.text()


def test_optional_service_failure_does_not_change_rehab_guidance(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w.state = 'ONLINE'
    w._show_silver()
    original = w.exercise_guide.instruction.text()
    w._handle_message(dict(kind='error', command='silver', text='test storage unavailable'))
    assert w.state == 'ONLINE' and w.exercise_guide.instruction.text() == original
    assert w.silver_help.isEnabled()


def test_activity_permission_and_personal_targets_are_explicit_and_demo_is_labeled(desktop):
    w, runtime, app = desktop
    w._select_scene('activity')
    w.activity_options.setCurrentIndex(1)
    w.activity_durations['stand_target_s'].setValue(25)
    setup = w._read_setup()
    assert setup['allowed_activity_tasks'] == ['stand'] and setup['stand_target_s'] == 25
    assert not setup['activity_permission']
    w.demo.setChecked(True)
    setup = w._read_setup()
    assert setup['demo_thresholds'] and setup['stand_target_s'] == 5
    assert not w.activity_durations['stand_target_s'].isEnabled()



def test_periodic_refresh_keeps_error_feedback_until_explicit_action(desktop, tmp_path):
    w, runtime, app = desktop
    care, clinical = SilverStore(tmp_path/'support.sqlite3'), Storage(tmp_path/'clinical.sqlite3')
    try:
        w._show_silver()
        _, kw = runtime.calls[-1]
        result = execute(care, clinical, None, **kw)
        d = w.silver_dialog
        d.render(result)
        d.show_error('TEST 语音不可用')
        d.refresh()
        d.refresh()
        assert 'TEST 语音不可用' in d.error.text()
        d.render(result)
        assert 'TEST 语音不可用' in d.error.text()
        d.render(dict(result, operation='request'))
        assert not d.error.text()
    finally:
        clinical.close()



def test_empty_snapshot_disables_family_response_controls(desktop, tmp_path):
    w, runtime, app = desktop
    care, clinical = SilverStore(tmp_path/'support.sqlite3'), Storage(tmp_path/'clinical.sqlite3')
    try:
        w._show_silver()
        d = w.silver_dialog
        assert not any(b.isEnabled() for b in (d.ack, d.claim, d.resolve, d.confirm))
        _, kw = runtime.calls[-1]
        d.render(execute(care, clinical, None, **kw))
        assert not d.requests.count()
        assert not any(b.isEnabled() for b in (d.ack, d.claim, d.resolve, d.confirm))
    finally:
        clinical.close()



def test_pending_refresh_disables_mutations_but_keeps_help_available(desktop, tmp_path):
    w, runtime, app = desktop
    care, clinical = SilverStore(tmp_path/'support.sqlite3'), Storage(tmp_path/'clinical.sqlite3')
    try:
        w._show_silver()
        d = w.silver_dialog
        assert d.pending and not d.check_button.isEnabled() and not d.save_policy.isEnabled()
        assert d.help_button.isEnabled()
        _, kw = runtime.calls[-1]
        d.render(execute(care, clinical, None, **kw))
        assert d.check_button.isEnabled() and d.save_policy.isEnabled()
        d.refresh()
        assert not d.check_button.isEnabled()
        d.show_error('TEST 刷新失败')
        assert d.check_button.isEnabled() and d.save_policy.isEnabled()
    finally:
        clinical.close()


def test_voice_failure_survives_delayed_sharing_receipt(desktop, tmp_path, monkeypatch):
    import sys
    w, runtime, app = desktop
    care, clinical = SilverStore(tmp_path/'support.sqlite3'), Storage(tmp_path/'clinical.sqlite3')
    try:
        w._show_silver()
        _, kw = runtime.calls[-1]
        result = execute(care, clinical, None, **kw)
        d = w.silver_dialog
        d.render(result)
        monkeypatch.setitem(sys.modules, 'PySide6.QtTextToSpeech', None)
        d.voice_test.click()
        assert '语音不可用' in d.voice_status.text()
        d.render(dict(result, operation='consent'))
        d.render(dict(result, operation='refresh'))
        assert d.voice_status.isVisible()
        assert '语音不可用' in d.voice_status.text()
    finally:
        clinical.close()
