"""Native training progress and optional post-session self-report."""
import copy
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
                              QProgressBar, QFormLayout, QSpinBox, QComboBox, QPlainTextEdit, QCheckBox)

from ..domain import SOURCES, CONTEXTS
from ..exercises import exercise_spec
from ..training import FEEDBACK_REASONS, validate_training_feedback
from .participants import plain_label
from .widgets import NoticeLabel


STAGES = {'ACTIVE': '本组训练', 'RECOVERY': '本组次数完成', 'RESTING': '组间休息',
          'PAUSED': '训练暂停', 'COMPLETE': '计划次数已完成', 'FINISHED': '训练已结束'}


class TrainingControls(QFrame):
    control_requested = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('card')
        self.execution, self.online, self.available = {}, False, False
        self.stage_key = None
        box = QVBoxLayout(self)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(6)
        row = QHBoxLayout()
        self.label = plain_label('准备开始训练')
        row.addWidget(self.label, 1)
        self.pause = QPushButton('暂停训练')
        self.pause.setToolTip('暂停计次，摄像头仍开启。需要关闭相机时，请点击“停止采集”。')
        self.pause.clicked.connect(lambda: self.control_requested.emit('resume' if self.pause.property('resume') else 'pause', self.confirm.isChecked()))
        self.next_set = QPushButton('下一组')
        self.next_set.setObjectName('primary')
        self.next_set.clicked.connect(lambda: self.control_requested.emit('next_set', self.confirm.isChecked()))
        row.addWidget(self.pause)
        row.addWidget(self.next_set)
        box.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setAccessibleName('本组完成次数')
        self.progress.setFixedHeight(20)
        self.progress.setTextVisible(True)
        box.addWidget(self.progress)
        self.note = plain_label('', 'muted')
        box.addWidget(self.note)
        self.quality = plain_label('', 'muted')
        box.addWidget(self.quality)
        self.confirm = QCheckBox('已确认本人、测试侧与机位未变')
        self.confirm.toggled.connect(lambda: self.set_execution(self.execution, self.online, self.available))
        box.addWidget(self.confirm)
        self.set_execution({}, False, False)

    def set_execution(self, training, online, available):
        self.execution, self.online, self.available = training, online, available
        stage = training.get('stage')
        key = (stage, training.get('set_number'), online)
        if self.stage_key != key:
            self.stage_key = key
            self.confirm.blockSignals(True)
            self.confirm.setChecked(False)
            self.confirm.blockSignals(False)
        self.confirm.setVisible(stage in ('PAUSED', 'RESTING'))
        self.confirm.setEnabled(online and available)
        self.label.setText(((training.get('exercise_label', '')+' · '+('左侧' if training.get('side') == 'left' else '右侧')+'\n'
                            if training.get('exercise_label') else '')+
                           f"第 {training['set_number']} / {training['target_sets']} 组 · "+STAGES.get(stage, '')
                            if training else '准备开始训练'))
        self.progress.setRange(0, max(1, training.get('target_reps', 1)))
        self.progress.setValue(training.get('set_reps', 0))
        self.progress.setFormat('%v / %m 次')
        self.progress.setVisible(bool(training))
        quality = training.get('observed_quality') or {}
        self.quality.setVisible(bool(quality))
        self.quality.setText(f"已观察目标达成 {quality.get('observed_goals_met', 0)} 次 · "
                             f"需调整 {quality.get('needs_adjustment', 0)} 次 · "
                             f"未能核实 {quality.get('unassessable', 0)} 次（仅限已设置目标）")
        resume = stage == 'PAUSED'
        self.pause.setProperty('resume', resume)
        self.pause.setText('继续训练' if resume else '暂停训练')
        self.pause.setEnabled(online and available and bool(training.get('can_resume' if resume else 'can_pause'))
                              and (not resume or self.confirm.isChecked()))
        self.next_set.setVisible(stage == 'RESTING')
        self.next_set.setEnabled(online and available and bool(training.get('can_next_set')) and self.confirm.isChecked())
        remaining = training.get('rest_remaining_s')
        self.note.setText(('按计划休息，剩余 '+str(math.ceil(remaining))+' 秒。' if stage == 'RESTING' and remaining else
                           '准备好后手动进入下一组。' if stage == 'RESTING' else
                           '不计动作；摄像头仍开启，继续前请保持原机位。' if resume else
                           '本次次数已完成，可结束并保存。' if stage == 'COMPLETE' else
                           '达到站位已计次；回坐另行观察，也可直接结束。' if stage == 'RECOVERY' else
                           training.get('guidance') or '继续时重新等待准备姿势；不适时可随时结束。'))


