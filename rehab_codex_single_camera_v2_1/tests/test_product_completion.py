"""Actual Qt controls and real product/rehab services, with TEST files and records only."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialogButtonBox, QFileDialog, QMessageBox, QInputDialog, QPushButton
from test_product_window import desktop, wait
from app.ui.product_dialogs import MedicationDialog, blank_health
from app.rehab_read_tools import RehabReadTools, TOOLS
from app.storage import Storage


def test_path_1_original_training_engine_real_feedback_and_home(tmp_path,monkeypatch):
    """Software lifecycle only: SYNTHETIC/TEST never enables a fake camera in the UI."""
    from test_app_controller import ControllerTests
    from test_product_window import AgentBridge, ProductBackend, ProductWindow
    from test_training_runtime import response
    from app.runtime import Runtime
    from PySide6.QtWidgets import QApplication
    task=ControllerTests();task.setUp()
    try:
        reference=task._assessment_reference()
        task.setup['plan'].update(target_reps=1,target_sets=1)
        task._training_preview(reference);task.c.start()
        sid=task.c.context.run_id
        t=0
        for angle in (0,90,0):
            for _ in range(30):task.frame(t,angle);t+=.1
        task.c.stop('user_stop')
        record=task.store.get_session(sid)
        assert record['summary']['completed']==1
        assert record['source_kind']=='SYNTHETIC' and record['usage_context']=='TEST'
        store=Storage(tmp_path/'home_rehab.sqlite3')
        for s in task.store.list_sessions():store.save_session(s)
        store.close()
    finally:task.tearDown()
    monkeypatch.setenv('ANKANG_PRODUCT_DISABLE_MODEL','1')
    with AgentBridge(data_dir=tmp_path/'product') as bridge:
        bridge.product('profile.save','participant-local',dict(profile=blank_health('TEST 康复闭环')))
    app=QApplication.instance() or QApplication([]);runtime=Runtime(tmp_path)
    w=None
    try:
        assert runtime.ready.wait(5)
        w=ProductWindow(runtime=runtime,backend=ProductBackend(tmp_path));w.show()
        wait(app,lambda:bool(w.snapshot) and not w.pending and not w.legacy.busy)
        w.legacy.source_kind.setCurrentIndex(w.legacy.source_kind.findData('SYNTHETIC'))
        w.legacy.usage.setCurrentIndex(w.legacy.usage.findData('TEST'))
        wait(app,lambda:not w.legacy.busy)
        w._request('snapshot');settle(w,app)
        w.interface_buttons['homeContinue'].click();wait(app,lambda:not w.legacy.busy)
        assert w.active_page=='rehab' and not w.interface_buttons['rehabStart'].isEnabled()
        # The same saved controller result is reopened by the real command bus and UI report.
        w._open_original_report(sid)
        wait(app,lambda:bool(w.legacy.report_windows) and not w.legacy.busy)
        report=w.legacy.report_windows[-1]
        feedback_button=next(b for b in report.findChildren(QPushButton) if '感受' in b.text())
        feedback_button.click()
        wait(app,lambda:w.legacy.feedback_dialog is not None and not w.legacy.busy)
        dialog=w.legacy.feedback_dialog
        dialog.scores['pain'].setValue(0);dialog.notes.setPlainText('TEST 控制器完成后反馈')
        dialog.save.click();wait(app,lambda:w.legacy.feedback_dialog is None and not w.legacy.busy)
        report.close();w.interface_buttons['rehabHome'].click();settle(w,app)
        assert w.active_page=='home'
        saved=runtime.store.get_session(sid)
        assert saved['training_feedback']['pain']==0
        assert saved['summary']==record['summary']
        assert any(r['id']==sid and r['training_feedback']['pain']==0 for r in w._rehab_data(TOOLS[2]))
        assert runtime.camera.worker is None
    finally:
        if w:
            w.legacy._allow_close=True;w.close();w.deleteLater();app.processEvents()
        if runtime.thread.is_alive():response(runtime,'shutdown');runtime.thread.join(5)


def settle(w,app):
    wait(app,lambda:not w.pending)


def close_detail(w,app):
    assert w.last_detail.isVisible()
    w.last_detail.findChild(QDialogButtonBox).button(QDialogButtonBox.Close).click()
    app.processEvents()
    assert w.last_detail is None


def test_paths_2_3_medication_detail_back_and_agent_to_rehab(desktop,monkeypatch):
    w,app=desktop
    w.interface_buttons['homeMedication'].click();settle(w,app)
    assert w.active_page=='medication' and w.medication_tabs.tabText(0)=='今日用药'
    assert w.medication_today.text()=='暂无用药安排'
    def save_dialog(dialog):
        for key,value in dict(name='TEST 已有医嘱药物',dose='TEST 剂量',times='TEST 08:00').items():dialog.fields[key].setText(value)
        dialog._save();return dialog.result()
    monkeypatch.setattr(MedicationDialog,'exec',save_dialog)
    w.medication_tabs.setCurrentIndex(1);w.interface_buttons['medAdd'].click();settle(w,app)
    assert w.medications.rowCount()==1
    w.medication_tabs.setCurrentIndex(0);w.today_medications.selectRow(0)
    w.interface_buttons['medTodayDetail'].click()
    assert 'TEST 已有医嘱药物' in w.last_detail.findChild(__import__('PySide6.QtWidgets',fromlist=['QTextBrowser']).QTextBrowser).toPlainText()
    close_detail(w,app);w.interface_buttons['medBack'].click();settle(w,app)
    assert w.active_page=='home'
    w.interface_buttons['homeAI'].click();settle(w,app)
    w.chat_input.setPlainText('我今天练什么？');w.chat_send.click();settle(w,app)
    assert '我今天练什么' in w.chat.toPlainText()
    assert not w.snapshot['modelAvailable'] and '尚未配置' in w.agent_status.text()
    w.interface_buttons['assistantRehab'].click();settle(w,app)
    assert w.active_page=='rehab' and w.rehab_tabs.currentIndex()==0
    w.interface_buttons['rehabHome'].click();settle(w,app)
    assert w.active_page=='home'


def test_path_4_archive_upload_detail_and_real_export(desktop,tmp_path,monkeypatch):
    w,app=desktop;w.navigate('health');settle(w,app);w.health_tabs.setCurrentIndex(2)
    path=tmp_path/'TEST-report.txt';path.write_text('TEST 健康档案，非真实资料',encoding='utf-8')
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a:(str(path),''))
    monkeypatch.setattr(QInputDialog,'getItem',lambda *a:('检验检查',True))
    next(b for b in w.product_action_buttons() if b.text()=='添加资料 / 图片 / 视频').click()
    settle(w,app)
    assert w.attachments.rowCount()==1 and w.health_tabs.currentIndex()==2
    w.attachments.selectRow(0);w.interface_buttons['archiveDetail'].click();close_detail(w,app)
    out=tmp_path/'export.txt'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(out),''))
    next(b for b in w.product_action_buttons() if b.text()=='导出所选附件').click();settle(w,app)
    assert out.read_bytes()==path.read_bytes() and '已导出' in w.notice.text()


def test_paths_5_7_member_permissions_notification_detail_business(desktop,monkeypatch):
    w,app=desktop
    profile=blank_health('TEST 合成用户');profile.update(familyContact='TEST 家属',familyPhone='TEST 电话')
    w._request('profile.save',{'profile':profile});settle(w,app)
    w.navigate('family');settle(w,app)
    w.interface_buttons['familyDetail'].click();close_detail(w,app)
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.Yes)
    next(b for b in w.product_action_buttons() if b.text()=='生成本机邀请码').click();settle(w,app)
    next(b for b in w.product_action_buttons() if b.text()=='确认绑定').click();settle(w,app)
    next(b for b in w.product_action_buttons() if b.text()=='授权家庭共享').click();settle(w,app)
    assert w.snapshot['projection']['canViewSharedDetail']
    w.interface_buttons['familyDetail'].click()
    next(b for b in w.last_detail.findChildren(QPushButton) if b.text()=='撤销共享').click();settle(w,app)
    assert not w.snapshot['projection']['canViewSharedDetail']
    w._consent(True);settle(w,app)
    w._send_chat('我刚才摔了一跤，现在胸口疼');settle(w,app)
    w.navigate('notifications');settle(w,app)
    next(b for b in w.product_action_buttons() if b.text()=='核对可共享通知并建立台账').click();settle(w,app)
    assert w.notifications.rowCount()>0
    w.notifications.selectRow(0);w.interface_buttons['notificationDetail'].click();close_detail(w,app)
    w.notifications.selectRow(0);w._ack_notification();settle(w,app)
    w.notification_filter.setCurrentText('已确认')
    assert w.notifications.rowCount()>0
    w.notifications.selectRow(0);w.interface_buttons['notificationBusiness'].click();settle(w,app)
    assert w.active_page in ('health','medication')
    w.navigate('notifications');settle(w,app)
    assert w.active_page=='notifications'


def test_path_6_full_scoped_training_history_detail_trends_report_export(desktop,tmp_path,monkeypatch):
    from app.runtime import Runtime
    from test_training_runtime import response
    w,app=desktop
    w.legacy.source_kind.setCurrentIndex(w.legacy.source_kind.findData('SYNTHETIC'))
    w.legacy.usage.setCurrentIndex(w.legacy.usage.findData('TEST'))
    scope=w.legacy._body_scope_key()
    store=Storage(tmp_path/'home_rehab.sqlite3')
    for i in range(8):
        store.save_session(dict(scope,id=f'TEST-training-{i}',scene_id='rehab',submode='training',
            exercise_id='shoulder_abduction',side='left',status='FINISHED',
            start_utc=f'2026-10-02T08:0{i}:00+08:00',end_utc=f'2026-10-02T08:0{i}:10+08:00',
            summary={'completed':1,'plan_completed':True},config_snapshot={},repetitions=[]))
    store.close()
    tools=RehabReadTools(tmp_path/'home_rehab.sqlite3',scope)
    assert len(tools(TOOLS[2],{})['records'])==5
    assert len(tools.desktop_snapshot()[TOOLS[2]]['records'])==8
    runtime=Runtime(tmp_path);assert runtime.ready.wait(5);w.legacy.runtime=runtime
    try:
        wait(app,lambda:not w.legacy.busy and runtime.messages.empty())
        w.navigate('history');settle(w,app);w.history_filter.setCurrentText('康复')
        assert w.timeline.rowCount()==8
        w.timeline.selectRow(0);w.interface_buttons['historyDetail'].click();close_detail(w,app)
        w.interface_buttons['historyTrends'].click()
        wait(app,lambda:w.legacy.longitudinal_dialog is not None and w.legacy.longitudinal_dialog.history is not None)
        assert w.legacy.longitudinal_dialog.history['anchor_id']=='TEST-training-7'
        assert w.active_page=='rehab'
        w.legacy.longitudinal_dialog.close();wait(app,lambda:not w.legacy.busy)
        w.navigate('history');settle(w,app);w.timeline.selectRow(0)
        w.interface_buttons['historyReport'].click()
        wait(app,lambda:bool(w.legacy.report_windows) and not w.legacy.busy)
        assert w.legacy.report_windows[-1].snapshot['id']=='TEST-training-7'
        w.legacy.report_windows[-1].close()
        w.navigate('history');settle(w,app)
        out=tmp_path/'timeline.txt';monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(out),''))
        w.interface_buttons['historyExport'].click();settle(w,app)
        assert len(out.read_text(encoding='utf-8').splitlines())==10
        assert '今天已完成 8 次训练' in w.tile_values['plan'].text()
    finally:response(runtime,'shutdown');runtime.thread.join(5)


def test_loading_duplicate_error_empty_disabled_and_button_audit(desktop,tmp_path,monkeypatch):
    w,app=desktop
    assert w._request('health.record',{'metric':'weight','value':61})
    assert not w._request('health.record',{'metric':'weight','value':62})
    assert '重复提交' in w.notice.text();settle(w,app)
    assert len(w.snapshot['state']['events'])==1
    assert w._request('health.record',{'metric':'missing','value':1});settle(w,app)
    assert '无效' in w.notice.text() and '正在' not in w.page_states[w.active_page].text()
    assert not w.interface_buttons['assistantNew'].isEnabled()
    assert not w.interface_buttons['medDose'].isEnabled()
    for page in w.page_widgets:
        assert w.navigate(page);settle(w,app)
        assert '正在' not in w.page_states[page].text()
    w.navigate('rehab');settle(w,app);w.resize(1180,780);app.processEvents()
    previous=w.legacy.height();w.interface_buttons['rehabOverview'].click();app.processEvents()
    assert w.rehab_overview_collapsed and w.legacy.height()>previous
    w.interface_buttons['rehabOverview'].click();app.processEvents()
    assert not w.rehab_overview_collapsed
    audit=w.button_audit()
    assert all(a['category'] in ('A','B','C','D') and a['action'] and a['feedback'] for a in audit)
    for page in w.page_widgets:
        w.navigate(page);settle(w,app)
        for b in w.page_widgets[page].findChildren(QPushButton):
            parent=b
            while parent and parent is not w.legacy:parent=parent.parentWidget()
            if parent is not w.legacy:
                assert b.property('actionId'),f'Unclassified product control: {page} {b.text()}'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(tmp_path/'missing-dir'/'backup.json'),''))
    w._backup();settle(w,app)
    assert '已导出' not in w.notice.text() and w.pending_export is None
    if os.environ.get('ANKANG_BUTTON_AUDIT'):
        Path(os.environ['ANKANG_BUTTON_AUDIT']).write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')


def test_owner_switch_clears_drafts_and_original_dialogs(desktop,monkeypatch):
    w,app=desktop
    other='TEST-other-person'
    w._request('profile.save',{'profile':blank_health('TEST 另一用户')},other);settle(w,app)
    w.chat_input.setPlainText('另一用户未发送草稿')
    w.dock_input.setPlainText('另一用户侧栏草稿')
    old_report=__import__('PySide6.QtWidgets',fromlist=['QDialog']).QDialog(w.legacy)
    w.legacy.report_windows.append(old_report);old_report.show()
    w._detail('另一用户资料',['TEST'])
    w.legacy.busy=0;w._select_owner('person-test');settle(w,app)
    assert not w.chat_input.toPlainText() and not w.dock_input.toPlainText()
    assert not old_report.isVisible() and w.last_detail is None
    assert w.snapshot['profile']['ownerId']=='person-test'
    own=dict(id='own',**w.legacy._body_scope_key(),scene_id='rehab',summary={})
    foreign=dict(own,id='foreign',participant_id=other)
    w.legacy._handle_message({'kind':'history','sessions':[foreign,own]})
    assert [s['id'] for s in w.legacy.sessions]==['own']
    before=len(w.legacy.report_windows)
    w.legacy._handle_message({'kind':'report','snapshot':foreign,'html':'TEST 不可显示'})
    assert len(w.legacy.report_windows)==before
    assert '所属用户' in w.legacy.notice.text()
    w.legacy._open_body_report()
    assert '请选择' in w.legacy.notice.text() or '请先选择' in w.legacy.notice.text()
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.No)
    before=len(w.legacy.runtime.calls)
    w.legacy._silver_command({'operation':'consent','family':False,'grants':[]})
    assert len(w.legacy.runtime.calls)==before
    from app.ui.silver import SilverDialog
    silver=SilverDialog(w.legacy);silver.timer.stop()
    silver.pending=True;silver.send('consent');assert '等待' in silver.error.text()
    silver.respond('ack');assert '请先选择' in silver.error.text()
    silver.close();silver.deleteLater()


def test_desktop_assessment_history_keeps_older_and_guided_records(tmp_path):
    scope=dict(participant_id='TEST-reader',source_kind='SYNTHETIC',usage_context='TEST')
    store=Storage(tmp_path/'home_rehab.sqlite3')
    for i in range(9):
        store.save_session(dict(scope,id=f'TEST-assessment-{i}',scene_id='rehab',submode='assessment',exercise_id='shoulder_abduction',side='left',status='FINISHED',end_utc=f'2026-10-02T10:0{i}:00Z',
            summary={'completed':1,'valid_ratio':0},config_snapshot={},repetitions=[],measurement_mode='guided_timed' if i==8 else 'auto_observed'))
    store.save_session(dict(scope,id='TEST-foreign',participant_id='other',scene_id='rehab',submode='assessment',exercise_id='shoulder_abduction',side='left',status='FINISHED',end_utc='2026-10-02T11:00:00Z',summary={},config_snapshot={}))
    store.close();tools=RehabReadTools(tmp_path/'home_rehab.sqlite3',scope)
    assert len(tools(TOOLS[1],{})['records'])==1
    records=tools.desktop_snapshot()[TOOLS[1]]['records']
    assert len(records)==9 and records[0]['session_id']=='TEST-assessment-8'
    assert records[0]['status']=='NOT_ASSESSED' and records[0]['measurement_mode']=='guided_timed'
