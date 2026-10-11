"""Replies report the recorded provider outcome, independently of configured keys."""
import pytest
from test_product_window import desktop, wait
from app.ui.product_widgets import conversation_html, conversation_source
from app.ui.product_record_review import record_review


@pytest.mark.parametrize('metadata,label',[
    ({'provider':'deepseek','status':'replied'},'DeepSeek 回复'),
    ({'provider':'local','status':'unavailable','reason':'not_configured'},'未配置 DeepSeek · 本地回复'),
    ({'provider':'local','status':'failed','reason':'network'},'DeepSeek 本轮未完成 · 本地回复'),
])
def test_native_reply_source_only_reports_trusted_outcome(metadata,label):
    assert conversation_source(metadata)==label
    colors=dict(secondary='#444444',text='#111111',soft='#eeeeee',surface='#ffffff')
    markup=conversation_html([
        dict(role='elder',text='<TEST user>',time='TEST',conversation=metadata),
        dict(role='agent',text='<TEST reply>',time='TEST',conversation=metadata),
    ],colors)
    assert markup.count(label)==1
    assert '&lt;TEST user&gt;' in markup and '&lt;TEST reply&gt;' in markup
    assert '<TEST reply>' not in markup


def test_native_source_does_not_claim_connection_or_expose_unknown_errors():
    for value in (None,{},'TEST secret',{'provider':'deepseek','status':'failed'},
                  {'provider':'local','status':'replied'},
                  {'provider':'<TEST secret>','status':'replied'},
                  {'provider':'local','status':'unavailable','reason':'<TEST secret>'}):
        assert conversation_source(value)==''
    title,details=record_review(dict(conversation=dict(provider='local',status='failed',reason='TEST secret'),
        understanding={},appliedChanges={},persistence={'status':'saved'},reply={'persisted':False}))
    assert 'DeepSeek 本轮未完成' in title and '本轮不记录' in title
    assert 'TEST secret' not in details


def test_live_widgets_show_recorded_reply_status_in_both_themes(desktop):
    w,app=desktop;w.navigate('assistant');wait(app,lambda:not w.pending)
    w.snapshot['state']['chat']=[
        dict(role='elder',text='TEST 普通聊天',time='2026-10-11T10:00:00Z'),
        dict(role='agent',text='TEST 本轮联网回复',time='2026-10-11T10:00:01Z',
             conversation={'provider':'deepseek','status':'replied'})]
    for theme in ('light','dark'):
        w.product_theme.apply(theme);w._render_conversation();app.processEvents()
        assert 'DeepSeek 回复' in w.chat.toPlainText()
        assert 'DeepSeek 回复' in w.dock_chat.toPlainText()
        assert '<TEST' not in w.chat.toPlainText()
    w.snapshot['conversationModelAvailable']=True
    w._show_assistant_section('overview');app.processEvents()
    from app.ui.product_assistant import refresh_summary
    refresh_summary(w)
    assert '已配置' in w.assistant_portal_status.text()
    assert '实际来源' in w.assistant_portal_status.text()
