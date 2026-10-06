from datetime import date
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QPushButton
from PySide6.QtTest import QTest
from test_product_window import desktop, wait, AgentBridge
from app.ui.product_dialogs import blank_health


def test_camera_photo_rejects_stale_frame_then_saves_original_private(desktop):
    import time
    from types import SimpleNamespace
    from PySide6.QtWidgets import QLabel
    from PySide6.QtGui import QImage
    w,app=desktop
    image=QImage(80,60,QImage.Format_RGB32);image.fill(Qt.white)
    stopped=[]
    packet=SimpleNamespace(context=SimpleNamespace(source_kind='LIVE_CAMERA'),received_monotonic=time.monotonic()-4)
    dialog=SimpleNamespace(last_packet=packet,stopping=False,canvas=SimpleNamespace(image=image),status=QLabel(),photo_button=QPushButton(),request_stop=lambda:stopped.append(True))
    w._save_camera_photo(dialog)
    assert '新鲜画面' in dialog.status.text() and not stopped
    packet.received_monotonic=time.monotonic()
    w._save_camera_photo(dialog);settle(w,app)
    assert stopped and not dialog.photo_button.isEnabled()
    attachment=w.snapshot['attachments'][0]
    assert attachment['visibility']=='private' and attachment['mediaType']=='image/png'


def test_initial_owner_selection_retries_after_runtime_ready(desktop):
    w,app=desktop
    owner=w.owner;w.owner='';w.snapshot={};w.legacy.busy=1
    w._select_owner(owner)
    assert not w.owner
    w.legacy.busy=0;w._poll();settle(w,app)
    assert w.owner==owner and w.snapshot


def test_manual_plan_change_review_keeps_unchecked_items_and_archives_overwrite(desktop,monkeypatch):
    from PySide6.QtWidgets import QDialog,QCheckBox,QMessageBox
    from app.ui.plan_library import PlanLibraryDialog
    from app.settings import default_plan
    w,app=desktop
    dialog=PlanLibraryDialog(w.legacy._body_scope_key(),w)
    dialog.five_page_flow=True;dialog.version_store=w.backend.daily
    receipts=[];dialog.save_requested.connect(lambda value,revision:receipts.append((value,revision)))
    dialog.new.click();dialog.name.setText('TEST 原计划');dialog._append_item(default_plan('shoulder_abduction'));dialog.save.click()
    previous=dict(receipts[-1][0],revision=1,status='ACTIVE')
    dialog.populate([previous],saved=True);dialog.edit.click()
    dialog.draft['items'][0]['settings']['target_reps']=9
    def review(box):
        assert box.windowTitle()=='核对计划变化'
        box.findChild(QCheckBox).setChecked(False)
        return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',review)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.No)
    dialog.save.click()
    saved,revision=receipts[-1]
    assert saved['id']!=previous['id'] and revision==0
    assert saved['items'][0]['settings']['target_reps']==previous['items'][0]['settings']['target_reps']
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
    dialog.save.click()
    assert receipts[-1][0]['id']==previous['id'] and receipts[-1][1]==1
    assert w.backend.daily.snapshot(w.owner,w.legacy._body_scope_key())['planVersions'][0]['id']==previous['id']
    dialog._cancel_edit();dialog.close();dialog.deleteLater()


def settle(w,app):
    wait(app,lambda:not w.pending)


def test_primary_navigation_and_health_records_remain_accessible(desktop):
    w,app=desktop
    assert list(w.nav_buttons)==['home','rehab','health','medication','family']
    w.interface_buttons['homeConversation'].setFocus(Qt.TabFocusReason)
    QTest.keyClick(w.interface_buttons['homeConversation'],Qt.Key_Space)
    assert w.active_page=='assistant'
    w.navigate('rehab');settle(w,app)
    assert w.rehab_tabs.currentIndex()==2 and not w.rehab_tabs.tabBar().isVisible()
    w.navigate('history');settle(w,app)
    assert w.active_page=='home' and w.home_sections.currentWidget() is w.page_widgets['history']
    assert w.timeline.isVisible()


