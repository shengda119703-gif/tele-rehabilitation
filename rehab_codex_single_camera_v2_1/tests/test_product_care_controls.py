"""Real Qt -> ProductBackend -> Node -> isolated DailyStore acceptance."""
from datetime import date
import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QLabel
from test_product_window import desktop, wait


def proposal(w, med_id='TEST-care-ui-med', med_name='TEST 确认药'):
    scope=dict(w.legacy._body_scope_key(),participant_id=w.owner)
    day=date.today().isoformat()
    w.backend.call('medication.save',w.owner,{'record':{'id':med_id,'name':med_name,'dose':'既有说明','purpose':'','times':'','status':'active'}},scope)
    w.backend.call('daily.medSchedule',w.owner,{'medId':med_id,'times':['08:00'],'start':day,'end':''},scope)
    workflow=w.backend.call('care.prepare',w.owner,{'requestId':'TEST-ui-'+__import__('uuid').uuid4().hex,'text':f'记录今天08:00的{med_name}已服用'},scope)
    return scope,day,workflow


def test_visible_confirmation_performs_no_write_until_click_and_returns_actual_receipt(desktop):
    w,app=desktop;scope,day,workflow=proposal(w)
    w.navigate('assistant');wait(app,lambda:not w.pending)
    controls=w.care_controls
    assert controls.isVisible() and controls.confirm.isEnabled()
    assert not w.backend.daily.snapshot(w.owner,scope)['doses']
    controls.open.click();app.processEvents()
    assert controls.dialog.isVisible() and '尚未执行' in controls.detail.toPlainText()
    controls.confirm.click();assert not controls.confirm.isEnabled()
    wait(app,lambda:not w.pending)
    assert w.backend.daily.snapshot(w.owner,scope)['doses']['TEST-care-ui-med|'+day+'|08:00']['status']=='taken'
    assert '已保存' in controls.detail.toPlainText()
    assert not controls.confirm.isEnabled() and not controls.workflows


def test_cancel_and_scope_change_cannot_execute_old_controls(desktop):
    w,app=desktop;scope,day,workflow=proposal(w)
    w.navigate('assistant');wait(app,lambda:not w.pending)
    controls=w.care_controls
    controls.cancel.click();wait(app,lambda:not w.pending)
    assert not w.backend.daily.snapshot(w.owner,scope)['doses']
    assert '已取消' in controls.detail.toPlainText()
    proposal(w);w._request('snapshot');wait(app,lambda:not w.pending)
    w.legacy.usage.setCurrentIndex(w.legacy.usage.findData('TEST'))
    before=w.pending;controls.submit('care.confirm');assert w.pending==before
    w._clear_views();assert not controls.workflows and not controls.dialog.isVisible()


def test_agent_module_navigation_uses_existing_gate_and_does_not_command_runtime(desktop):
    w,app=desktop;w.navigate('assistant');wait(app,lambda:not w.pending)
    calls=list(w.legacy.runtime.calls)
    w._send_chat('打开用药页');wait(app,lambda:not w.pending)
    assert w.active_page=='medication' and w.legacy.runtime.calls==calls
    w._send_chat('查看健康记录和药物清单');wait(app,lambda:not w.pending)
    assert '健康档案' in w.chat.toPlainText() and '尚无已保存药物' in w.chat.toPlainText()


def test_completed_receipt_does_not_promote_another_pending_operation(desktop):
    w,app=desktop
    scope,day,first=proposal(w,'TEST-care-a','TEST 第一项确认药')
    _,_,second=proposal(w,'TEST-care-b','TEST 第二项确认药')
    w.navigate('assistant');wait(app,lambda:not w.pending)
    controls=w.care_controls
    controls.select.setCurrentIndex(controls.select.findData(first['id']))
    controls.open.click();controls.confirm.click()
    wait(app,lambda:not w.pending)
    saved=w.backend.daily.snapshot(w.owner,scope)
    assert saved['doses']['TEST-care-a|'+day+'|08:00']['status']=='taken'
    assert 'TEST-care-b|'+day+'|08:00' not in saved['doses']
    assert controls.dialog.isVisible()
    assert 'TEST 第一项确认药' in controls.detail.toPlainText() and '已保存' in controls.detail.toPlainText()
    assert 'TEST 第二项确认药' not in controls.detail.toPlainText()
    assert controls.select.currentIndex()==-1 and not controls.confirm.isEnabled()
    assert [item['id'] for item in controls.workflows]==[second['id']]
    controls.select.setCurrentIndex(controls.select.findData(second['id']))
    assert controls.confirm.isEnabled() and 'TEST 第二项确认药' in controls.detail.toPlainText()
    assert 'TEST-care-b|'+day+'|08:00' not in w.backend.daily.snapshot(w.owner,scope)['doses']


@pytest.mark.parametrize(('control','value'),[('source_kind','REPLAY_FILE'),('usage','TEST')])
def test_scope_switch_immediately_closes_confirmation_and_refreshes_current_scope(desktop,control,value):
    w,app=desktop;scope,day,workflow=proposal(w)
    w.navigate('assistant');wait(app,lambda:not w.pending)
    controls=w.care_controls;controls.open.click()
    assert controls.dialog.isVisible() and controls.workflows
    combo=getattr(w.legacy,control);combo.setCurrentIndex(combo.findData(value))
    assert not controls.dialog.isVisible() and not controls.workflows
    assert not controls.confirm.isEnabled()
    before=w.pending;controls.submit('care.confirm');assert w.pending==before
    wait(app,lambda:not w.pending and not w.refresh_needed)
    assert not controls.workflows
    assert not w.backend.daily.snapshot(w.owner,scope)['doses']


@pytest.mark.parametrize('mode',['light','dark'])
def test_confirmation_dialog_labels_receive_central_theme_palette(desktop,mode):
    w,app=desktop;proposal(w);w.navigate('assistant');wait(app,lambda:not w.pending)
    w.product_theme.apply(mode);w.care_controls.open.click();app.processEvents()
    dialog=w.care_controls.dialog
    expected=w.product_theme.colors['text']
    assert dialog.palette().color(QPalette.WindowText).name()==expected
    labels=dialog.findChildren(QLabel)
    assert labels and all(item.palette().color(QPalette.WindowText).name()==expected for item in labels)
    if mode=='dark':
        assert dialog.palette().color(QPalette.Window).lightness()<dialog.palette().color(QPalette.WindowText).lightness()


def test_fitness_navigation_selects_existing_mode_and_respects_active_task_gate(desktop):
    w,app=desktop;calls=list(w.legacy.runtime.calls)
    assert w.navigate('fitness')
    wait(app,lambda:not w.pending)
    assert w.active_page=='rehab' and w.rehab_modes.currentIndex()==2
    assert w.rehab_modes.tabText(w.rehab_modes.currentIndex())=='健身'
    assert w.legacy.runtime.calls==calls
    w.legacy.state='ONLINE'
    assert not w.navigate('fitness')
    assert w.legacy.runtime.calls==calls
    w.legacy.state='UNSELECTED'
