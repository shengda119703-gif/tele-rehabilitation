import copy
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.ui.automatic_plans import AutomaticPlanDialog
from app.ui.training import TrainingFeedbackDialog
from app.automatic_plans import program_progress
from test_product_navigation import desktop
from test_automatic_plans import proposal, record, execution, SCOPE
from app.assessment import build_body_profile
from app.training_plans import prepare_training_plan
from test_automatic_plans import measured


def test_dialog_never_prefills_suitability_or_starts_camera(desktop):
    w, runtime, app = desktop
    d = AutomaticPlanDialog(SCOPE, w)
    requests = []
    d.requested.connect(lambda *args: requests.append(args))
    d.receive(dict(kind='automatic_proposal', proposal=proposal()))
    d.show()
    app.processEvents()
    assert not d.general.isChecked() and not d.standing.isChecked()
    assert '1 · 你的测试情况' in d.browser.toPlainText()
    QTest.mouseClick(d.primary, Qt.MouseButton.LeftButton)
    assert requests[-1][0] == 'accept_automatic_plan'
    assert requests[-1][1]['screening']['general_activity_ok'] is False
    assert not d.primary.isEnabled() and runtime.calls == []
    d.set_busy(False)
    d.reject()


def test_progress_next_quality_and_missing_feedback_recovery(desktop):
    w, runtime, app = desktop
    r = record()
    s = execution(r, training_feedback={})
    d = AutomaticPlanDialog(SCOPE, w)
    d.receive(dict(kind='automatic_progress', record=r, progress=program_progress(r, [s])))
    d.show()
    app.processEvents()
    assert not d.primary.isEnabled() and d.feedback_button.isVisible()
    assert not d.checks.isVisible()
    seen = []
    d.feedback_requested.connect(seen.append)
    d.feedback_button.click()
    assert seen == [s['id']]
    d.reject()


def test_hub_wires_generation_and_late_result_cannot_change_user(desktop):
    w, runtime, app = desktop
    w._show_training_hub()
    w.training_hub.automatic.click()
    assert runtime.calls[-1][0] == 'automatic_proposal'
    assert w.automatic_dialog
    before = copy.deepcopy(w.setup)
    w._handle_message(dict(kind='automatic_item_prepared', scope=SCOPE, plan={}))
    assert w._automatic_to_activate is None and w.setup == before
    w._handle_message(dict(kind='command_done', command='automatic_proposal'))
    w.automatic_dialog.reject()


def test_accepted_program_prepares_without_manual_parameter_dialog(desktop):
    w, runtime, app = desktop
    scope = w._body_scope_key()
    s = measured(**scope)
    from app.automatic_plans import generate_proposal, create_automatic_plan
    from test_automatic_plans import NOW, SCREEN
    profile = build_body_profile([s], **scope)
    r = create_automatic_plan(generate_proposal(profile, [s], now=NOW), SCREEN, now=NOW)
    r['revision'] = 1
    plan = prepare_training_plan(r, r['items'][0]['key'], profile)
    plan['training_plan_confirmed'] = True
    w._open_automatic_plan()
    w._handle_message(dict(kind='command_done', command='automatic_proposal'))
    w.automatic_dialog.set_busy(True)
    w._send('prepare_automatic_item')
    w._handle_message(dict(kind='automatic_item_prepared', scope=scope, plan=plan))
    w._handle_message(dict(kind='command_done', command='prepare_automatic_item'))
    assert w.automatic_dialog is None
    assert w.setup['plan']['training_plan_confirmed'] is True
    assert w.setup['plan']['saved_plan_reference']['record_origin'] == 'assessment_rules'
    assert w.submode.currentData() == 'training'
    assert not any(name in ('open', 'start') for name, _ in runtime.calls)


def test_comfort_shortcut_is_explicit_and_does_not_invent_completed_task(desktop):
    w, runtime, app = desktop
    s = execution(record(), summary={'completed': 1, 'plan_completed': False})
    s.pop('training_feedback')
    d = TrainingFeedbackDialog(s, w)
    values = []
    d.save_requested.connect(lambda sid, value, revision: values.append(value))
    assert d.scores['pain'].value() == -1
    d.comfortable.click()
    assert values[-1]['pain'] == values[-1]['fatigue'] == 0
    assert values[-1]['reason'] == 'not_recorded'
    d.reject()
