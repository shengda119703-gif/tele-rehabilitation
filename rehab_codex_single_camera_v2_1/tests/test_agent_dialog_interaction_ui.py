import copy

import pytest
from PySide6.QtCore import Qt, QUrl, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from app.ui.rehab_agent import RehabAgentDialog, ModelSettingsDialog
from app.ui.agent_presentation import present_result
from app.agent_statements import StatementSession
from app.agent_conversation import converse
from app.silver_store import SilverStore
from test_product_navigation import desktop
from test_automatic_plans import SCOPE


@pytest.mark.parametrize('key', [Qt.Key_Return, Qt.Key_Enter])
@pytest.mark.parametrize('immediate', [False, True])
@pytest.mark.parametrize('force_return_default', [False, True])
def test_enter_three_rounds_single_send_no_close(desktop, tmp_path, key, immediate, force_return_default):
    _, _, app = desktop
    d = RehabAgentDialog(SCOPE)
    session = StatementSession(SCOPE, lambda: SilverStore(tmp_path/'support.sqlite3'))
    sent, clicks, closed = [], [], []
    d.finished.connect(closed.append)
    for button in d.findChildren(QPushButton):
        button.clicked.connect(lambda checked=False, b=button: clicks.append(b.text()))
    close = next(b for b in d.findChildren(QPushButton) if b.text() == '返回原页面')
    if force_return_default:
        # Regression remains safe even if a later UI edit accidentally adds a default.
        close.setAutoDefault(True)
        close.setDefault(True)
    def requested(text, request_id):
        sent.append((text, request_id))
        if immediate:
            d.receive(request_id, session.turn(text))
    d.requested.connect(requested)
    d.show()
    app.processEvents()
    app.processEvents()
    try:
        for index, text in enumerate(('昨天妈妈头晕', '我今天没头晕', '我头晕'), 1):
            d.input.setFocus()
            d.input.setText(text)
            QTest.keyClick(d.input, key)
            app.processEvents()
            assert d.isVisible() and not closed and not clicks
            assert len(sent) == index and sent[-1][0] == text
            assert d.input.text() == ''
            # Disabled-input keys, or a second key on now-empty input, do nothing.
            QTest.keyClick(d.input, key)
            QTest.keyClick(d, key)
            assert d.isVisible() and len(sent) == index and not clicks
            if not immediate:
                d.receive(d.request_id, session.turn(text))
            assert d.input.isEnabled() and d.input.hasFocus()
        QTest.mouseClick(close, Qt.LeftButton)
        assert not d.isVisible() and closed == [0] and clicks == ['返回原页面']
    finally:
        d.deleteLater()
        app.processEvents()


def test_enter_during_write_never_confirms_or_closes(desktop, tmp_path):
    _, _, app = desktop
    care = SilverStore(tmp_path/'support.sqlite3')
    session = StatementSession(SCOPE, lambda: care)
    d = RehabAgentDialog(SCOPE)
    sends, operations = [], []
    d.requested.connect(lambda *args: sends.append(args))
    d.operation_requested.connect(lambda *args: operations.append(args))
    d.show()
    app.processEvents()
    d.input.setFocus()
    d.input.setText('我今天头晕')
    QTest.keyClick(d.input, Qt.Key_Return)
    result = session.turn(sends[-1][0])
    d.receive(d.request_id, result)
    token = result['proposed_actions'][0]['id']
    d.action_row.itemAt(0).widget().click()
    assert d.write_busy and len(operations) == 1
    for key in (Qt.Key_Return, Qt.Key_Enter):
        QTest.keyClick(d.input, key)
        QTest.keyClick(d, key)
    assert d.isVisible() and len(sends) == 1 and len(operations) == 1
    assert not care.records(SCOPE, 'agent_self_report')
    d.receive(d.request_id, session.act(token))
    assert d.isVisible() and '已保存到本机' in d.browser.toPlainText()
    assert not d.write_busy and d.input.hasFocus()
    d.reject()


def test_all_static_dynamic_and_settings_buttons_never_default(desktop, tmp_path):
    _, _, app = desktop
    d = RehabAgentDialog(SCOPE)
    session = StatementSession(SCOPE, lambda: SilverStore(tmp_path/'support.sqlite3'))
    settings = ModelSettingsDialog(parent=d)
    def check(dialog):
        assert all(not b.autoDefault() and not b.isDefault() for b in dialog.findChildren(QPushButton))
    d.show()
    app.processEvents()
    app.processEvents()
    check(d)
    check(settings)
    for text in ('我今天头晕，我今天腿疼', '我刚才说错了'):
        d.ask(text)
        d.receive(d.request_id, session.turn(text))
        check(d)
    d.ask('告诉家人我今天头晕')
    d.receive(d.request_id, converse(None, SCOPE, '告诉家人我今天头晕'))
    check(d)
    d.input.setFocus()
    d.input.setText('我头晕')
    sent = []
    d.requested.connect(lambda *args: sent.append(args))
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier, '', True, 1)
    QApplication.sendEvent(d.input, event)
    assert not sent and d.isVisible()
    d.reject()


