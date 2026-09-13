import pytest
from app.reports import render_report
from app.ui.dialogs import ReportDialog
from test_product_navigation import desktop
from test_result_summary import snapshot


def preview_neck(w):
    w._choose_catalog_exercise('neck_flexion')
    w.state = 'PREVIEW'
    w._confirmed = False
    w._buttons()


def test_journey_skips_joint_sampling_and_confirms_without_starting(desktop):
    w, runtime, app = desktop
    preview_neck(w)
    assert w.setup_tabs.currentIndex() == 2
    assert '不要求髋部' in w.journey.explanation.text()
    w.confirm_button.click()
    assert w._journey_step().key == 'confirm'
    assert not runtime.calls and not w.manual.isChecked()
    w.confirm_button.click()
    assert runtime.calls[-1][0] == 'confirm'
    assert runtime.calls[-1][1]['setup']['participant_confirmed'] is True
    assert not runtime.calls[-1][1]['setup']['plan'].get('joint_baseline')
    assert not any(name == 'start' for name, args in runtime.calls)


def test_error_stays_at_current_step_then_invalidation_resets_guidance(desktop):
    w, runtime, app = desktop
    preview_neck(w)
    w.confirm_button.click()
    w._handle_message(dict(kind='error', command='confirm', text='预览设置已改变，请重试'))
    w._buttons()
    assert w._journey_step().key == 'confirm'
    assert '请重试' in w.journey.message.text()
    w._invalidate()
    assert w._journey_step().key == 'camera'
    assert not w._journey_error


def test_save_failure_does_not_open_report_and_success_requests_persisted_id_once(desktop):
    w, runtime, app = desktop
    preview_neck(w)
    w.state = 'ONLINE'
    w._finish_task()
    w.state = 'SAVE_FAILED'
    w._buttons()
    assert w._journey_step().key == 'save_failed'
    assert not any(n == 'report' for n, _ in runtime.calls)
    w.state = 'UNSELECTED'
    w._handle_message(dict(kind='saved', id='persisted-id'))
    assert ('report', {'id': 'persisted-id'}) in runtime.calls
    assert w._journey_step().key == 'result'
    w._handle_message(dict(kind='saved', id='persisted-id'))
    assert sum(n == 'report' for n, _ in runtime.calls) == 1


def test_report_opens_understandable_summary_and_preserves_details(desktop):
    w, runtime, app = desktop
    s = snapshot()
    d = ReportDialog(s, render_report(s), lambda sid: None, w)
    d.show()
    app.processEvents()
    assert d.overview.isVisible()
    assert '这些数字怎么理解' in d.overview.toPlainText()
    assert '每次动作' in d.browser.toPlainText()
    d.close()


def test_companion_is_explicit_and_not_bypassed(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w.state = 'PREVIEW'
    w._journey_framed = True
    w.setup['plan']['needs_companion'] = True
    w._buttons()
    w.confirm_button.click()
    assert '陪同' in w.journey.message.text()
    assert not any(n == 'confirm' for n, _ in runtime.calls)
    w.journey.companion.setChecked(True)
    w.confirm_button.click()
    assert runtime.calls[-1][1]['setup']['companion_confirmed'] is True


def test_sit_stand_journey_has_no_mandatory_sampling_steps(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('sit_to_stand')
    w.state = 'PREVIEW'
    w._journey_framed = True
    w._buttons()
    assert w._journey_step().key == 'confirm'
    w.confirm_button.click()
    assert runtime.calls[-1][0] == 'confirm'
    assert not any(name == 'prepare_sample' for name, _ in runtime.calls)


def test_training_preflight_has_an_action_but_no_enabled_start(desktop):
    w, runtime, app = desktop
    w._select_rehab('training')
    w.state, w._confirmed = 'PREVIEW', True
    w._buttons()
    assert not w.start_button.isEnabled() and not w.start_button.isVisible()
    assert w.confirm_button.text() == '选择评估记录'
    w.confirm_button.click()
    assert not any(n == 'start' for n, _ in runtime.calls)
    assert w.pages.currentIndex() == 2


def test_training_result_follows_feedback_close_but_not_after_context_change(desktop):
    w, runtime, app = desktop
    w._select_rehab('training')
    w.state = 'ONLINE'
    w._finish_task()
    w.state = 'UNSELECTED'
    w._handle_message(dict(kind='saved', id='training-saved'))
    assert not any(n == 'report' for n, _ in runtime.calls)
    w._feedback_closed()
    assert ('report', {'id': 'training-saved'}) in runtime.calls
    count = len(runtime.calls)
    w._feedback_closed()
    assert len(runtime.calls) == count
    w._result_after_feedback = ('old-training', w._body_scope_key())
    w._invalidate()
    w._feedback_closed()
    assert ('report', {'id': 'old-training'}) not in runtime.calls
