"""Isolated actual Qt/Runtime/SQLite journey; explicit QA entries, no camera.

Does not open a normal patient's database, start HTTP, run inference or invent
assessment evidence. Each run owns a new directory. Screenshot review remains
required; this is not Android, physiological accuracy or physical-camera QA.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['ANKANG_PRODUCT_DISABLE_MODEL'] = '1'
os.environ['ANKANG_VOICE_DISABLED'] = '1'
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'rehab_codex_single_camera_v2_1'), str(ROOT)]

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox
from app.runtime import Runtime
from app.storage import Storage
from app.guided_practice import execute
from app.settings import default_plan
from app.training_plans import item_from_plan, new_training_plan
from app.product.backend import ProductBackend
from app.ui.product_window import ProductWindow
from app.ui.guided_practice import PracticePlanLibraryDialog
from app.ui.product_dialogs import blank_health
from bridges.ankang.client import AgentBridge


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--theme', choices=['light', 'dark', 'high-contrast'], default='light')
    parser.add_argument('--width', type=int, default=1440)
    parser.add_argument('--height', type=int, default=940)
    args = parser.parse_args()
    out = args.output_root/('actual-qt-practice-' + uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    data = out/'data'
    app = QApplication.instance() or QApplication([])
    for filename in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + filename)
    app.setStyle('Fusion'); app.setFont(QFont('Microsoft YaHei UI', 10))
    with AgentBridge(data_dir=data/'product') as bridge:
        bridge.product('profile.save', 'TEST-qt-practice', dict(profile=blank_health('TEST 流程用户')))
    runtime = Runtime(data)
    assert runtime.ready.wait(10)
    w = ProductWindow(runtime=runtime, backend=ProductBackend(data))
    w.resize(args.width, args.height); w.show()
    snapshots = []
    result = dict(output=str(out), provider='qt-local-1', explicit_qa_input=True,
                  physical_device=False, camera_opened=False, clinical_accuracy_test=False,
                  theme=args.theme, scale=os.environ.get('QT_SCALE_FACTOR'), passed=False)

    def wait(condition, limit=12):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            app.processEvents()
            if condition(): return
            QTest.qWait(20)
        raise AssertionError('Timed out: ' + w.legacy.notice.text() + ' / ' +
                             (w.legacy.practice_dialog.notice.text() if w.legacy.practice_dialog else ''))

    def click(button):
        app.processEvents(); assert button.isEnabled(), button.text()
        at = time.monotonic()
        if isinstance(button, QCheckBox): QTest.mouseClick(button, Qt.LeftButton, pos=QPoint(9, button.height()//2))
        else: QTest.mouseClick(button, Qt.LeftButton)
        app.processEvents()
        snapshots.append(dict(action=button.text(), dispatch_return_ms=(time.monotonic()-at)*1000))

    def capture(name, widget=None):
        app.processEvents()
        assert (widget or w).grab().save(str(out/(name+'.png')))

    try:
        wait(lambda: bool(w.snapshot) and not w.pending and not w.legacy.busy)
        w.refresher.stop()
        w.legacy.source_kind.setCurrentIndex(w.legacy.source_kind.findData('SYNTHETIC'))
        w.legacy.usage.setCurrentIndex(w.legacy.usage.findData('TEST'))
        wait(lambda: not w.pending and not w.legacy.busy)
        scope = w.legacy._body_scope_key()
        store = Storage(data/'home_rehab.sqlite3')
        try:
            settings = default_plan('shoulder_abduction')
            settings.update(target_reps=3, target_sets=2, rest_between_sets_s=None, side='left')
            saved = store.save_training_plan(new_training_plan(scope, 'TEST 本人已有安排',
                                [item_from_plan(settings)]), expected_revision=0)
            assert store.list_sessions() == []
        finally: store.close()
        w.navigate('rehab'); wait(lambda: not w.pending)
        w._request('snapshot'); wait(lambda: not w.pending)
        w.product_theme.apply(args.theme)
        capture('01-original-rehab-entry')
        plan = w._rehab_data('rehab.get_training_plan')[0]
        assert plan['next_available'] is False and plan['guided_available'] is True
        click(w.interface_buttons['rehabContinue'])
        wait(lambda: isinstance(w.legacy.plan_library_dialog, PracticePlanLibraryDialog)
                        and not w.legacy.busy)
        library = w.legacy.plan_library_dialog
        assert library.use.isEnabled() and not library.current_item()['available']
        capture('02-original-library', library)
        click(library.use)
        wait(lambda: w.legacy.practice_dialog is not None)
        d = w.legacy.practice_dialog
        assert d.stage == 'SETUP' and not d.primary.isEnabled() and d.count.value() == -1
        click(d.confirm); click(d.support)
        wait(lambda: d.primary.isEnabled())
        capture('03-confirm-arrangement', d)
        QTest.keyClick(d.primary, Qt.Key_Space)
        wait(lambda: d.stage == 'EXERCISING' and not d.pending)
        original_id = d.record['id']
        assert runtime.camera.worker is None and runtime.controller.session is None
        capture('04-native-practice', d)
        QTest.qWait(350)
        click(d.pause); wait(lambda: not d.pending)
        elapsed = d.elapsed_ms
        QTest.qWait(150); assert d.elapsed_ms == elapsed
        click(d.back); assert not d.isVisible() and d.stage == 'PAUSED'
        # Original continue button returns to the same journey via its saved library.
        w._continue_training(); wait(lambda: w.legacy.plan_library_dialog is not None and not w.legacy.busy)
        click(w.legacy.plan_library_dialog.use); wait(lambda: d.isVisible())
        assert w.legacy.practice_dialog is d and d.record['id'] == original_id and not d.confirm.isVisible()
        click(d.pause); wait(lambda: d.stage == 'EXERCISING' and not d.pending)
        click(d.end); assert d.stage == 'WRAP_UP' and d.count.value() == -1
        d.count.setValue(3); d.reason.setCurrentIndex(d.reason.findData('completed_set'))
        assert all(s.value() == -1 for s in d.scores.values())
        capture('05-wrap-up', d)
        # Actual SQLite commit succeeds, but one original Runtime reply is lost.
        original_receive = w.legacy._handle_message
        lost = []
        def receive(message):
            if not lost and message.get('kind') == 'practice_result' and message.get('command') == 'practice_finish':
                lost.append(message); return
            original_receive(message)
        w.legacy._handle_message = receive
        click(d.primary); wait(lambda: bool(lost))
        frozen = dict(d.finish_payload)
        assert lost[0]['result']['state'] == 'COMMITTED' and d.stage == 'WRAP_UP'
        d.pending['started'] -= 21; d._tick()
        w.legacy._handle_message = original_receive
        click(d.primary); wait(lambda: d.stage == 'SUMMARY' and not d.pending)
        assert d.finish_payload == frozen and d.record['id'] == original_id
        assert d.record['self_reported_count'] == 3 and d.record['confirmed_count'] is None
        assert d.record['formal_plan_contribution'] is None
        capture('06-saved', d)
        click(d.primary)
        w.legacy._history(); wait(lambda: not w.legacy.busy)
        assert w.legacy.sessions == [] and len(w.legacy.practice_history) == 1
        w.legacy.table.selectRow(0); w.legacy._open_report()
        wait(lambda: w.legacy.practice_dialog is not d)
        d = w.legacy.practice_dialog
        assert d.stage == 'SUMMARY' and d.record['id'] == original_id
        capture('07-original-history-record', d); d.hide()
        w.navigate('history'); wait(lambda: not w.pending)
        w._request('snapshot'); wait(lambda: not w.pending)
        assert len([e for e in w.filtered_entries if len(e)>4 and e[4].get('record_type') == 'GUIDED_PRACTICE']) == 1
        capture('08-unified-history')
        store = Storage(data/'home_rehab.sqlite3')
        try:
            entries = execute(store, 'practice_history', scope, {})
            assert len(entries) == 1 and not store.list_sessions()
            assert store.get_training_plan(saved['id'])['revision'] == saved['revision']
            result.update(passed=True, record_id=original_id, practice_count=len(entries),
                          measured_sessions=len(store.list_sessions()), self_reported_qa_count=3,
                          confirmed_count=entries[0]['confirmed_count'], formal_contribution=entries[0]['formal_plan_contribution'],
                          lost_reply_reconciled=True, keyboard_start=True, dispatches=snapshots,
                          runtime_camera_worker_present=runtime.camera.worker is not None)
        finally: store.close()
    except Exception as error:
        result['error'] = repr(error); capture('failed-current-state')
        raise
    finally:
        (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=True))
        w.legacy._allow_close = True; w.close(); app.processEvents()
        if runtime.thread.is_alive(): runtime.command('shutdown'); runtime.thread.join(10)
        assert not runtime.thread.is_alive()


if __name__ == '__main__': main()
