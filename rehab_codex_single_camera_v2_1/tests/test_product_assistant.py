"""Real Qt modular assistant paths over the existing product fixture/bridge."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_product_window import desktop,wait
from app.ui.product_dialogs import blank_health
from bridges.ankang.client import AgentBridge


def section(w,key):
    return w.assistant_sections.currentWidget() is w.assistant_views[key]


def test_portal_cards_are_clickable_and_tools_are_not_piled_into_first_screen(desktop):
    w,app=desktop;w.navigate('assistant');wait(app,lambda:not w.pending)
    assert section(w,'conversation') and w.chat.isVisible()
    w.interface_buttons['assistantBackConversation'].click()
    assert section(w,'overview')
    assert all(b.isVisible() for b in w.assistant_module_buttons.values())
    assert not w.chat.isVisible() and not w.voice_status.isVisible() and not w.assistant_reference.isVisible()
    for key in ('conversation','voice','materials','reference'):
        card=w.assistant_module_buttons[key]
        card.setFocus();QTest.keyClick(card,Qt.Key_Space);app.processEvents()
        assert section(w,key)
        w.interface_buttons['assistantBack'+key.title()].click();app.processEvents()
        assert section(w,'overview') and w.assistant_view_history==['overview']


def test_conversation_draft_and_history_survive_module_back_and_global_assistant(desktop):
    w,app=desktop;w.navigate('assistant');wait(app,lambda:not w.pending)
    w.interface_buttons['assistantModuleConversation'].click()
    chat=w.chat;editor=w.chat_input
    editor.setPlainText('TEST 未发送草稿');w.private_turn.setChecked(True)
    w.interface_buttons['assistantReferenceEntry'].click();assert section(w,'reference')
    w.interface_buttons['assistantBackReference'].click();assert section(w,'conversation')
    assert editor.toPlainText()=='TEST 未发送草稿' and w.private_turn.isChecked()
    w.interface_buttons['assistantBackConversation'].click();w.interface_buttons['assistantModuleConversation'].click()
    assert w.chat is chat and w.chat_input is editor and editor.toPlainText()=='TEST 未发送草稿'
    w._open_global_assistant();assert section(w,'conversation')
    w.assistant_dock.close();assert section(w,'conversation') and editor.toPlainText()=='TEST 未发送草稿'
    w.private_turn.setChecked(False);editor.setPlainText('TEST 今天感觉还好');w.chat_send.click()
    wait(app,lambda:not w.pending)
    assert section(w,'conversation') and 'TEST 今天感觉还好' in chat.toPlainText()
    assert any('TEST 今天感觉还好' in m['text'] for m in w.snapshot['state']['chat'])


def test_visible_voice_entry_opens_honest_status_without_starting_unavailable_asr(desktop):
    w,app=desktop;w.navigate('assistant');wait(app,lambda:not w.pending)
    w.interface_buttons['assistantModuleConversation'].click()
    entry=w.interface_buttons['assistantVoiceEntry']
    assert entry.isVisible() and entry.isEnabled() and not entry.icon().isNull()
    editor=w.chat_input;editor.setPlainText('TEST 保留文字')
    pending=w.pending;entry.click();app.processEvents()
    assert section(w,'conversation') and w.pending==pending
    assert '未接入' in w.dictation_status.text()
    w.interface_buttons['assistantVoiceSettings'].click();assert section(w,'voice')
    assert not w.interface_buttons['voiceOutput'].isEnabled()
    w.interface_buttons['assistantVoiceText'].click();assert section(w,'conversation')
    assert editor.toPlainText()=='TEST 保留文字'
    # UI capability state only; no claim that the fixture has a physical ASR host.
    w.private_turn.setChecked(True)
    assert editor.toPlainText()=='TEST 保留文字' and w.pending==0


def test_owner_switch_resets_modules_and_drafts_and_materials_links_to_real_archive(desktop):
    w,app=desktop
    with AgentBridge(data_dir=w.backend.data_dir/'product') as bridge:
        bridge.product('profile.save','person-second',dict(profile=blank_health('TEST 第二位')))
    w._request('profile.list');wait(app,lambda:not w.pending)
    w.navigate('assistant');wait(app,lambda:not w.pending)
    w.interface_buttons['assistantModuleConversation'].click()
    w._send_chat('TEST 前一位的对话');wait(app,lambda:not w.pending)
    assert 'TEST 前一位的对话' in w.chat.toPlainText()
    w.chat_input.setPlainText('TEST 前一位的草稿')
    w.interface_buttons['assistantVoiceSettings'].click();assert section(w,'voice')
    w._select_owner('person-second');wait(app,lambda:not w.pending and not w.legacy.busy)
    assert section(w,'conversation') and not w.chat_input.toPlainText()
    assert not w.snapshot['state']['chat'] and '前一位' not in w.chat.toPlainText()
    assert '前一位' not in w.dock_chat.toPlainText()
    assert '前一位' not in w.assistant_portal_status.text()
    w.interface_buttons['assistantModuleMaterials'].click()
    assert w.interface_buttons['assistantAttachment'].isVisible()
    w.interface_buttons['assistantArchiveEntry'].click();wait(app,lambda:not w.pending)
    assert w.active_page=='health' and w.health_tabs.currentIndex()==2
    w.navigate('assistant');wait(app,lambda:not w.pending);assert section(w,'conversation')


def test_medication_shortcut_edits_draft_only_and_explicit_send_keeps_privacy(desktop):
    from copy import deepcopy
    w,app=desktop;w.navigate('assistant');wait(app,lambda:not w.pending)
    shortcut=next(b for b in w.product_action_buttons() if b.property('actionId')=='product-201')
    assert shortcut.text()=='记录用药情况' and shortcut.property('actionTarget')=='ui.chat.draft'
    before=deepcopy(w.snapshot['state'])
    w.private_turn.setChecked(True)
    QTest.mouseClick(shortcut,Qt.LeftButton);app.processEvents()
    assert w.chat_input.toPlainText()=='我想记录今天的用药情况。'
    assert w.chat_input.hasFocus() and not w.pending
    assert w.private_turn.isChecked() and w.snapshot['state']==before
    # Repeating the shortcut neither duplicates the starter nor sends it.
    shortcut.setFocus();QTest.keyClick(shortcut,Qt.Key_Space);app.processEvents()
    assert w.chat_input.toPlainText()=='我想记录今天的用药情况。' and not w.pending
    draft='TEST 我今天没有漏服药，只想核对记录。'
    w.chat_input.setPlainText(draft)
    QTest.mouseClick(shortcut,Qt.LeftButton);app.processEvents()
    assert w.chat_input.toPlainText()==draft and w.chat_input.hasFocus()
    assert not w.pending and w.snapshot['state']==before
    # Re-read persistence before explicit send; no hidden turn/event was created.
    w._request('snapshot');wait(app,lambda:not w.pending)
    assert w.snapshot['state']['chat']==before['chat'] and w.snapshot['state']['events']==before['events']
    QTest.keyClick(w.chat_input,Qt.Key_Return,Qt.ControlModifier);wait(app,lambda:not w.pending)
    assert draft in w.chat.toPlainText() and not w.chat_input.toPlainText()
    assert w.snapshot['state']['events']==before['events']
    assert '本轮不记录' in w.record_receipt.text()
    # Explicit medication commands retain their original domain route.
    assert w.interface_buttons['medMiss'].property('actionTarget')=='chat'
    assert w.interface_buttons['medMissedAdd'].property('actionTarget')=='chat'


def test_conversation_chrome_keeps_errors_receipts_and_contextual_assistant(desktop):
    w,app=desktop;w.navigate('assistant');wait(app,lambda:not w.pending)
    assert not w.product_meta.isVisible() and not w.interface_buttons['globalAssistant'].isVisible()
    assert not w.agent_status.isVisible() and w.assistant_status_toggle.text()=='基础模式'
    w.assistant_status_toggle.setFocus();QTest.keyClick(w.assistant_status_toggle,Qt.Key_Space)
    assert w.agent_status.isVisible() and '尚未配置' in w.agent_status.text()
    assert w.assistant_connection.text()==w.storage_label.text()
    QTest.keyClick(w.assistant_status_toggle,Qt.Key_Space);assert not w.agent_status.isVisible()
    w._send_chat('今天头晕');wait(app,lambda:not w.pending)
    assert w.record_receipt.isVisible() and w.record_disclosure.isVisible()
    assert not w.notice.isVisible() and not w.page_states['assistant'].isVisible()
    w._message('操作已完成，已刷新本机资料。',severity='success');w._completion_controls()
    assert w.notice.isVisible()  # A non-chat operation may have only this acknowledgement.
    w._message('TEST 导出已保存',severity='success');w._completion_controls()
    assert w.notice.isVisible()  # Specific successful actions still have feedback.
    w._message('TEST 保存失败，记录尚未保存',severity='danger');w._completion_controls()
    assert w.notice.isVisible() and w.notice.property('fluentStatus')=='danger'
    w._message('TEST 需要确认人物关系');w._completion_controls();assert w.notice.isVisible()
    w.interface_buttons['assistantVoiceSettings'].click()
    assert w.product_meta.isVisible() and w.interface_buttons['globalAssistant'].isVisible()
    w.interface_buttons['assistantVoiceText'].click();assert not w.product_meta.isVisible()
    w.navigate('health');wait(app,lambda:not w.pending)
    assert w.product_meta.isVisible() and w.interface_buttons['globalAssistant'].isVisible()
    QTest.mouseClick(w.interface_buttons['globalAssistant'],Qt.LeftButton);assert w.assistant_dock.isVisible()
    w.assistant_dock.close();w.navigate('assistant');wait(app,lambda:not w.pending)
    QTest.keyClick(w.chat_input,Qt.Key_J,Qt.ControlModifier);app.processEvents()
    assert w.assistant_dock.isVisible()  # Original keyboard capability remains available.
    w.assistant_dock.close();w._clear_views();assert not w.assistant_status_toggle.isChecked()
