"""One instruction at a time, with explicit human acknowledgement controls."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton


class JourneyPanel(QFrame):
    guided_requested = Signal(bool)
    repeat_requested = Signal()
    another_requested = Signal()
    detail_requested = Signal()
    automatic_requested = Signal()
    countdown_cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('card')
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 20, 18, 16)
        box.setSpacing(12)
        self.progress = QLabel()
        self.progress.setObjectName('muted')
        self.title = QLabel()
        self.title.setStyleSheet('font-size:24px;font-weight:600;')
        self.context = QLabel()
        self.context.setObjectName('muted')
        self.instruction = QLabel()
        self.instruction.setStyleSheet('font-size:20px;')
        self.countdown = QLabel()
        self.countdown.setObjectName('countdown')
        self.countdown.setStyleSheet('font-size:34px;font-weight:700;color:#5933ab;')
        self.countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cancel_countdown = QPushButton('先不开始')
        self.cancel_countdown.setObjectName('textButton')
        self.cancel_countdown.clicked.connect(self.countdown_cancelled)
        self.explanation = QLabel()
        self.explanation.setObjectName('muted')
        self.companion = QCheckBox('陪同者已在场')
        self.message = QLabel()
        self.message.setObjectName('notice')
        self.offer = QLabel()
        self.offer.setObjectName('muted')
        self.guided = QCheckBox('引导计时练习（不自动测角度）')
        self.guided.setToolTip('看不清或记不上起点时，仍然可以按提示完成练习并保存记录。')
        self.guided.toggled.connect(self.guided_requested)
        self.summary = QLabel()
        self.summary.setObjectName('feedback')
        self.settings = QPushButton('调整测试侧 / 机位与设置')
        self.settings.setObjectName('textButton')
        self.repeat = QPushButton('再做一次')
        self.repeat.clicked.connect(self.repeat_requested)
        for widget in (self.progress, self.title, self.context, self.instruction, self.countdown,
                       self.cancel_countdown, self.explanation, self.companion, self.message,
                       self.offer, self.guided, self.summary):
            if isinstance(widget, QLabel):
                widget.setWordWrap(True)
                widget.setTextFormat(Qt.TextFormat.PlainText)
            box.addWidget(widget)
        nexts = QHBoxLayout()
        nexts.setContentsMargins(0, 0, 0, 0)
        self.another = QPushButton('换一个动作')
        self.another.clicked.connect(self.another_requested)
        self.detail = QPushButton('查看详细数据')
        self.detail.clicked.connect(self.detail_requested)
        for button in (self.repeat, self.another, self.detail):
            nexts.addWidget(button)
        self.next_actions = QFrame()
        self.next_actions.setLayout(nexts)
        box.addWidget(self.next_actions)
        self.automatic = QPushButton('自动安排 / 继续下一项训练')
        self.automatic.setObjectName('primary')
        self.automatic.clicked.connect(self.automatic_requested)
        box.addWidget(self.automatic)
        box.addWidget(self.settings)
        box.addStretch()

    def set_countdown(self, seconds):
        running = isinstance(seconds, int) and seconds > 0
        self.countdown.setText(f'{seconds} 秒后开始…' if running else '')
        self.countdown.setVisible(running)
        self.cancel_countdown.setVisible(running)

    def render(self, step, *, context, companion, needs_companion, enabled, message='',
               offer='', guided=False, guided_available=False, summary=''):
        finished = step.key == 'result'
        hint = ('本次已完成' if finished else
                '记录中，请保持姿势' if step.action == '正在记录…' else '按下方主按钮继续')
        self.progress.setText(f'第 {step.number} / {step.total} 步 · {hint}')
        self.title.setText(step.title)
        self.context.setText(context)
        self.context.setVisible(not finished)
        self.instruction.setText(step.instruction)
        # The finished step keeps only the result and the next actions, so they
        # stay reachable in a small window.
        self.instruction.setVisible(not finished)
        for widget, checked in ((self.companion, companion), (self.guided, guided)):
            widget.blockSignals(True)
            widget.setChecked(checked)
            widget.blockSignals(False)
            widget.setEnabled(enabled)
        self.companion.setVisible(step.key == 'confirm' and needs_companion)
        self.guided.setVisible(guided_available and step.key not in ('active', 'result', 'save_failed'))
        self.explanation.setVisible(self.explanation.isVisible() and not finished)
        self.message.setText(message)
        self.message.setVisible(bool(message))
        self.offer.setText(offer)
        self.offer.setVisible(bool(offer) and not finished)
        self.summary.setText(summary)
        self.summary.setVisible(bool(summary))
        self.next_actions.setVisible(finished)
        self.automatic.setVisible(finished and guided_available and not guided)
        self.automatic.setEnabled(enabled)
        for button in (self.repeat, self.another, self.detail):
            button.setEnabled(enabled)
        self.settings.setVisible(not finished)
        self.settings.setEnabled(enabled and step.key not in ('active', 'save_failed'))
