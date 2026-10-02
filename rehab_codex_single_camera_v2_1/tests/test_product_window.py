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
    wait(app,lambda:bool(w.snapshot))
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