def test_first_use_choice_flow_and_skip_are_real_saved_data(desktop):
    w,app=desktop
    w._first_use(existing=True)
    assert w.daily_dialog
    w.daily_dialog.findChild(QLineEdit).setText('TEST 选择题用户')
    next(b for b in w.daily_dialog.findChildren(QPushButton) if b.text()=='跳过问题，进入首页').click()
    settle(w,app)
    assert w.snapshot['dailyProduct']['onboarding']['skipped']
    assert not w.snapshot['dailyProduct']['schedules']
    w._first_use(existing=True)
    next(b for b in w.daily_dialog.findChildren(QPushButton) if b.text()=='完成建档').click()
    settle(w,app)
    assert w.snapshot['dailyProduct']['schedules'][0]['kind']=='assessment'
    assert not w._rehab_data('rehab.get_training_plan')
    assert any(name=='save_participant' for name,_ in w.legacy.runtime.calls)


def test_per_dose_public_ui_and_actual_backend_persistence(desktop):
    w,app=desktop;day=date.today().isoformat()
    w._request('medication.save',{'record':dict(id='medicine',name='TEST 已有医嘱',dose='TEST 剂量',purpose='',times='早晚',status='active')});settle(w,app)
    w._request('daily.medSchedule',dict(medId='medicine',times=['08:00','20:00'],start=day,end=''));settle(w,app)
    w.navigate('medication');settle(w,app)
    assert w.dose_table.rowCount()==2
    w.dose_table.selectRow(0);app.processEvents();w._completion_controls()
    w.interface_buttons['doseTaken'].click();settle(w,app)
    assert w.dose_table.item(0,3).text()=='已服用'
    w.interface_buttons['doseReset'].click();settle(w,app)
    assert w.dose_table.item(0,3).text()=='未记录'
    assert len(w.snapshot['dailyProduct']['doseAudit'])==2
    w.dose_table.selectRow(1);w._completion_controls();w.interface_buttons['doseSkipped'].click();settle(w,app)
    assert w.dose_table.item(1,3).text()=='已跳过'
    assert not any('medicationMissed' in (e.get('observation') or {}).get('tags',[]) for e in w.snapshot['state']['events'])


def test_family_category_projection_never_exposes_private_or_chat(desktop):
    w,app=desktop
    with AgentBridge(data_dir=w.backend.data_dir/'product') as bridge:
        bridge.product('profile.save','parent',dict(profile=blank_health('TEST 家人')))
        bridge.product('health.record','parent',dict(metric='weight',value=61,visibility='private'))
        bridge.product('health.record','parent',dict(metric='systolic',value=123,visibility='family_ok'))
        bridge.product('chat','parent',dict(text='不要记录：TEST 私密草稿内容'))
    store=w.backend.daily;scope=w.legacy._body_scope_key()
    code=store.apply('parent','daily.familyInvite',{},scope)['code']
    w._request('daily.familyBind',{'code':code});settle(w,app)
    assert w.snapshot['familyMembers'][0]['categories']==[]
    store.apply('parent','daily.familyGrant',dict(member=w.owner,categories=['health']),scope)
    w._request('snapshot');settle(w,app)
    member=w.snapshot['familyMembers'][0]
    assert len(member['health'])==1 and '123' in member['health'][0]['text']
    assert '61' not in str(member) and '私密草稿' not in str(member) and 'chat' not in member
    w.navigate('family');settle(w,app);w.linked_family.selectRow(0);w._completion_controls()
    w.interface_buttons['familyReadOnly'].click();app.processEvents()
    assert not any('编辑' in b.text() for b in w.last_detail.findChildren(QPushButton))
    from PySide6.QtWidgets import QTextBrowser
    assert '收缩压：123' in w.last_detail.findChild(QTextBrowser).toPlainText()
    assert 'systolic:' not in w.last_detail.findChild(QTextBrowser).toPlainText()
    assert any(b.text()=='关闭' for b in w.last_detail.findChildren(QPushButton))
    w.last_detail.close()
    store.apply('parent','daily.familyGrant',dict(member=w.owner,categories=[]),scope)
    w._request('snapshot');settle(w,app)
    assert 'health' not in w.snapshot['familyMembers'][0]


def test_owner_switch_clears_new_data_before_read_and_does_not_reset_recorded_doses(desktop):
    w,app=desktop
    with AgentBridge(data_dir=w.backend.data_dir/'product') as bridge:
        bridge.product('profile.save','second',dict(profile=blank_health('TEST 第二位')))
    w._request('profile.list');settle(w,app)
    w.home_schedule.setText('TEST 私人安排');w.health_archive_profile.setText('TEST 私人档案')
    w._select_owner('second')
    assert '私人' not in w.home_schedule.text() and w.dose_table.rowCount()==0 and w.linked_family.rowCount()==0
    settle(w,app)
    assert w.owner=='second' and not w.snapshot['dailyProduct']['doses']
