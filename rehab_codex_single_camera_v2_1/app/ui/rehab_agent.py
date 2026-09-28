"""Small native assistant surface; navigation stays in MainWindow."""
import copy
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser


class RehabAgentDialog(QDialog):
    requested = Signal(str, str)
    navigate = Signal(str)

    def __init__(self, scope, parent=None):
        super().__init__(parent)
        self.scope = copy.deepcopy(scope)
        self.request_id = None
        self.allowed_actions = set()
        self.setWindowTitle('康复管家')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(740, 600)
        box = QVBoxLayout(self)
        title = QLabel('先问一句，再开始今天的康复')
        title.setStyleSheet('font-size:24px;font-weight:600;')
        title.setWordWrap(True)
        box.addWidget(title)
        note = QLabel('本地规则版 · 只读取当前用户和来源的保存记录 · 对话不上传、不保存')
        note.setWordWrap(True)
        box.addWidget(note)
        self.browser = QTextBrowser()
        self.browser.setPlainText('我可以帮你看评估、解释训练安排，再带你进入已有页面。')
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
        for widget in [self.send, self.input, *self.quick]:
            widget.setEnabled(not busy)

    def ask(self, text):
        if not self.send.isEnabled() or not text.strip():
            return
        self.clear_actions()
        self.request_id = uuid4().hex
        self.browser.setPlainText('正在读取当前用户的保存记录…')
        self.set_busy(True)
        self.requested.emit(text, self.request_id)

    def receive(self, request_id, result):
        if request_id != self.request_id or result['scope'] != self.scope:
            return
        self.clear_actions()
        self.set_busy(False)
        self.browser.setPlainText(result['text'])
        self.browser.append('\n读取时间：' + result['at'] + '\n操作时会再次核对最新数据。')
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
        self.browser.setPlainText('未能读取：' + text)
