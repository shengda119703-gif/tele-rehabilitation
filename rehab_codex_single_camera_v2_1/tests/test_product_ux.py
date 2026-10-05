"""User-facing receipt, draft and reading continuity over the real local bridge."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_product_window import desktop,wait
from app.ui.product_record_review import record_review


def test_live_turn_receipt_and_keyboard_send_preserve_next_draft(desktop):
    w,app=desktop;w.navigate('assistant');wait(app,lambda:not w.pending)
    w.interface_buttons['assistantModuleConversation'].click()
    w.chat_input.setPlainText('今天收缩压130');w.chat_input.setFocus()
    QTest.keyClick(w.chat_input,Qt.Key_Return,Qt.ControlModifier)
    assert w.pending and '正在理解' in w.record_receipt.text()
    w.chat_input.setPlainText('TEST 下一条尚未发送的草稿')
    wait(app,lambda:not w.pending)
    assert w.chat_input.toPlainText()=='TEST 下一条尚未发送的草稿'
    assert w.record_disclosure.isVisible()
    assert '已保存到本机' in w.record_receipt.text()
    assert '本人' in w.record_review.toPlainText() and '今天' in w.record_review.toPlainText()
    assert any(e['type']=='measurement' for e in w.snapshot['state']['events'])
    QTest.mouseClick(w.record_disclosure,Qt.LeftButton);app.processEvents()
    assert w.record_dialog.isVisible()
    w._clear_views();app.processEvents()
    assert not w.record_dialog.isVisible() and not w.record_review.toPlainText()


def test_quick_question_does_not_erase_unsent_draft_and_no_record_receipt_is_honest(desktop):
    w,app=desktop;w.chat_input.setPlainText('TEST 尚未发送')
    w._send_chat('你好');wait(app,lambda:not w.pending)
    assert w.chat_input.toPlainText()=='TEST 尚未发送'
    before=len(w.snapshot['state']['events'])
    w.private_turn.setChecked(True);w.chat_input.setPlainText('今天头晕')
    w._send_chat();wait(app,lambda:not w.pending)
    assert '本轮不记录' in w.record_receipt.text()
    assert len(w.snapshot['state']['events'])==before
    assert not w.chat_input.toPlainText()


def test_refresh_retains_reader_scroll_and_text_selection(desktop):
    w,app=desktop
    w.snapshot['state']['chat']=[dict(role='elder',text=f'TEST 长对话 {i}',time='TEST') for i in range(60)]
    w._render_conversation();w.chat.verticalScrollBar().setValue(0)
    cursor=w.chat.textCursor();cursor.select(cursor.SelectionType.Document);w.chat.setTextCursor(cursor)
    selected=cursor.selectedText();w._render_conversation()
    assert w.chat.verticalScrollBar().value()==0
    assert w.chat.textCursor().selectedText()==selected


def test_receipt_never_claims_unsaved_or_uncertain_input_is_saved_fact():
    turn=dict(understanding=dict(claims=[dict(subject='mother',status='uncertain',timeScope='yesterday',text='<TEST>')]),
              appliedChanges={},persistence=dict(status='failed'),reply={})
    title,details=record_review(turn)
    assert '尚未确认保存' in title
    assert '母亲' in details and '不确定' in details and '昨天' in details
    assert '&lt;TEST&gt;' in details and '<TEST>' not in details


def test_recovery_saved_feedback_has_room_for_every_wrapped_line(desktop):
    w,app=desktop;w.navigate('rehab');wait(app,lambda:not w.pending)
    field=w.recovery_fields['result']
    field.setText('TEST 肩外展 · 2026-10-05 10:00\n已记录 1 次；已完成计划目标\n疼痛评分：0；疲劳评分：0；本人说明：'+('TEST 完整反馈。'*15))
    for width in (1440,1024,1440):
        w.resize(width,720);QTest.qWait(150);app.processEvents()
        assert field.height()>=field.heightForWidth(field.width()),(field.size(),field.heightForWidth(field.width()))
        assert w.rehab_tabs.widget(0).horizontalScrollBar().maximum()==0
def test_navigation_marker_settles_after_rapid_keyboard_navigation(desktop, monkeypatch):
    from PySide6.QtCore import Qt, QAbstractAnimation
    from PySide6.QtTest import QTest
    w,app=desktop
    wait(app,lambda:not w.pending)
    for page in ('health','home','family'):
        w.nav_buttons[page].setFocus(Qt.TabFocusReason)
        QTest.keyClick(w.nav_buttons[page],Qt.Key_Space)
        wait(app,lambda:not w.pending)
    QTest.qWait(200)
    assert w.active_page=='family'
    target=w.nav_buttons['family']
    assert w.selection_rail.mark.geometry().center().y()==target.geometry().center().y()
    assert w.selection_rail.animation.state()==QAbstractAnimation.Stopped
    monkeypatch.setenv('ANKANG_REDUCED_MOTION','1')
    w.navigate('home',refresh=False)
    assert w.selection_rail.animation.state()==QAbstractAnimation.Stopped
    assert w.selection_rail.mark.geometry().center().y()==w.nav_buttons['home'].geometry().center().y()


def test_assistant_entry_keyboard_and_current_settings_height(desktop):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w,app=desktop
    w.resize(1024,720);w.navigate('assistant');wait(app,lambda:not w.pending)
    entry=w.assistant_module_buttons['conversation'];entry.setFocus(Qt.TabFocusReason)
    QTest.keyClick(entry,Qt.Key_Space);app.processEvents()
    assert w.assistant_sections.currentWidget() is w.assistant_views['conversation']
    assert w.chat_input.hasFocus()
    assert w.page_widgets['assistant'].horizontalScrollBar().maximum()==0
    w.navigate('settings');wait(app,lambda:not w.pending)
    w.settings_tabs.setCurrentIndex(3);app.processEvents();large=w.settings_tabs.height()
    w.settings_tabs.setCurrentIndex(0);app.processEvents()
    assert w.settings_tabs.height()<large
