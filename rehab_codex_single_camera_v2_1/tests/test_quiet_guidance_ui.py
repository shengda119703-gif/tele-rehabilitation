import copy
from dataclasses import replace

from PySide6.QtTest import QTest
from PySide6.QtCore import QEventLoop, QTimer

from app.guidance import GuidancePolicy
from app.settings import default_plan
from test_product_navigation import desktop
from test_distance_ui import coach, render, state


def presentation(policy, now, valid=True):
    data = state()
    data.update(current_measurement_valid=valid, observation_status='VALID' if valid else 'UNKNOWN',
                adjustment='请调整侧面取景，让左髋也进入画面。')
    data['guidance'] = policy.render(data, default_plan(), now=now)
    return data


def test_main_and_distance_present_one_adjustment_and_clear_it_on_recovery(coach, desktop):
    c, app = coach
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w.auto_distance.setChecked(False)
    policy = GuidancePolicy()
    for now, valid in ((0., True), (.1, False), (1.7, False), (1.8, True)):
        data = presentation(policy, now, valid)
        w._render_view(data)
        render(c, data)
        guidance = data['guidance']
        assert w.exercise_guide.instruction.text() == guidance['instruction']
        assert w.feedback.text() == guidance['status']
        if guidance['level'] == 'action':
            assert w.exercise_guide.status.isVisible() and '下一步' in w.exercise_guide.status.text()
        else:
            assert not w.exercise_guide.status.isVisible()
        if guidance['level'] == 'adjust':
            assert c.presentation.currentWidget() is c.hold
            assert c.hold.text() == guidance['instruction']
            assert c.feedback.text() == '' and w.feedback.text() == ''
        else:
            assert c.presentation.currentWidget() is c.guide
            assert c.guide.instruction.text() == guidance['instruction']
        if not valid:
            assert not w.exercise_guide.image_available
            assert w.angle_card.value.text() == '—'
    assert '左髋' not in w.exercise_guide.instruction.text()


def test_final_button_is_one_manual_confirmation_and_sampling_does_not_start(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_adduction')
    w.state = 'PREVIEW'
    w._journey_framed = True
    w.setup['plan']['joint_baseline'] = {'rest_value': 55.}
    w._buttons()
    assert w.manual.isHidden() and w.preparation_review.isVisible()
    assert '确认准备' in w.confirm_button.text()
    w.confirm_button.click()
    assert runtime.calls[-1][0] == 'confirm'
    assert runtime.calls[-1][1]['setup']['participant_confirmed']
    assert not any(name == 'start' for name, _ in runtime.calls)


def test_transient_notices_expire_but_errors_and_stop_controls_remain(desktop):
    w, runtime, app = desktop
    w.notice.flash('已记录', milliseconds=30)
    loop = QEventLoop()
    guard = QTimer(loop)
    guard.setSingleShot(True)
    guard.timeout.connect(loop.quit)
    w.notice._expiry.timeout.connect(loop.quit)
    guard.start(5000)
    loop.exec()  # Exercise actual timer delivery, including deferred native events.
    guard.stop()
    w.notice._expiry.timeout.disconnect(loop.quit)
    assert w.notice.isHidden(), (w.notice.text(), w.notice._expiry.isActive(), w.notice._expiry.remainingTime())
    w.notice.flash('已记录', milliseconds=30)
    w.notice.setText('保存失败')
    assert not w.notice._expiry.isActive()
    QTest.qWait(50)
    assert w.notice.text() == '保存失败' and not w.notice.isHidden()
    w.state, w.busy, w.preparation_active = 'PREVIEW', 3, True
    w._buttons()
    assert w.privacy_button.isEnabled() and not w.privacy_button.isHidden() and not w.confirm_button.isEnabled()


def test_old_context_preparation_results_are_ignored(desktop):
    from app.domain import Context
    w, runtime, app = desktop
    w.last_generation = 5
    context = Context(generation=4, scene_id='rehab', source_kind='SYNTHETIC', source_ref='fixture', usage_context='TEST')
    w._handle_message(dict(kind='preparation', context=context, active=True, text='旧倒计时'))
    assert w.preparation_status.text() != '旧倒计时'


def test_adjustment_stays_visible_when_settings_tab_is_open(desktop):
    w, runtime, app = desktop
    w._choose_catalog_exercise('shoulder_abduction')
    w.auto_distance.setChecked(False)
    policy = GuidancePolicy()
    presentation(policy, 0., False)
    data = presentation(policy, 2., False)
    w._render_view(data)
    assert w.feedback.text() == ''
    w.setup_tabs.setCurrentIndex(1)
    assert w.feedback.text() == data['guidance']['instruction']
    assert w.timing_readout.text() == ''
    w.setup_tabs.setCurrentIndex(0)
    assert w.feedback.text() == ''
    w.setup_tabs.setCurrentIndex(2)
    assert w.journey.instruction.text() == data['guidance']['instruction']
    assert not w.feedback.text()
    recovered = presentation(policy, 2.1, True)
    w._render_view(recovered)
    assert w.journey.instruction.text() == recovered['guidance']['instruction']
    assert '左髋' not in w.journey.instruction.text()
