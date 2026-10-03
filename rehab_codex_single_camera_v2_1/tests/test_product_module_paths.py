"""Real Qt detail/back paths, same widgets/actions/data and active monitoring guards."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog,QInputDialog
from test_product_window import desktop,wait,AgentBridge
from app.ui.product_dialogs import blank_health


def settle(w,app):wait(app,lambda:not w.pending)


def test_rehab_summary_tabs_open_workspace_only_on_action_and_block_active_back(desktop,monkeypatch):
    w,app=desktop;original=w.legacy
    w.navigate('rehab');settle(w,app)
    assert w.rehab_tabs.isVisible() and not original.isVisible()
    assert [w.rehab_tabs.tabText(i) for i in range(4)]==['今日训练','康复评估','训练计划','康复进度']
    for i in range(4):
        w.rehab_tabs.setCurrentIndex(i);app.processEvents()
        assert not original.isVisible() and w.rehab_tabs.isVisible()
    calls=[];monkeypatch.setattr(original,'_show_catalog',lambda:calls.append('assessment'))
    w.rehab_tabs.setCurrentIndex(1);w.interface_buttons['rehabAssess'].click();settle(w,app)
    assert calls==['assessment'] and original.isVisible() and w.legacy is original
    assert w.interface_buttons['rehabWorkspaceBack'].isVisible()
    for state in ('CONNECTING','PREVIEW','ONLINE','SAVE_FAILED'):
        original.state=state;w._completion_controls()
        assert not w.interface_buttons['rehabWorkspaceBack'].isEnabled()
        assert not w._show_rehab_scope(False) and original.isVisible()
        assert not w.navigate('home') and w.active_page=='rehab'
    original.state='UNSELECTED';original._camera_testing=True
    assert not w._show_rehab_scope(False)
    original._camera_testing=False;original.busy=1
    assert not w._show_rehab_scope(False)
    original.busy=0;w._completion_controls();w.interface_buttons['rehabWorkspaceBack'].click()
    assert w.rehab_tabs.isVisible() and not original.isVisible()


def test_health_metric_details_save_back_refresh_and_clear_on_owner_switch(desktop):
    w,app=desktop;w.navigate('health');settle(w,app)
    assert w.twin_text.isVisible() and not w.metrics.isVisible()
    entry=w.interface_buttons['healthMetricsEntry'];entry.setFocus();QTest.keyClick(entry,Qt.Key_Space)
    assert w.metrics.isVisible() and not w.twin_text.isVisible()
    w.metric_select.setCurrentIndex(w.metric_select.findData('weight'));w.metric_value.setValue(62)
    next(b for b in w.product_action_buttons() if b.property('actionTarget')=='health.record').click();settle(w,app)
    assert w.snapshot['state']['events'][-1]['measurement']['value']==62
    assert w.metrics.isVisible() and '62' in w.health_metric_summary.text()
    w.interface_buttons['healthMetricsBack'].click()
    assert not w.metrics.isVisible() and w.twin_text.isVisible()
    w.navigate('home');settle(w,app);w.navigate('health');settle(w,app)
    assert w.twin_text.isVisible() and '62' in w.health_metric_summary.text()
    with AgentBridge(data_dir=w.backend.data_dir/'product') as bridge:
        bridge.product('profile.save','second-module-owner',dict(profile=blank_health('TEST 新用户')))
    w._request('profile.list');settle(w,app)
    w.interface_buttons['healthMetricsEntry'].click();w.metric_value.setValue(91);w.metric_shared.setChecked(True)
    w._select_owner('second-module-owner');settle(w,app)
    assert w.health_status_sections.currentIndex()==0 and not w.metrics.rowCount()
    assert '62' not in w.health_metric_summary.text() and w.metric_value.value()==0 and not w.metric_shared.isChecked()


def test_today_medication_detail_operations_use_original_task_and_chat(desktop):
    w,app=desktop
    w._request('medication.save',dict(record=dict(id='test-module-med',name='TEST 医嘱药物',dose='TEST 剂量',times='TEST 08:00',purpose='',status='active')));settle(w,app)
    w.navigate('medication');settle(w,app)
    assert w.today_medications.isVisible() and not w.interface_buttons['medConfirm'].isVisible()
    w.interface_buttons['medTodayActions'].click();app.processEvents()
    assert w.interface_buttons['medConfirm'].isVisible() and not w.today_medications.isVisible()
    assert not w.interface_buttons['medDose'].isEnabled() and w.interface_buttons['medDose'].toolTip()
    w.interface_buttons['medConfirm'].click();settle(w,app)
    assert next(t for t in w.snapshot['state']['tasks'] if t['kind']=='medication_check')['status']=='completed'
    w.interface_buttons['medTodayActionsBack'].click();assert w.today_medications.isVisible()
    w.interface_buttons['medTodayActions'].click();w.interface_buttons['medMiss'].click();settle(w,app)
    assert w.active_page=='assistant' and w.assistant_sections.currentWidget() is w.assistant_views['conversation']
    assert any('漏服' in m['text'] for m in w.snapshot['state']['chat'])
    w.navigate('medication');settle(w,app)
    assert w.med_today_sections.currentIndex()==0


def test_assistant_material_upload_back_and_global_send_keep_page_and_draft(desktop,tmp_path,monkeypatch):
    w,app=desktop;w.navigate('assistant');settle(w,app)
    w.interface_buttons['assistantModuleConversation'].click();w.chat_input.setPlainText('TEST 未发送草稿')
    w.interface_buttons['assistantMaterialsEntry'].click()
    path=tmp_path/'TEST-资料.txt';path.write_text('TEST 公开验收材料',encoding='utf-8')
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(path),''))
    monkeypatch.setattr(QInputDialog,'getItem',lambda *args:('其他资料',True))
    w.interface_buttons['assistantAttachment'].click();settle(w,app)
    assert len(w.snapshot['attachments'])==1 and '已' in w.notice.text()
    w.interface_buttons['assistantBackMaterials'].click()
    assert w.assistant_sections.currentWidget() is w.assistant_views['conversation']
    assert w.chat_input.toPlainText()=='TEST 未发送草稿'
    w.navigate('health');settle(w,app)
    page=w.pages.currentWidget();w.interface_buttons['globalAssistant'].click()
    assert w.assistant_dock.isVisible() and w.pages.currentWidget() is page
    w.dock_input.setPlainText('TEST 今天的记录');w.interface_buttons['dockSend'].click();settle(w,app)
    assert 'TEST 今天的记录' in w.dock_chat.toPlainText() and w.active_page=='health'
    w.assistant_dock.close();assert w.pages.currentWidget() is page