@pytest.mark.parametrize('text,reply_fragment,secondary,count', [
    ('昨天妈妈头晕', '妈妈昨天头晕', '家人 · 昨天 · 头晕', 0),
    ('我今天没头晕', '今天没有头晕', '本人 · 今天 · 头晕 · 否定', 0),
    ('我头晕', '现在正在头晕，还是之前发生过头晕', '本人 · 时间待确认 · 头晕', 0),
    ('我今天头晕', '你说自己今天头晕', '本人 · 今天 · 头晕', 1),
    ('我今天头晕，我今天腿疼', '今天腿疼', '本人 · 今天 · 腿疼', 2),
    ('如果我现在头晕', '是一个假设', '假设', 0),
    ('我现在可能头晕', '还不能确定这件事是否实际发生', '不确定', 0),
    ('头晕', '是你本人还是家人的情况', '人物待确认', 0),
])
def test_targeted_reply_compact_display_keeps_full_contract(desktop, tmp_path, text, reply_fragment, secondary, count):
    _, _, app = desktop
    session = StatementSession(SCOPE, lambda: SilverStore(tmp_path/'support.sqlite3'))
    result = session.turn(text)
    original = copy.deepcopy(result)
    view = present_result(result, text)
    assert result == original
    assert reply_fragment in view['assistant'] and secondary in view['secondary']
    assert len(result['proposed_actions']) == count
    assert not view['receipt_text'] and not view['privacy_notice']
    assert all(k in result for k in ('main_text', 'understanding', 'evidence_summary', 'receipt',
                                    'privacy_status', 'proposed_actions', 'delivery_status'))
    d = RehabAgentDialog(SCOPE)
    d.show()
    app.processEvents()
    d.ask(text)
    d.receive(d.request_id, result)
    body = d.browser.toPlainText()
    assert reply_fragment in body and secondary in body
    assert all(s not in body for s in ('理解依据（原话解析）', '未写入自报记录', '隐私与执行状态', '本轮未发送给 DeepSeek'))
    assert ('待确认操作' in body) == bool(count)
    assert d.transcript[-1]['result'] == original
    d.browser.anchorClicked.emit(QUrl('details:' + d.transcript[-1]['id']))
    assert '未写入自报记录' in d.browser.toPlainText() and '本轮未发送给 DeepSeek' in d.browser.toPlainText()
    assert result == original
    d.reject()


@pytest.mark.parametrize('text', ['不要记录，我今天头晕', '别告诉家人，我今天头晕', '告诉家人我今天头晕'])
def test_explicit_privacy_remains_prominent(desktop, text):
    _, _, app = desktop
    d = RehabAgentDialog(SCOPE)
    d.show()
    app.processEvents()
    d.ask(text)
    result = converse(None, SCOPE, text)
    d.receive(d.request_id, result)
    body = d.browser.toPlainText()
    assert '隐私与执行状态' in body and result['privacy_notice'] in body
    assert not d.proposals
    d.reject()


def test_saved_retracted_ids_folded_and_cancel_discard_visible(desktop, tmp_path):
    _, _, app = desktop
    care = SilverStore(tmp_path/'support.sqlite3')
    session = StatementSession(SCOPE, lambda: care)
    d = RehabAgentDialog(SCOPE)
    d.show()
    app.processEvents()
    def turn(text):
        d.ask(text)
        result = session.turn(text)
        d.receive(d.request_id, result)
        return result
    result = turn('我今天头晕')
    for expected, fragment in (('saved', '已保存到本机'), ('retracted', '已撤回这一条')):
        token = result['proposed_actions'][0]['id']
        d.confirm_operation(token)
        result = session.act(token)
        d.receive(d.request_id, result)
        assert result['receipt']['status'] == expected
        body = d.browser.toPlainText()
        assert '自报 / 记录回执' in body and fragment in body and '记录号：' not in body
        assert result['receipt']['record_id'] not in body
        assert d.transcript[-1]['result']['receipt']['revision'] > 0
        d.toggle_details(QUrl('details:' + d.transcript[-1]['id']))
        assert result['receipt']['record_id'] in d.browser.toPlainText()
        d.toggle_details(QUrl('details:' + d.transcript[-1]['id']))
        if expected == 'saved':
            result = turn('我刚才说错了，没有头晕')
    turn('我今天腿疼')
    result = turn('我刚才说错了')
    token = result['proposed_actions'][0]['id']
    d.confirm_operation(token)
    result = session.act(token)
    d.receive(d.request_id, result)
    assert '已撤销这条未保存自述' in d.browser.toPlainText()
    turn('我今天头晕')
    d.confirm_operation('cancel')
    d.receive(d.request_id, session.act('cancel'))
    assert '没有新增或更改自报' in d.browser.toPlainText()
    d.reject()
