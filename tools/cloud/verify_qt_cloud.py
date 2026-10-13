"""Actual Qt account dialog, actual saved replay and public HTTPS, isolated QA only."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from app.cloud_account import CloudAccount, CloudError, transport
from app.storage import Storage
from app.ui.cloud_account import CloudAccountDialog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('private_file', type=Path)
    parser.add_argument('database', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--doctor-file', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    credentials = json.loads(args.private_file.read_text())
    patient = credentials['identity']['patient_id']
    app = QApplication([])
    app.setStyle('Fusion')
    for font in ('msyh.ttc', 'msyhbd.ttc'):
        QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/font))
    app.setFont(QFont('Microsoft YaHei UI', 10))
    store = Storage(args.database)
    snapshots = store.list_sessions()
    assert snapshots and all(s['participant_id'] == patient for s in snapshots)
    client = CloudAccount(args.output/'cloud-state')
    dialog = CloudAccountDialog(args.output/'cloud-state', patient, 'QA 录像参与者', lambda: store.list_sessions(), client=client)
    dialog.show()
    def click(title):
        button = next(b for b in dialog.findChildren(QPushButton) if b.text() == title)
        QTest.mouseClick(button, Qt.LeftButton)
        deadline = time.monotonic() + 55
        while dialog.future and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        assert not dialog.future, 'Cloud UI did not finish within its network bounds'
    try:
        dialog.username.setText(credentials['username'])
        dialog.password.setText(credentials['password'])
        click('登录')
        assert dialog.status.text().startswith('已登录'), dialog.status.text()
        assert not dialog.password.text()
        dialog.confirm.setChecked(True)
        click('上传本人已保存结果')
        assert dialog.status.text().startswith('本次上传 1 条'), dialog.status.text()
        records = client.records()
        desktop = [r for r in records if r['source_kind']=='DESKTOP_LOCAL']
        apk = [r for r in records if r['source_kind']=='APK_LOCAL']
        assert len(desktop)==1 and apk
        assert desktop[0]['payload']['result']['summary']==snapshots[0]['summary']
        click('重试待上传')
        assert dialog.status.text().startswith('本次上传 0 条'), dialog.status.text()
        assert len(client.records())==len(records)
        dialog.grab().save(str(args.output/'PRIVATE-qt-cloud-records.png'))
        click('授权医生查看')
        assert dialog.status.text()=='已授权医生查看', dialog.status.text()
        lines = args.doctor_file.read_text(encoding='utf-8-sig').splitlines()
        password = next(line[5:] for line in lines if line.startswith('初始密码：'))
        doctor = transport('/auth/password/login','POST',dict(username='doctor',password=password,client_kind='DESKTOP'))
        try:
            permitted = transport('/patients/'+patient+'/records?offset=0&limit=10',token=doctor['access_token'])
            assert permitted['items']==records
            click('撤销医生授权')
            assert dialog.status.text()=='医生授权已撤销'
            try:
                transport('/patients/'+patient,token=doctor['access_token'])
            except CloudError as error:
                assert error.status==404
            else:
                raise AssertionError('Doctor could read after revoke')
        finally:
            transport('/auth/logout','POST',{},doctor['access_token'])
        result=dict(actual_qt_dialog=True,actual_saved_replay=True,desktop_uploaded=1,
            desktop_completed=snapshots[0]['summary']['completed'],summary_exact=True,retry_duplicates=0,
            phone_records_read=len(apk),doctor_shared_read=True,revocation_immediate=True,
            physical_camera_used=False,original_patient_databases_used=False)
        (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
    finally:
        if not dialog.future:
            dialog.close()
        client.logout()
        store.close()


if __name__=='__main__':
    main()
