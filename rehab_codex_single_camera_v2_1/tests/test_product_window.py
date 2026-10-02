import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import queue
import time
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from app.ui.product_window import ProductWindow, NAVIGATION
from app.product.backend import ProductBackend
from app.ui.product_dialogs import blank_health
from app.ui.product_dialogs import ProductProfileDialog

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from bridges.ankang.client import AgentBridge


class PassiveRuntime:
    def __init__(self,data_dir):
        self.data_dir = data_dir
        self.messages,self.views = queue.Queue(),queue.Queue()
        self.calls = []
    def command(self,name,**args):
        self.calls.append((name,args))


def wait(app,predicate):
    deadline = time.monotonic()+12
    while not predicate() and time.monotonic()<deadline:
        app.processEvents()
        QTest.qWait(15)
    assert predicate()


@pytest.fixture
def desktop(tmp_path,monkeypatch):
    monkeypatch.setenv('ANKANG_PRODUCT_DISABLE_MODEL','1')
    with AgentBridge(data_dir=tmp_path/'product') as bridge:
        bridge.product('profile.save','person-test',dict(profile=blank_health('合成产品用户'),rehabGoal='TEST 生活目标'))
    app = QApplication.instance() or QApplication([])
    for filename in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):
        path = Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/filename
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('Microsoft YaHei UI',10))
    runtime = PassiveRuntime(tmp_path)
    w = ProductWindow(runtime=runtime,backend=ProductBackend(tmp_path))
    w.legacy.busy = 0
    w.show()
    wait(app,lambda:bool(w.snapshot) and w.pending==0)
    yield w,app
    w.legacy._allow_close = True
    w.close()
    w.deleteLater()
    app.processEvents()


def test_all_pages_connected_to_real_bridge_and_rehab_gates(desktop):
    w,app = desktop
    assert len(NAVIGATION)==7
    assert w.owner == 'person-test'
    assert w.legacy.participant_id == w.owner
    assert w.snapshot['storage']=='persistent-local'
    assert w.snapshot['history']['report']['sections']
    assert 'rehab.get_training_plan' in w.snapshot['rehabilitation']
    assert not w.legacy.findChild(__import__('PySide6.QtWidgets',fromlist=['QFrame']).QFrame,'sidebar').isVisible()
    for key in [n[0] for n in NAVIGATION]+['notifications','settings']:
        assert w.navigate(key)
        wait(app,lambda:w.pending==0)
        assert w.pages.currentWidget() is w.page_widgets[key]
    w.navigate('rehab')
    w.legacy.state = 'ONLINE'
    assert not w.navigate('health')
    assert w.active_page == 'rehab'
    w.legacy.state = 'UNSELECTED'


def test_onboarding_and_owner_switch_clear_old_data(desktop):
    w,app = desktop
    dialog = ProductProfileDialog(participants=[])
    dialog._save()
    assert dialog.value is None
    dialog.inputs['name'].setText('TEST 新用户')
    dialog.inputs['rehabGoal'].setText('TEST 居家活动')
    dialog._save()
    payload = dict(dialog.value)
    owner = payload.pop('ownerId')
    w._request('profile.save',payload,owner)
    wait(app,lambda:w.pending==0)
    assert any(p['ownerId']==owner for p in w.profiles)
    w.chat.setPlainText('旧用户内容')
    w.legacy.busy = 0
    w._select_owner('person-test' if w.owner==owner else owner)
    assert w.chat.toPlainText()==''
    assert w.metrics.rowCount()==0
    wait(app,lambda:w.pending==0)
    assert w.snapshot['profile']['ownerId']==w.owner
    dialog.deleteLater()


