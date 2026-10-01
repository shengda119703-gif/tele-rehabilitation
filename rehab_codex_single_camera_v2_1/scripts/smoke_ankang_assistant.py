"""Offscreen synthetic smoke using the real desktop Runtime and existing Node bridge.
Run after building the bridge: python scripts/smoke_ankang_assistant.py
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow


def wait(app, predicate, timeout=15):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        app.processEvents()
        QTest.qWait(10)
    assert predicate(), 'UI operation did not complete'


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='rehab-ankang-synthetic-') as data:
        window = MainWindow(data_dir=data)
        window.show()
        try:
            wait(app, lambda: window.runtime.ready.is_set() and window.busy == 0)
            app.processEvents()
            # Current participant is the existing application ID, not its displayed name.
            original = window.participant_id
            QTest.mouseClick(window.assistant_nav, Qt.MouseButton.LeftButton)
            dialog = window.assistant_dialog
            assert dialog.isVisible()
            for revision, text in enumerate(['我今天头晕', '我今天量了血压150/95'], 1):
                dialog.input.setText(text)
                if revision == 1:
                    QTest.keyClick(dialog.input, Qt.Key.Key_Return)
                    QTest.mouseClick(dialog.send, Qt.MouseButton.LeftButton)
                else:
                    dialog.send.click()
                wait(app, lambda: not dialog.busy)
                assert dialog.last_result, dialog.status.text()
                assert dialog.last_result['revision'] == revision
                assert len(dialog.last_result['snapshot']['chat']) == revision * 2
                assert dialog.isVisible() and window.isVisible()
                print('Python UI ->', text)
                print('Agent ->', dialog.last_result['reply']['text'])
            wait(app, lambda: window.busy == 0)
            window.participant.setText('synthetic-assistant-other')
            window._apply_participant()
            assert dialog.participant_id == 'synthetic-assistant-other' and not dialog.chat.toPlainText()
            dialog.input.setText('你好')
            dialog.send.click()
            wait(app, lambda: not dialog.busy)
            assert dialog.last_result['revision'] == 1
            assert len(dialog.last_result['snapshot']['chat']) == 2
            wait(app, lambda: window.busy == 0)
            window.participant.setText(original)
            window._apply_participant()
            assert '血压' in dialog.chat.toPlainText() and '你好' not in dialog.chat.toPlainText()
            dialog.worker.bridge.terminate()
            dialog.worker.bridge._process.wait(timeout=5)
            dialog.input.setText('合成故障验证')
            dialog.send.click()
            wait(app, lambda: not dialog.busy)
            assert '助手不可用' in dialog.status.text() and window.isVisible()
            dialog.input.setText('新会话合成测试')
            dialog.send.click()
            wait(app, lambda: not dialog.busy)
            assert dialog.last_result['revision'] == 1
            bridge_process = dialog.worker.bridge._process
            dialog.close()
            for navigate in (window._show_catalog, window._show_training_hub, window._show_body, window._history):
                wait(app, lambda: window.busy == 0)
                navigate()
                app.processEvents()
                assert window.pages.currentWidget().isVisible()
            print('PASS: startup, assistant entry, two turns, Enter dedup, participant isolation, real Node failure, original pages')
        finally:
            window.close()
            wait(app, lambda: not window.isVisible(), timeout=20)
            window.runtime.thread.join(timeout=5)
            if window.assistant_dialog:
                window.assistant_dialog.worker.thread.join(timeout=5)
                assert not window.assistant_dialog.worker.thread.is_alive()
                if 'bridge_process' in locals():
                    assert bridge_process.poll() is not None
            assert not window.runtime.thread.is_alive()
    print('PASS: desktop and Node resources closed; temporary synthetic data only')

if __name__ == '__main__':
    main()
