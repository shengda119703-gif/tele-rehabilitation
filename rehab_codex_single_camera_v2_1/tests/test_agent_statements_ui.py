from app.agent_statements import StatementSession
from app.silver_store import SilverStore
from test_product_navigation import desktop
from test_rehab_agent_ui import reply


def test_ui_confirmation_receipt_reset_and_scope_guard(desktop, tmp_path):
    w, runtime, app = desktop
    w.agent_button.click()
    reply(w)
    d = w.agent_dialog
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(d.scope, lambda: care)
    d.ask('我今天头晕')
    result = s.turn('我今天头晕')
    d.receive(d.request_id, result)
    body = d.browser.toPlainText()
    assert all(label in body for label in ('康复管家', '本人 · 今天 · 头晕', '待确认操作'))
    assert '未写入自报记录' not in body and '隐私与执行状态' not in body
    assert d.transcript[-1]['result']['receipt']['status'] == 'not_saved'
    assert not care.records(d.scope, 'agent_self_report')
    token = result['proposed_actions'][0]['id']
    button = d.action_row.itemAt(0).widget()
    assert '确认保存' in button.text() and '原话' in button.toolTip()
    button.click()
    name, payload = runtime.calls[-1]
    assert name == 'rehab_agent' and payload['operation'] == 'act' and payload['action_id'] == token
    assert 'config' not in payload
    d.receive(d.request_id, s.act(token))
    assert '已保存到本机' in d.browser.toPlainText()
    assert d.history[-1]['shareable'] is False
    cid = d.conversation_id
    d.clear_conversation()
    assert runtime.calls[-1][1] == dict(operation='reset', conversation_id=cid)
    assert d.conversation_id != cid and not d.proposals
    d.ask('查看自报记录')
    result = s.turn('查看自报记录')
    d.receive(d.request_id, result)
    assert '头晕' in d.browser.toPlainText()
    assert '确认撤回' in d.action_row.itemAt(0).widget().text()
    w.participant_id = 'other'
    before = len(runtime.calls)
    d.action_row.itemAt(0).widget().click()
    assert len(runtime.calls) == before
    assert '变化' in d.browser.toPlainText() and not d.proposals
    d.reject()


def test_cancel_and_stale_reply_do_not_restore_confirmation(desktop, tmp_path):
    w, runtime, app = desktop
    w.agent_button.click()
    reply(w)
    d = w.agent_dialog
    s = StatementSession(d.scope, lambda: SilverStore(tmp_path/'support.sqlite3'))
    d.ask('我今天头晕')
    result = s.turn('我今天头晕')
    old_id = d.request_id
    d.receive(old_id, result)
    d.action_row.itemAt(1).widget().click()
    assert runtime.calls[-1][1]['action_id'] == 'cancel'
    d.receive(d.request_id, s.act('cancel'))
    d.receive(old_id, result)
    assert not d.proposals and '已取消' in d.browser.toPlainText()
    d.reject()


def test_paging_can_select_fifth_without_changing_first_four(desktop, tmp_path):
    w, runtime, app = desktop
    w.agent_button.click()
    reply(w)
    d = w.agent_dialog
    care = SilverStore(tmp_path/'support.sqlite3')
    s = StatementSession(d.scope, lambda: care)
    for _ in range(5):
        proposed = s.turn('我今天头晕')
        s.act(proposed['proposed_actions'][0]['id'])
    d.ask('查看自报记录')
    result = s.turn('查看自报记录')
    d.receive(d.request_id, result)
    before = len(runtime.calls)
    d.action_row.itemAt(4).widget().click()
    assert len(runtime.calls) == before
    assert len(d.proposals) == 1
    fifth = result['proposed_actions'][4]['id']
    assert fifth in d.proposals
    d.action_row.itemAt(0).widget().click()
    assert runtime.calls[-1][1]['action_id'] == fifth
    d.receive(d.request_id, s.act(fifth))
    rows = care.records(d.scope, 'agent_self_report')
    assert sum(r['status'] == 'ACTIVE' for r in rows) == 4
    assert sum(r['status'] == 'RETRACTED' for r in rows) == 1
    d.reject()
