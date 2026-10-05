"""Native embedded editors against the real Runtime; isolated SYNTHETIC / TEST only."""
import os
os.environ.update(QT_QPA_PLATFORM='windows',ANKANG_PRODUCT_DISABLE_MODEL='1',ANKANG_VOICE_DISABLED='1')
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT.parent)]
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QTimer
from app.runtime import Runtime
from app.ui.product_window import ProductWindow
from app.ui.product_dialogs import blank_health
from app.settings import default_plan
from bridges.ankang.client import AgentBridge
from test_product_window import wait
import time

def wait_runtime(predicate):
    deadline=time.monotonic()+55
    while not predicate() and time.monotonic()<deadline:
        app.processEvents();QTest.qWait(20)
    assert predicate()

app=QApplication.instance() or QApplication([])
out=ROOT/'qa-output/five-pages/plan-path'
out.mkdir(parents=True,exist_ok=True)
for width,theme in ((1440,'light'),(1024,'light'),(1440,'dark'),(1024,'dark')):
    with tempfile.TemporaryDirectory(prefix='five-plan-TEST-') as td:
        with AgentBridge(data_dir=Path(td)/'product') as bridge:
            bridge.product('profile.save','TEST-plan-user',dict(profile=blank_health('TEST 计划用户')))
        runtime=Runtime(data_dir=Path(td));w=ProductWindow(runtime=runtime)
        w.resize(width,940);w.show();w.product_theme.apply(theme)
        try:
            try:wait_runtime(lambda:bool(w.snapshot) and not w.pending and not w.legacy.busy)
            except AssertionError:
                print('startup state:',bool(w.snapshot),w.pending,w.legacy.busy,w.notice.text(),w.legacy.notice.text(),flush=True)
                raise
            w.legacy.source_kind.setCurrentIndex(w.legacy.source_kind.findData('SYNTHETIC'))
            wait(app,lambda:not w.legacy.busy)
            w.legacy.usage.setCurrentIndex(w.legacy.usage.findData('TEST'))
            wait(app,lambda:not w.legacy.busy)
            w._request('snapshot');wait(app,lambda:not w.pending)
            w._plan_library();wait(app,lambda:w.legacy.plan_library_dialog and not w.legacy.busy)
            editor=w.legacy.plan_library_dialog
            assert not editor.isWindow()
            editor.new.click();editor.name.setText('TEST 已有人工安排')
            editor._append_item(default_plan('shoulder_abduction'))
            QTest.qWait(120)
            w.grab().save(str(out/f'{width}-{theme}-editor.png'))
            wait(app,lambda:editor.save.isEnabled())
            editor.save.click()
            # Real Runtime I/O may exceed the 12-second passive-UI test wait
            # under load. Keep the bounded real-Runtime timeout and diagnostics.
            try:wait_runtime(lambda:not w.legacy.busy and editor.records)
            except AssertionError:
                print('save state:',w.legacy.busy,editor.pending,editor.error.text(),w.legacy.notice.text(),flush=True)
                raise
            wait(app,lambda:editor.close_button.isEnabled())
            editor.close_button.click();wait(app,lambda:not w.pending)
            assert w.legacy.plan_library_dialog is None, 'Editor did not close'
            try:wait(app,lambda:bool(w._rehab_data('rehab.get_training_plan')))
            except AssertionError:
                print('saved state:',w.owner,w.legacy._body_scope_key(),editor.scope,editor.records,w.notice.text(),w.snapshot.get('rehabilitation_ui'),flush=True)
                raise
            def accept_schedule():
                dialog=QApplication.activeModalWidget()
                assert dialog and dialog.windowTitle()=='安排训练日期'
                dialog.accept()
            QTimer.singleShot(100,accept_schedule)
            w._schedule_plan();wait(app,lambda:not w.pending)
            assert w.snapshot['dailyProduct']['schedules']
            QTest.qWait(100);w.grab().save(str(out/f'{width}-{theme}-saved-plan.png'))
            w._automatic_plan();wait(app,lambda:w.legacy.automatic_dialog and not w.legacy.busy)
            assert w.legacy.automatic_dialog.proposal
            QTest.qWait(100);w.grab().save(str(out/f'{width}-{theme}-automatic-empty.png'))
            w.legacy.automatic_dialog.close_button.click();wait(app,lambda:not w.pending)
            print(f'{width} {theme}: real Runtime plan save and dated schedule PASS',flush=True)
        finally:
            w.legacy._allow_close=True;w.close();w.deleteLater();app.processEvents()
            runtime.command('shutdown');runtime.thread.join(5)
            assert not runtime.thread.is_alive()
