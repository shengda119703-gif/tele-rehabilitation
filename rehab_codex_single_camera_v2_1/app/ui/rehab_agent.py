"""Small native assistant surface; navigation stays in MainWindow."""
import copy
import html
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                              QPushButton, QTextBrowser, QFormLayout, QCheckBox)

from ..agent_conversation import ModelConfig


class ModelSettingsDialog(QDialog):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = None
        self.setWindowTitle('连接原安康使用的 MiniMax')
        self.resize(580, 390)
        box = QVBoxLayout(self)
        note = QLabel('填写原安康使用的配置。密钥仅保留在本次软件运行的内存中，不写入文件。\n'
                      '模型会收到你主动发送的文字和最近 6 轮可分享对话；本地康复数据库内容不会发送。')
        note.setWordWrap(True)
        box.addWidget(note)
        form = QFormLayout()
        self.endpoint = QLineEdit(config.base_url if config else 'https://api.minimax.cn/v1')
        self.model = QLineEdit(config.model if config else 'MiniMax-M3')
        self.key = QLineEdit(config.api_key if config else '')
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('在这里粘贴 API Key，不要发在聊天中')
        form.addRow('服务根地址', self.endpoint)
        form.addRow('模型名称', self.model)
        form.addRow('API Key', self.key)
        box.addLayout(form)
        self.consent = QCheckBox('我同意向上述服务发送主动输入的文字和最近对话（可能产生 API 费用）')
        box.addWidget(self.consent)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        box.addWidget(self.error)
        row = QHBoxLayout()
        apply = QPushButton('启用配置')
        apply.clicked.connect(self.save)
        cancel = QPushButton('取消')
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

    def __init__(self, scope, parent=None, config=None):
        super().__init__(parent)
        self.scope = copy.deepcopy(scope)
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
        note = QLabel('对话只在当前窗口保留。连接模型后会发送文字和最近对话；康复记录留在本机。')
        note.setWordWrap(True)
        box.addWidget(note)
        status_row = QHBoxLayout()
        self.mode_label = QLabel('MiniMax 已配置 · 尚未验证连接' if config else '未连接 MiniMax · 当前仅支持本地有限回答')
        self.mode_label.setWordWrap(True)
        status_row.addWidget(self.mode_label, 1)
        self.settings_button = QPushButton('连接 MiniMax')
        self.settings_button.clicked.connect(self.configure)
        status_row.addWidget(self.settings_button)
        self.clear_button = QPushButton('清空对话')
        self.clear_button.clicked.connect(self.clear_conversation)
        status_row.addWidget(self.clear_button)
        self.disconnect_button = QPushButton('断开模型')
        self.disconnect_button.clicked.connect(self.disconnect)
        status_row.addWidget(self.disconnect_button)
        box.addLayout(status_row)
        self.browser = QTextBrowser()
        self.browser.setPlainText('连接 MiniMax 后可以自由聊天和连续追问。已有康复记录始终由本地规则核对。')
        box.addWidget(self.browser, 1)
        self.quick = []
        row = QHBoxLayout()
        for text in ('今天该练什么', '我的评估结果', '查看历史记录'):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, q=text: self.ask(q))
            self.quick.append(button)
            row.addWidget(button)
        box.addLayout(row)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setMaxLength(500)
        self.input.setPlaceholderText('例如：为什么这样安排？')
        self.input.setAccessibleName('给康复管家的问题')
        self.input.returnPressed.connect(lambda: self.ask(self.input.text()))
        row.addWidget(self.input, 1)
        self.send = QPushButton('询问')
        self.send.clicked.connect(lambda: self.ask(self.input.text()))
        row.addWidget(self.send)
        box.addLayout(row)
        self.action_row = QHBoxLayout()
        box.addLayout(self.action_row)
        close = QPushButton('返回原页面')
        close.clicked.connect(self.reject)
        box.addWidget(close)

    def clear_actions(self):
        self.allowed_actions.clear()
        while self.action_row.count():
            widget = self.action_row.takeAt(0).widget()
            widget.setEnabled(False)
            widget.deleteLater()

    def set_busy(self, busy):
        for widget in [self.send, self.input, self.settings_button, self.clear_button,
                       self.disconnect_button, *self.quick]:
            widget.setEnabled(not busy)

    def configure(self):
        dialog = ModelSettingsDialog(self.model_config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.model_config = dialog.config
            self.clear_conversation()
            self.mode_label.setText('MiniMax 已配置 · 发送一句话验证连接')
        dialog.deleteLater()

    def disconnect(self):
        self.model_config = None
        self.clear_conversation()
        self.mode_label.setText('已断开 MiniMax · 当前仅支持本地有限回答')

    def clear_conversation(self):
        self.history.clear()
        self.transcript.clear()
        self.request_id = None
        self.clear_actions()
        self.browser.setPlainText('已清空对话。你想聊什么？')

    def render(self):
        parts = []
        for turn in self.transcript[-20:]:
            parts.append('<p><b>你</b><br>' + html.escape(turn['user']).replace('\n', '<br>') + '</p>')
            if turn.get('assistant'):
                parts.append('<p><b>康复管家</b><br>' + html.escape(turn['assistant']).replace('\n', '<br>') + '</p>')
            if turn.get('local_text'):
                parts.append('<p><b>本机记录与规则核对</b><br>' + html.escape(turn['local_text']).replace('\n', '<br>') + '</p>')
        self.browser.setHtml(''.join(parts))
        self.browser.verticalScrollBar().setValue(self.browser.verticalScrollBar().maximum())

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
        self.transcript[-1].update(assistant=result['text'], local_text=result.get('local_text', ''))
        self.history.append(dict(user=self.pending_text, assistant=result['text'],
                                 shareable=result.get('shareable', False)))
        self.history = self.history[-6:]
        self.mode_label.setText(result.get('mode_label', '本地记录查询'))
        self.render()
        for action in result['actions']:
            self.allowed_actions.add(action['id'])
            button = QPushButton(action['label'])
            button.clicked.connect(lambda checked=False, a=action['id']: self.navigate.emit(a))
            self.action_row.addWidget(button)

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
