"""Small native assistant surface; navigation stays in MainWindow."""
import copy
import html
from uuid import uuid4

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                              QPushButton, QTextBrowser, QFormLayout, QCheckBox)

from ..agent_conversation import ModelConfig
from .agent_presentation import present_result


def dialog_button(text):
    # QDialog auto-default buttons can take focus while ask() disables input.
    # Every static and dynamic action uses this policy, including settings.
    button = QPushButton(text)
    button.setAutoDefault(False)
    button.setDefault(False)
    return button


class ConversationInput(QLineEdit):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            if not event.isAutoRepeat():
                self.returnPressed.emit()
            return  # Do not propagate the same key to QDialog's default action.
        super().keyPressEvent(event)


class ModelSettingsDialog(QDialog):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = None
        self.setWindowTitle('连接 DeepSeek')
        self.resize(580, 390)
        box = QVBoxLayout(self)
        note = QLabel('密钥仅保留在本次软件运行的内存中，不写入文件。\n'
                      'DeepSeek 会收到你主动发送的文字、最近 6 轮可分享对话；查询康复记录时，'
                      '还会收到本机生成的最小结果摘要。姓名、原始数据库记录和摄像头画面不会发送。')
        note.setWordWrap(True)
        box.addWidget(note)
        form = QFormLayout()
        self.endpoint = QLineEdit(config.base_url if config else 'https://api.deepseek.com')
        self.endpoint.setReadOnly(True)
        self.model = QLineEdit(config.model if config else 'deepseek-flash')
        self.key = QLineEdit(config.api_key if config else '')
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('在这里粘贴 API Key，不要发在聊天中')
        form.addRow('服务根地址', self.endpoint)
        form.addRow('模型名称', self.model)
        form.addRow('API Key', self.key)
        box.addLayout(form)
        self.consent = QCheckBox('我同意向 DeepSeek 发送上述文字与最小结果摘要（可能产生 API 费用）')
        box.addWidget(self.consent)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        box.addWidget(self.error)
        row = QHBoxLayout()
        apply = dialog_button('启用配置')
        apply.clicked.connect(self.save)
        cancel = dialog_button('取消')
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        row.addWidget(apply)
        box.addLayout(row)

    def save(self):
        try:
            self.config = ModelConfig(self.endpoint.text().strip().rstrip('/'), self.model.text().strip(),
                                      self.key.text().strip(), self.consent.isChecked()).validate()
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class RehabAgentDialog(QDialog):
    requested = Signal(str, str)
    navigate = Signal(str)
    operation_requested = Signal(str, str)
    reset_requested = Signal(str)

    def __init__(self, scope, parent=None, config=None):
        super().__init__(parent)
        self.scope = copy.deepcopy(scope)
        self.conversation_id = uuid4().hex
        self.proposals = {}
        self.write_busy = False
        self.request_id = None
        self.allowed_actions = set()
        self.model_config = config
        self.history = []
        self.transcript = []
        self.pending_text = ''
        self.setWindowTitle('康复管家')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(820, 700)
        box = QVBoxLayout(self)
        title = QLabel('可以聊聊天，也可以一起安排康复')
        title.setStyleSheet('font-size:24px;font-weight:600;')
        title.setWordWrap(True)
        box.addWidget(title)
        note = QLabel('对话临时保留；明确确认保存的自报可重开查看，与摄像头评估分开。清空对话不删除已保存自报。')
        note.setWordWrap(True)
        box.addWidget(note)
        status_row = QHBoxLayout()
        self.mode_label = QLabel('DeepSeek 已配置 · 尚未验证连接' if config else '未连接 DeepSeek · 当前仅支持本地有限回答')
        self.mode_label.setWordWrap(True)
        status_row.addWidget(self.mode_label, 1)
        self.settings_button = dialog_button('连接 DeepSeek')
        self.settings_button.clicked.connect(self.configure)
        status_row.addWidget(self.settings_button)
        self.clear_button = dialog_button('清空对话')
        self.clear_button.clicked.connect(self.clear_conversation)
        status_row.addWidget(self.clear_button)
        self.disconnect_button = dialog_button('断开模型')
        self.disconnect_button.clicked.connect(self.disconnect)
        status_row.addWidget(self.disconnect_button)
        box.addLayout(status_row)
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self.toggle_details)
        self.scroll_timer = QTimer(self)
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self.scroll_to_latest)
        self.browser.setPlainText('连接 DeepSeek 后可以自由聊天和连续追问。已有康复记录始终由本机规则核对。')
        box.addWidget(self.browser, 1)
        self.quick = []
        row = QHBoxLayout()
        for text in ('今天该练什么', '我的评估结果', '查看历史记录', '查看自报记录'):
            button = dialog_button(text)
            button.clicked.connect(lambda checked=False, q=text: self.ask(q))
            self.quick.append(button)
            row.addWidget(button)
        box.addLayout(row)
        row = QHBoxLayout()
        self.input = ConversationInput()
        self.input.setMaxLength(500)
        self.input.setPlaceholderText('例如：为什么这样安排？')
        self.input.setAccessibleName('给康复管家的问题')
        self.input.returnPressed.connect(lambda: self.ask(self.input.text()))
        row.addWidget(self.input, 1)
        self.send = dialog_button('询问')
        self.send.clicked.connect(lambda: self.ask(self.input.text()))
        row.addWidget(self.send)
        box.addLayout(row)
        self.action_row = QVBoxLayout()
        box.addLayout(self.action_row)
        close = dialog_button('返回原页面')
        close.clicked.connect(self.reject)
        box.addWidget(close)

    def clear_actions(self):
        self.allowed_actions.clear()
        self.proposals.clear()
        while self.action_row.count():
            widget = self.action_row.takeAt(0).widget()
            widget.setEnabled(False)
            widget.hide()
            widget.deleteLater()

    def set_busy(self, busy):
        if not busy:
            self.write_busy = False
        for widget in [self.send, self.input, self.settings_button, self.clear_button,
                       self.disconnect_button, *self.quick]:
            widget.setEnabled(not busy)
        if not busy:
            self.input.setFocus()

    def configure(self):
        dialog = ModelSettingsDialog(self.model_config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.model_config = dialog.config
            self.clear_conversation()
            self.mode_label.setText('DeepSeek 已配置 · 发送一句话验证连接')
        dialog.deleteLater()

    def disconnect(self):
        self.model_config = None
        self.clear_conversation()
        self.mode_label.setText('已断开 DeepSeek · 当前仅支持本地有限回答')

    def clear_conversation(self):
        if self.write_busy:
            return
        self.reset_requested.emit(self.conversation_id)
        self.conversation_id = uuid4().hex
        self.history.clear()
        self.transcript.clear()
        self.request_id = None
        self.clear_actions()
        self.browser.setPlainText('已清空临时对话和待确认操作。已保存的自报仍可通过“查看自报记录”查看。')

    def render(self, *, scroll_to_end=True):
        parts = []
        scroll = self.browser.verticalScrollBar().value()
        def block(label, text):
            return '<p><b>' + label + '</b><br>' + html.escape(text).replace('\n', '<br>') + '</p>'
        for turn in self.transcript[-20:]:
            turn.setdefault('id', uuid4().hex)
            parts.append(block('你', turn['user']))
            if turn.get('assistant'):
                parts.append(block('康复管家', turn['assistant']))
            if turn.get('secondary'):
                parts.append('<p style="color:#686477;font-size:12px;">' + html.escape(turn['secondary']) + '</p>')
            for key, label in (('local_text', '本机记录与规则核对'), ('evidence_summary', '依据'),
                               ('receipt_text', '自报 / 记录回执'), ('record_summary', '本机自报记录'),
                               ('pending_summary', '待确认操作（逐条核对）'), ('privacy_notice', '隐私与执行状态')):
                if turn.get(key):
                    parts.append(block(label, turn[key]))
            if turn.get('result'):
                expanded = turn.get('details_open', False)
                parts.append('<p style="font-size:12px;"><a href="details:' + turn['id'] + '">' +
                             ('收起详细信息' if expanded else '查看详细信息') + '</a></p>')
                if expanded:
                    result = turn['result']
                    receipt = result.get('receipt', {})
                    for label, value in (('依据详情', result.get('evidence_summary', '')),
                                         ('记录详情', receipt.get('text', '')),
                                         ('完整记录', result.get('record_summary', '')),
                                         ('隐私详情', result.get('privacy_notice', ''))):
                        if value:
                            parts.append(block(label, value))
                    if 'revision' in receipt:
                        parts.append(block('记录版本', str(receipt['revision'])))
                    if result.get('delivery_status') == 'NOT_CONNECTED':
                        parts.append(block('送达状态', '远程通知未接入，未发送给家属。'))
        self.browser.setHtml(''.join(parts))
        self.scroll_timer.stop()
        if scroll_to_end:
            self.scroll_to_latest()
            self.scroll_timer.start(0)  # Reflow after action buttons change the browser height.
        else:
            self.browser.verticalScrollBar().setValue(scroll)

    def scroll_to_latest(self):
        self.browser.verticalScrollBar().setValue(self.browser.verticalScrollBar().maximum())

    def toggle_details(self, url):
        if url.scheme() != 'details':
            return
        turn_id = url.path()
        for turn in self.transcript:
            if turn.get('id') == turn_id:
                turn['details_open'] = not turn.get('details_open', False)
                self.render(scroll_to_end=False)
                return

    def keyPressEvent(self, event):
        # Disabled input can redirect keys to the dialog during a request/write.
        # Return never invokes navigation or a confirmation/default button here.
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            return
        super().keyPressEvent(event)

    def ask(self, text):
        if not self.send.isEnabled() or not text.strip():
            return
        self.clear_actions()
        self.request_id = uuid4().hex
        self.pending_text = text.strip()
        self.transcript.append(dict(user=self.pending_text, assistant='正在回复…'))
        self.transcript = self.transcript[-20:]
        self.render()
        self.input.clear()
        self.set_busy(True)
        self.requested.emit(text, self.request_id)

    def receive(self, request_id, result):
        if request_id != self.request_id or result['scope'] != self.scope:
            return
        self.clear_actions()
        self.set_busy(False)
        if not self.transcript:
            self.transcript.append(dict(user=self.pending_text))
        self.transcript[-1].update(present_result(result, self.pending_text), result=copy.deepcopy(result))
        shareable = result.get('shareable', False)
        self.history.append(dict(
            user=self.pending_text,
            assistant=result['text'],
            tool_context=result.get('local_text', '') if shareable else '',
            shareable=shareable))
        self.history = self.history[-6:]
        self.mode_label.setText(result.get('mode_label', '本地记录查询'))
        self.render()
        for action in result['actions']:
            self.allowed_actions.add(action['id'])
            button = dialog_button(action['label'])
            button.clicked.connect(lambda checked=False, a=action['id']: self.navigate.emit(a))
            self.action_row.addWidget(button)

        proposals = result.get('proposed_actions', [])
        if proposals:
            self._show_proposals(proposals)

    def _show_proposals(self, proposals, offset=0):
        self.clear_actions()
        page = proposals[offset:offset+4]
        for proposal in page:
            self.proposals[proposal['id']] = proposal
            button = dialog_button(proposal['label'])
            button.setToolTip(proposal['summary'])
            button.setAccessibleDescription(proposal['summary'])
            button.clicked.connect(lambda checked=False, a=proposal['id']: self.confirm_operation(a))
            self.action_row.addWidget(button)
        details = '\n\n'.join(p['summary'] for p in page)
        self.transcript[-1]['pending_summary'] = details
        if len(proposals) > 4:
            label = f'切换待确认项（当前 {offset+1}–{offset+len(page)} / {len(proposals)}）'
            more = dialog_button(label)
            next_offset = offset+4 if offset+4 < len(proposals) else 0
            more.clicked.connect(lambda: self._show_proposals(proposals, next_offset))
            self.action_row.addWidget(more)
        cancel = dialog_button('取消待确认操作')
        cancel.clicked.connect(lambda: self.confirm_operation('cancel'))
        self.action_row.addWidget(cancel)
        self.render()

    def confirm_operation(self, action_id):
        if not self.send.isEnabled() or (action_id != 'cancel' and action_id not in self.proposals):
            return
        label = '取消待确认操作' if action_id == 'cancel' else self.proposals[action_id]['label']
        self.request_id = uuid4().hex
        self.pending_text = label
        self.transcript.append(dict(user=label, assistant='正在处理确认…'))
        self.transcript = self.transcript[-20:]
        self.clear_actions()
        self.set_busy(True)
        self.render()
        self.write_busy = True
        self.operation_requested.emit(action_id, self.request_id)

    def reject(self):
        if self.write_busy:
            return  # Wait for a write receipt instead of hiding an in-flight write.
        super().reject()

    def closeEvent(self, event):
        if self.write_busy:
            event.ignore()
        else:
            super().closeEvent(event)

    def show_error(self, request_id, text):
        if request_id != self.request_id:
            return
        self.clear_actions()
        self.set_busy(False)
        if self.transcript:
            self.transcript[-1]['assistant'] = '本轮未完成：' + text
            self.transcript[-1]['local_text'] = ''
        self.mode_label.setText('本轮失败 · 可以重试')
        self.render()
