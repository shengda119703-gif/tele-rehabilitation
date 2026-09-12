"""Patient-facing step viewer. It consumes observations, never controls counting."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy

from ..exercise_guides import guide_steps
from ..exercise_instructions import exercise_instructions


class ExerciseGuide(QFrame):
    def __init__(self, parent=None, *, root=None, distance=False):
        super().__init__(parent)
        self.root = root
        self.distance = distance
        self.info = None
        self.identity = None
        self.steps = ()
        self.step_index = 0
        self.image_available = False
        self._pixmap = QPixmap()
        self.setObjectName('guideCard')
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 12, 12, 12)
        box.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel('动作提示')
        title.setObjectName('sectionTitle')
        top.addWidget(title)
        top.addStretch()
        self.side_label = QLabel()
        self.side_label.setObjectName('tag')
        top.addWidget(self.side_label)
        box.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.step_buttons = []
        for i, label in enumerate(('1 准备', '2 动作', '3 回位')):
            button = QPushButton(label)
            button.setObjectName('stepTab')
            button.setCheckable(True)
            button.setAccessibleName('查看' + label)
            button.clicked.connect(lambda checked=False, n=i: self.select_step(n))
            row.addWidget(button, 1)
            self.step_buttons.append(button)
        box.addLayout(row)
        self.picture = QLabel()
        self.picture.setObjectName('guidePicture')
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setWordWrap(True)
        self.picture.setMinimumWidth(0)
        if distance:
            self.picture.setMinimumHeight(140)
            self.picture.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        else:
            self.picture.setFixedHeight(128)
        self.instruction = QLabel()
        self.instruction.setObjectName('guideInstruction')
        self.instruction.setWordWrap(True)
        self.instruction.setTextFormat(Qt.TextFormat.PlainText)
        box.addWidget(self.instruction)
        box.addWidget(self.picture, 1 if distance else 0)
        controls = QHBoxLayout()
        self.previous_button = QPushButton('上一步')
        self.next_button = QPushButton('下一步')
        for button in (self.previous_button, self.next_button):
            button.setObjectName('textButton')
            controls.addWidget(button)
        self.previous_button.clicked.connect(lambda: self.select_step(self.step_index - 1))
        self.next_button.clicked.connect(lambda: self.select_step(self.step_index + 1))
        box.addLayout(controls)
        self.status = QLabel('先阅读步骤，再按已确认的安排开始。')
        self.status.setObjectName('muted')
        self.status.setWordWrap(True)
        box.addWidget(self.status)
        if distance:
            for button in (*self.step_buttons, self.previous_button, self.next_button):
                button.hide()
            self.set_distance_font(36)
        else:
            box.addStretch()

    def set_distance_font(self, pixels):
        if not self.distance:
            return
        pixels = max(32, min(48, int(pixels)))
        self.setStyleSheet(f'''
            QLabel#guideInstruction {{ font-size:{pixels}px; color:#292135; font-weight:700; }}
            QLabel#guidePicture {{ font-size:22px; }}
            QLabel#sectionTitle {{ font-size:22px; }}
            QLabel#tag, QLabel#muted {{ font-size:20px; }}
        ''')

    def set_exercise(self, exercise_id, side):
        identity = (exercise_id, side)
        if identity == self.identity:
            return
        self.steps = guide_steps(exercise_id, side, root=self.root)
        self.identity = identity
        self.side_label.setText('本人左侧' if side == 'left' else '本人右侧')
        info = exercise_instructions(exercise_id)
        self.info = info
        self.setAccessibleName(info['label'] + '动作图解')
        self.select_step(0)
        self.status.setText('仅浏览 · 尚未开始')

    def select_step(self, index):
        if not self.steps or not 0 <= index < len(self.steps):
            return
        self.step_index = index
        for i, button in enumerate(self.step_buttons):
            button.setChecked(i == index)
        self.previous_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < 2)
        step = self.steps[index]
        self.instruction.setText(self.info[step['key']] if self.distance else step['text'])
        self.picture.setAccessibleName(step['alt'])
        self.picture.setToolTip(step['alt'])
        self.image_available = False
        self._pixmap = QPixmap()
        path = step['image_path']
        message = '示意图待补充'
        try:
            if path.is_file():
                reader = QImageReader(str(path))
                size = reader.size()
                if (path.stat().st_size <= 20 * 1024 * 1024 and size.isValid()
                        and max(size.width(), size.height()) <= 4096):
                    image = reader.read()
                    if not image.isNull():
                        self._pixmap = QPixmap.fromImage(image)
                        self.image_available = True
                if not self.image_available:
                    message = '示意图无法读取，请参考文字'
        except OSError:
            message = '示意图无法读取，请参考文字'
        self.picture.clear()
        if self.image_available:
            self._fit_picture()
        else:
            self.picture.setText(message)

    def _fit_picture(self):
        if self.image_available:
            self.picture.setPixmap(self._pixmap.scaled(
                max(1, self.picture.width() - 16), max(1, self.picture.height() - 16),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_picture()

    def apply_guidance(self, guidance):
        phase = guidance.get('phase')
        index = {'REST': 0, 'WAIT_READY': 0, 'SEATED_READY': 0, 'RAISING': 1, 'RISING': 1,
                 'PEAK_OR_HOLD': 1, 'LOWERING': 2, 'ready': 0, 'outbound': 1, 'return': 2}.get(phase)
        prompt = guidance.get('prompt_label')
        if index is not None and prompt:
            # A guided prompt states what to do now; the step picture illustrates
            # that request and is never presented as an observed phase.
            if index != self.step_index or not getattr(self, '_guidance_image_active', False):
                self.select_step(index)
            self._guidance_image_active = True
            self.instruction.setText(guidance['instruction'])
            remaining = guidance.get('prompt_remaining_s')
            seconds = f" · 还有 {remaining:.0f} 秒" if isinstance(remaining, (int, float)) else ''
            self.status.setText('按提示：'+prompt+seconds)
            self.status.show()
            return
        action_cue = index is not None and guidance['measurement_valid'] and guidance['level'] == 'action'
        if action_cue:
            if index != self.step_index or not getattr(self, '_guidance_image_active', False):
                self.select_step(index)
            self._guidance_image_active = True
        else:
            self._guidance_image_active = False
            self.image_available = False
            self._pixmap = QPixmap()
            self.picture.clear()
            self.picture.setText('示意图待补充')
            for button in self.step_buttons:
                button.setChecked(False)
        self.instruction.setText(guidance['instruction'])
        self.instruction.setToolTip(guidance.get('detail', guidance['instruction']))
        if action_cue:
            self.status.setText('下一步 · ' + (guidance.get('cue_label') or self.steps[index]['title']))
            self.status.show()
        else:
            self.status.clear()
            self.status.hide()

    def follow_observation(self, state, phase, *, valid=False, training_stage=None):
        self.status.show()
        if state in ('OFFLINE', 'ERROR', 'SAVE_FAILED', 'PRIVACY_PAUSED'):
            self.status.setText('采集已中断或停止，请暂停动作。')
            return
        if state != 'ONLINE':
            self.status.setText('仅浏览 · 尚未开始')
            return
        if training_stage and training_stage not in ('ACTIVE', 'RECOVERY'):
            self.status.setText({'PAUSED': '训练已暂停，请先休息。', 'RESTING': '组间休息中，请等待确认后继续。',
                                 'COMPLETE': '本次训练已完成，请结束并保存。',
                                 'FINISHED': '训练已结束，图解仅供阅读。'}.get(training_stage, '请先完成准备确认。'))
            return
        if not valid:
            self.status.setText('画面证据不足 · 自动提示已暂停')
            return
        index = {'WAIT_READY': 0, 'REST': 1, 'SEATED_READY': 1, 'RAISING': 1,
                 'RISING': 1, 'PEAK_OR_HOLD': 1, 'STANDING_REACHED': 2, 'LOWERING': 2}.get(phase)
        if index is None:
            self.status.setText('等待明确动作阶段；图解仅供阅读。')
            return
        if index != self.step_index:
            self.select_step(index)
        self.status.setText('下一步 · ' + self.steps[index]['title'])
