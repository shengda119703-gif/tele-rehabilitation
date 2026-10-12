"""Bounded account dialog using the existing Qt product controls."""
from concurrent.futures import ThreadPoolExecutor
import html
import json

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QTextBrowser)

from ..cloud_account import CloudAccount, CloudError, desktop_record, ORIGIN


class CloudAccountDialog(QDialog):
    def __init__(self, directory, local_id, name, snapshots, parent=None, client=None):
        super().__init__(parent)
        self.setWindowTitle('云账号与记录')
        self.resize(660, 620)
        self.setModal(True)
        self.local_id, self.snapshots = local_id, snapshots
        self.client = client or CloudAccount(directory)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cloud-account')
        self.future = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('统一云服务  ·  ' + ORIGIN))
        self.status = QLabel('登录后可上传本机结果，或查看其他端上传的记录。')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        form = QFormLayout()
        self.username, self.password = QLineEdit(), QLineEdit()
        self.username.setAccessibleName('云账号')
        self.password.setAccessibleName('云账号密码')
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setMaxLength(128)
        form.addRow('账号', self.username)
        form.addRow('密码', self.password)
        layout.addLayout(form)
        self.actions = []
        row = QHBoxLayout()
        def action(text, callback, destination=row):
            button = QPushButton(text)
            button.setMinimumHeight(40)
            button.clicked.connect(callback)
            destination.addWidget(button)
            self.actions.append(button)
            return button
        action('登录', self.login)
        action('注册', self.register)
        action('退出账号', lambda: self.run(self.client.logout, '已退出；本机记录和待上传队列保留'))
        layout.addLayout(row)
        self.confirm = QCheckBox('当前本机档案「' + name + '」属于这个云账号')
        layout.addWidget(self.confirm)
        row = QHBoxLayout()
        action('上传本人已保存结果', self.upload, row)
        action('重试待上传', lambda: self.run(self.client.sync, '上传完成'), row)
        action('查看云记录', lambda: self.run(self.client.records, '已读取最近10条云记录'), row)
        layout.addLayout(row)
        row = QHBoxLayout()
        action('授权医生查看', lambda: self.run(lambda: self.client.grant(True), '已授权医生查看'), row)
        action('撤销医生授权', lambda: self.run(lambda: self.client.grant(False), '医生授权已撤销'), row)
        layout.addLayout(row)
        self.records = QTextBrowser()
        self.records.setAccessibleName('云端分析结果')
        layout.addWidget(self.records, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        try:
            session = self.client.session()
        except CloudError as exc:
            session = None
            self.status.setText(str(exc))
        if session:
            self.username.setText(session['username'])
            self.status.setText('已保存登录状态：' + session['username'] + '；请点击查看云记录核对连接。')

    def run(self, work, message):
        if self.future:
            return
        self.message = message
        self.status.setText('正在连接…')
        for button in self.actions:
            button.setEnabled(False)
        self.confirm.setEnabled(False)
        self.username.setEnabled(False)
        self.password.setEnabled(False)
        self.future = self.pool.submit(work)

    def login(self):
        username, password = self.username.text(), self.password.text()
        self.password.clear()
        self.confirm.setChecked(False)
        self.run(lambda: self.client.login(username, password), '已登录：' + username)

    def register(self):
        username, password = self.username.text(), self.password.text()
        self.password.clear()
        def work():
            self.client.register(username, password)
            return self.client.login(username, password)
        self.confirm.setChecked(False)
        self.run(work, '注册并登录成功：' + username)

    def upload(self):
        if not self.confirm.isChecked():
            self.status.setText('请确认本机档案归属，再上传结果。')
            return
        def work():
            self.client.bind(self.local_id)
            entries = [s for s in self.snapshots() if s.get('participant_id') == self.local_id]
            queued, excluded = 0, 0
            for entry in entries:
                try:
                    payload = desktop_record(entry, self.local_id)
                except CloudError:
                    excluded += 1
                    continue
                self.client.queue(self.local_id, 'session:' + entry['id'], payload)
                queued += 1
            result = self.client.sync()
            result.update(queued=queued, excluded=excluded)
            return result
        self.run(work, '本人结果已上传')

    def poll(self):
        if not self.future or not self.future.done():
            return
        future, self.future = self.future, None
        try:
            value = future.result()
            message = self.message
            if isinstance(value, dict) and 'uploaded' in value:
                message = f"本次上传 {value['uploaded']} 条；展示或未结束记录不上传。"
            self.status.setText(message)
            entries = value.get('records') if isinstance(value, dict) else value
            if isinstance(entries, list):
                lines = []
                for record in entries:
                    p = record['payload']
                    lines.append('<h3>' + html.escape(p.get('title', '分析记录')) + '</h3><pre>' +
                                 html.escape(json.dumps(p, ensure_ascii=False, indent=2)) + '</pre>')
                self.records.setHtml(''.join(lines) if lines else '<p>暂无云记录。</p>')
        except Exception as exc:
            self.status.setText(str(exc) if isinstance(exc, (CloudError, ValueError)) else '操作未完成，本机记录保留，请重试。')
        for button in self.actions:
            button.setEnabled(True)
        self.confirm.setEnabled(True)
        self.username.setEnabled(True)
        self.password.setEnabled(True)

    def closeEvent(self, event):
        if self.future:
            self.status.setText('请求正在处理，请等回复后关闭。')
            event.ignore()
            return
        self.timer.stop()
        self.password.clear()
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)

    def reject(self):
        if self.future:
            return
        self.timer.stop()
        self.password.clear()
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().reject()
