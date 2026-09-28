import copy

import pytest

from test_product_navigation import desktop


def reply(w, **changes):
    d = w.agent_dialog
    result = dict(scope=d.scope, text='当前尚无评估', at='2026-09-28T00:00:00Z',
                  actions=[dict(id='assessment', label='去做身体评估')])
    result.update(changes)
    w._handle_message(dict(kind='rehab_agent', request_id=d.request_id, result=result))
    w._handle_message(dict(kind='command_done', command='rehab_agent'))


def test_entry_reads_then_explicit_action_uses_existing_page(desktop):
    w, r, app = desktop
    before = copy.deepcopy(w.setup)
    w.agent_button.click()
    assert r.calls[-1][0] == 'rehab_agent'
    assert w.agent_dialog and not w.agent_dialog.send.isEnabled()
    reply(w)
    assert w.agent_dialog.send.isEnabled()
    w.agent_dialog.action_row.itemAt(0).widget().click()
    assert w.agent_dialog is None and w.pages.currentWidget() is w.catalog
    assert w.setup == before
    assert not any(n in ('open', 'start', 'accept_automatic_plan') for n, _ in r.calls)


@pytest.mark.parametrize('state', ['ONLINE', 'PREVIEW', 'CONNECTING', 'SAVE_FAILED'])
def test_agent_does_not_hide_active_training_or_unsaved_result(desktop, state):
    w, r, app = desktop
    w.state = state
    w.agent_button.click()
    assert w.agent_dialog is None and not r.calls


def test_late_reply_old_request_and_changed_scope_cannot_navigate(desktop):
    w, r, app = desktop
    w.agent_button.click()
    d = w.agent_dialog
    d.receive('old-request', dict(scope=d.scope, text='wrong'))
    assert not d.allowed_actions
    reply(w)
    w.participant_id = 'someone-else'
    w._agent_navigate('assessment')
    assert not d.allowed_actions and '变化' in d.browser.toPlainText()
    d.reject()


def test_failure_clears_old_actions_and_allows_retry(desktop):
    w, r, app = desktop
    w.agent_button.click()
    reply(w)
    d = w.agent_dialog
    d.ask('今天练什么')
    assert not d.allowed_actions
    w._handle_message(dict(kind='error', command='rehab_agent', request_id=d.request_id, text='读取失败'))
    w._handle_message(dict(kind='command_done', command='rehab_agent'))
    assert d.send.isEnabled() and '读取失败' in d.browser.toPlainText()
    d.reject()


def test_plan_action_opens_existing_screen_without_prefilled_screening(desktop):
    w, r, app = desktop
    w.agent_button.click()
    reply(w, actions=[dict(id='automatic', label='查看并确认训练安排')])
    w._agent_navigate('automatic')
    assert r.calls[-1][0] == 'automatic_proposal'
    assert w.automatic_dialog and not w.automatic_dialog.general.isChecked()
    w.automatic_dialog.reject()


def test_family_share_action_opens_existing_silver_screen_without_sending(desktop):
    w, r, app = desktop
    w.agent_button.click()
    reply(w, actions=[dict(id='silver', label='查看家庭共享设置')])
    w._agent_navigate('silver')
    assert w.agent_dialog is None and w.silver_dialog.isVisible()
    assert not any(n in ('request', 'consent', 'send_family') for n, _ in r.calls)
    w.silver_dialog.close()
