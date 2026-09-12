"""Training entry screen with current preparation and a manual plan library."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton

from ..exercises import exercise_spec
from ..exercise_instructions import exercise_instructions


class TrainingHub(QWidget):
    assessment_requested = Signal()
    records_requested = Signal()
    resume_requested = Signal()
    library_requested = Signal()
    automatic_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.has_reference = False
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(18)
        current = QFrame()
        current.setObjectName('card')
        panel = QVBoxLayout(current)
        panel.setContentsMargins(24, 22, 24, 22)
        panel.setSpacing(14)
        self.automatic = QPushButton('根据评估自动安排 / 继续训练')
        self.automatic.setObjectName('primary')
        self.automatic.clicked.connect(self.automatic_requested.emit)
        panel.addWidget(self.automatic)
        self.plan_title = QLabel()
        self.plan_title.setObjectName('sectionTitle')
        self.plan_title.setWordWrap(True)
        panel.addWidget(self.plan_title)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setObjectName('muted')
        panel.addWidget(self.description)
        self.plan_details = QLabel()
        self.plan_details.setObjectName('planSummary')
        self.plan_details.setWordWrap(True)
        panel.addWidget(self.plan_details)
        self.resume = QPushButton('准备训练')
        self.resume.setObjectName('primary')
        self.resume.clicked.connect(self.resume_requested.emit)
        panel.addWidget(self.resume)
        actions = QHBoxLayout()
        self.records = QPushButton('选择评估记录')
        self.records.clicked.connect(self.records_requested.emit)
        self.assess = QPushButton('先做身体评估')
        self.assess.clicked.connect(self.assessment_requested.emit)
        actions.addWidget(self.records)
        actions.addWidget(self.assess)
        self.library = QPushButton('我的训练计划')
        self.library.clicked.connect(self.library_requested.emit)
        actions.addWidget(self.library)
        panel.addLayout(actions)
        box.addWidget(current)
        box.addStretch()
        note = QLabel('按已确认计划练习；疼痛、头晕或不适时立即停止。')
        note.setObjectName('safetyNote')
        note.setWordWrap(True)
        box.addWidget(note)
        self.set_plan({}, {})

    def set_plan(self, plan, scope):
        reference = plan.get('assessment_reference') or {}
        self.has_reference = bool(
            plan.get('submode') == 'training' and reference.get('status') == 'ASSESSED'
            and reference.get('session_id')
            and all(scope.get(k) is not None and reference.get(k) == scope[k]
                    for k in ('participant_id', 'source_kind', 'usage_context'))
            and plan.get('participant_id') == scope.get('participant_id')
            and reference.get('exercise_id') == plan.get('exercise_id')
            and reference.get('side') == plan.get('side'))
        self.resume.setVisible(self.has_reference)
        self.plan_details.setVisible(self.has_reference)
        self.records.setObjectName('textButton' if self.has_reference else 'primary')
        self.records.style().unpolish(self.records)
        self.records.style().polish(self.records)
        if not self.has_reference:
            self.plan_title.setText('还没有选择训练动作')
            self.description.setText('点击上方自动安排，系统会读取评估并生成练习顺序，无需填写次数与组数。也可选择专业人员的人工安排。')
            self.plan_details.clear()
            return
        spec = exercise_spec(plan['exercise_id'])
        info = exercise_instructions(plan['exercise_id'])
        side = '本人左侧' if plan['side'] == 'left' else '本人右侧'
        self.plan_title.setText(spec['label'] + ' · ' + side)
        self.description.setText(info['move'])
        rest = plan.get('rest_between_sets_s')
        rest_label = '休息时间未指定' if rest is None else f'组间休息 {rest:g} 秒'
        confirmed = '已确认' if plan.get('training_plan_confirmed') else '待确认'
        self.plan_details.setText(f"{plan.get('target_reps', '—')} 次 × {plan.get('target_sets', '—')} 组\n"
                                  f"{rest_label} · 计划{confirmed}")
