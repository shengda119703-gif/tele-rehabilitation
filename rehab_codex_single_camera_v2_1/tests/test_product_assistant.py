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