class TrainingFeedbackDialog(QDialog):
    save_requested = Signal(str, dict, int)

    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.snapshot = copy.deepcopy(snapshot)
        self.pending = False
        self.setWindowTitle('训练结束')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(580, 590)
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(plain_label('本次训练已保存', 'sectionTitle'))
        summary = snapshot.get('summary') or {}
        spec = exercise_spec(snapshot.get('exercise_id') or snapshot['config_snapshot']['plan']['exercise_id'])
        layout.addWidget(plain_label(spec['label']+' · '+('左侧' if snapshot.get('side') == 'left' else '右侧' if snapshot.get('side') == 'right' else '侧别未记录')))
        person = snapshot.get('participant_snapshot') or {}
        layout.addWidget(plain_label('用户：'+person.get('display_name', snapshot.get('participant_id', '未记录')),
                                    'muted'))
        layout.addWidget(plain_label(SOURCES.get(snapshot.get('source_kind'), '来源未记录')+' / '+CONTEXTS.get(snapshot.get('usage_context'), '情境未记录'), 'muted'))
        groups = summary.get('training') or {}
        text = f"完成 {summary.get('completed', 0)} 次"
        if groups:
            text += f" · {summary.get('completed_sets', 0)} / {groups['target_sets']} 组"
        layout.addWidget(plain_label(text, 'sectionTitle'))
        layout.addWidget(plain_label('记录本人感受，可由家属代录；也可以暂不填写。', 'muted'))
        value = snapshot.get('training_feedback') or {}
        form = QFormLayout()
        self.scores = {}
        for key, label in [('pain', '当前疼痛'), ('fatigue', '当前疲劳')]:
            widget = QSpinBox()
            widget.setRange(-1, 10)
            widget.setSpecialValueText('未填写')
            widget.setValue(value.get(key) if value.get(key) is not None else -1)
            widget.setSuffix(' / 10')
            self.scores[key] = widget
            form.addRow(label, widget)
        self.reason = QComboBox()
        for key, label in FEEDBACK_REASONS.items():
            self.reason.addItem(label, key)
        self.reason.setCurrentIndex(self.reason.findData(value.get('reason', 'not_recorded')))
        form.addRow('结束原因', self.reason)
        layout.addLayout(form)
        layout.addWidget(plain_label('自评 0 表示没有疼痛 / 不疲劳，10 表示程度最重。不会据此自动加减训练量。', 'muted'))
        self.notes = QPlainTextEdit(value.get('notes', ''))
        self.notes.setPlaceholderText('补充说明（可选，最多 1000 字）')
        self.notes.setAccessibleName('训练感受补充说明')
        layout.addWidget(self.notes, 1)
        self.error = NoticeLabel()
        self.error.setObjectName('notice')
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.clear()
        layout.addWidget(self.error)
        row = QHBoxLayout()
        self.skip = QPushButton('暂不填写')
        self.skip.clicked.connect(self.reject)
        self.save = QPushButton('保存感受')
        self.save.setObjectName('primary')
        self.save.clicked.connect(self.submit)
        row.addStretch()
        row.addWidget(self.skip)
        row.addWidget(self.save)
        layout.addLayout(row)
        self.comfortable = QPushButton('我没有疼痛，也不疲劳 · 记录感受')
        self.comfortable.clicked.connect(self._comfortable)
        layout.addWidget(self.comfortable)

    def _comfortable(self):
        if self.pending:
            return
        for score in self.scores.values():
            score.setValue(0)
        # Do not infer task completion from comfort.
        if (self.snapshot.get('summary') or {}).get('plan_completed') is True:
            self.reason.setCurrentIndex(self.reason.findData('completed'))
        self.submit()

    def submit(self):
        if self.pending:
            return
        value = {key: widget.value() if widget.value() >= 0 else None for key, widget in self.scores.items()}
        value.update(reason=self.reason.currentData(), notes=self.notes.toPlainText())
        try:
            value = validate_training_feedback(value)
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.error.clear()
        self.save_requested.emit(self.snapshot['id'], value, (self.snapshot.get('training_feedback') or {}).get('revision', 0))

    def set_busy(self, busy):
        self.pending = bool(busy)
        for widget in (*self.scores.values(), self.reason, self.notes, self.save, self.skip, self.comfortable):
            widget.setEnabled(not busy)
        self.save.setText('正在保存…' if busy else '保存感受')

    def reject(self):
        if not self.pending:
            super().reject()

    def closeEvent(self, event):
        if self.pending:
            event.ignore()
        else:
            super().closeEvent(event)
