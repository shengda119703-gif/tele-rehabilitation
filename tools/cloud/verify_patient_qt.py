"""Actual patient Qt contact UI, fictional accounts and fresh local stores only."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'rehab_codex_single_camera_v2_1'),
               str(ROOT / 'rehab_codex_single_camera_v2_1/tests'), str(ROOT)]
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
from cloud_service.app import BASE, create_app
from cloud_service.config import Settings
from cloud_service.database import Database
from cloud_service.security import bootstrap_doctor
from cloud_service.tests.test_accounts import client as web_client, login
from cloud_service.tests.test_workbench import publish
from app.cloud_account import CloudAccount
from app.ui.cloud_account import CloudAccountDialog
from app.ui.product_theme import core_style, design_tokens
from test_cloud_account import MemoryVault
from test_workbench_clients import LocalHTTP


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    out = parser.parse_args().output.resolve()
    if ROOT / '.runtime' not in out.parents:
        raise SystemExit('Use a fresh output directory under .runtime; no patient data is used.')
    out.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    app.setStyle('Fusion')
    for font in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
        font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / font
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont('Microsoft YaHei UI', 10))
    settings = Settings('sqlite:///' + str(out / 'TEST-only.sqlite3'), 'x' * 40, ('http://testserver',), 'test')
    db = Database(settings.database_url)
    db.migrate()
    bootstrap_doctor(db, settings, '1')
    server = create_app(settings, db)
    http = LocalHTTP(server)
    account = CloudAccount(out / 'TEST-contact-only', http, MemoryVault())
    account.register('test-patient-contact', '1')
    doctor = web_client(server)
    assert login(doctor, 'doctor').is_success
    dialog = CloudAccountDialog(out / 'TEST-contact-only', 'TEST-local-owner', 'TEST 虚构患者', lambda: [], client=account)

    def wait(target=None):
        target = target or dialog
        until = time.monotonic() + 20
        while time.monotonic() < until:
            app.processEvents()
            QTest.qWait(20)
            if target.future is None:
                QTest.qWait(100)
                app.processEvents()
                if target.future is None:
                    return
        raise AssertionError('TEST contact UI failed to finish')

    def theme(mode):
        colors = design_tokens(mode)
        palette = QPalette()
        for role, key in ((QPalette.Window, 'window'), (QPalette.Base, 'surface'),
                          (QPalette.Text, 'text'), (QPalette.WindowText, 'text'),
                          (QPalette.Button, 'surface'), (QPalette.ButtonText, 'text'),
                          (QPalette.Highlight, 'brand'), (QPalette.HighlightedText, 'on_brand'),
                          (QPalette.PlaceholderText, 'secondary')):
            palette.setColor(role, QColor(colors[key]))
        for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
            palette.setColor(QPalette.Disabled, role, QColor(colors['disabled_text']))
        app.setPalette(palette)
        app.setStyleSheet(core_style(colors))
        app.processEvents()

    def screenshot(name):
        app.processEvents()
        QTest.qWait(100)
        assert dialog.grab().save(str(out / (name + '.png')))

    try:
        theme('light')
        dialog.show()
        app.processEvents()
        assert dialog.pages.currentWidget() is dialog.account_page
        assert not dialog.confirm.isEnabled()
        assert dialog.windowTitle() == '联系康复医师'
        assert '已停用' in dialog.plan_html({'title': 'TEST 停用方案', 'execution_status': 'STOPPED'})
        assert '人工执行' in dialog.plan_html({'title': 'TEST 人工方案', 'execution_status': 'MANUAL_ONLY'})
        assert not any('API' in b.text() for b in dialog.findChildren(QPushButton))
        screenshot('light-first-use')
        dialog.username.setText('test-patient-contact')
        dialog.password.setText('1')
        dialog.login()
        wait()
        assert dialog.pages.currentWidget() is dialog.patient_page
        assert not dialog.password.text()
        assert not dialog.confirm.isChecked()
        assert not account.consent('TEST-local-owner')
        assert '授权' in dialog.status.text(), dialog.status.text()
        patient = account.session()['patient_id']
        original_question = QMessageBox.question
        QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes
        try:
            dialog.show_settings()
            wait()
            dialog.set_doctor_access(True)
            wait()
        finally:
            QMessageBox.question = original_question
        assert dialog.doctor_access
        dialog.confirm.setChecked(True)
        dialog.bind_profile()
        wait()
        assert not account.consent('TEST-local-owner'), 'Binding must not silently consent to uploads'
        dialog.show_chat()
        wait()
        dialog.message_input.setPlainText('TEST 患者：请问本周训练怎样安排？')
        dialog.send_message()
        assert not dialog.chat_button.isEnabled(), 'Busy state must prevent duplicate requests'
        wait()
        assert not dialog.message_input.toPlainText()
        response = doctor.post(BASE + '/patients/' + patient + '/messages', json={
            'operation_id': str(uuid4()), 'text': 'TEST 医师：这是隔离验收回复，请先核对本人评估。'})
        assert response.is_success, response.text
        publish(doctor, patient)
        dialog.reconnect()
        wait()
        assert 'TEST 医师' in dialog.chat_records.toPlainText()
        dialog.message_input.setFocus()
        app.processEvents()
        QTest.keyClick(dialog.message_input, Qt.Key_Tab)
        assert QApplication.focusWidget() is not None
        for mode in ('light', 'dark', 'high-contrast'):
            theme(mode)
            dialog.resize(700, 720)
            dialog.show_chat()
            wait()
            assert not dialog.username.isVisible()
            assert not dialog.confirm.isVisible()
            screenshot(mode + '-chat')
            dialog.show_plans()
            wait()
            assert dialog.plan_list
            assert 'TEST' in dialog.plan_records.toPlainText()
            screenshot(mode + '-plans')
            dialog.show_settings()
            wait()
            screenshot(mode + '-sharing')
            dialog.show_chat()
            wait()
            dialog.resize(520, 560)
            app.processEvents()
            assert dialog.message_input.width() < dialog.width()
            for button in dialog.findChildren(QPushButton):
                if button.isVisible():
                    pos = button.mapTo(dialog, button.rect().topRight())
                    assert pos.x() < dialog.width(), 'Visible action clipped: ' + button.text()
            screenshot(mode + '-small-chat')
        http.offline = True
        dialog.message_input.setPlainText('TEST 离线问题：恢复连接后重发同一条。')
        dialog.send_message()
        wait()
        assert dialog.pending_message
        with account.db() as connection:
            assert connection.execute('SELECT COUNT(*) FROM message_outbox WHERE resource_id IS NULL').fetchone()[0] == 1
        http.offline = False
        dialog.reconnect()
        wait()
        assert not dialog.pending_message
        messages = account.messages()['items']
        assert sum('TEST 离线问题' in m['text'] for m in messages) == 1
        dialog.close()
        reopened = CloudAccountDialog(out / 'TEST-contact-only', 'TEST-local-owner', 'TEST 虚构患者', lambda: [], client=account)
        reopened.show()
        limit = time.monotonic() + 20
        while time.monotonic() < limit:
            app.processEvents()
            QTest.qWait(20)
            if reopened.future is None and 'TEST 离线问题' in reopened.chat_records.toPlainText():
                break
        assert reopened.pages.currentWidget() is reopened.patient_page
        assert reopened.confirm.isChecked()
        assert not reopened.upload_consent.isChecked()
        assert 'TEST 离线问题' in reopened.chat_records.toPlainText()
        http.offline = True
        reopened.logout()
        wait(reopened)
        assert reopened.pages.currentWidget() is reopened.account_page
        assert account.session() is None
        reopened.close()
        result = dict(actual_qt=True, isolated_test_service=True, real_patient_data_used=False,
            account_separate_from_chat=True, saved_login_opens_chat=True,
            explicit_doctor_grant=True, binding_does_not_upload=True,
            durable_chat_and_offline_retry=True, retry_duplicates=0, offline_logout=True,
            physician_plan_page=True, patient_api_controls_removed=True,
            minimum_size=[520, 560], themes=['light', 'dark', 'high-contrast'],
            keyboard_focus=True, screenshots=13)
        (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        if not dialog.future:
            dialog.close()
        http.client.close()
        doctor.close()
        db.engine.dispose()


if __name__ == '__main__':
    main()
