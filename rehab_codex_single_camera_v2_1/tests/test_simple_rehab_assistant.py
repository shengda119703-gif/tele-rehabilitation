from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLineEdit, QCheckBox, QPushButton, QTextBrowser
from PySide6.QtTest import QTest
from test_product_window import desktop, wait


def test_simple_assistant_and_local_plan_dialog(desktop, monkeypatch):
    w, app = desktop
    before = w.snapshot['state']['events']
    w._send_chat('记录血压180并分享给家属')
    wait(app, lambda: not w.pending)
    assert w.snapshot['state']['events'] == before
    assert not w.snapshot['careAvailable']
    assert not hasattr(w, 'care_controls')
    w._send_chat('E-LOW-009 怎么做')
    wait(app, lambda: not w.pending)
    assert 'E-LOW-009' in w.chat.toPlainText()
    assert '不要用手掰脚' in w.chat.toPlainText()
    results = []
    preview=w._show_local_plan
    monkeypatch.setattr(w, '_show_local_plan', lambda result: results.append(result))

    def fill():
        dialog = QApplication.activeModalWidget()
        inputs = dialog.findChildren(QLineEdit)
        inputs[0].setText('TEST 目标'); inputs[1].setText('踝')
        inputs[2].setText('稳固椅')
        dialog.findChild(QCheckBox).setChecked(True)
        next(b for b in dialog.findChildren(QPushButton) if b.text() == '生成候选计划').click()

    QTimer.singleShot(100, fill)
    w._local_plan_dialog()
    wait(app, lambda: not w.pending)
    assert results[0]['items'][0]['id']=='T-LOW-046'
    assert '1—3组×5—10次' in results[0]['items'][0]['sourceDose']
    assert w.snapshot['state']['events'] == before
    w.navigate('assistant'); w._show_assistant_section('conversation')
    wait(app, lambda: not w.pending)
    folder = Path.home()/'AppData/Local/AnkangChecks/report-manual-20261013/screenshots'
    folder.mkdir(parents=True, exist_ok=True)
    for mode in ('light', 'dark'):
        w.product_theme.apply(mode); w.resize(1100, 760); QTest.qWait(150)
        w.grab().save(str(folder/f'simple-assistant-{mode}.png'))
        def capture():
            dialog=QApplication.activeModalWidget()
            assert '停止或调整条件' in dialog.findChild(QTextBrowser,'local-plan-preview').toPlainText()
            dialog.grab().save(str(folder/f'full-library-plan-{mode}.png'))
            dialog.accept()
        QTimer.singleShot(150,capture)
        preview(results[0])
