"""Bounded account dialog using the existing Qt product controls."""
from concurrent.futures import ThreadPoolExecutor
import html
import json
from uuid import uuid4

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QTextBrowser, QPlainTextEdit, QComboBox, QMessageBox)

from ..cloud_account import CloudAccount, CloudError, desktop_record, ORIGIN


class CloudAccountDialog(QDialog):
    def __init__(self, directory, local_id, name, snapshots, parent=None, client=None, product_snapshot=None, rehab_store=None, scope=None):
        super().__init__(parent)
        self.setWindowTitle('工作台')
        self.setObjectName('workbenchDialog')
        self.setProperty('visualScope', 'core')
        self.resize(740, 780)
        self.setModal(True)
        self.local_id, self.snapshots = local_id, snapshots
        self.product_snapshot = product_snapshot
        self.rehab_store, self.scope = rehab_store, scope
        self.oldest_message = 0
        self.pending_message = None
        self.plan_list = []
        self.plan_offset = 0
        self.current_revision = 0
        self.mode = 'records'
        self.client = client or CloudAccount(directory)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cloud-account')
        self.future = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('统一云服务  ·  ' + ORIGIN))
        self.status = QLabel('登录本人云账号后，可分享档案、与医生文字沟通、查看医生方案。')
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
        action('退出账号', self.logout)
        layout.addLayout(row)
        self.can_upload = bool(local_id)
        self.confirm = QCheckBox('当前本机档案「' + name + '」属于这个云账号' if self.can_upload else
                                 '上传本机结果前，请在“我的档案”中选择或新建本人档案')
        self.confirm.setEnabled(self.can_upload)
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
        self.upload_consent = QCheckBox('同意自动同步本人康复资料、已保存评估、训练结果和计划（不含录像原件）')
        self.upload_consent.setAccessibleName('自动同步本人康复记录')
        self.upload_consent.toggled.connect(self.set_upload_consent)
        layout.addWidget(self.upload_consent)
        row = QHBoxLayout()
        action('与医生聊天', lambda: self.run(self.client.messages, '已读取最近消息', 'messages'), row)
        action('更早消息', lambda: self.run(lambda: self.client.messages(self.oldest_message), '已读取更早消息', 'messages'), row)
        action('重试发送', lambda: self.run(self.client.sync_messages, '待发消息已重试', 'sent'), row)
        action('医生方案', lambda: self.run(self.client.plans, '已读取最近5项医生发布方案', 'plans'), row)
        action('更早方案', lambda: self.run(lambda: self.client.plans(self.plan_offset + 5), '已读取更早方案', 'plans'), row)
        action('当前方案', lambda: self.run(self.client.current, '已读取当前方案', 'current'), row)
        layout.addLayout(row)
        self.records = QTextBrowser()
        self.records.setOpenExternalLinks(False)
        self.records.setAccessibleName('工作台内容')
        layout.addWidget(self.records, 1)
        self.message_input = QPlainTextEdit()
        self.message_input.setPlaceholderText('给医生的文字（最多 4000 字）；主动点击发送后才提交。')
        self.message_input.setAccessibleName('给医生的文字')
        self.message_input.setMaximumHeight(90)
        layout.addWidget(self.message_input)
        row = QHBoxLayout()
        action('发送给医生', self.send_message, row)
        self.plan_select = QComboBox()
        self.plan_select.setAccessibleName('选择医生发布方案')
        row.addWidget(self.plan_select, 1)
        action('设为当前方案', self.accept_plan, row)
        layout.addLayout(row)
        note = QLabel('采用前核对本机最新本人评估；通过后加入本地计划库。开始训练仍需原来的机位与准备确认。')
        note.setWordWrap(True)
        layout.addWidget(note)
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
            with self.client.db() as db:
                pending = db.execute('SELECT operation_id,text FROM message_outbox WHERE patient_id=? AND resource_id IS NULL', (session['patient_id'],)).fetchall()
            if pending:
                self.status.setText(f'本机保留 {len(pending)} 条待发文字；连接恢复后点击“重试发送”。')
                self.pending_message = (pending[-1]['operation_id'], pending[-1]['text'])
                self.message_input.setPlainText(pending[-1]['text'])
        self.upload_consent.blockSignals(True)
        self.upload_consent.setChecked(bool(local_id and self.client.consent(local_id)))
        self.upload_consent.blockSignals(False)

    def run(self, work, message, mode='records'):
        if self.future:
            return
        self.message = message
        self.mode = mode
        self.status.setText('正在连接…')
        for button in self.actions:
            button.setEnabled(False)
        self.confirm.setEnabled(False)
        self.username.setEnabled(False)
        self.password.setEnabled(False)
        self.upload_consent.setEnabled(False)
        self.future = self.pool.submit(work)

    def login(self):
        username, password = self.username.text(), self.password.text()
        self.password.clear()
        self.confirm.setChecked(False)
        self.records.clear()
        self.plan_list = []
        self.plan_select.clear()
        self.pending_message = None
        self.message_input.clear()
        self.upload_consent.blockSignals(True)
        self.upload_consent.setChecked(False)
        self.upload_consent.blockSignals(False)
        self.run(lambda: self.client.login(username, password), '已登录：' + username)

    def register(self):
        username, password = self.username.text(), self.password.text()
        self.password.clear()
        def work():
            self.client.register(username, password)
            return self.client.login(username, password)
        self.confirm.setChecked(False)
        self.run(work, '注册并登录成功：' + username)

    def logout(self):
        self.records.clear()
        self.plan_list = []
        self.plan_select.clear()
        self.pending_message = None
        self.message_input.clear()
        self.confirm.setChecked(False)
        self.upload_consent.blockSignals(True)
        self.upload_consent.setChecked(False)
        self.upload_consent.blockSignals(False)
        self.run(self.client.logout, '已退出；本机记录和待上传队列保留', 'logout')

    def upload(self):
        if not self.can_upload or not self.confirm.isChecked():
            self.status.setText('请确认本机档案归属，再上传结果。')
            return
        if not self.upload_consent.isChecked():
            self.status.setText('请先明确勾选本人康复记录同步同意，再上传。')
            return
        def work():
            self.client.bind(self.local_id)
            if self.product_snapshot:
                self.client.queue_product(self.local_id, self.product_snapshot())
            if self.rehab_store:
                self.client.queue_rehab(self.local_id, self.rehab_store)
            result = self.client.sync()
            return result
        self.run(work, '本人结果已上传')

    def set_upload_consent(self, enabled):
        if enabled and (not self.can_upload or not self.confirm.isChecked()):
            self.status.setText('请先登录，并确认当前本机档案属于该云账号。')
            self.upload_consent.blockSignals(True)
            self.upload_consent.setChecked(False)
            self.upload_consent.blockSignals(False)
            return
        def work():
            if enabled:
                self.client.bind(self.local_id)
            self.client.consent(self.local_id, enabled)
            return {}
        self.run(work, '已开启本人康复记录自动同步' if enabled else '已暂停本人康复记录自动同步', 'consent')

    def send_message(self):
        text = self.message_input.toPlainText().strip()
        if not text or len(text) > 4000:
            self.status.setText('请填写 1–4000 字的文字。')
            return
        if not self.pending_message or self.pending_message[1] != text:
            self.pending_message = (str(uuid4()), text)
        operation_id, text = self.pending_message
        def work():
            self.client.send(operation_id, text)
            return self.client.messages()
        self.run(work, '文字已发送给医生', 'sent')

    def accept_plan(self):
        index = self.plan_select.currentIndex()
        if index < 0 or index >= len(self.plan_list):
            self.status.setText('请先读取并选择医生发布的方案。')
            return
        plan = self.plan_list[index]
        if not self.local_id or not self.rehab_store or not self.scope or not self.confirm.isChecked():
            self.status.setText('请确认本人本机档案，再按当前真实来源核对评估。')
            return
        if QMessageBox.question(self, '采用医生方案', '将按本机最新评估核对并保存「' + plan['title'] + '」。保存后可在康复计划库中选择训练，是否采用？') != QMessageBox.Yes:
            return
        self.run(lambda: self.client.adopt(plan, self.current_revision, self.local_id, self.scope, self.rehab_store), '已加入本地计划库并设为当前方案', 'accepted')

    @staticmethod
    def plan_html(plan):
        if not plan:
            return '<p>尚未选择当前医生方案。</p>'
        value = '<h3>' + html.escape(plan['title']) + '</h3><p>' + html.escape(plan.get('summary', '')) + '</p>'
        for item in plan.get('items', []):
            settings = item.get('settings', {})
            detail = ('左侧' if item.get('side') == 'left' else '右侧') + ' · ' + str(settings.get('target_reps', '')) + ' 次 / 组 · ' + str(settings.get('target_sets', '')) + ' 组 · 组间休息 ' + str(settings.get('rest_between_sets_s') or 0) + ' 秒'
            if settings.get('target_angle_deg') is not None:
                detail += ' · 目标角度 ' + str(settings['target_angle_deg']) + '°'
            value += '<h4>' + html.escape(item.get('name', '')) + '</h4><p>' + html.escape(detail) + '</p><p>' + html.escape(item.get('dose', '')) + '</p><p>' + html.escape(item.get('caution', '')) + '</p>'
        return value

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
            if self.mode in ('messages', 'sent'):
                self.records.setHtml(''.join('<p><b>' + ('医生' if m['author_role'] == 'DOCTOR_ADMIN' else '我') + '：</b>' + html.escape(m['text']).replace('\n', '<br>') + '</p>' for m in value['items']) or '<p>暂无文字消息；医生授权开启后可发送。</p>')
                if self.mode == 'sent':
                    self.message_input.clear()
                    self.pending_message = None
                if value['items']:
                    self.oldest_message = value['items'][0]['sequence']
                    if not value.get('offline'):
                        cursor = value['items'][-1]['sequence']
                        self.pool.submit(self.client.mark_read, cursor)
                if value.get('offline'):
                    self.status.setText('离线显示本机缓存消息；待发消息保留。')
            elif self.mode == 'plans':
                self.plan_offset = value.get('offset', 0)
                self.plan_list = value['items']
                self.current_revision = value['current_revision']
                self.plan_select.clear()
                for p in self.plan_list:
                    self.plan_select.addItem(p['title'] + (' · 当前' if p['id'] == value['current_plan_id'] else ''))
                self.records.setHtml(''.join(self.plan_html(p) for p in self.plan_list) or '<p>医生尚未发布方案。</p>')
            elif self.mode in ('current', 'accepted'):
                self.current_revision = value['current_revision']
                self.records.setHtml(self.plan_html(value.get('plan')))
                if value.get('local_status') in ('SUPERSEDED', 'NEEDS_REVIEW'):
                    self.status.setText('云端回执已核对；本机方案仍暂停，请刷新当前方案或补测后再核对。')
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
        self.confirm.setEnabled(self.can_upload)
        self.username.setEnabled(True)
        self.password.setEnabled(True)
        self.upload_consent.setEnabled(self.can_upload)

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