def test_empty_first_run_waits_for_runtime_then_saves(tmp_path,monkeypatch):
    monkeypatch.setenv('ANKANG_PRODUCT_DISABLE_MODEL','1')
    app = QApplication.instance() or QApplication([])
    seen = []
    def complete(dialog):
        seen.append(True)
        dialog.inputs['name'].setText('TEST 首次用户')
        dialog._save()
        return dialog.result()
    monkeypatch.setattr(ProductProfileDialog,'exec',complete)
    w = ProductWindow(runtime=PassiveRuntime(tmp_path),backend=ProductBackend(tmp_path))
    w.legacy.busy = 1
    w.show()
    try:
        wait(app,lambda:w.pending==0)
        assert not seen
        w.legacy.busy = 0
        wait(app,lambda:bool(w.snapshot))
        assert seen and w.snapshot['profile']['profile']['name']=='TEST 首次用户'
        assert w.active_page=='home'
    finally:
        w.legacy._allow_close = True
        w.close()
        w.deleteLater()
        app.processEvents()


def test_revoke_clears_visible_family_summary(desktop):
    w,app = desktop
    w._request('family.invite')
    wait(app,lambda:w.pending==0)
    w._request('family.bind',dict(code=w.invite_input.text()))
    wait(app,lambda:w.pending==0)
    w._request('family.grant')
    wait(app,lambda:w.pending==0)
    w._request('family.summary')
    wait(app,lambda:w.pending==0)
    assert '当前授权范围' in w.family_summary.toPlainText()
    w._request('family.revoke')
    wait(app,lambda:w.pending==0)
    assert '当前授权范围' not in w.family_summary.toPlainText()
    assert '摘要尚未开放' in w.family_summary.toPlainText()
    assert any(a.get('action')=='family.revoke' for a in w.snapshot['audits'])


def test_metric_medication_chat_persistence_and_family_summary(desktop):
    w,app = desktop
    w._request('health.record',dict(metric='weight',value=62,visibility='private'))
    wait(app,lambda:w.pending==0)
    assert w.metrics.rowCount()==1
    assert w.timeline.rowCount()==1
    w._request('medication.save',dict(record=dict(id='test-med',name='TEST 药物',dose='',purpose='',times='',status='active')))
    wait(app,lambda:w.pending==0)
    assert w.medications.rowCount()==1
    w._confirm_medication()
    wait(app,lambda:w.pending==0)
    assert '已完成' in w.medication_today.text()
    w._send_chat('不要记录：测试私密对话')
    wait(app,lambda:w.pending==0)
    assert '测试私密对话' in w.chat.toPlainText()
    w._request('family.summary')
    wait(app,lambda:w.pending==0)
    assert '摘要尚未开放' in w.family_summary.toPlainText()
    with AgentBridge(data_dir=w.legacy.runtime.data_dir/'product') as bridge:
        stored = bridge.product('snapshot',w.owner)
        assert len(stored['state']['events'])==1
        assert not any('测试私密对话' in m['text'] for m in stored['state']['chat'])
    w.navigate('home')
    wait(app,lambda:w.pending==0)
    if os.environ.get('ANKANG_PRODUCT_QA_IMAGE'):
        w.grab().save(os.environ['ANKANG_PRODUCT_QA_IMAGE'])
        for key in [n[0] for n in NAVIGATION]+['notifications','settings']:
            w.navigate(key)
            wait(app,lambda:w.pending==0)
            w.grab().save(str(Path(os.environ['ANKANG_PRODUCT_QA_IMAGE']).with_name('productization-'+key+'.png')))


def test_device_file_ui_validates_owner_then_uses_real_health_pipeline(desktop, tmp_path, monkeypatch):
    import json
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    w, app = desktop
    filename = tmp_path/'measurements.json'
    payload = dict(ownerId='another-user', source='device', measurements=[dict(
        id='device-bp-test', metric='systolic', value=118, unit='mmHg',
        timestamp='2026-10-02T08:00:00Z', source='device', visibility='private')])
    filename.write_text(json.dumps(payload), encoding='utf-8')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(filename), 'JSON'))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    w.interface_buttons['deviceImport'].click()
    wait(app, lambda:w.pending==0)
    assert '文件用户须与当前用户一致' in w.notice.text()
    assert w.metrics.rowCount()==0
    payload['ownerId']=w.owner
    filename.write_text(json.dumps(payload), encoding='utf-8')
    w.interface_buttons['deviceImport'].click()
    wait(app, lambda:w.pending==0)
    assert w.metrics.rowCount()==1
    assert w.metrics.item(0,3).text()=='设备记录'
    assert w.health_timeline.rowCount()==1
    with AgentBridge(data_dir=w.legacy.runtime.data_dir/'product') as bridge:
        stored=bridge.product('snapshot',w.owner)
        assert stored['state']['events'][0]['measurement']['value']==118


