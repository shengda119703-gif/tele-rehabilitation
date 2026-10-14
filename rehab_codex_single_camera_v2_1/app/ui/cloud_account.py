"""Patient contact page; account and sharing controls remain separate from chat."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
from uuid import uuid4

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QTextBrowser, QPlainTextEdit, QComboBox, QMessageBox, QFileDialog,
    QScrollArea, QWidget, QStackedWidget)

from ..cloud_account import CloudAccount, CloudError


class CloudAccountDialog(QDialog):
    def __init__(self, directory, local_id, name, snapshots, parent=None, client=None, product_snapshot=None, rehab_store=None, scope=None):
        super().__init__(parent)
        self.setWindowTitle('联系康复医师')
        self.setObjectName('workbenchDialog')
        self.setProperty('visualScope', 'core')
        self.resize(700, 720)
        self.setMinimumSize(520, 560)
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
        self.account_session = None
        self.doctor_access = None
        self.page_mode = 'messages'
        self.refresh_tick = 0
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cloud-account')
        self.future = None
        outer = QVBoxLayout(self)
        title = QLabel('联系康复医师')
        title.setObjectName('productTitle')
        outer.addWidget(title)
        self.status = QLabel('首次开通身份后，聊天记录会保留；以后可直接进入。')
        self.status.setWordWrap(True)
        self.status.setAccessibleName('医师沟通连接状态')
        outer.addWidget(self.status)
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        self.account_page = QWidget()
        login_layout = QVBoxLayout(self.account_page)
        introduction = QLabel('与康复医师一对一沟通\n\n请登录本人账号，首次使用可注册。身份用于保存聊天、报告和医生方案。医生请进入独立的医生工作台。')
        introduction.setWordWrap(True)
        login_layout.addStretch()
        login_layout.addWidget(introduction)
        form = QFormLayout()
        self.username, self.password = QLineEdit(), QLineEdit()
        self.username.setAccessibleName('本人账号')
        self.password.setAccessibleName('本人账号密码')
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setMaxLength(128)
        self.username.setMaxLength(64)
        form.addRow('账号', self.username)
        form.addRow('密码', self.password)
        login_layout.addLayout(form)
        self.actions = []
        self.auth_actions = []
        self.patient_actions = []
        def action(text, callback, destination, *, auth=False, primary=False):
            button = QPushButton(text)
            button.setMinimumHeight(40)
            button.setAccessibleName(text)
            if primary:
                button.setProperty('fluentAppearance', 'primary')
            button.clicked.connect(callback)
            destination.addWidget(button)
            self.actions.append(button)
            (self.auth_actions if auth else self.patient_actions).append(button)
            return button
        row = QHBoxLayout()
        action('登录', self.login, row, auth=True, primary=True)
        action('首次使用，注册', self.register, row, auth=True)
        login_layout.addLayout(row)
        login_layout.addStretch()
        self.pages.addWidget(self.account_page)
        self.patient_page = QWidget()
        patient_layout = QVBoxLayout(self.patient_page)
        self.identity = QLabel()
        self.identity.setObjectName('productMuted')
        self.identity.setWordWrap(True)
        patient_layout.addWidget(self.identity)
        row = QHBoxLayout()
        self.chat_button = action('与医师沟通', self.show_chat, row)
        self.plans_button = action('医生方案', self.show_plans, row)
        self.settings_button = action('资料授权', self.show_settings, row)
        for navigation in (self.chat_button, self.plans_button, self.settings_button):
            navigation.setCheckable(True)
            navigation.setAutoExclusive(True)
        patient_layout.addLayout(row)
        self.content_pages = QStackedWidget()
        patient_layout.addWidget(self.content_pages, 1)
        chat_page = QWidget()
        chat_layout = QVBoxLayout(chat_page)
        self.chat_records = QTextBrowser()
        self.chat_records.setOpenExternalLinks(False)
        self.chat_records.setAccessibleName('与康复医师的聊天历史')
        self.chat_records.setMinimumHeight(150)
        self.chat_records.setHtml('<p>正在读取聊天历史…</p>')
        chat_layout.addWidget(self.chat_records, 1)
        self.message_input = QPlainTextEdit()
        self.message_input.setPlaceholderText('描述你遇到的问题，或告诉医师本次训练情况…')
        self.message_input.setAccessibleName('给康复医师的文字')
        self.message_input.setMaximumHeight(100)
        chat_layout.addWidget(self.message_input)
        row = QHBoxLayout()
        action('分享报告', self.share_report, row)
        row.addStretch()
        action('发送', self.send_message, row, primary=True)
        chat_layout.addLayout(row)
        row = QHBoxLayout()
        action('更早消息', lambda: self.run(lambda: self.client.messages(self.oldest_message), '已读取更早消息', 'history'), row)
        row.addStretch()
        self.retry_button = action('重新连接', self.reconnect, row)
        self.retry_button.hide()
        chat_layout.addLayout(row)
        self.content_pages.addWidget(chat_page)
        plans_page = QWidget()
        plans_layout = QVBoxLayout(plans_page)
        self.plan_records = QTextBrowser()
        self.plan_records.setOpenExternalLinks(False)
        self.plan_records.setAccessibleName('医生发布的康复方案')
        plans_layout.addWidget(self.plan_records, 1)
        self.plan_select = QComboBox()
        self.plan_select.setAccessibleName('选择医生发布方案')
        self.plan_select.currentIndexChanged.connect(self.select_plan)
        plans_layout.addWidget(self.plan_select)
        row = QHBoxLayout()
        action('更早方案', lambda: self.run(lambda: self.client.plans(self.plan_offset + 5), '已读取更早方案', 'plans'), row)
        action('当前方案', lambda: self.run(self.client.current, '已读取当前方案', 'current'), row)
        action('确认采用', self.accept_plan, row, primary=True)
        plans_layout.addLayout(row)
        note = QLabel('采用前核对本人最新评估；通过后加入康复计划库。聊天不会直接更改训练方案。')
        note.setWordWrap(True)
        plans_layout.addWidget(note)
        self.content_pages.addWidget(plans_page)
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.settings_scroll.setAccessibleName('本人资料与医生授权设置')
        settings = QWidget()
        self.settings_scroll.setWidget(settings)
        layout = QVBoxLayout(settings)
        self.grant_status = QLabel('医生授权状态：正在核对')
        self.grant_status.setWordWrap(True)
        layout.addWidget(self.grant_status)
        sharing_note = QLabel('同意后，医师可查看你分享的康复资料并与你沟通。报告原件仅在你主动选择时上传。')
        sharing_note.setWordWrap(True)
        layout.addWidget(sharing_note)
        row = QHBoxLayout()
        action('同意医生查看并沟通', lambda: self.set_doctor_access(True), row)
        action('撤销授权', lambda: self.set_doctor_access(False), row)
        layout.addLayout(row)
        self.can_upload = bool(local_id)
        profile_name = QLabel('本机档案：' + name if self.can_upload else '上传本机结果前，请在“我的档案”中选择或新建本人档案')
        profile_name.setWordWrap(True)
        layout.addWidget(profile_name)
        self.confirm = QCheckBox('我确认这份本机档案属于本人账号')
        self.confirm.setEnabled(self.can_upload)
        layout.addWidget(self.confirm)
        row = QHBoxLayout()
        action('保存档案归属', self.bind_profile, row)
        action('上传本人已保存结果', self.upload, row)
        layout.addLayout(row)
        self.upload_consent = QCheckBox('同意自动同步本人评估、训练记录与计划')
        self.upload_consent.setAccessibleName('自动同步本人康复记录')
        self.upload_consent.toggled.connect(self.set_upload_consent)
        layout.addWidget(self.upload_consent)
        row = QHBoxLayout()
        action('查看已分享记录', lambda: self.run(self.client.records, '已读取本人分享记录', 'records'), row)
        layout.addLayout(row)
        row = QHBoxLayout()
        action('康复目标与器材', lambda: self.run(self.client.workflow, '已读取本人资料，可复用或修改', 'workflow'), row)
        action('请求进阶核对', lambda: self.run(lambda: self.client.candidate('PROGRESSION'), '已提交医生核对，不自动增加负重', 'candidate'), row)
        layout.addLayout(row)
        row = QHBoxLayout()
        action('提交起始候选', lambda: self.run(lambda: self.client.candidate('STARTER'), '候选已提交医生核对，不改变当前方案', 'candidate'), row)
        layout.addLayout(row)
        self.settings_records = QTextBrowser()
        self.settings_records.setOpenExternalLinks(False)
        self.settings_records.setAccessibleName('本人已分享资料')
        self.settings_records.setMinimumHeight(120)
        layout.addWidget(self.settings_records)
        row = QHBoxLayout()
        action('退出账号', self.logout, row)
        layout.addLayout(row)
        layout.addStretch()
        self.content_pages.addWidget(self.settings_scroll)
        self.pages.addWidget(self.patient_page)
        self.records = self.chat_records
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
            self.restore_identity(session)
            QTimer.singleShot(0, self.reconnect)
        else:
            self.pages.setCurrentWidget(self.account_page)
            self.username.setFocus()
        self.upload_consent.blockSignals(True)
        self.upload_consent.setChecked(bool(local_id and self.client.consent(local_id)))
        self.upload_consent.blockSignals(False)
        self.refresh_controls()

    def refresh_controls(self):
        busy = self.future is not None
        authenticated = self.account_session is not None
        for button in self.auth_actions:
            button.setEnabled(not busy)
        for button in self.patient_actions:
            button.setEnabled(not busy and authenticated)
        self.confirm.setEnabled(not busy and authenticated and self.can_upload)
        self.upload_consent.setEnabled(not busy and authenticated and self.can_upload)
        self.username.setEnabled(not busy)
        self.password.setEnabled(not busy)
        self.message_input.setEnabled(authenticated)

    def restore_identity(self, session):
        self.account_session = session
        self.identity.setText('本人：' + session['username'] + '  ·  康复医师一对一沟通')
        self.pages.setCurrentWidget(self.patient_page)
        self.content_pages.setCurrentIndex(0)
        self.page_mode = 'messages'
        self.update_navigation()
        self.browsing_history = False
        with self.client.db() as db:
            binding = db.execute('SELECT patient_id FROM bindings WHERE local_id=?', (self.local_id,)).fetchone()
            pending = db.execute('SELECT operation_id,text FROM message_outbox WHERE patient_id=? AND resource_id IS NULL ORDER BY rowid', (session['patient_id'],)).fetchall()
        self.confirm.setChecked(bool(binding and binding[0] == session['patient_id']))
        self.upload_consent.blockSignals(True)
        self.upload_consent.setChecked(bool(self.local_id and self.client.consent(self.local_id)))
        self.upload_consent.blockSignals(False)
        if pending:
            self.pending_message = (pending[-1]['operation_id'], pending[-1]['text'])
            self.message_input.setPlainText(pending[-1]['text'])
        self.refresh_controls()

    def show_chat(self):
        self.page_mode = 'messages'
        self.update_navigation()
        self.browsing_history = False
        self.content_pages.setCurrentIndex(0)
        self.records = self.chat_records
        self.reconnect()

    def show_plans(self):
        self.page_mode = 'plans'
        self.update_navigation()
        self.content_pages.setCurrentIndex(1)
        self.records = self.plan_records
        self.run(self.client.plans, '已读取医生方案', 'plans')

    def show_settings(self):
        self.page_mode = 'settings'
        self.update_navigation()
        self.content_pages.setCurrentIndex(2)
        self.records = self.settings_records
        self.run(lambda: self.client.patient_call(''), '可选择分享范围，也可随时撤销医生授权', 'settings')

    def update_navigation(self):
        for mode, button in (('messages', self.chat_button), ('plans', self.plans_button), ('settings', self.settings_button)):
            selected = mode == self.page_mode
            button.setChecked(selected)
            button.setProperty('fluentAppearance', 'primary' if selected else 'secondary')
            button.style().unpolish(button)
            button.style().polish(button)

    def reconnect(self):
        if not self.account_session:
            return
        def work():
            try:
                messages = self.client.sync_messages()
            except CloudError:
                messages = self.client.messages()
            try:
                patient = self.client.patient_call('')
            except CloudError:
                patient = None
            return {'messages': messages, 'patient': patient}
        self.run(work, '聊天已更新；发送的文字与分享资料不会自动改动训练方案', 'connected')

    def set_doctor_access(self, enabled):
        prompt = ('同意康复医师查看你已分享的康复记录、报告，并与你沟通？' if enabled else
                  '撤销后，医师不能继续查看资料和与你发送新消息。已保留的聊天和本人记录不会删除。')
        if QMessageBox.question(self, '医生授权', prompt) != QMessageBox.Yes:
            return
        def work():
            value = self.client.grant(enabled)
            value['doctor_access'] = enabled
            return value
        self.run(work, '已同意医师查看并沟通' if enabled else '已撤销医生授权', 'grant')

    def bind_profile(self):
        if not self.can_upload or not self.confirm.isChecked():
            self.status.setText('请先确认本机档案属于当前本人账号。')
            return
        self.run(lambda: self.client.bind(self.local_id), '已保存本人档案归属，尚未上传资料', 'bound')

    def select_plan(self, index):
        if 0 <= index < len(self.plan_list):
            self.plan_records.setHtml(self.plan_html(self.plan_list[index]))

    def run(self, work, message, mode='records'):
        if self.future:
            return
        self.message = message
        self.mode = mode
        self.records = (self.chat_records if mode in ('messages', 'history', 'sent', 'connected', 'auto_messages') else
                        self.plan_records if mode in ('plans', 'current', 'accepted') else self.settings_records)
        if mode != 'auto_messages':
            self.status.setText('正在连接…')
        self.future = self.pool.submit(work)
        self.refresh_controls()

    def share_report(self):
        from pathlib import Path
        filename, _ = QFileDialog.getOpenFileName(self, '选择分享给医生的报告原件', '', '报告原件 (*.pdf *.png *.jpg *.jpeg)')
        if not filename:
            return
        path = Path(filename)
        try:
            size = path.stat().st_size
        except OSError:
            self.status.setText('原件无法读取，请重新选择。')
            return
        if size > 2 * 1024 * 1024:
            self.status.setText('请选择不超过2MB的报告原件。')
            return
        if QMessageBox.question(self, '分享报告原件', '将「' + path.name + '」上传并授权医生查看？需要同时开启医生授权。原件不做识字或模型分析。') != QMessageBox.Yes:
            return
        mime = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}.get(path.suffix.lower())
        if mime is None:
            self.status.setText('请选择 PDF、PNG 或 JPEG 原件。')
            return
        def work():
            raw = path.read_bytes()
            with self.client.lock:
                patient = self.client.me()['patient_id']
                # Persist only the request identity, never a plaintext copy of the original.
                key = 'report-request:' + patient + ':' + hashlib.sha256(path.name.encode() + b'\0' + raw).hexdigest()
                with self.client.db() as db:
                    db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', (key, str(uuid4())))
                    operation = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()[0]
                return self.client.share_report(path.name, raw, mime, operation)
        self.run(work, '报告已分享；医师授权开启后可查看', 'report')

    def workflow_profile(self, state):
        profile = state.get('profile') or {}
        dialog = QDialog(self)
        dialog.setWindowTitle('本人目标、器材与限制')
        dialog.setProperty('visualScope', 'core')
        form = QFormLayout(dialog)
        goal = QLineEdit(profile.get('goal', ''))
        goal.setMaxLength(500)
        region, level = QComboBox(), QComboBox()
        region.addItems(['肩', '肘', '腕', '髋', '膝', '踝', '颈', '躯干', '一般活动'])
        region.setCurrentText(profile.get('region', '肩'))
        level.addItems(['L0', 'L1', 'L2', 'L3'])
        level.setCurrentIndex(profile.get('level', 0))
        equipment = QPlainTextEdit('\n'.join(profile.get('equipment', [])))
        restrictions = QPlainTextEdit('\n'.join(profile.get('restrictions', [])))
        confirmation = QCheckBox('已阅读适用与停止条件；疑问先联系医生')
        confirmation.setChecked(profile.get('screening_confirmed', False))
        form.addRow('康复目标', goal)
        form.addRow('部位', region)
        form.addRow('自填能力（不是测量肌力，需医生核对）', level)
        form.addRow('现有器材（每行一项，保留动作库原名称）', equipment)
        form.addRow('当前限制（每行一项）', restrictions)
        form.addRow(confirmation)
        note = QLabel('流程：问答了解 → 手动选择原康复评估 → 保存并同步结果 → 提交候选 → 医生核对并发布 → 本人采用。填写的限制由医生判断，不让模型判定可以训练。')
        note.setWordWrap(True)
        form.addRow(note)
        save, cancel = QPushButton('保存供下次复用'), QPushButton('关闭')
        save.clicked.connect(dialog.accept)
        cancel.clicked.connect(dialog.reject)
        form.addRow(save, cancel)
        dialog.resize(580, 640)
        if dialog.exec() == QDialog.Accepted:
            document = {'expected_version': state['profile_version'], 'goal': goal.text(), 'region': region.currentText(),
                'level': level.currentIndex(), 'equipment': [v.strip() for v in equipment.toPlainText().splitlines() if v.strip()],
                'restrictions': [v.strip() for v in restrictions.toPlainText().splitlines() if v.strip()], 'screening_confirmed': confirmation.isChecked()}
            self.run(lambda: self.client.save_workflow_profile(document), '资料已保存。请到原康复页面手动评估，再同步真实结果', 'workflow_saved')

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
        self.run(lambda: self.client.login(username, password), '已登录：' + username, 'auth')

    def register(self):
        username, password = self.username.text(), self.password.text()
        self.password.clear()
        def work():
            self.client.register(username, password)
            return self.client.login(username, password)
        self.confirm.setChecked(False)
        self.run(work, '注册并登录成功：' + username, 'auth')

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
        def work():
            try:
                self.client.logout()
            except CloudError:
                # The adapter clears the local identity in its finally block.
                if self.client.session() is not None:
                    raise
            return None
        self.run(work, '已退出本机账号；本人记录和待发送文字仍保留', 'logout')

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
            self.status.setText('请先到“资料授权”确认本人本机档案，再按当前真实来源核对评估。')
            return
        if QMessageBox.question(self, '采用医生方案', '将按本机最新评估核对并保存「' + plan['title'] + '」。保存后可在康复计划库中选择训练，是否采用？') != QMessageBox.Yes:
            return
        self.run(lambda: self.client.adopt(plan, self.current_revision, self.local_id, self.scope, self.rehab_store), '已加入本地计划库并设为当前方案', 'accepted')

    @staticmethod
    def plan_html(plan):
        if not plan:
            return '<p>尚未选择当前医生方案。</p>'
        value = '<h3>' + html.escape(plan['title']) + '</h3><p>' + html.escape(plan.get('summary', '')) + '</p>'
        execution = {'READY': '今天可按已核对方案训练', 'REST_DAY': '今天没有安排软件训练',
                     'MANUAL_ONLY': '本阶段由专业人员指导人工执行，不能自动开始', 'STOPPED': '医生已停用，不能继续采用或开始'}
        if plan.get('execution_status') in execution:
            value += '<p><b>' + execution[plan['execution_status']] + '</b></p>'
        if plan.get('stop_reason'):
            value += '<p>停用原因：' + html.escape(plan['stop_reason']) + '</p>'
        if plan.get('execution_date'):
            value += '<p>日期：' + html.escape(plan['execution_date']) + '  ' + html.escape(plan.get('phase_name', '')) + '</p>'
        for item in plan.get('items', []):
            settings = item.get('settings', {})
            detail = ('左侧' if item.get('side') == 'left' else '右侧') + ' · ' + str(settings.get('target_reps', '')) + ' 次 / 组 · ' + str(settings.get('target_sets', '')) + ' 组 · 组间休息 ' + str(settings.get('rest_between_sets_s') or 0) + ' 秒'
            if settings.get('target_angle_deg') is not None:
                detail += ' · 目标角度 ' + str(settings['target_angle_deg']) + '°'
            value += '<h4>' + html.escape(item.get('name', '')) + '</h4><p>' + html.escape(detail) + '</p><p>' + html.escape(item.get('dose', '')) + '</p><p>' + html.escape(item.get('caution', '')) + '</p>'
        return value

    def poll(self):
        if not self.future or not self.future.done():
            if not self.future and self.account_session and self.page_mode == 'messages' and not getattr(self, 'browsing_history', False):
                self.refresh_tick += 1
                if self.refresh_tick >= 150:
                    self.refresh_tick = 0
                    self.run(self.client.sync_messages, '聊天已更新', 'auto_messages')
            return
        future, self.future = self.future, None
        try:
            value = future.result()
            message = self.message
            if isinstance(value, dict) and 'uploaded' in value:
                message = f"本次上传 {value['uploaded']} 条；展示或未结束记录不上传。"
            self.status.setText(message)
            if self.mode == 'auth':
                self.restore_identity(self.client.session())
                QTimer.singleShot(0, self.reconnect)
            elif self.mode == 'logout':
                self.account_session = None
                self.doctor_access = None
                self.pages.setCurrentWidget(self.account_page)
                self.username.setFocus()
            elif self.mode in ('settings', 'grant'):
                self.doctor_access = value['doctor_access']
                self.grant_status.setText('医生授权：已同意查看与沟通' if self.doctor_access else '医生授权：尚未同意，可在下方选择')
            elif self.mode in ('workflow', 'workflow_saved'):
                self.records.setPlainText('\n'.join(value['steps']) + '\n\n' + value['assessment_note'] + '\n\n可选评估：\n' + '\n'.join(a['name'] + '：' + a['description'] for a in value['suggested_assessments']))
                if self.mode == 'workflow':
                    QTimer.singleShot(0, lambda: self.workflow_profile(value))
            elif self.mode == 'candidate':
                self.records.setPlainText(value['document']['note'] + '\n\n' + '\n'.join(c['id']+' '+c['name']+'\n源剂量范围：'+c['sourceDose']+'\n开始条件：'+c['startConditions']+'\n停止条件：'+c['stopConditions'] for c in value['document']['cards']))
            elif self.mode == 'report':
                self.status.setText('报告「' + value['item']['filename'] + '」已保存；' + ('医生授权开启后可查看。' if value['item'].get('shared') else '该原件的分享已撤销，本次重试不会重新授权。'))
            elif self.mode in ('messages', 'history', 'sent', 'connected', 'auto_messages'):
                if self.mode == 'connected':
                    patient = value.get('patient')
                    value = value['messages']
                    if patient:
                        self.doctor_access = patient['doctor_access']
                        self.grant_status.setText('医生授权：已同意查看与沟通' if self.doctor_access else '医生授权：尚未同意，可在下方选择')
                self.browsing_history = self.mode == 'history'
                self.records.setHtml(''.join('<p><b>' + ('医生' if m['author_role'] == 'DOCTOR_ADMIN' else '我') + '：</b>' + html.escape(m['text']).replace('\n', '<br>') + '</p>' for m in value['items']) or '<p>暂无文字消息；医生授权开启后可发送。</p>')
                with self.client.db() as db:
                    pending = db.execute('SELECT operation_id,text FROM message_outbox WHERE patient_id=? AND resource_id IS NULL ORDER BY rowid', (self.account_session['patient_id'],)).fetchall()
                if not pending and self.pending_message:
                    if self.message_input.toPlainText().strip() == self.pending_message[1]:
                        self.message_input.clear()
                    self.pending_message = None
                if pending:
                    self.records.append('<p><b>我 · 待发送：</b>' + html.escape(pending[-1]['text']).replace('\n', '<br>') + '</p>')
                    self.status.setText('文字已保存在本机，连接恢复后自动发送。')
                if value['items']:
                    self.oldest_message = value['items'][0]['sequence']
                    if not value.get('offline'):
                        cursor = value['items'][-1]['sequence']
                        self.pool.submit(self.client.mark_read, cursor)
                if value.get('offline'):
                    self.status.setText('离线显示本机缓存消息；待发消息保留。')
                    self.retry_button.show()
                else:
                    self.retry_button.hide()
                    if self.doctor_access is False:
                        self.status.setText('首次咨询请到“资料授权”同意医生查看与沟通；你可自行选择分享范围。')
                if self.mode != 'history':
                    self.records.verticalScrollBar().setValue(self.records.verticalScrollBar().maximum())
            elif self.mode == 'plans':
                self.plan_offset = value.get('offset', 0)
                self.plan_list = value['items']
                self.current_revision = value['current_revision']
                self.plan_select.blockSignals(True)
                self.plan_select.clear()
                for p in self.plan_list:
                    self.plan_select.addItem(p['title'] + (' · 当前' if p['id'] == value['current_plan_id'] else ''))
                self.plan_select.blockSignals(False)
                self.records.setHtml(self.plan_html(self.plan_list[0]) if self.plan_list else '<p>医生尚未发布方案。你可以先在聊天中说明情况。</p>')
            elif self.mode in ('current', 'accepted'):
                self.current_revision = value['current_revision']
                self.plan_list = [value['plan']] if value.get('plan') else []
                self.plan_select.blockSignals(True)
                self.plan_select.clear()
                for plan in self.plan_list:
                    self.plan_select.addItem(plan['title'] + ' · 当前')
                self.plan_select.blockSignals(False)
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
            self.retry_button.setVisible(self.account_session is not None and self.page_mode == 'messages')
            if isinstance(exc, CloudError) and exc.status == 401 and self.client.session() is None:
                self.account_session = None
                self.pages.setCurrentWidget(self.account_page)
                self.status.setText('登录已过期，请重新登录。聊天与本机记录仍保留。')
        self.refresh_tick = 0
        self.refresh_controls()

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
