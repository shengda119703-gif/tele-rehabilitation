"""Native event/control boundaries. TEST fixture replies are not camera evidence."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import copy
import time
from uuid import uuid4

import pytest
from PySide6.QtWidgets import QApplication

from app.guided_practice import execute
from app.storage import Storage
from app.training_plans import new_training_plan
from app.ui.guided_practice import GuidedPracticeDialog, PracticePlanLibraryDialog
from test_product_navigation import PassiveRuntime
from test_saved_training_plans import SCOPE, item
from app.ui.product_rehab import ProductRehabWindow


@pytest.fixture
def native(tmp_path):
    app = QApplication.instance() or QApplication([])
    runtime = PassiveRuntime()
    window = ProductRehabWindow(runtime=runtime)
    window._body_scope_key = lambda: copy.deepcopy(SCOPE)
    store = Storage(tmp_path/'home_rehab.sqlite3')
    plan = store.save_training_plan(new_training_plan(SCOPE, 'TEST 已有安排', [item()]), expected_revision=0)
    prepared = execute(store, 'practice_prepare', SCOPE, dict(id=plan['id'], revision=1, entry_key=plan['items'][0]['key']))
    dialog = GuidedPracticeDialog(window, prepared=prepared)
    window.practice_dialog = dialog
    dialog.show(); app.processEvents()
    yield window, dialog, store, runtime, app
    dialog.timer.stop(); dialog.watch.stop(); dialog.hide(); dialog.deleteLater()
    window._allow_close = True; window.close(); window.deleteLater(); app.processEvents(); store.close()


def reply(dialog, store, runtime):
    name, args = runtime.calls[-1]
    result = execute(store, name, args['scope'], args)
    dialog.receive(dict(kind='practice_result', command=name, request_id=args['request_id'], scope=args['scope'], result=result))
    return result


def begin(dialog, store, runtime):
    dialog.confirm.setChecked(True); dialog.support.setChecked(True); dialog._render()
    assert dialog.primary.isEnabled()
    dialog.primary.click(); reply(dialog, store, runtime)
    assert dialog.stage == 'EXERCISING'


def test_native_pause_and_return_stop_timer_but_keep_original_journey(native):
    window, d, store, runtime, app = native
    begin(d, store, runtime)
    original = d.record['id']; d.last_tick = time.monotonic() - .4; d._tick()
    assert 350 < d.elapsed_ms < 500
    d.pause.click(); assert d.stage == 'PAUSED'
    reply(d, store, runtime); elapsed = d.elapsed_ms
    d._tick(); assert d.elapsed_ms == elapsed
    d.back.click(); assert not d.isVisible()
    window._resume_training_preparation(); app.processEvents()
    assert d.isVisible() and d.stage == 'PAUSED' and d.record['id'] == original
    assert not d.confirm.isVisible()
    d.pause.click(); assert d.stage == 'PAUSED'  # Resume waits for real policy query.
    reply(d, store, runtime); assert d.stage == 'EXERCISING'


def test_long_gui_gap_pauses_without_credit_and_end_is_immediate(native):
    _, d, store, runtime, _ = native
    begin(d, store, runtime)
    d.last_tick = time.monotonic() - 30; d._tick()
    assert d.elapsed_ms == 0 and d.stage == 'PAUSED'
    d.end.click(); assert d.stage == 'WRAP_UP' and d.count.value() == -1
    d.count.setValue(3); d.primary.click()
    assert d.stage == 'WRAP_UP' and d.finish_payload['count'] == 3
    assert d.record['confirmed_count'] is None
    reply(d, store, runtime)
    assert d.stage == 'SUMMARY' and d.record['state'] == 'COMMITTED'
    assert d.record['finish_payload']['feedback'] == dict(pain=None, fatigue=None)


def test_lost_finish_reply_retains_immutable_key_and_user_fields(native):
    _, d, store, runtime, _ = native
    begin(d, store, runtime); d.end.click(); d.count.setValue(3); d.primary.click()
    name, args = runtime.calls[-1]
    committed = execute(store, name, args['scope'], args)
    frozen = copy.deepcopy(d.finish_payload)
    d.pending['started'] -= 21; d._tick()
    assert not d.pending and d.count.value() == 3
    assert not d.count.isEnabled()  # The submitted operation is immutable.
    d.primary.click(); result = reply(d, store, runtime)
    assert result == committed and d.finish_payload == frozen
    assert len(execute(store, 'practice_history', SCOPE, {})) == 1


def test_late_reply_and_owner_switch_cannot_resume_other_person(native):
    window, d, store, runtime, _ = native
    begin(d, store, runtime)
    d.pause.click(); reply(d, store, runtime); d.pause.click()
    name, args = runtime.calls[-1]
    result = execute(store, name, args['scope'], args)
    before = d.elapsed_ms
    assert not d.receive(dict(kind='practice_result', command=name, request_id=str(uuid4()), scope=SCOPE, result=result))
    window._body_scope_key = lambda: dict(SCOPE, participant_id='TEST-other')
    d._tick()
    assert not d.isVisible() and d.stage == 'PAUSED'
    assert not d.receive(dict(kind='practice_result', command=name, request_id=args['request_id'], scope=SCOPE, result=result))
    assert d.elapsed_ms == before


def test_archive_between_pause_and_resume_blocks_execution_but_save_still_works(native):
    _, d, store, runtime, _ = native
    begin(d, store, runtime); d.pause.click(); reply(d, store, runtime)
    ref = d.record['plan_ref']
    store.set_training_plan_archived(ref['id'], SCOPE, True, expected_revision=ref['revision'])
    d.pause.click(); reply(d, store, runtime)
    assert d.stage == 'PAUSED' and not d.record['execution_allowed']
    d.end.click(); d.primary.click(); reply(d, store, runtime)
    assert d.stage == 'SUMMARY'


def test_late_resume_permission_cannot_restart_after_user_end(native):
    _, d, store, runtime, _ = native
    begin(d, store, runtime); d.pause.click(); reply(d, store, runtime)
    d.pause.click(); assert d.pending and d.stage == 'PAUSED'
    d.end.click(); assert d.stage == 'WRAP_UP'
    reply(d, store, runtime)
    assert d.stage == 'WRAP_UP' and d.last_tick is None and not d.resume_requested


def test_late_resume_error_preserves_wrap_up_and_explicit_input(native):
    _, d, store, runtime, _ = native
    begin(d, store, runtime); d.pause.click(); reply(d, store, runtime)
    d.pause.click(); _, args = runtime.calls[-1]
    d.end.click(); d.count.setValue(3)
    d.receive(dict(kind='error', command='practice_get', request_id=args['request_id'], text='TEST 读取失败'))
    assert d.stage == 'WRAP_UP' and d.count.value() == 3 and d.last_tick is None
    assert not d.resume_requested and d.primary.isEnabled()


def test_start_reply_after_return_keeps_practice_paused(native):
    _, d, store, runtime, app = native
    d.confirm.setChecked(True); d.support.setChecked(True); d._render(); d.primary.click()
    assert d.pending
    d.back.click(); app.processEvents(); reply(d, store, runtime)
    assert d.record['state'] == 'PRACTICING' and d.stage == 'PAUSED' and d.last_tick is None
    assert not d.isVisible() and d.elapsed_ms == 0


def test_wrong_scope_reply_does_not_clear_current_pending_operation(native):
    _, d, store, runtime, _ = native
    d.confirm.setChecked(True); d.support.setChecked(True); d._render(); d.primary.click()
    name, args = runtime.calls[-1]; pending = copy.deepcopy(d.pending)
    result = execute(store, name, args['scope'], args)
    assert not d.receive(dict(kind='practice_result', command=name, request_id=args['request_id'],
        scope=dict(SCOPE, participant_id='TEST-other'), result=result))
    assert d.pending == pending and d.record is None
    reply(d, store, runtime); assert d.stage == 'EXERCISING'


def test_original_history_does_not_replace_active_practice_controller(native):
    window, d, store, runtime, app = native
    begin(d, store, runtime); original = d.record['id']
    window._open_practice_record(original)
    assert window.practice_dialog is d and d.isVisible()
    window._open_practice_record(str(uuid4()))
    assert not d.isVisible() and d.stage == 'PAUSED'
    pending = window._practice_history_request
    historical = copy.deepcopy(d.record)
    historical.update(state='COMMITTED', id=str(uuid4()))
    window._handle_message(dict(kind='practice_result', command='practice_get',
        request_id=pending['request_id'], scope=SCOPE, result=historical))
    assert window.practice_dialog is d and window.practice_record_dialog.stage == 'SUMMARY'
    window._resume_training_preparation(); app.processEvents()
    assert window.practice_dialog is d and d.record['id'] == original and d.isVisible()
    window.practice_record_dialog.hide(); window.practice_record_dialog.deleteLater()


def test_legacy_client_uses_original_plan_library_but_keeps_owned_history(native, monkeypatch):
    window, d, store, runtime, app = native
    monkeypatch.setenv('ANKANG_REHAB_EXPERIENCE', 'legacy')
    window._open_plan_library()
    assert window.plan_library_dialog and not isinstance(window.plan_library_dialog, PracticePlanLibraryDialog)
    assert runtime.calls[-1][0] == 'training_plans'
    window.plan_library_dialog.set_busy(False); window.plan_library_dialog.reject()
    begin(d, store, runtime); d.end.click(); d.primary.click(); reply(d, store, runtime)
    assert d.record['state'] == 'COMMITTED'
    assert len(execute(store, 'practice_history', SCOPE, {})) == 1


def test_original_library_layout_and_unknown_decision_are_not_grants(native):
    window, _, store, _, app = native
    plans = store.list_training_plans(SCOPE)
    p = copy.deepcopy(plans[0]); p['items'][0]['available'] = False
    library = PracticePlanLibraryDialog(SCOPE, window)
    try:
        library.populate([p]); assert not library.use.isEnabled()
        checked = execute(store, 'practice_prepare', SCOPE, dict(id=p['id'], revision=1, entry_key=p['items'][0]['key']))['decision']
        p['items'][0]['practice_decision'] = checked
        library.populate([p]); assert library.use.isEnabled()
        assert library.table.columnCount() == 5
        library.set_busy(True); assert not library.use.isEnabled()
    finally:
        library.set_busy(False); library.reject(); library.deleteLater(); app.processEvents()
