"""Task routing and safe state presentation, with explicit TEST read models."""
from test_product_window import desktop,wait

def present(w,plan=None):
    w.snapshot['rehabilitation_ui']['rehab.get_training_plan']['records']=[plan] if plan else []
    w._present_rehab(plan,[],[],w.legacy._body_scope_key())
    w._completion_controls()

def plan(available=True,done=False):
    return dict(id='TEST-plan',name='TEST 累计安排',next_available=available,availability_reason='TEST 来源条件不成立',
        items=[dict(key='TEST-item',exercise_id='shoulder_abduction',exercise_label='TEST 肩外展',side='left',settings={})],
        progress=dict(next_key=None if done else 'TEST-item',completed=int(done),total=1))

def test_empty_task_routes_to_assessment_without_starting_camera(desktop,monkeypatch):
    w,app=desktop;w.navigate('rehab');wait(app,lambda:not w.pending);w.refresher.stop()
    present(w);calls=[];monkeypatch.setattr(w.legacy,'_show_catalog',lambda:calls.append('assessment'))
    assert w.interface_buttons['rehabContinue'].text()=='开始评估'
    assert not w.rehab_progress.isVisible()
    assert not w.interface_buttons['rehabStart'].isVisible()
    assert not w.recovery_sections['result'].isVisible()
    w.interface_buttons['rehabContinue'].click()
    assert calls==['assessment'] and w.rehab_workspace.isVisible()
    assert not any(name in ('start','open') for name,args in w.legacy.runtime.calls)
    w.interface_buttons['rehabWorkspaceBack'].click()
    assert w.rehab_tabs.currentIndex()==1

def test_plan_primary_respects_unavailable_complete_and_running_states(desktop,monkeypatch):
    w,app=desktop;w.navigate('rehab');wait(app,lambda:not w.pending);w.refresher.stop()
    calls=[];monkeypatch.setattr(w,'_continue_training',lambda:calls.append('prepare'))
    present(w,plan());assert w.interface_buttons['rehabContinue'].text()=='准备训练'
    w.interface_buttons['rehabContinue'].click();assert calls==['prepare']
    present(w,plan(False));assert not w.interface_buttons['rehabContinue'].isEnabled()
    w.interface_buttons['rehabContinue'].click();assert calls==['prepare']
    present(w,plan(done=True));assert w.interface_buttons['rehabContinue'].text()=='查看训练记录'
    w.interface_buttons['rehabContinue'].click();assert w.rehab_tabs.currentIndex()==3
    for state in ('CONNECTING','PREVIEW','ONLINE','SAVE_FAILED'):
        w.legacy.state=state;w._completion_controls();assert not w.interface_buttons['rehabContinue'].isEnabled()
    w.legacy.state='UNSELECTED'

def test_summaries_and_utilities_have_single_visible_home(desktop):
    w,app=desktop;w.navigate('rehab');wait(app,lambda:not w.pending)
    assert w.recovery_sections['assessment'].parentWidget() is w.rehab_tabs.widget(1).widget()
    assert w.recovery_sections['trend'].parentWidget() is w.rehab_tabs.widget(3).widget()
    assert not w.interface_buttons['rehabHome'].isVisible()
    assert not w.interface_buttons['silverRehab'].isVisible()
    assert not w.interface_buttons['recoveryAsk'].isVisible()
    w.navigate('settings');wait(app,lambda:not w.pending)
    assert w.interface_buttons['rehabPerson'].isVisible()
    w.navigate('family');wait(app,lambda:not w.pending)
    assert not w.interface_buttons['silverFamily'].isVisible()
    w.interface_buttons['familyOldTools'].click()
    assert w.interface_buttons['silverFamily'].isVisible()

def test_long_feedback_preview_keeps_original_record_and_full_detail(desktop):
    w,app=desktop
    feedback=dict(pain=0,fatigue=0,notes='TEST 完整本人说明。'*30)
    preview=w._feedback_preview(feedback)
    assert '完整说明见详情' in preview and len(preview)<120
    assert feedback['notes'] in w._feedback_text(feedback)
    assert len(feedback['notes'])>300
