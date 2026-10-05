"""Visual migration must preserve published actions, native focus and owner isolation."""
import csv
from pathlib import Path
from PySide6.QtCore import Qt,SIGNAL
from PySide6.QtGui import QColor,QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton
from test_product_window import desktop,wait
from app.ui.product_theme import design_tokens
from app.ui.product_assistant import ASSISTANT_NAV_ACTIONS
from app.ui.product_completion import MODULE_NAV_ACTIONS, RECOVERY_NAV_ACTIONS


def test_published_116_button_contract_and_native_connections(desktop):
    w,app=desktop
    audit=Path(__file__).resolve().parents[2]/'docs/validation/PRODUCT_UI_BUTTON_AUDIT_2026-10-02.csv'
    with audit.open(encoding='utf-8-sig',newline='') as stream:
        expected={r['ID']:(r['用户按钮'],r['实际动作']) for r in csv.DictReader(stream)}
    # The previous CSV captured visible pages; the already-existing closed dock is extra.
    expected['dockSend']=('发送','chat')
    expected['rehabAction']=('查看下一项 / 动作目录','原动作目录')
    actual={b.property('actionId'):(b.text(),b.property('actionTarget')) for b in w.product_action_buttons()}
    assert {key:actual[key] for key in expected}==expected
    assert set(actual)-set(expected)==ASSISTANT_NAV_ACTIONS|MODULE_NAV_ACTIONS|RECOVERY_NAV_ACTIONS|{'voiceFinish'}
    assert len(actual)==len(w.product_action_buttons())==118+len(ASSISTANT_NAV_ACTIONS)+len(MODULE_NAV_ACTIONS)+len(RECOVERY_NAV_ACTIONS)
    assert all(b.property('actionKind')=='B' for b in w.product_action_buttons() if b.property('actionId') in ASSISTANT_NAV_ACTIONS)
    assert all(b.receivers(SIGNAL('clicked(bool)'))>0 for b in w.product_action_buttons())


def test_minimum_window_composer_keyboard_focus_and_disabled_controls(desktop):
    w,app=desktop
    w.resize(1024,720);w.navigate('assistant');wait(app,lambda:not w.pending)
    w.interface_buttons['assistantModuleConversation'].click()
    app.processEvents()
    assert w.next_training.font().pixelSize()==20
    assert w.greeting.font().pixelSize()==28
    viewport=w.page_widgets['assistant'].viewport()
    assert viewport.rect().contains(w.chat_send.mapTo(viewport,w.chat_send.rect().bottomRight()))
    assert w.page_widgets['assistant'].horizontalScrollBar().maximum()==0
    w.chat_input.setFocus(Qt.TabFocusReason);app.processEvents()
    assert w.chat_input.hasFocus()
    QTest.keyClick(w.chat_input,Qt.Key_Tab)  # Native editor keeps Tab behavior, no global interception.
    assert w.chat_input.hasFocus()
    w.chat_send.setFocus(Qt.TabFocusReason);app.processEvents()
    assert w.chat_send.hasFocus()
    assert not w.interface_buttons['assistantNew'].isEnabled()
    assert not w.interface_buttons['voiceInput'].isEnabled()
    assert w.interface_buttons['assistantNew'].toolTip()
    w._open_global_assistant();assert w.active_page=='assistant' and w.dock_input.hasFocus()
    w.assistant_dock.close();assert w.active_page=='assistant'


def test_theme_changes_do_not_change_actions_or_data_and_render_escaped_messages(desktop):
    w,app=desktop
    original={b.property('actionId'):(b.property('actionTarget'),b.isEnabled()) for b in w.product_action_buttons()}
    w.snapshot['state']['chat']=[dict(role='elder',text='<script>TEST</script>\n第二行',time='TEST 时间')]
    for mode in ('light','dark','high-contrast','light'):
        palette=QPalette()
        palette.setColor(QPalette.Text,QColor('white'));palette.setColor(QPalette.Window,QColor('black'))
        palette.setColor(QPalette.Base,QColor('black'));palette.setColor(QPalette.Highlight,QColor('yellow'))
        palette.setColor(QPalette.HighlightedText,QColor('black'))
        w.product_theme.apply(mode,palette)
        app.processEvents()
        assert '<script>TEST</script>' in w.chat.toPlainText()
        assert '我' in w.chat.toPlainText() and '第二行' in w.dock_chat.toPlainText()
        assert original=={b.property('actionId'):(b.property('actionTarget'),b.isEnabled()) for b in w.product_action_buttons()}
        # All product pages now follow the active semantic palette, including contrast mode.
        assert w.health_metric_summary.palette().color(QPalette.WindowText).name()==design_tokens(mode,palette)['text']
        assert w.today_medications.palette().color(QPalette.Text).name()==design_tokens(mode,palette)['text']
        # Native delegates must retain readable alternating and selected rows.
        for view in (w.today_medications,w.rehab_tables['今日恢复'],w.metrics,w.trends):
            actual=view.palette()
            for foreground,background in ((QPalette.Text,QPalette.AlternateBase),(QPalette.HighlightedText,QPalette.Highlight)):
                a,b=sorted((luminance(actual.color(foreground).name()),luminance(actual.color(background).name())))
                assert (b+.05)/(a+.05)>=4.5,(mode,view.objectName(),foreground,background)
    w._message('TEST 服务失败',severity='danger')
    assert w.notice.isVisible() and w.notice.property('fluentStatus')=='danger'
    w._visual_progress(dict(total=4,completed=2))
    assert w.home_progress.value()==w.rehab_progress.value()==2
    w._clear_views()
    assert not w.chat.toPlainText() and w.home_progress.value()==w.rehab_progress.value()==0


def luminance(color):
    channels=[int(color[i:i+2],16)/255 for i in (1,3,5)]
    linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
    return sum(v*k for v,k in zip(linear,(.2126,.7152,.0722)))


def test_core_reading_and_status_contrast():
    for mode in ('light','dark'):
        c=design_tokens(mode)
        pairs=[('text','surface'),('secondary','surface'),('on_brand','brand'),('disabled_text','disabled_bg')]
        pairs += [(status,status+'_bg') for status in ('info','success','warning','danger')]
        for foreground,background in pairs:
            a,b=sorted((luminance(c[foreground]),luminance(c[background])))
            assert (b+.05)/(a+.05)>=4.5,(mode,foreground,background)