def test_optional_ports_show_real_unavailability_and_clear_on_owner_change(desktop):
    w, app=desktop
    assert not w.interface_buttons['voiceInput'].isEnabled()
    assert not w.interface_buttons['healthkitImport'].isEnabled()
    assert not w.interface_buttons['syncPublish'].isEnabled()
    assert '未配置外部渠道' in w.notification_status.text()
    # Rendering injected port status is UI coverage, not physical device acceptance.
    w._render_extensions(dict(voice=dict(available=True,phase='idle'),devices=['fixture-device'],
        healthkit=True,notification=True,sync=dict(mode='cross-device',detail='fixture-peer')))
    assert w.interface_buttons['voiceInput'].isEnabled()
    assert w.interface_buttons['devicePull'].isEnabled()
    assert '渠道已配置' in w.notification_status.text()
    w._render_extensions(dict(syncAvailable=True,sync=dict(mode='local-only',detail='未连接')))
    assert w.interface_buttons['syncStart'].isEnabled()
    assert '仅本机' in w.sync_status.text()
    w._clear_views()
    assert w.device_adapter.count()==0
    assert not w.interface_buttons['voiceInput'].isEnabled()
    assert not w.interface_buttons['syncPublish'].isEnabled()


def test_global_assistant_keeps_active_rehab_and_uses_same_private_session(desktop):
    w, app=desktop
    w.navigate('rehab')
    wait(app, lambda:w.pending==0)
    w.legacy.state='ONLINE'
    w.interface_buttons['globalAssistant'].click()
    assert w.active_page=='rehab'
    assert w.assistant_dock.isVisible()
    assert '当前页面：康复' in w.assistant_context.text()
    w.private_turn.setChecked(True)
    w.dock_input.setPlainText('TEST 私密侧栏对话')
    w.interface_buttons['dockSend'].click()
    wait(app, lambda:w.pending==0)
    assert w.active_page=='rehab'
    assert 'TEST 私密侧栏对话' in w.dock_chat.toPlainText()
    with AgentBridge(data_dir=w.legacy.runtime.data_dir/'product') as bridge:
        stored=bridge.product('snapshot',w.owner)
        assert not any('TEST 私密侧栏对话' in m['text'] for m in stored['state']['chat'])
    w.legacy.state='UNSELECTED'


def test_medication_history_filter_and_restored_silver_entrance(desktop, monkeypatch):
    w, app=desktop
    w._send_chat('今天漏服了药')
    wait(app, lambda:w.pending==0)
    assert w.medication_history.rowCount()>0
    w.history_filter.setCurrentText('用药')
    assert w.timeline.rowCount()==w.medication_history.rowCount()
    assert any('漏服' in w.timeline.item(r,2).text() for r in range(w.timeline.rowCount()))
    w.history_filter.setCurrentText('评估')
    assert w.timeline.rowCount()==0
    calls=[]
    monkeypatch.setattr(w.legacy,'_show_silver',lambda:calls.append(w.legacy.participant_id))
    w.interface_buttons['silverFamily'].click()
    wait(app, lambda:w.pending==0)
    assert calls==[w.owner] and w.active_page=='rehab'
    w.interface_buttons['settingsDevices'].click()
    assert w.active_page=='health' and w.health_tabs.tabText(w.health_tabs.currentIndex())=='设备'
