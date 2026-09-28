from PySide6.QtWidgets import QLineEdit

from app.ui.rehab_agent import ModelSettingsDialog
from test_product_navigation import desktop
from test_rehab_agent_ui import reply
from test_agent_conversation import CONFIG


def test_settings_key_masked_and_consent_not_inherited(desktop):
    w, runtime, app = desktop
    d = ModelSettingsDialog(CONFIG, w)
    assert d.key.echoMode() == QLineEdit.EchoMode.Password
    assert not d.consent.isChecked()
    d.save()
    assert '确认' in d.error.text()
    d.consent.setChecked(True)
    d.save()
    assert d.config == CONFIG


def test_transcript_context_clear_and_no_global_busy(desktop):
    w, runtime, app = desktop
    w.agent_button.click()
    assert w.busy == 0
    reply(w, text='本地记录', mode='local', shareable=False)
    d = w.agent_dialog
    d.model_config = CONFIG
    d.ask('我是傻逼吗')
    reply(w, text='发生什么事了吗？', mode='model', shareable=True)
    d.ask('就是刚才很烦')
    _, kwargs = runtime.calls[-1]
    assert kwargs['config'] == CONFIG
    assert kwargs['history'][-1]['user'] == '我是傻逼吗'
    reply(w, text='愿意说说刚才的事吗？', shareable=True)
    text = d.browser.toPlainText()
    assert '我是傻逼吗' in text and '就是刚才很烦' in text
    d.clear_conversation()
    assert not d.history and not d.transcript and not d.allowed_actions
    d.reject()
    assert w._agent_model_config == CONFIG


def test_private_turn_cannot_leak_to_next_request_and_disconnect_clears(desktop):
    w, runtime, app = desktop
    w.agent_button.click()
    reply(w)
    d = w.agent_dialog
    d.model_config = CONFIG
    d.ask('不要记录我的秘密')
    reply(w, text='本轮未联网', shareable=False)
    assert d.history[-1]['shareable'] is False
    d.disconnect()
    assert d.model_config is None and not d.history
    d.reject()
    assert w._agent_model_config is None
