from __future__ import annotations

import copy
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import queue
import time
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QGridLayout, QFormLayout, QLabel, QPushButton, QComboBox, QLineEdit, QCheckBox,
    QDoubleSpinBox, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QMessageBox, QDialog,
    QInputDialog, QTextBrowser)

from ..domain import SCENES, EXERCISES, SOURCES, CONTEXTS, digest, dumps
from ..longitudinal import compare_conditions, CONDITION_LABELS
from ..settings import ROOT, default_setup, default_plan
from ..exercises import exercise_spec
from ..exercise_instructions import exercise_instructions
from ..journey import (JourneyStep, current_step, current_scene_step, preparation_steps, SCENE_ROIS)
from ..guided import GUIDED_NOTE
from ..assessment import build_training_reference
from ..participants import legacy_participant, new_participant
from ..camera_selection import choose_camera
from ..dual_camera import checked_devices, make_dual_source, VIEWS
from ..runtime import Runtime
from .dialogs import PlanDialog, ReportDialog, EventsDialog
from .widgets import ROI_LABELS, Disclosure, NoticeLabel

from .theme import STYLE
from .workspace import build_workspace
from .participants import ParticipantDialog, ParticipantSummary
from .training import TrainingFeedbackDialog, STAGES as TRAINING_STAGES
from .assessment_batches import AssessmentBatchDialog
from .camera_test import CameraTestDialog
from .distance_coach import DistanceCoach
from .plan_library import PlanLibraryDialog
from .automatic_plans import AutomaticPlanDialog
from .longitudinal import LongitudinalDialog

STATUS = {'UNSELECTED': '相机未打开', 'CONNECTING': '正在连接', 'PREVIEW': '预览中',
          'ONLINE': '记录中', 'OFFLINE': '输入已断开', 'PRIVACY_PAUSED': '采集已停止',
          'ERROR': '输入异常', 'SAVE_FAILED': '报告待保存'}
PHASES = {'WAIT_READY': '等待准备', 'REST': '准备姿势', 'RAISING': '动作出程',
          'PEAK_OR_HOLD': '幅度观察 / 保持', 'LOWERING': '正在回位', 'SEATED_READY': '坐位准备',
          'RISING': '正在起立', 'STANDING_REACHED': '已达到站位', 'UNKNOWN': '无法判断',
          'SEATED': '可见坐位', 'STANDING': '可见站位', 'WALKING': '可见步行', 'VISIBLE_MOVING': '可见移动',
          'GUIDED': '引导计时', 'VISIBLE_IN_BED': '可见床区姿态', 'BED_EDGE_SIT': '可见床边坐位',
          'BED_EDGE_STAND': '可见床边站立', 'OBSERVED_EXIT': '已观察经过出口',
          'LOW_CANDIDATE': '疑似异常低位 · 待确认', 'LOW_EVENT': '持续低位事件', 'OBSERVING': '观察中'}


def combo(items):
    widget = QComboBox()
    for key, title in items.items():
        widget.addItem(title, key)
    return widget


def card():
    frame = QFrame()
    frame.setObjectName('card')
    return frame


class MainWindow(QMainWindow):
    def __init__(self, runtime=None, data_dir=None):
        super().__init__()
        self.setWindowTitle('康复助手')
        self.resize(1360, 900)
        self.setMinimumSize(1100, 730)
        self.setStyleSheet(STYLE)
        self.runtime = runtime or Runtime(data_dir)
        self.scene = 'rehab'
        self.setup = default_setup()
        self.participant_id = self.setup['plan']['participant_id']
        self.participant_records = {self.participant_id: legacy_participant(self.participant_id)}
        self.participant_dialog = None
        self._participant_to_activate = None
        self.body_profile = None
        self._summarize_after_save = None
        self._feedback_after_save = None
        self.feedback_dialog = None
        self.batch_dialog = None
        self.plan_library_dialog = None
        self.longitudinal_dialog = None
        self._plan_to_activate = None
        self.automatic_dialog = None
        self._automatic_to_activate = None
        self._demo_scope_to_activate = None
        self._training_execution = {}
        self._journey_framed = False
        self._journey_error = ''
        self._latest_report_id = None
        self._latest_snapshot = None
        self._guided = False
        self._preparation_failed = False
        self._framing_valid_since = None
        self._self_reported = 0
        self._start_countdown = 0
        self._guided_paused = False
        self._preparation_reuse_shown = None
        self._result_after_feedback = None
        self.silver_dialog = None
        self.family_demo_dialog = None
        self._silver_return_device = None
        self.state = 'UNSELECTED'
        self.busy = 0
        self.pending_commands = Counter()
        self.constructing = True
        self._allow_close = False
        self._closing = False
        self.sessions = []
        self.report_windows = []
        self.events_dialog = None
        self.last_generation = -1
        self._accept_context_frames = True
        self._preferred_camera = None
        self._preferred_camera_pair = None
        self._preferred_secondary_camera = None
        self._last_devices = []
        self._allow_single_camera = True
        self._camera_selection_touched = False
        self._camera_notice_text = ''
        self._camera_testing = False
        self.camera_test_dialog = None
        self.distance_coach = None
        self._last_coach_view = None
        self._live_mirror, self._replay_mirror = True, False
        self._build()
        self.catalog.checklist_requested.connect(self._open_assessment_batch)
        self.constructing = False
        self._sync_scene()
        self._show_catalog(initial=True)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(30)
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._tick_start_countdown)

    def _build(self):
        build_workspace(self)

    def _show_silver(self, *, refresh=True):
        if self.silver_dialog is None:
            from .silver import SilverDialog
            self.silver_dialog = SilverDialog(self)
            self.silver_dialog.operation.connect(self._silver_command)
            self.silver_dialog.navigate.connect(self._silver_navigate)
            self.silver_dialog.privacy.connect(lambda: self._send('privacy', reason='silver_privacy_pause'))
            self.silver_dialog.task.connect(lambda task: self._send('task', task=task))
            self.silver_dialog.family_demo_requested.connect(self._show_family_demo)
        self.silver_dialog.show()
        self.silver_dialog.raise_()
        if refresh:
            self.silver_dialog.refresh()

    def _silver_command(self, operation):
        # Optional page commands do not disable rehabilitation controls or stop inference.
        self.runtime.command('silver', scope=self._body_scope_key(), **operation)

    def _show_family_demo(self):
        if self.family_demo_dialog is None:
            from .family_demo import FamilyDemoDialog
            self.family_demo_dialog = FamilyDemoDialog(self)
            self.family_demo_dialog.operation.connect(lambda operation: self.runtime.command('family_demo', **operation))
        self.family_demo_dialog.show()
        self.runtime.command('family_demo', action='status')

    def _silver_help(self):
        self._show_silver(refresh=False)
        self.silver_dialog.role.blockSignals(True)
        self.silver_dialog.role.setCurrentIndex(0)
        self.silver_dialog.role.blockSignals(False)
        self.silver_dialog.request('help', '本人主动请求帮助')

    def _silver_navigate(self, scene, camera_role):
        if self.busy or self._camera_testing or self.state in ('ONLINE', 'PREVIEW', 'CONNECTING', 'SAVE_FAILED'):
            self.silver_dialog.show_error('请先停止采集并保存当前任务，再切换观察场景')
            return
        if scene == 'training':
            self.silver_dialog.close()
            self._show_training_hub()
            return
        if scene not in ('activity', 'bedroom_demo', 'safety_demo'):
            return
        device = self.secondary_device.currentData() if camera_role == 'secondary' else (self._silver_return_device or self.device.currentData())
        if self.source_kind.currentData() != 'LIVE_CAMERA' or not device:
            self.silver_dialog.show_error('请先选择实时摄像头；B 使用输入设置中已选的第二相机')
            return
        if self._silver_return_device is None:
            self._silver_return_device = self.device.currentData()
        self._select_scene(scene)
        self.device.setCurrentIndex(next((i for i in range(self.device.count()) if self.device.itemData(i) == device), 0))
        self.silver_dialog.close()
        self.notice.setText('当前只准备所选场景，另一机位未监测。请打开预览、圈定区域并确认活动许可。')

    def _idle_copy(self):
        live = self.source_kind.currentData() == 'LIVE_CAMERA'
        return {
            'SAVE_FAILED': ('报告尚未保存', '请重试保存，或先备份本次结果', '本次结果待保存，暂不能开始新任务。'),
            'OFFLINE': ('输入已断开', '检查连接后重新预览', '输入已中断。重新预览和确认后才能开始新任务。'),
            'ERROR': ('输入异常', '检查设备或视频文件后重新预览', '输入不可用，请检查提示的原因。'),
            'PRIVACY_PAUSED': ('采集已停止', '点击“打开预览”重新准备', '采集已停止，未继续记录。'),
            'CONNECTING': ('正在打开输入', '正在连接设备' if live else '正在读取视频', '正在打开输入，请稍候。'),
        }.get(self.state, ('摄像头尚未打开' if live else '视频尚未打开',
                          ('点击“打开预览”' if self.device.currentData() else '请在顶部选择摄像头') if live else '选择视频，点击“打开预览”',
                          '打开预览，按右侧步骤完成准备。'))

    def _mark_navigation(self):
        page = self.pages.currentIndex()
        training = self.scene == 'rehab' and self.submode.currentData() == 'training'
        for key, button in self.scene_buttons.items():
            button.setChecked((page == 3 and key == 'rehab') or
                              (page == 0 and key == self.scene and not (key == 'rehab' and training)))
        self.training_nav.setChecked(page == 4 or (page == 0 and training))
        self.body_nav.setChecked(page == 2)
        self.history_nav.setChecked(page == 1)

    def _show_catalog(self, checked=False, *, initial=False):
        if not initial and (self.state in ('ONLINE', 'SAVE_FAILED') or self.busy or self._camera_testing):
            self.notice.setText('请先结束并保存本次任务，再选择评估动作。')
            return
        if not initial:
            self._select_rehab('assessment')
            self._invalidate()
        self.pages.setCurrentIndex(3)
        self.title.setText('身体评估')
        self.subtitle.setText('选择部位和动作，完成后查看身体档案。')
        self.notice.clear()
        self._mark_navigation()
        self._buttons()

    def _choose_catalog_exercise(self, exercise_id):
        if self.busy or self._camera_testing or self.state in ('ONLINE', 'SAVE_FAILED'):
            self.notice.setText('请等待本次任务保存完成。')
            return
        exercise_spec(exercise_id)  # Reject unknown IDs, never select row zero.
        self.setup['plan'].pop('assessment_batch_id', None)
        self.setup['plan'].pop('assessment_entry_key', None)
        self._select_rehab('assessment')
        self.joint_group.setCurrentIndex(self.joint_group.findData('all'))
        self.exercise.setCurrentIndex(self.exercise.findData(exercise_id))
        self.pages.setCurrentIndex(0)
        self._sync_scene()
        self.setup_tabs.setCurrentIndex(2)
        self.setup_panel.verticalScrollBar().setValue(0)
        self.monitor_scroll.verticalScrollBar().setValue(0)
        self.notice.clear()

    def _show_training_hub(self):
        if self.state in ('ONLINE', 'SAVE_FAILED') or self.busy or self._camera_testing:
            self.notice.setText('请先结束并保存当前任务，再进入训练中心。')
            return
        self._invalidate()
        self.training_hub.set_plan(self.setup['plan'], self._body_scope_key())
        self.pages.setCurrentWidget(self.training_hub)
        self.title.setText('训练中心')
        self.subtitle.setText('从评估出发，按已确认的安排练习。')
        self.notice.clear()
        self._mark_navigation()
        self._buttons()

    def _resume_training_preparation(self):
        if self.state in ('ONLINE', 'SAVE_FAILED') or self.busy:
            self.notice.setText('请先结束并保存当前任务。')
            return
        self.training_hub.set_plan(self.setup['plan'], self._body_scope_key())
        if not self.training_hub.has_reference:
            self.notice.setText('当前没有可引用的评估，请重新选择记录。')
            return
        self._select_rehab('training')

    def _open_plan_library(self):
        if self.state in ('ONLINE', 'SAVE_FAILED') or self.busy or self._camera_testing:
            self.notice.setText('请先结束并保存当前任务，再打开训练计划库。')
            return
        self._invalidate()
        scope = self._body_scope_key()
        self.training_hub.set_plan(self.setup['plan'], scope)
        candidate = self.setup['plan'] if self.training_hub.has_reference else None
        dialog = PlanLibraryDialog(scope, self, candidate=candidate)
        self.plan_library_dialog = dialog
        dialog.refresh_requested.connect(lambda: self._library_command('training_plans'))
        dialog.save_requested.connect(lambda plan, revision: self._library_command(
            'save_training_plan', plan=plan, expected_revision=revision))
        dialog.archive_requested.connect(lambda pid, revision, archived: self._library_command(
            'archive_training_plan', id=pid, expected_revision=revision, archived=archived))
        dialog.training_requested.connect(lambda pid, revision, entry: self._library_command(
            'prepare_training_plan', id=pid, expected_revision=revision, entry_key=entry))
        dialog.finished.connect(lambda: setattr(self, 'plan_library_dialog', None))
        dialog.set_busy(True)
        dialog.show()
        # A preceding preview stop remains ahead of this read in the runtime queue.
        self._send('training_plans', scope=scope)

    def _open_automatic_plan(self):
        if self.state in ('ONLINE', 'SAVE_FAILED') or self.busy or self._camera_testing:
            self.notice.setText('请先结束并保存当前任务，再安排下一项训练。')
            return
        self._invalidate()
        dialog = AutomaticPlanDialog(self._body_scope_key(), self)
        self.automatic_dialog = dialog
        dialog.requested.connect(self._automatic_command)
        dialog.feedback_requested.connect(self._automatic_feedback)
        dialog.finished.connect(lambda: setattr(self, 'automatic_dialog', None))
        dialog.show()
        self._send('automatic_proposal', scope=dialog.scope)

    def _create_demo_training_plan(self):
        if self.state in ('ONLINE', 'SAVE_FAILED', 'PREVIEW', 'CONNECTING') or self.busy or self._camera_testing:
            self.notice.setText('请先结束当前采集，再生成演示计划。')
            return
        self.notice.setText('正在用合成评估数据生成临时训练计划…')
        self._send('create_demo_training_plan')

    def _activate_demo_training_plan(self, result):
        scope, participant = result['scope'], result['participant']
        self.participant_records[participant['participant_id']] = participant
        source_index = self.source_kind.findData(scope['source_kind'])
        usage_index = self.usage.findData(scope['usage_context'])
        if source_index < 0 or usage_index < 0:
            self.notice.setText('演示计划已生成，但当前界面无法切换到演示数据范围。')
            return
        self.source_kind.setCurrentIndex(source_index)
        self.usage.setCurrentIndex(usage_index)
        self._refresh_participant_controls()
        self.participant.setText(participant['participant_id'])
        self._apply_participant()
        self._show_training_hub()
        self.notice.flash('已生成临时演示计划：4 项评估自动形成 4 项基础训练。')
        self._open_automatic_plan()

    def _automatic_feedback(self, session_id):
        if self.busy or not self.automatic_dialog or self.automatic_dialog.scope != self._body_scope_key():
            return
        self.automatic_dialog.accept()
        self._send('training_review', id=session_id)

    def _automatic_command(self, name, kwargs):
        dialog = self.automatic_dialog
        if not dialog:
            return
        if self.busy or dialog.scope != self._body_scope_key():
            dialog.set_busy(False)
            dialog.error.setText('当前任务或用户已变化，请关闭后重新打开自动安排。')
            return
        self._send(name, scope=dialog.scope, **kwargs)

    def _library_command(self, name, **kwargs):
        dialog = self.plan_library_dialog
        if self.busy or not dialog or dialog.scope != self._body_scope_key():
            return
        dialog.error.clear()
        dialog.set_busy(True)
        self._send(name, scope=dialog.scope, **kwargs)

    def _activate_saved_plan(self, prepared):
        if prepared['scope'] != self._body_scope_key():
            return
        plan = prepared['plan']
        self._invalidate()
        self._select_rehab('training')
        self.joint_group.setCurrentIndex(self.joint_group.findData('all'))
        self.exercise.setCurrentIndex(self.exercise.findData(plan['exercise_id']))
        self.side.setCurrentIndex(self.side.findData(plan['side']))
        self.setup['plan'] = copy.deepcopy(plan)
        self.setup.update(participant_confirmed=False, companion_confirmed=False,
                          setup_confirmed_at=None, profile_id='')
        self.setup.pop('profile_version', None)
        self._sync_scene()
        self.setup_tabs.setCurrentIndex(2)
        reference = plan['saved_plan_reference']
        self.notice.setText('次数和组数已自动安排。按步骤摆好机位，准备好后开始；不必填写计划。'
                            if reference.get('record_origin') == 'assessment_rules' else
                            f"已载入计划第 {reference['revision']} 版的所选项目。请核对并确认本次计划，再预览和确认机位。")

    def _source_card(self, parent):
        frame = card()
        grid = QGridLayout(frame)
        grid.setContentsMargins(14, 10, 14, 10)
        self.source_kind = combo({'LIVE_CAMERA': '实时摄像头', 'REPLAY_FILE': '本地录像回放',
                                  'SYNTHETIC': '自动计划演示（合成）'})
        self.source_kind.currentIndexChanged.connect(self._source_changed)
        self.backend = combo({700: 'DSHOW', 1400: 'MSMF'})
        self.backend.currentIndexChanged.connect(self._backend_changed)
        self.device = QComboBox()
        self.device.addItem('选择摄像头', None)
        self.device.currentIndexChanged.connect(self._device_changed)
        self.refresh = QPushButton('刷新')
        self.refresh.clicked.connect(lambda: self._send('enumerate', backend=self.backend.currentData()))
        self.usage = combo({'SELF_USE': '自主使用', 'CONTROLLED_DEMO': '受控演示', 'TEST': '软件测试'})
        self.usage.currentIndexChanged.connect(self._usage_changed)
        grid.addWidget(QLabel('输入'), 0, 0)
        grid.addWidget(self.source_kind, 0, 1)
        grid.addWidget(self.device, 0, 2)
        grid.addWidget(self.refresh, 0, 3)
        self.camera_test_button = QPushButton('打开摄像头并测试')
        self.camera_test_button.setObjectName('primary')
        self.camera_test_button.clicked.connect(self._start_camera_test)
        grid.addWidget(self.camera_test_button, 0, 4)
        grid.setColumnStretch(2, 1)
        self.dual_row = QWidget()
        dual = QHBoxLayout(self.dual_row)
        dual.setContentsMargins(0, 0, 0, 0)
        self.dual_toggle = QCheckBox('双摄：正面＋侧面')
        self.dual_toggle.toggled.connect(self._dual_changed)
        dual.addWidget(self.dual_toggle)
        self.dual_controls = QWidget()
        roles = QHBoxLayout(self.dual_controls)
        roles.setContentsMargins(12, 0, 0, 0)
        roles.addWidget(QLabel('上方为正面 · 侧面相机'))
        self.secondary_device = QComboBox()
        self.secondary_device.addItem('请选择侧面摄像头', None)
        self.secondary_device.setAccessibleName('侧面摄像头')
        self.secondary_device.currentIndexChanged.connect(self._secondary_device_changed)
        roles.addWidget(self.secondary_device, 1)
        self.dual_role_hint = QLabel()
        self.dual_role_hint.setObjectName('muted')
        roles.addWidget(self.dual_role_hint)
        dual.addWidget(self.dual_controls, 1)
        grid.addWidget(self.dual_row, 1, 0, 1, 6)
        self.dual_controls.hide()
        self.source_options = Disclosure('输入设置')
        advanced = QHBoxLayout()
        advanced.addWidget(QLabel('相机接口'))
        advanced.addWidget(self.backend)
        advanced.addSpacing(12)
        advanced.addWidget(QLabel('使用情境'))
        advanced.addWidget(self.usage)
        advanced.addStretch()
        self.source_options.box.addLayout(advanced)
        # The header sits beside the device; optional fields occupy another row.
        grid.addWidget(self.source_options.toggle, 0, 5)
        grid.addWidget(self.source_options.content, 2, 0, 1, 6)
        self.source_options.setParent(frame)
        self.source_options.hide()
        self.replay_row = QWidget()
        replay = QHBoxLayout(self.replay_row)
        replay.setContentsMargins(0, 0, 0, 0)
        self.file = QLineEdit()
        self.file.setPlaceholderText('选择本地视频文件')
        self.file.setReadOnly(True)
        browse = QPushButton('选择视频')
        browse.clicked.connect(self._browse)
        self.speed = combo({.5: '0.5× 播放', 1.: '1× 播放', 2.: '2× 播放'})
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(self._invalidate)
        self.seek = QDoubleSpinBox()
        self.seek.setRange(0, 86400)
        self.seek.setSuffix(' 秒起播')
        self.seek.valueChanged.connect(self._invalidate)
        self.preview_segment_button = QPushButton('预览 1.2 秒片段')
        self.preview_segment_button.clicked.connect(lambda: self._send('preview_segment'))
        replay.addWidget(self.file, 1)
        replay.addWidget(browse)
        replay.addWidget(self.speed)
        replay.addWidget(self.seek)
        replay.addWidget(self.preview_segment_button)
        grid.addWidget(self.replay_row, 1, 0, 1, 5)
        self.replay_row.setVisible(False)
        parent.addWidget(frame)

    def _setup_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = card()
        box = QVBoxLayout(panel)
        box.setContentsMargins(16, 14, 16, 16)
        box.setSpacing(10)
        self.rehab_controls = QWidget()
        form = QFormLayout(self.rehab_controls)
        form.setContentsMargins(0, 0, 0, 0)
        self.exercise = combo(EXERCISES)
        self.exercise.setMaxVisibleItems(12)
        self.exercise.setToolTip('先选动作；标记为实验性的项目仅提供二维观察，具体限制见说明。')
        self.joint_group = combo({'all': '全部部位', 'shoulder': '肩', 'elbow': '肘', 'hip': '髋',
                                  'knee': '膝 / 坐站', 'wrist': '腕', 'ankle': '踝', 'finger': '手指',
                                  'neck': '头颈', 'trunk': '躯干'})
        self.joint_group.currentIndexChanged.connect(self._filter_exercises)
        self.exercise.currentIndexChanged.connect(self._exercise_changed)
        self.submode = combo({'assessment': '评估', 'training': '训练'})
        self.submode.setParent(self.rehab_controls)
        self.submode.hide()  # Distinct sidebar sections now own this value.
        self.side = combo({'left': '左侧（本人左侧）', 'right': '右侧（本人右侧）'})
        self.side.currentIndexChanged.connect(self._placement_changed)
        # Selection now belongs to the catalog. Keep the existing selectors as
        # the single action state so runtime switching contracts stay unchanged.
        self.joint_group.setParent(self.rehab_controls)
        self.joint_group.hide()
        self.exercise.setParent(self.rehab_controls)
        self.exercise.hide()
        form.addRow('测试侧', self.side)
        box.addWidget(self.rehab_controls)
        self.view = combo({'frontal': '正面机位', 'sagittal': '侧面机位', 'fixed': '固定观察机位'})
        self.view.currentIndexChanged.connect(self._placement_changed)
        box.addWidget(self.view)
        self.camera_instruction = QLabel()
        self.camera_instruction.setWordWrap(True)
        self.camera_instruction.setObjectName('muted')
        box.addWidget(self.camera_instruction)
        self.movement_details = Disclosure('完整文字步骤', expanded=False)
        self.movement_steps = QLabel()
        self.movement_steps.setWordWrap(True)
        self.movement_details.box.addWidget(self.movement_steps)
        self.measurement_details = Disclosure('测量说明')
        self.action_guide = QLabel()
        self.action_guide.setWordWrap(True)
        self.action_guide.setObjectName('muted')
        self.measurement_details.box.addWidget(self.action_guide)
        self.reference_text = QLabel()
        self.reference_text.setWordWrap(True)
        self.reference_text.setObjectName('feedback')
        box.addWidget(self.reference_text)
        self.reference_button = QPushButton('选择评估记录')
        self.reference_button.clicked.connect(self._show_body)
        box.addWidget(self.reference_button)
        self.plan_text = QLabel()
        self.plan_text.setWordWrap(True)
        box.addWidget(self.plan_text)
        self.plan_button = QPushButton('设置个人目标与计划')
        self.plan_button.setObjectName('primary')
        self.plan_button.clicked.connect(self._plan)
        box.addWidget(self.plan_button)
        self.personal_reminders = QLabel()
        self.personal_reminders.setTextFormat(Qt.TextFormat.PlainText)
        self.personal_reminders.setWordWrap(True)
        self.personal_reminders.setObjectName('safetyNote')
        box.addWidget(self.personal_reminders)
        self.baselines = QWidget()
        baselinebox = QVBoxLayout(self.baselines)
        baselinebox.setContentsMargins(0, 0, 0, 0)
        baselinebox.addWidget(QLabel('记录起点'))
        self.sit_baseline_buttons = []
        for label, position in (('倒计时记录当前坐位', 'seated'), ('倒计时记录当前站位', 'standing')):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, p=position: self._start_preparation('baseline', p))
            self.sit_baseline_buttons.append(button)
            baselinebox.addWidget(button)
        self.baseline_text = QLabel('坐位：未记录  /  站位：未记录')
        self.baseline_text.setWordWrap(True)
        baselinebox.addWidget(self.baseline_text)
        box.addWidget(self.baselines)
        self.joint_baselines = QWidget()
        jointbox = QVBoxLayout(self.joint_baselines)
        jointbox.setContentsMargins(0, 0, 0, 0)
        self.joint_rest_button = QPushButton('记录舒适起始姿势')
        self.joint_rest_button.clicked.connect(lambda: self._record_joint_baseline('rest'))
        self.joint_direction_button = QPushButton('记录活动方向')
        self.joint_direction_button.clicked.connect(lambda: self._record_joint_baseline('direction'))
        self.joint_baseline_text = QLabel()
        self.joint_baseline_text.setWordWrap(True)
        for widget in (self.joint_rest_button, self.joint_direction_button, self.joint_baseline_text):
            jointbox.addWidget(widget)
        box.addWidget(self.joint_baselines)
        self.optional_baseline = Disclosure('起点记录（可选）')
        box.addWidget(self.optional_baseline)
        self.preparation_active = False
        self.preparation_status = NoticeLabel()
        self.preparation_status.setWordWrap(True)
        box.addWidget(self.preparation_status)
        self.preparation_cancel = QPushButton('取消本次采样')
        self.preparation_cancel.clicked.connect(lambda: self._send('cancel_preparation'))
        box.addWidget(self.preparation_cancel)
        self.preparation_retry = QPushButton('重试采样')
        self.preparation_retry.clicked.connect(self._retry_preparation)
        box.addWidget(self.preparation_retry)
        self.preparation_cancel.hide()
        self.preparation_retry.hide()
        self.region_controls = QWidget()
        region = QVBoxLayout(self.region_controls)
        region.setContentsMargins(0, 0, 0, 0)
        region.addWidget(QLabel('圈定本场景区域'))
        self.roi_select = combo({'': '选择区域后在预览上拖动', **ROI_LABELS})
        self.roi_select.currentIndexChanged.connect(lambda: self._edit_region())
        region.addWidget(self.roi_select)
        self.roi_info = QLabel('尚未圈区')
        self.roi_info.setWordWrap(True)
        region.addWidget(self.roi_info)
        clear = QPushButton('重新圈区')
        clear.clicked.connect(self._clear_regions)
        region.addWidget(clear)
        box.addWidget(self.region_controls)
        self.activity_controls = QWidget()
        activity = QVBoxLayout(self.activity_controls)
        activity.setContentsMargins(0, 0, 0, 0)
        self.demo = QCheckBox('使用演示阈值：坐位 15 秒提醒')
        self.demo.toggled.connect(self._invalidate)
        activity.addWidget(self.demo)
        self.permission = QCheckBox('已确认本次站立 / 步行活动许可')
        self.permission.toggled.connect(self._confirmation_changed)
        activity.addWidget(self.permission)
        self.activity_options = QComboBox()
        for label, kinds in (('允许站立和步行', ['stand', 'walk']), ('仅允许站立', ['stand']),
                             ('仅允许步行', ['walk']), ('暂不安排活动任务', [])):
            self.activity_options.addItem(label, kinds)
        self.activity_options.currentIndexChanged.connect(self._invalidate)
        activity.addWidget(self.activity_options)
        timing = QFormLayout()
        self.activity_durations = {}
        for key, label in (('sedentary_trigger_s', '坐位提醒（秒）'), ('stand_target_s', '站立目标（秒）'), ('walk_target_s', '步行目标（秒）')):
            spin = QDoubleSpinBox()
            spin.setDecimals(0)
            spin.setRange(1, 14400)
            spin.setValue(self.setup[key])
            spin.valueChanged.connect(self._invalidate)
            self.activity_durations[key] = spin
            timing.addRow(label, spin)
        activity.addLayout(timing)
        activity_note = QLabel('按本人适合的安排人工填写，不是统一运动处方。演示时使用 15 / 5 / 8 秒并永久标记。')
        activity_note.setWordWrap(True)
        activity.addWidget(activity_note)
        self.task_buttons = []
        for label, task in (('选择站立任务', 'stand'), ('选择步行任务', 'walk'), ('延期本次提醒', 'snooze'), ('拒绝本次提醒', 'skip'), ('停止活动任务', 'stop'), ('仅自报已完成', 'self_report')):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, t=task: self._send('task', task=t))
            activity.addWidget(button)
            self.task_buttons.append(button)
        box.addWidget(self.activity_controls)
        self.bed_controls = QWidget()
        bed = QVBoxLayout(self.bed_controls)
        bed.setContentsMargins(0, 0, 0, 0)
        self.real_bed = QCheckBox('本次画面是真实床区')
        self.assistance = QCheckBox('已人工配置需要协助')
        self.night = QCheckBox('本次按夜间情境演示')
        for w in (self.real_bed, self.assistance, self.night):
            bed.addWidget(w)
            w.toggled.connect(self._invalidate)
        box.addWidget(self.bed_controls)
        self.mirror = QCheckBox('镜像预览')
        self.mirror.setToolTip('只改变显示方向，左侧和右侧始终指本人左右。')
        self.mirror.setChecked(self._live_mirror)
        self.canvas.mirror = self._live_mirror
        self.mirror.toggled.connect(self._mirror_changed)
        self.guided_toggle = QCheckBox('引导计时练习（不自动测角度）')
        self.guided_toggle.setToolTip('看不清或记不上起点时，仍然可以按固定节奏完成练习并保存记录。')
        box.addWidget(self.guided_toggle)
        self.guided_note = QLabel(GUIDED_NOTE)
        self.guided_note.setWordWrap(True)
        self.guided_note.setObjectName('muted')
        box.addWidget(self.guided_note)
        self.manual = QCheckBox('已看过画面与安全提示')
        self.manual.setObjectName('manualConfirmation')
        self.manual.toggled.connect(self._confirmation_changed)
        box.addWidget(self.manual)
        self.preparation_review = QLabel()
        self.preparation_review.setWordWrap(True)
        box.addWidget(self.preparation_review)
        self.companion = QCheckBox('陪同者已在场')
        self.companion.toggled.connect(self._confirmation_changed)
        box.addWidget(self.companion)
        self.poses = QCheckBox('保存本次骨架调试数据')
        self.poses.setToolTip('只影响本次会话。未勾选时只保存指标报告。')
        self.poses.toggled.connect(self._confirmation_changed)
        note = QLabel('疼痛、头晕或不适时，请立即停止。')
        note.setObjectName('safetyNote')
        note.setWordWrap(True)
        box.addWidget(note)
        box.addWidget(self.measurement_details)
        self.more_setup = Disclosure('更多设置')
        self.more_setup.box.addWidget(self.mirror)
        self.more_setup.box.addWidget(self.poses)
        saving_note = QLabel('未选择时仅保存指标报告。默认不录制视频和截图。')
        saving_note.setObjectName('muted')
        saving_note.setWordWrap(True)
        self.more_setup.box.addWidget(saving_note)
        load = QPushButton('载入已保存机位')
        load.clicked.connect(lambda: self._send('profile'))
        self.more_setup.box.addWidget(load)
        self.more_setup.box.addWidget(self.movement_details)
        box.addWidget(self.more_setup)
        box.addStretch()
        scroll.setWidget(panel)
        return scroll

    def _history_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        intro = QLabel('报告保存在本机。实时、回放和受控演示分别标记；不同测量条件不直接比较。')
        intro.setWordWrap(True)
        box.addWidget(intro)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['开始时间', '任务', '来源 / 情境', '完整次数', '有效观察', '结束原因'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda: self._open_report())
        box.addWidget(self.table, 1)
        self.history_empty = QLabel('尚无历史报告。完成并保存一次任务后，记录会出现在这里。')
        self.history_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self.history_empty)
        row = QHBoxLayout()
        for title, callback in (('刷新', self._history), ('打开报告', self._open_report), ('纵向记录', self._open_longitudinal), ('导出所选报告', self._export_selected), ('比较两份报告', self._compare), ('删除所选报告', self._delete_report), ('返回任务', lambda: self._select_scene(self.scene))):
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        box.addLayout(row)
        self.pages.addWidget(page)

    def _body_page(self):
        from .body_overview import BodyOverview
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(14)
        self.personal_summary = ParticipantSummary()
        self.personal_summary.edit_requested.connect(lambda: self._edit_participant())
        self.personal_summary.set_profile(self.participant_records[self.participant_id])
        box.addWidget(self.personal_summary)
        self.body_scope = QLabel()
        self.body_scope.setObjectName('muted')
        self.body_scope.setWordWrap(True)
        box.addWidget(self.body_scope)
        self.body_overview = BodyOverview()
        self.body_overview.item_selected.connect(self._body_item_selected)
        box.addWidget(self.body_overview, 1)
        # A real full-detail view is retained for measurement conditions and
        # unsupported coverage. Daily navigation uses the native overview.
        self.body_detail_dialog = QDialog(self)
        self.body_detail_dialog.setWindowTitle('评估明细与测量条件')
        self.body_detail_dialog.resize(1050, 740)
        detail_box = QVBoxLayout(self.body_detail_dialog)
        self.body_browser = QTextBrowser()
        self.body_browser.setOpenExternalLinks(False)
        self.body_browser.setHtml('<h2>尚无评估记录</h2>')
        detail_box.addWidget(self.body_browser)
        self.body_action = QComboBox(page)
        self.body_action.hide()
        self.body_train = QPushButton('进入训练')
        self.body_train.setObjectName('primary')
        self.body_train.setEnabled(False)
        self.body_train.clicked.connect(self._train_from_body)
        actions = QHBoxLayout()
        for label, callback in (('继续评估', self._show_catalog),
                                ('本轮评估清单', self._open_assessment_batch),
                                ('查看报告', self._open_body_report),
                                ('完整明细', self.body_detail_dialog.show),
                                ('刷新', self._show_body),
                                ('导出评估', self._export_body)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch()
        actions.addWidget(self.body_train)
        box.addLayout(actions)
        self.pages.addWidget(page)

    def _body_item_selected(self, item):
        if not hasattr(self, 'body_action'):
            return
        index = -1
        if item and item.get('status') == 'ASSESSED':
            for row in range(self.body_action.count()):
                option = self.body_action.itemData(row)
                if (option['exercise_id'], option['side']) == (item['exercise_id'], item['side']):
                    index = row
                    break
        self.body_action.setCurrentIndex(index)
        self._buttons()

    def _body_scope_key(self):
        return dict(participant_id=self.participant_id, source_kind=self.source_kind.currentData(),
                    usage_context=self.usage.currentData())

    def _open_assessment_batch(self):
        if self.busy or self.state in ('ONLINE', 'SAVE_FAILED'):
            self.notice.setText('请先结束并保存当前任务，再打开评估清单。')
            return
        self._invalidate()
        dialog = AssessmentBatchDialog(self._body_scope_key(), self)
        self.batch_dialog = dialog
        dialog.create_requested.connect(lambda items: self._batch_command('create_assessment_batch', items=items))
        dialog.change_requested.connect(lambda change: self._batch_command('change_assessment_batch', **change))
        dialog.assessment_requested.connect(self._choose_batch_item)
        dialog.report_requested.connect(lambda sid: self._batch_report(sid))
        dialog.finished.connect(lambda: setattr(self, 'batch_dialog', None))
        dialog.set_busy(True)
        dialog.show()
        self._send('assessment_batch', scope=dialog.scope)

    def _batch_command(self, name, **kwargs):
        if self.busy or not self.batch_dialog:
            return
        self.batch_dialog.set_busy(True)
        self._send(name, scope=self.batch_dialog.scope, **kwargs)

    def _batch_report(self, sid):
        if self.batch_dialog:
            self.batch_dialog.accept()
        self._send('report', id=sid)

    def _choose_batch_item(self, batch, item):
        from ..assessment_batches import scope_key
        if self.busy or self.state in ('ONLINE', 'SAVE_FAILED') or scope_key(batch) != self._body_scope_key():
            return
        if self.batch_dialog:
            self.batch_dialog.accept()
        self._choose_catalog_exercise(item['exercise_id'])
        self.side.setCurrentIndex(self.side.findData(item['side']))
        self.setup['plan'].update(assessment_batch_id=batch['id'], assessment_entry_key=item['key'])
        self._sync_scene()
        self.notice.setText('已选择本轮项目。请打开预览并重新确认准备；保存后可从清单继续。')

    def _clear_training_reference(self):
        self.setup['plan'].pop('assessment_reference', None)
        self.setup['plan'].pop('saved_plan_reference', None)
        self.setup['plan']['training_plan_confirmed'] = False
        self.setup['plan'].pop('assessment_batch_id', None)
        self.setup['plan'].pop('assessment_entry_key', None)

    def _refresh_participant_controls(self):
        self.participant_records.setdefault(self.participant_id, legacy_participant(self.participant_id))
        self.participant_select.blockSignals(True)
        self.participant_select.clear()
        records = sorted(self.participant_records.values(), key=lambda p: (p['display_name'].casefold(), p['participant_id']))
        names = Counter(p['display_name'] for p in records)
        for profile in records:
            name = profile['display_name']
            label = name[:20]+('…' if len(name) > 20 else '')
            if names[name] > 1:
                label += ' · '+profile['participant_id'][-8:]
            if not profile.get('revision'):
                label += ' · 未填档案'
            self.participant_select.addItem(label, profile['participant_id'])
            self.participant_select.setItemData(self.participant_select.count()-1,
                                               name+'\n编号：'+profile['participant_id'], Qt.ItemDataRole.ToolTipRole)
        self.participant_select.setCurrentIndex(self.participant_select.findData(self.participant_id))
        self.participant_select.blockSignals(False)
        if hasattr(self, 'personal_summary'):
            self.personal_summary.set_profile(self.participant_records[self.participant_id])
        if hasattr(self, 'personal_reminders'):
            self._update_personal_reminders()

    def _update_personal_reminders(self):
        profile = self.participant_records[self.participant_id]
        messages = []
        if profile.get('restrictions'):
            messages.append('档案中有已填活动限制，请先在“个人信息”中核对。')
        if profile.get('support') in ('assisted', 'to_confirm'):
            messages.append('档案中记录了陪同需求，请确认本次安排。')
        self.personal_reminders.setText('\n'.join(messages))
        self.personal_reminders.setVisible(bool(messages) and self.scene == 'rehab')

    def _participant_selected(self):
        if self.constructing:
            return
        pid = self.participant_select.currentData()
        if pid:
            self.participant.setText(pid)
            self._apply_participant()

    def _edit_participant(self, *, new=False):
        if self.state in ('ONLINE', 'SAVE_FAILED') or self.busy:
            self.notice.setText('请先结束并保存本次任务，再编辑个人信息。')
            return
        self._invalidate()
        profile = new_participant() if new else self.participant_records.get(self.participant_id, legacy_participant(self.participant_id))
        dialog = ParticipantDialog(profile, self)
        self.participant_dialog = dialog
        dialog.save_requested.connect(self._save_participant)
        dialog.finished.connect(self._participant_editor_closed)
        dialog.set_busy(self.busy > 0)
        dialog.show()

    def _participant_editor_closed(self, result):
        self.participant_dialog = None
        # Reload revisions after an edit/cancel, including a conflict in another
        # app window. Existing unsaved form data is never silently replaced.
        if result != QDialog.DialogCode.Accepted:
            self._send('participants')

    def _save_participant(self, profile, revision):
        if self.busy or self.state in ('ONLINE', 'SAVE_FAILED'):
            return
        self.participant_dialog.set_busy(True)
        self._send('save_participant', profile=profile, expected_revision=revision)

    def _apply_participant(self):
        name = self.participant.text().strip()
        if not name:
            self.notice.setText('请输入一个匿名用户编号。')
            return
        if name == self.participant_id:
            return
        if self.state in ('ONLINE', 'SAVE_FAILED') or self.busy:
            self.participant.setText(self.participant_id)
            self._refresh_participant_controls()
            self.notice.setText('请先结束并保存当前任务，再切换用户。')
            return
        self._invalidate()
        self.participant_id = name
        self.participant.setText(name)
        self._refresh_participant_controls()
        self.setup['plan'] = default_plan(self.exercise.currentData())
        self.setup['plan'].update(participant_id=name, submode=self.submode.currentData())
        self.body_profile = None
        self.body_action.clear()
        self.body_overview.set_loading()
        self.body_browser.clear()
        self.body_detail_dialog.hide()
        self._summarize_after_save = None
        self.body_train.setEnabled(False)
        if self.pages.currentIndex() == 2:
            self._request_body()
        else:
            self._sync_scene()
        self.notice.setText('已切换用户，请重新选择评估或确认训练计划。')

    def _select_rehab(self, mode):
        if self.state == 'SAVE_FAILED' or self.busy:
            self.notice.setText('请等待当前操作完成；有待保存结果时请先处理。')
            return
        if self.submode.currentData() != mode:
            self._invalidate()
            self.submode.setCurrentIndex(self.submode.findData(mode))
            self.setup['plan'] = default_plan(self.exercise.currentData())
            self.setup['plan'].update(participant_id=self.participant_id, submode=mode)
        self._select_scene('rehab')
        self.setup_tabs.setCurrentIndex(2)
        self.movement_details.toggle.setChecked(False)
        self.notice.setText('评估：按自己的舒适幅度完成动作，不追求统一正常值。' if mode == 'assessment'
                            else '训练：请从身体档案选择评估，再确认训练计划。')

    def _finish_task(self):
        if self.scene == 'rehab' and self.submode.currentData() == 'assessment' and self.state == 'ONLINE':
            self._summarize_after_save = self._body_scope_key()
        if self.scene == 'rehab' and self.submode.currentData() == 'training' and self.state == 'ONLINE':
            self._feedback_after_save = self.participant_id
        self._send('stop', reason='user_stop')

    def _request_training_review(self, sid):
        if self.state in ('ONLINE', 'SAVE_FAILED') or self.busy:
            self.notice.setText('请先结束并保存当前任务，再填写训练感受。')
            return
        self._send('training_review', id=sid)

    def _save_training_feedback(self, sid, feedback, revision):
        if self.busy or not self.feedback_dialog:
            return
        self.feedback_dialog.set_busy(True)
        self._send('save_training_feedback', id=sid, feedback=feedback, expected_revision=revision)

    def _feedback_closed(self):
        self.feedback_dialog = None
        pending, self._result_after_feedback = self._result_after_feedback, None
        if pending and pending[1] == self._body_scope_key():
            self._send('report', id=pending[0])

    def _show_body(self):
        if self.state in ('ONLINE', 'SAVE_FAILED') or self.busy:
            self.notice.setText('请先完成并保存当前任务，再查看身体信息。')
            return
        self._invalidate()
        self.notice.clear()
        self._request_body()

    def _refresh_body_profile(self):
        """Re-summarise assessments in place, without leaving the current page."""
        self.body_profile = None
        self.body_action.clear()
        self.body_train.setEnabled(False)
        self.body_overview.set_loading()
        self._send('body_profile', **self._body_scope_key())

    def _request_body(self):
        self.pages.setCurrentIndex(2)
        self.title.setText('身体档案')
        self.subtitle.setText('查看各部位的评估记录，选择项目进入训练。')
        self.body_scope.setText(f"{SOURCES.get(self.source_kind.currentData(), '')} / {CONTEXTS.get(self.usage.currentData(), '')}　｜　其他来源与情境不合并")
        for button in self.scene_buttons.values():
            button.setChecked(False)
        self.training_nav.setChecked(False)
        self.body_nav.setChecked(True)
        self._mark_navigation()
        self.body_browser.setHtml('<h2>正在汇总本地评估记录…</h2>')
        self._refresh_body_profile()

    def _train_from_body(self):
        item = self.body_action.currentData()
        if not item or not self.body_profile or self.busy:
            return
        reference = build_training_reference(self.body_profile, item['exercise_id'], item['side'])
        if reference.get('status') != 'ASSESSED':
            self.notice.setText('该项目尚无可用评估，请先完成评估。')
            return
        self._select_rehab('training')
        self.joint_group.setCurrentIndex(self.joint_group.findData('all'))
        self.exercise.setCurrentIndex(self.exercise.findData(item['exercise_id']))
        self.side.setCurrentIndex(self.side.findData(item['side']))
        self.setup['plan'] = default_plan(item['exercise_id'])
        self.setup['plan'].update(submode='training', participant_id=self.participant_id,
                                  side=item['side'],
                                  assessment_reference=copy.deepcopy(reference), training_plan_confirmed=False)
        self._sync_scene()
        self.notice.setText('已选择评估。请确认训练计划，再打开预览。')

    def _export_body(self):
        if not self.body_profile or self.busy:
            return
        directory = QFileDialog.getExistingDirectory(self, '选择身体信息导出目录')
        if directory:
            output = Path(directory)/('body-profile-'+uuid4().hex[:12])
            self._send('export_body_profile', directory=str(output), **self._body_scope_key())

    def _open_body_report(self):
        item = self.body_overview.current_item()
        if item and item.get('session_id') and not self.busy:
            self._send('report', id=item['session_id'])

    def _send(self, name, **kw):
        if name in ('start', 'training_control'):
            self.notice.clear()
        self.busy += 1
        self.pending_commands[name] += 1
        self._buttons()
        self.runtime.command(name, **kw)

    def _invalidate(self, *args):
        if self.constructing:
            return
        self._journey_framed = False
        self._framing_valid_since = None
        self._preparation_failed = False
        self._preparation_reuse_shown = None
        self._latest_snapshot = None
        self._self_reported = 0
        self._cancel_start_countdown()
        if self.silver_dialog:
            self.silver_dialog.close()
        self._journey_error = ''
        self._latest_report_id = None
        self._close_distance_coach()
        self._result_after_feedback = None
        self._last_coach_view = None
        self.preparation_active = False
        self._last_sample_request = None
        self.preparation_status.clear()
        self.preparation_retry.hide()
        self.manual.setChecked(False)
        self._confirmed = False
        self.start_button.setEnabled(False)
        self._accept_context_frames = False
        self._training_execution = {}
        self.video_pair.clear()
        self.exercise_guide.select_step(0)
        self.exercise_guide.follow_observation('UNSELECTED', None)
        for metric_card in (self.count_card, self.angle_card, self.valid_card):
            metric_card.show_value(None)
        if self.state in ('ONLINE', 'PREVIEW', 'CONNECTING', 'ERROR'):
            self.canvas.set_frame(None)
            self._send('switch', reason='configuration_change')
        self.state = 'UNSELECTED' if self.state != 'SAVE_FAILED' else self.state
        self._buttons()

    def _source_changed(self):
        if self.constructing:
            return
        self._invalidate()
        self.setup['plan']['joint_baseline'] = {}
        self._clear_training_reference()
        live = self.source_kind.currentData() == 'LIVE_CAMERA'
        self.mirror.blockSignals(True)
        self.mirror.setChecked(self._live_mirror if live else self._replay_mirror)
        self.mirror.blockSignals(False)
        self.canvas.mirror = self.mirror.isChecked()
        self.canvas.update()
        for w in (self.device, self.refresh, self.backend):
            w.setVisible(live)
        self.replay_row.setVisible(self.source_kind.currentData() == 'REPLAY_FILE')
        self.usage.setCurrentIndex(0 if live else 2)
        self.setup['rois'] = {}
        self.setup['plan']['calibration'] = {}
        self.canvas.rois = {}
        self._sync_scene()
        self._refresh_body_scope()
        self._buttons()

    def _usage_changed(self):
        if self.constructing:
            return
        self._invalidate()
        self.setup['plan']['joint_baseline'] = {}
        self._clear_training_reference()
        self._sync_scene()
        self._refresh_body_scope()

    def _refresh_body_scope(self):
        if self.body_profile and any(self.body_profile.get(k) != v for k, v in self._body_scope_key().items()):
            self.body_profile = None
            self.body_action.clear()
            self.body_overview.set_loading()
            self.body_browser.clear()
            self.body_detail_dialog.hide()
            if self.pages.currentIndex() == 2:
                self._request_body()

    def _backend_changed(self):
        if self.constructing:
            return
        self._invalidate()
        self.setup['plan']['calibration'] = {}
        self.setup['plan']['joint_baseline'] = {}
        self.setup['rois'] = {}
        self.canvas.rois = {}
        self._camera_selection_touched = True
        self._allow_single_camera = False  # Changing backend requires explicit rebinding.
        self.device.blockSignals(True)
        self.device.clear()
        self.device.addItem('请选择摄像头', None)
        self.device.blockSignals(False)
        self.secondary_device.blockSignals(True)
        self.secondary_device.clear()
        self.secondary_device.addItem('请选择侧面摄像头', None)
        self.secondary_device.blockSignals(False)
        self._last_devices = []
        self._send('enumerate', backend=self.backend.currentData())

    def _device_changed(self):
        if self.constructing:
            return
        self._invalidate()
        self.setup['plan']['calibration'] = {}
        self.setup['plan']['joint_baseline'] = {}
        self.setup['rois'] = {}
        self.canvas.rois = {}
        self._camera_selection_touched = True
        self._allow_single_camera = False
        self._preferred_camera = self.device.currentData()
        if self._preferred_camera:
            if self._dual_enabled():
                self._remember_pair_selection()
            else:
                self.runtime.command('remember_camera', device=self._preferred_camera)
            if self.notice.text() == self._camera_notice_text:
                self.notice.clear()
        self._sync_scene()

    def _dual_enabled(self):
        return self.scene == 'rehab' and self.source_kind.currentData() == 'LIVE_CAMERA' and self.dual_toggle.isChecked()

    def _sync_dual_controls(self):
        available = self.scene == 'rehab' and self.source_kind.currentData() == 'LIVE_CAMERA'
        enabled = self._dual_enabled()
        self.dual_row.setVisible(available)
        self.dual_controls.setVisible(enabled)
        self.device.setAccessibleName('正面摄像头' if enabled else '摄像头')
        self.dual_role_hint.setText('本动作使用'+VIEWS.get(self.view.currentData(), '指定')+'机位')
        self.video_pair.configure(enabled, self.view.currentData())
        if enabled:
            self.manual.setText('已看过两路画面与安全提示')
            self.manual.setToolTip('确认按提示安排机位即可；陪同者入镜不会阻止任务。')
        self.poses.setText('保存本次两路骨架调试数据' if enabled else '保存本次骨架调试数据')

    def _dual_changed(self):
        if self.constructing:
            return
        self._invalidate()
        self.setup['plan']['calibration'] = {}
        self.setup['rois'] = {}
        self.canvas.rois = {}
        self._camera_selection_touched = True
        if self.dual_toggle.isChecked() and self._preferred_camera_pair:
            preferred = self._preferred_camera_pair
            for widget, view in ((self.device, 'frontal'), (self.secondary_device, 'sagittal')):
                selected = choose_camera(self._last_devices, preferred.get(view), allow_single=False)
                widget.blockSignals(True)
                widget.setCurrentIndex(next((i for i in range(widget.count()) if selected and widget.itemData(i) == selected), 0))
                widget.blockSignals(False)
            self._preferred_secondary_camera = preferred.get('sagittal')
        self._sync_scene()

    def _remember_pair_selection(self):
        try:
            refs = checked_devices(dict(frontal=self.device.currentData(), sagittal=self.secondary_device.currentData()))
        except ValueError:
            return
        self._preferred_camera_pair = refs
        self.runtime.command('remember_camera_pair', devices=refs)

    def _secondary_device_changed(self):
        if self.constructing:
            return
        self._invalidate()
        self.setup['plan']['calibration'] = {}
        self.setup['rois'] = {}
        self.canvas.rois = {}
        self._preferred_secondary_camera = self.secondary_device.currentData()
        self._camera_selection_touched = True
        if self._dual_enabled():
            self._remember_pair_selection()
        self._sync_scene()

    def _fill_secondary_devices(self, devices):
        previous = self.secondary_device.currentData() or self._preferred_secondary_camera or (self._preferred_camera_pair or {}).get('sagittal')
        selected = choose_camera(devices, previous, allow_single=False) if previous else None
        self.secondary_device.blockSignals(True)
        self.secondary_device.clear()
        self.secondary_device.addItem('侧面设备不可用，请重选' if previous else '请选择侧面摄像头', None)
        names = Counter(d['name'] for d in devices)
        for d in devices:
            title = d['name']+(f" · {d['index']} / {digest(d.get('path', ''))[:5]}" if names[d['name']] > 1 else '')
            self.secondary_device.addItem(title, d)
            self.secondary_device.setItemData(self.secondary_device.count()-1, f"索引 {d['index']} · 接口 {d['backend']}", Qt.ItemDataRole.ToolTipRole)
            if d is selected:
                self.secondary_device.setCurrentIndex(self.secondary_device.count()-1)
        self.secondary_device.blockSignals(False)
        if selected:
            self._preferred_secondary_camera = selected
        elif self._dual_enabled() and self.state == 'PREVIEW':
            self.manual.setChecked(False)
            self._confirmed = False
            self.runtime.command('unconfirm')

    def _placement_changed(self):
        if self.constructing:
            return
        self._invalidate()
        if self.setup['plan'].get('side') != self.side.currentData():
            self.setup['plan'] = default_plan(self.exercise.currentData())
            self.setup['plan'].update(participant_id=self.participant_id, submode=self.submode.currentData(),
                                      side=self.side.currentData())
        self.setup['plan']['calibration'] = {}
        self._sync_scene()

    def _exercise_changed(self):
        if self.constructing:
            return
        self._invalidate()
        self.setup['plan'] = default_plan(self.exercise.currentData())
        self.setup['plan'].update(participant_id=self.participant_id, submode=self.submode.currentData())
        self.view.setCurrentIndex(self.view.findData(self.setup['plan']['view']))
        self._sync_scene()

    def _filter_exercises(self):
        selected = self.exercise.currentData()
        joint = self.joint_group.currentData()
        self.exercise.blockSignals(True)
        self.exercise.clear()
        for eid, label in EXERCISES.items():
            if joint == 'all' or exercise_spec(eid)['joint'] == joint:
                self.exercise.addItem(label, eid)
        index = self.exercise.findData(selected)
        self.exercise.setCurrentIndex(max(0, index))
        self.exercise.blockSignals(False)
        if self.exercise.currentData() != selected:
            self._exercise_changed()

    def _select_scene(self, scene):
        if scene != self.scene:
            self._invalidate()
            self.scene = scene
            self.setup = default_setup(scene, self.exercise.currentData())
            self.setup['plan'].update(participant_id=self.participant_id, submode=self.submode.currentData())
            self.canvas.rois = {}
            self.view.setCurrentIndex(self.view.findData(self.setup['view'] if scene == 'rehab' else 'fixed'))
            if scene == 'rehab' and self._silver_return_device:
                device, self._silver_return_device = self._silver_return_device, None
                self.device.blockSignals(True)
                self.device.setCurrentIndex(next((i for i in range(self.device.count()) if self.device.itemData(i) == device), 0))
                self.device.blockSignals(False)
        self.pages.setCurrentIndex(0)
        self._sync_scene()

    def _sync_scene(self):
        self._update_personal_reminders()
        training = self.scene == 'rehab' and self.submode.currentData() == 'training'
        # Guided sessions have no set/rest engine, so its controls stay hidden
        # instead of offering an action that can only fail.
        self.training_panel.setVisible(training and not self._guided)
        self.task_header.setVisible(not training)
        self.setup['plan'].update(participant_id=self.participant_id, side=self.side.currentData(),
                                  submode=self.submode.currentData())
        self.title.setText(('训练指导' if training else '身体评估') if self.scene == 'rehab' else SCENES[self.scene])
        self.rehab_controls.setVisible(self.scene == 'rehab')
        self.plan_button.setVisible(training)
        self.plan_text.setVisible(training)
        self.baselines.setVisible(False)
        self.guided_toggle.setVisible(self.scene == 'rehab')
        self.guided_note.setVisible(self.scene == 'rehab' and self._guided)
        self.guided_toggle.blockSignals(True)
        self.guided_toggle.setChecked(self._guided)
        self.guided_toggle.blockSignals(False)
        self.region_controls.setVisible(self.scene != 'rehab')
        self.activity_controls.setVisible(self.scene == 'activity')
        self.manual.setText('已看过画面与安全提示' if self.scene == 'rehab' else '已确认单人、机位与全部区域')
        self.bed_controls.setVisible(self.scene == 'bedroom_demo')
        for key, button in self.scene_buttons.items():
            button.setChecked(key == self.scene and not (key == 'rehab' and training))
        self.training_nav.setChecked(training)
        self.body_nav.setChecked(False)
        is_demo = self.scene in ('bedroom_demo', 'safety_demo')
        self.usage.setEnabled(not is_demo)
        if is_demo:
            self.usage.blockSignals(True)
            self.usage.setCurrentIndex(self.usage.findData('CONTROLLED_DEMO'))
            self.usage.blockSignals(False)
        plan = self.setup['plan']
        spec = exercise_spec(plan['exercise_id'])
        instructions = exercise_instructions(plan['exercise_id'])
        self.task_title.setText(spec['label'] if self.scene == 'rehab' else SCENES[self.scene])
        self.task_meta.setText(('左侧' if plan['side'] == 'left' else '右侧')+' · '+instructions['view_label']+
                              (' · 实验性二维观察' if spec['experimental'] else ' · 二维动作观察')
                              if self.scene == 'rehab' else '仅观察当前场景')
        self.catalog_button.setVisible(self.scene == 'rehab' and not training)
        self.camera_instruction.setText(instructions['camera'])
        self.camera_instruction.setVisible(self.scene == 'rehab')
        self.exercise_guide.setVisible(self.scene == 'rehab')
        self.timing_readout.clear()
        self.timing_readout.hide()
        self.exercise_guide.set_exercise(plan['exercise_id'], plan['side'])
        self.setup_tabs.setTabVisible(0, self.scene == 'rehab')
        if self.scene != 'rehab' and self.setup_tabs.currentIndex() == 0:
            self.setup_tabs.setCurrentIndex(2)  # These scenes now have their own step list.
        self.movement_steps.setText(instructions['position']+'\n\n1  '+instructions['start']+'\n\n2  '+instructions['move']+'\n\n3  '+instructions['return'])
        self.movement_details.setVisible(self.scene == 'rehab')
        self.measurement_details.setVisible(self.scene == 'rehab')
        self.companion.setVisible(bool(plan.get('needs_companion')) or self.scene != 'rehab')
        joint_task = self.scene == 'rehab' and plan['exercise_id'] != 'sit_to_stand' and not self._guided
        optional = joint_task and not spec['baseline_required']
        target_layout = self.optional_baseline.box if optional else self.setup_panel.widget().layout()
        if target_layout.indexOf(self.joint_baselines) < 0:
            target_layout.insertWidget(0 if optional else target_layout.indexOf(self.optional_baseline), self.joint_baselines)
        self.optional_baseline.setVisible(False)
        self.joint_baselines.setVisible(False)
        self.joint_direction_button.setVisible(spec['directional_calibration'])
        self.joint_rest_button.setText('已侧抬臂，倒计时记录起点' if plan['exercise_id'] == 'shoulder_adduction' else '倒计时记录舒适起点')
        self.joint_direction_button.setText('已按动作方向试做，倒计时记录')
        baseline = plan.get('joint_baseline') or {}
        self.joint_baseline_text.setText(
            ('起点已记录' if baseline else '起点未记录')+
            (' · 方向已记录' if baseline.get('direction_sign') else ' · 方向未记录' if spec['directional_calibration'] else '')+
            '')
        if plan['exercise_id'] == 'shoulder_adduction':
            value = baseline.get('rest_value')
            self.joint_baseline_text.setText(f'侧抬臂起点：{value:.0f}° · 内收时角度减小' if isinstance(value, (int, float)) else
                                             '先舒适侧抬臂，再记录；不是垂臂起点')
        self.manual.setToolTip('点击确认即可继续；当前关节是否可见不会阻止开始。')
        goal = '角度目标：未设置' if plan['target_angle_deg'] is None else f"角度目标：{plan['target_angle_deg']:g}°"
        if training:
            confirmation = '计划已确认' if plan.get('training_plan_confirmed') else '计划待确认'
            rest = plan.get('rest_between_sets_s')
            rest_text = '组间休息：未指定时间' if rest is None else f'组间休息：{rest:g} 秒'
            self.plan_text.setText(f"{plan['target_reps']} 次 × {plan['target_sets']} 组\n{goal}\n{rest_text}\n{confirmation} · 组间手动继续")
        else:
            self.plan_text.setText('评估模式：记录可见幅度、完整动作和观察质量。\n结束后汇总身体信息，不自动诊断或生成处方。')
        self.plan_button.setText('修改训练计划' if plan.get('training_plan_confirmed') else '确认训练计划')
        self.action_guide.setVisible(self.scene == 'rehab')
        self.action_guide.setText(instructions['measurement_label']+'\n\n'+instructions['count']+'\n\n'+instructions['boundary']+
            ('\n\n橙色手部点：模型未提供逐点置信度。' if spec['backend'] in ('mediapipe_hands', 'mediapipe_wrist') else '')+
            '\n\n起点和方向校准用于动作分期，不是正常值或训练目标。')
        self.reference_text.setVisible(training)
        self.reference_button.setVisible(training)
        reference = plan.get('assessment_reference') or {}
        reference_time = reference.get('start_utc')
        reference_time_label = (reference_time.replace('T', ' ')[:16]+' UTC'
                                if isinstance(reference_time, str) and reference_time else '评估时间未记录')
        self.reference_text.setText(('评估：'+(reference.get('exercise_label') or spec['label'])+' · '+('左侧' if reference.get('side') == 'left' else '右侧')+'\n'+reference_time_label)
                                    if reference.get('session_id') else '还没有选择评估记录。')
        self.source_badge.setText(SOURCES.get(self.source_kind.currentData(), '输入未选择')+' · '+CONTEXTS.get(self.usage.currentData(), ''))
        if self.state not in ('ONLINE', 'PREVIEW'):
            self.canvas.caption, self.canvas.subcaption, feedback = self._idle_copy()
            self.feedback.setText(feedback)
            self.canvas.update()
        self.start_button.setText('开始训练' if training else '开始评估' if self.scene == 'rehab' else '开始观察')
        self.stop_button.setText('完成并保存' if self.scene == 'rehab' and not training else '结束并保存' if training else '停止并保存')
        cal = plan.get('calibration', {})
        self.baseline_text.setText('坐位：'+('已记录' if 'seated_knee' in cal else '未记录')+' / 站位：'+('已记录' if 'standing_knee' in cal else '未记录'))
        self.subtitle.setText({'rehab': '按已确认的计划完成训练。' if training else '检查拍摄位置，在舒适范围内完成动作。', 'activity': '只累计画面内有证据的活动时段。',
                              'bedroom_demo': '受控区域演示 · 只报告已观察到的过程。', 'safety_demo': '受控低位演示 · 疑似事件需要人工确认。'}[self.scene])
        self.roi_info.setText('已圈定：'+('、'.join(ROI_LABELS.get(k, k) for k in self.setup['rois']) or '无'))
        labels = {'rehab': [('完成次数', ' 次'), ('二维投影角', '°')],
                  'activity': [('累计可见坐位', ' 秒'), ('连续可见坐位', ' 秒')],
                  'bedroom_demo': [('已记录状态变化', ' 次'), ('有效可见时长', ' 秒')],
                  'safety_demo': [('本次疑似事件', ' 条'), ('持续低位观察', ' 秒')]}[self.scene]
        self.count_card.configure(*labels[0])
        self.angle_card.configure(*labels[1])
        if self.scene == 'rehab':
            self.angle_card.caption.setToolTip(spec['metric_label'])
        self._mark_navigation()
        if self.pages.currentIndex() == 3:
            self.title.setText('身体评估')
            self.subtitle.setText('选择部位和动作，完成后查看身体档案。')
        elif self.pages.currentIndex() in (1, 2):
            self.title.setText('历史记录' if self.pages.currentIndex() == 1 else '身体档案')
        elif self.pages.currentWidget() is self.training_hub:
            self.training_hub.set_plan(plan, self._body_scope_key())
            self.title.setText('训练中心')
            self.subtitle.setText('从评估出发，按已确认的安排练习。')
        self._sync_dual_controls()
        self._buttons()

    def _mirror_changed(self):
        # Display only. Re-acknowledging is enough; the camera keeps running.
        self._confirmed = False
        self.manual.setChecked(False)
        if self.state == 'PREVIEW':
            self.runtime.command('unconfirm')
        self._cancel_start_countdown()
        if self.source_kind.currentData() == 'LIVE_CAMERA':
            self._live_mirror = self.mirror.isChecked()
        else:
            self._replay_mirror = self.mirror.isChecked()
        self.canvas.mirror = self.mirror.isChecked()
        self.canvas.update()
        self.video_pair.set_mirror(self.mirror.isChecked())

    def _test_mirror_changed(self, checked):
        # Raw camera testing has no active clinical setup; share this display
        # preference without reopening or stopping its capture.
        self._live_mirror = checked
        self.mirror.blockSignals(True)
        self.mirror.setChecked(checked)
        self.mirror.blockSignals(False)
        self.canvas.mirror = checked
        self.canvas.update()
        self.video_pair.set_mirror(checked)

    def _open_distance_coach(self):
        if self.scene != 'rehab' or self.pages.currentIndex() != 0 or self.busy or self._camera_testing or self.state == 'SAVE_FAILED':
            return
        if self.distance_coach is None:
            self.distance_coach = DistanceCoach(self)
            self.distance_coach.finish_requested.connect(self._finish_task)
            self.distance_coach.privacy_requested.connect(lambda: self._send('privacy', reason='privacy_pause'))
            self.distance_coach.control_requested.connect(
                lambda action, confirmed: self._send('training_control', action=action, setup_confirmed=confirmed))
            self.distance_coach.self_report_requested.connect(lambda: self._send('self_report'))
            self.distance_coach.guided_pause_requested.connect(self._toggle_guided_pause)
        self._render_distance_coach()
        self.distance_coach.showFullScreen()

    def _render_distance_coach(self):
        if self.distance_coach is not None:
            data = self._last_coach_view or dict(state=self.state, summary={})
            self.distance_coach.set_countdown(self._start_countdown)
            self.distance_coach.render(data, self.setup['plan'], mirror=self.mirror.isChecked(),
                                       source_kind=self.source_kind.currentData(), usage_context=self.usage.currentData(),
                                       available=self.busy == 0 and not self._camera_testing)

    def _close_distance_coach(self):
        if self.distance_coach is not None:
            self.distance_coach.reject()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择本地视频', '', '视频 (*.mp4 *.avi *.mov *.mkv *.wmv);;所有文件 (*)')
        if path:
            self._invalidate()
            self.file.setText(path)
            self.setup['plan']['calibration'] = {}
            self.setup['rois'] = {}
            self.canvas.rois = {}

    def _read_setup(self):
        setup = copy.deepcopy(self.setup)
        setup.update(scene_id=self.scene, view=self.view.currentData(), mirror=self.mirror.isChecked(),
                     participant_confirmed=self.manual.isChecked(), companion_confirmed=self.companion.isChecked(),
                     poses_consent=self.poses.isChecked(), activity_permission=self.permission.isChecked(),
                     demo_thresholds=self.demo.isChecked(), real_bed=self.real_bed.isChecked(),
                     needs_assistance=self.assistance.isChecked(), night_confirmed=self.night.isChecked())
        setup['continuation_mode'] = 'guided' if self._guided and self.scene == 'rehab' else 'auto'
        setup['allowed_activity_tasks'] = list(self.activity_options.currentData())
        setup.update({key: control.value() for key, control in self.activity_durations.items()})
        setup['plan'].update(exercise_id=self.exercise.currentData(), side=self.side.currentData(),
                             submode=self.submode.currentData(), view=self.view.currentData(), participant_id=self.participant_id)
        if self._dual_enabled():
            setup['dual_camera'] = dict(primary_view=self.view.currentData(), same_participant_confirmed=self.manual.isChecked())
        else:
            setup.pop('dual_camera', None)
        if setup['demo_thresholds']:
            setup.update(sedentary_trigger_s=15., stand_target_s=5., walk_target_s=8.)
        return setup

    def _source(self):
        kind = self.source_kind.currentData()
        if kind == 'LIVE_CAMERA':
            if self._dual_enabled():
                return make_dual_source(dict(frontal=self.device.currentData(), sagittal=self.secondary_device.currentData()),
                                        self.view.currentData(), self.usage.currentData())
            d = self.device.currentData()
            if not d:
                raise ValueError('请刷新并人工选择一个摄像头')
            saved = {k: v for k, v in d.items() if k != 'index'}
            return {'kind': kind, 'device_ref': saved, 'ref': 'camera:'+digest(saved)[:24], 'usage_context': self.usage.currentData()}
        if not self.file.text() or not Path(self.file.text()).is_file():
            raise ValueError('请先选择本地视频文件')
        path = Path(self.file.text()).resolve()
        ref = 'file:'+digest({'path': str(path), 'size': path.stat().st_size, 'mtime': path.stat().st_mtime_ns})[:24]
        return {'kind': kind, 'file': str(path), 'ref': ref, 'recording_id': ref, 'usage_context': self.usage.currentData()}

    def _preview(self):
        if self._camera_testing:
            return
        self._journey_framed = False
        self._journey_error = ''
        self._latest_report_id = None
        self.setup_tabs.setCurrentIndex(2 if self.scene == 'rehab' else 1)
        if self.participant.text().strip() != self.participant_id:
            self.notice.setText('用户编号尚未应用，请先点击“切换 / 新建用户”。')
            return
        try:
            source = self._source()
        except ValueError as exc:
            self.notice.setText(str(exc))
            return
        self.manual.setChecked(False)
        self._framing_valid_since = None
        self._preparation_failed = False
        self._preparation_reuse_shown = None
        self._cancel_start_countdown()
        # Preparation is offered back to the new preview only when the runtime
        # observes the same recorded conditions; it decides, not the interface.
        self.canvas.caption = '正在连接输入'
        self.video_pair.clear()
        self.last_generation = -1
        self._accept_context_frames = True
        self._send('open', source=source, setup=self._read_setup(), options={'speed': self.speed.currentData(), 'seek_s': self.seek.value()})

    def _start_camera_test(self):
        if self.busy or self._camera_testing or self.state in ('ONLINE', 'SAVE_FAILED'):
            return
        try:
            source = self._source()
            if source['kind'] != 'LIVE_CAMERA':
                raise ValueError('请先切换到实时摄像头')
        except ValueError as exc:
            self.notice.setText(str(exc))
            return
        self._invalidate()
        self.notice.clear()
        self._camera_testing = True
        self._accept_context_frames = True
        self.last_generation = -1
        title = (f'正面：{self.device.currentText()} / 侧面：{self.secondary_device.currentText()}'
                 if self._dual_enabled() else self.device.currentText())
        self.camera_test_dialog = CameraTestDialog(title, self, mirror=self._live_mirror, dual_view=source.get('dual_camera'))
        self.camera_test_dialog.mirror_toggle.toggled.connect(self._test_mirror_changed)
        self.camera_test_dialog.stop_requested.connect(lambda: self._send('stop_camera_test'))
        self.camera_test_dialog.show()
        self._send('camera_test', source=source)

    def _confirm(self):
        if self.scene == 'rehab':
            self.manual.blockSignals(True)
            self.manual.setChecked(True)  # The labelled final button is the explicit manual acknowledgement.
            self.manual.blockSignals(False)
        self._send('confirm', setup=self._read_setup())

    def _journey_step(self):
        if self.scene != 'rehab':
            return current_scene_step(self.scene, self.state, rois=tuple(self.setup['rois']),
                                      permission=self.permission.isChecked(),
                                      confirmed=getattr(self, '_confirmed', False),
                                      saved=bool(self._latest_report_id))
        request = getattr(self, '_last_sample_request', None)
        if self.state == 'PREVIEW' and self.preparation_active and request:
            steps = preparation_steps(self.setup['plan'], dual=self._dual_enabled(), guided=self._guided)
            for number, step in enumerate(steps, 1):
                if step[0] == request[1]:
                    return JourneyStep(step[0], step[1], '保持本步骤姿势，等待下方记录完成；需要调整时可取消。',
                                       '正在记录…', number, len(steps))
        return current_step(self.setup['plan'], self.state, framed=self._journey_framed,
                            confirmed=getattr(self, '_confirmed', False), dual=self._dual_enabled(),
                            saved=bool(self._latest_report_id), guided=self._guided)

    def _journey_next(self):
        if self.busy or self._camera_testing or self.preparation_active or self.state in ('CONNECTING', 'SAVE_FAILED'):
            return
        if self._start_countdown:
            return
        self._journey_error = ''
        if self.scene != 'rehab':
            self.setup_tabs.setCurrentIndex(2)
            step = self._journey_step().key
            if step == 'camera':
                self._preview()
            elif step == 'regions':
                missing = [title for name, title in SCENE_ROIS[self.scene] if name not in self.setup['rois']]
                if missing:
                    self._journey_error = '还需要圈定：'+'、'.join(missing)+'。在“设置”里选择区域名称，再在画面上拖矩形。'
                    self.setup_tabs.setCurrentIndex(1)
            elif step == 'permission':
                # The labelled button is the explicit permission, as elsewhere.
                self.permission.setChecked(True)
                self.notice.flash('已确认本次站立 / 步行活动许可。可在“设置”里调整任务与时间。')
            elif step == 'confirm':
                self._confirm()
            elif step == 'start':
                self._begin_start_countdown()
            elif step == 'active':
                self._finish_task()
            elif step == 'result':
                self._send('report', id=self._latest_report_id)
            self._buttons()
            return
        self.setup_tabs.setCurrentIndex(2)
        step = self._journey_step().key
        if step == 'reference':
            self._show_body()
        elif step == 'plan':
            self._plan()
        elif step == 'camera':
            self._preview()
        elif step == 'framing':
            self._journey_framed = True  # A UI acknowledgement, never runtime confirmation.
        elif step in ('rest', 'direction'):
            self._record_joint_baseline(step)
        elif step in ('seated', 'standing'):
            self._start_preparation('baseline', step)
        elif step == 'confirm':
            if self.setup['plan'].get('needs_companion') and not self.companion.isChecked():
                self._journey_error = '本次安排需要陪同，请确认陪同者在场并勾选。'
                self.journey.companion.setFocus()
            else:
                self._confirm()
        elif step == 'start':
            self._begin_start_countdown()
        elif step == 'active':
            self._finish_task()
        elif step == 'result':
            self._send('report', id=self._latest_report_id)
        self._buttons()

    def _begin_start_countdown(self):
        """A short interface countdown before the run starts. It records nothing."""
        if self.state != 'PREVIEW' or self.busy or self._start_countdown:
            return
        if not self.countdown_enabled.isChecked():
            self._send('start')
            return
        self._start_countdown = 3
        self.journey.set_countdown(self._start_countdown)
        self.countdown_timer.start()
        self._buttons()

    def _cancel_start_countdown(self):
        if self._start_countdown:
            self.notice.flash('已取消开始倒计时，可以继续调整。')
        self._start_countdown = 0
        self.countdown_timer.stop()
        if hasattr(self, 'journey'):
            self.journey.set_countdown(0)
        if self.distance_coach is not None:
            self.distance_coach.set_countdown(0)
        self._buttons()

    def _tick_start_countdown(self):
        if self.state != 'PREVIEW' or self.busy or not self._start_countdown:
            self._cancel_start_countdown()
            return
        self._start_countdown -= 1
        self.journey.set_countdown(self._start_countdown)
        if self.distance_coach is not None:
            self.distance_coach.set_countdown(self._start_countdown)
        if self._start_countdown <= 0:
            self.countdown_timer.stop()
            self._start_countdown = 0
            self._send('start')
        self._buttons()

    def _set_guided_mode(self, enabled):
        if self.constructing or bool(enabled) == self._guided:
            return
        self._guided = bool(enabled)
        for control in (self.guided_toggle, self.journey.guided):
            control.blockSignals(True)
            control.setChecked(self._guided)
            control.blockSignals(False)
        self._journey_error = ''
        self._cancel_start_countdown()
        self._confirmed = False
        self.manual.setChecked(False)
        if self.state == 'PREVIEW':
            self.runtime.command('unconfirm')
        self.notice.flash('已切换到引导计时练习：按提示活动，完成一次可自己点“记一次”。' if self._guided
                          else '已回到自动测量：确认后即可开始，起点在运行中自动建立。')
        self._sync_scene()

    def _toggle_guided_pause(self):
        if self.busy or self.state != 'ONLINE' or not self._guided:
            return
        self._send('guided_pause', paused=not self._guided_paused)

    def _open_latest_report(self):
        if self._latest_report_id and not self.busy:
            self._send('report', id=self._latest_report_id)

    def _render_journey(self, available):
        rehab = self.scene == 'rehab'
        self.setup_tabs.setTabVisible(2, True)
        step = self._journey_step()
        self.preparation_review.setVisible(rehab and self.state == 'PREVIEW' and step.key == 'confirm'
                                           and not self.preparation_active)
        if getattr(self, '_journey_last_step', None) != step.key:
            self._journey_last_step = step.key
            # Reset after Qt recalculates the step height, not on every frame.
            QTimer.singleShot(0, lambda key=step.key: self.journey_scroll.verticalScrollBar().setValue(0)
                              if self._journey_last_step == key else None)
        info = exercise_instructions(self.exercise.currentData())
        explanation = ''
        if rehab and self.exercise.currentData() in ('neck_flexion', 'neck_extension') and step.key in ('camera', 'framing'):
            explanation = ('本动作不要求髋部入镜。同侧眼、耳清楚可见并保持摄像头固定即可；'
                           '肩部用于帮助核对坐姿，不清楚时也不会阻止测量。双摄仍使用侧面画面完成观察。')
            if step.key == 'framing':
                explanation = '同侧眼、耳清楚入镜即可；不要求髋部、脚或另一侧肩入镜。请保持坐稳和摄像头固定。'
        self.journey.explanation.setText(explanation)
        self.journey.explanation.setVisible(bool(explanation))
        guidance = (self._last_coach_view or {}).get('guidance') if rehab else None
        offer = ''
        if rehab and self._guided:
            offer = GUIDED_NOTE
        elif rehab and step.key not in ('active', 'result', 'save_failed'):
            if self._preparation_failed:
                offer = '这一步可以先跳过：勾选下面的“引导计时练习”，按提示完成本次活动并保存记录。'
            elif (guidance or {}).get('offer') == 'guided':
                offer = (guidance or {}).get('offer_text', '')
        context = (self.side.currentText()+' · '+info['view_label']+(' · 引导计时' if self._guided else '')
                   if rehab else SCENES[self.scene]+' · 仅观察当前场景')
        self.journey.render(step, context=context,
                            companion=self.companion.isChecked(),
                            needs_companion=self.setup['plan'].get('needs_companion', False),
                            enabled=available and not self.preparation_active and not self._start_countdown,
                            message=self._journey_error, offer=offer, guided=self._guided,
                            guided_available=rehab, summary=self._completion_summary(step))
        self.journey.set_countdown(self._start_countdown)
        if self.source_kind.currentData() == 'SYNTHETIC':
            self.next_step_hint.setText('演示数据仅用于查看自动计划；切回实时摄像头可进行真人训练')
            self.preview_button.setText('演示计划仅供查看')
            self.preview_button.setEnabled(False)
            return
        self.next_step_hint.setText(f'{step.number} / {step.total}  {step.title}')
        if self.state in ('UNSELECTED', 'OFFLINE', 'ERROR', 'PRIVACY_PAUSED'):
            button = self.preview_button
        elif self.state == 'PREVIEW':
            button = self.start_button if step.key == 'start' else self.confirm_button
        else:
            return
        button.setText(step.action)
        button.setEnabled(available and not self.preparation_active and not self._start_countdown and
                          (step.key != 'start' or self.participant.text().strip() == self.participant_id))

    def _completion_summary(self, step):
        """Say plainly what this saved record does and does not contain."""
        snapshot = self._latest_snapshot
        if step.key != 'result' or not snapshot or snapshot.get('id') != self._latest_report_id:
            return ''
        summary = snapshot.get('summary') or {}
        guided = snapshot.get('measurement_mode') == 'guided_timed'
        lines = ['本次为引导计时：没有自动判定次数或幅度，不作为训练所需的评估依据。' if guided
                 else f"自动观察到的完整动作：{summary.get('completed', 0)} 次。"]
        span = None if guided else summary.get('motion_range')
        approximate = summary.get('approximate_range')
        if isinstance(span, dict) and summary.get('motion_range_valid') is not False:
            lines.append(f"可观察幅度：{span['min_deg']:.0f}° ～ {span['max_deg']:.0f}°。")
        elif isinstance(approximate, dict):
            lines.append(f"近似角度范围：{approximate['min_deg']:.0f}° ～ {approximate['max_deg']:.0f}°"
                         "（按有效帧统计，未按动作分期）。")
        else:
            lines.append('这次没有取得可解释的角度范围；缺测不等于 0。')
        reported = summary.get('self_reported_reps') or 0
        if reported:
            lines.append(f'自己记录的完成次数：{reported} 次（本人报告，不是自动测量）。')
        quality = summary.get('observed_quality')
        if quality and not guided:
            lines.append(f"已观察目标达成 {quality['observed_goals_met']} 次；需调整 {quality['needs_adjustment']} 次；"
                         f"未能核实 {quality['unassessable']} 次。仅限已设置目标，不是整体动作合格率。")
        return '\n'.join(lines)

    def _record_joint_baseline(self, position):
        self._start_preparation('joint_baseline', position)

    def _start_preparation(self, sample, position):
        if self.preparation_active or self.busy or self.state != 'PREVIEW':
            return
        self._journey_error = ''
        self.notice.clear()
        self._confirmed = False
        self.manual.setChecked(False)
        context = (self._last_coach_view or {}).get('context')
        self._last_sample_request = (sample, position, context)
        self.preparation_active = True
        self.preparation_status.clear()
        self.preparation_retry.hide()
        self._send('prepare_sample', sample=sample, position=position, expected_context=context)
        self._buttons()

    def _retry_preparation(self):
        request = getattr(self, '_last_sample_request', None)
        if request and request[2] == (self._last_coach_view or {}).get('context'):
            self._start_preparation(*request[:2])

    def _plan(self):
        if (self.setup['plan'].get('saved_plan_reference') or {}).get('record_origin') == 'assessment_rules':
            self.notice.setText('当前参数由评估自动安排。需要调整时请返回训练中心重新安排；专业人员也可另建人工计划。')
            return
        dialog = PlanDialog(self._read_setup()['plan'], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._invalidate()
            self.setup['plan'] = dialog.plan
            self._sync_scene()

    def _edit_region(self):
        self.canvas.edit_roi = self.roi_select.currentData() if self.state == 'PREVIEW' else None
        if self.roi_select.currentData() and self.state != 'PREVIEW':
            self.notice.setText('请先预览，再选择区域并在画面中拖出矩形。')

    def _roi_changed(self, name, roi):
        self.setup['rois'][name] = roi
        self._confirmed = False
        self.runtime.command('unconfirm')
        self.manual.setChecked(False)
        self.start_button.setEnabled(False)
        self._sync_scene()

    def _confirmation_changed(self, *args):
        if self.constructing:
            return
        self._confirmed = False
        if self.state == 'PREVIEW':
            self.runtime.command('unconfirm')
        self._buttons()

    def _clear_regions(self):
        self._invalidate()
        self.setup['rois'] = {}
        self.setup['plan']['calibration'] = {}
        self.canvas.rois = {}
        self._sync_scene()

    def _buttons(self):
        if not hasattr(self, 'preview_button'):
            return
        available = self.busy == 0 and not self._camera_testing
        capture_source = self.source_kind.currentData() in ('LIVE_CAMERA', 'REPLAY_FILE')
        self.distance_button.setVisible(self.scene == 'rehab')
        self.distance_button.setEnabled(available and self.state != 'SAVE_FAILED')
        self.auto_distance.setVisible(self.scene == 'rehab')
        self.auto_distance.setEnabled(available and self.state != 'ONLINE')
        if self.distance_coach is not None:
            self.distance_coach.set_controls(available)
        self.camera_test_button.setVisible(self.source_kind.currentData() == 'LIVE_CAMERA')
        self.camera_test_button.setEnabled(available and self.state not in ('ONLINE', 'SAVE_FAILED'))
        test_style = 'primary' if self.pages.currentIndex() == 3 else ''
        if self.camera_test_button.objectName() != test_style:
            self.camera_test_button.setObjectName(test_style)
            self.camera_test_button.style().unpolish(self.camera_test_button)
            self.camera_test_button.style().polish(self.camera_test_button)
        self.training_panel.set_execution(self._training_execution, self.state == 'ONLINE', available)
        self.preview_button.setEnabled(available and capture_source and self.state not in ('ONLINE', 'SAVE_FAILED'))
        preparing = getattr(self, 'preparation_active', False)
        self.confirm_button.setEnabled(available and self.state == 'PREVIEW' and not preparing)
        self.confirm_button.setText('已核对，确认准备')
        training_ready = (self.scene != 'rehab' or self.submode.currentData() != 'training'
                          or (self.setup['plan'].get('training_plan_confirmed') and
                              (self.setup['plan'].get('assessment_reference') or {}).get('status') == 'ASSESSED'))
        self.start_button.setEnabled(available and self.state == 'PREVIEW' and getattr(self, '_confirmed', False)
                                     and bool(training_ready) and self.participant.text().strip() == self.participant_id)
        self.stop_button.setEnabled(self.state in ('ONLINE', 'PREVIEW', 'CONNECTING', 'ERROR'))
        self.privacy_button.setEnabled(self.state in ('ONLINE', 'PREVIEW', 'CONNECTING'))
        guided_running = self.scene == 'rehab' and self.state == 'ONLINE' and self._guided
        self.guided_pause_button.setVisible(guided_running)
        self.guided_pause_button.setEnabled(available and guided_running)
        self.guided_pause_button.setText('继续提示' if self._guided_paused else '暂停提示')
        self.self_report_button.setVisible(self.scene == 'rehab' and self.state == 'ONLINE')
        self.self_report_button.setEnabled(available and self.state == 'ONLINE')
        self.self_report_button.setText('记一次（我完成了）' if not self._self_reported
                                        else f'记一次（已记 {self._self_reported} 次）')
        self.retry_button.setVisible(self.state == 'SAVE_FAILED')
        self.retry_button.setEnabled(available)
        self.backup_button.setVisible(self.state == 'SAVE_FAILED')
        self.discard_button.setVisible(self.state == 'SAVE_FAILED')
        self.backup_button.setEnabled(available)
        self.discard_button.setEnabled(available)
        confirmed = getattr(self, '_confirmed', False)
        self.preview_button.setVisible(self.state in ('UNSELECTED', 'OFFLINE', 'ERROR', 'PRIVACY_PAUSED'))
        self.confirm_button.setVisible(self.state == 'PREVIEW' and (not confirmed or not training_ready))
        self.start_button.setVisible(self.state == 'PREVIEW' and confirmed and bool(training_ready))
        self.stop_button.setVisible(self.state in ('ONLINE', 'ERROR'))
        self.privacy_button.setVisible(self.state in ('PREVIEW', 'ONLINE', 'CONNECTING'))
        primary = (self.retry_button if self.state == 'SAVE_FAILED' else self.stop_button if self.state == 'ONLINE'
                   else self.start_button if self.state == 'PREVIEW' and confirmed and training_ready
                   else self.confirm_button if self.state == 'PREVIEW' else self.preview_button)
        if self._start_countdown:
            for button in (self.preview_button, self.confirm_button, self.start_button):
                button.setEnabled(False)
        for button in (self.preview_button, self.confirm_button, self.start_button, self.stop_button, self.retry_button):
            name = 'primary' if button is primary else ''
            if button.objectName() != name:
                button.setObjectName(name)
                button.style().unpolish(button)
                button.style().polish(button)
        hint = {'UNSELECTED': '1 / 3  打开预览', 'PREVIEW': '3 / 3  开始任务' if confirmed else '2 / 3  检查机位与准备',
                'CONNECTING': '正在连接…', 'ONLINE': '正在记录', 'SAVE_FAILED': '请先保存本次结果',
                'OFFLINE': '输入已断开，请重新预览', 'ERROR': '检查输入后重试', 'PRIVACY_PAUSED': '采集已停止'}.get(self.state, '')
        if self.state == 'PREVIEW' and confirmed and not training_ready:
            hint = '请先确认训练计划'
        if self.state == 'UNSELECTED' and self.source_kind.currentData() == 'LIVE_CAMERA' and not self.device.currentData():
            hint = '请在顶部选择摄像头'
        elif self.state == 'UNSELECTED' and not capture_source:
            hint = '演示数据仅用于查看自动计划；切回实时摄像头可进行真人训练'
        self.next_step_hint.setText(hint)
        self.metrics_panel.setVisible(self.state in ('ONLINE', 'SAVE_FAILED'))
        self.feedback.setVisible(self.state not in ('UNSELECTED', 'CONNECTING'))
        if hasattr(self, 'poses'):
            for button in (self.joint_rest_button, self.joint_direction_button, *self.sit_baseline_buttons):
                button.setEnabled(available and self.state == 'PREVIEW' and not preparing and not self._guided)
            self.guided_toggle.setEnabled(available and self.state != 'ONLINE')
            self.preparation_cancel.setVisible(preparing and self.state == 'PREVIEW')
            self.preparation_review.setVisible(self.scene == 'rehab' and self.state == 'PREVIEW' and not confirmed and not preparing)
            self.preparation_review.setText('可直接确认并开始。不需要等待关节全部可见；画面清楚时自动记录，不清楚的片段会自动跳过。')
            self.manual.setVisible(self.scene != 'rehab')
            editable = available and self.state not in ('ONLINE', 'SAVE_FAILED')
            for w in (self.participant, self.participant_select, self.participant_button, self.participant_new,
                      self.joint_group, self.exercise, self.side, self.view,
                      self.plan_button, self.reference_button, self.source_kind, self.device, self.backend, self.refresh, self.mirror,
                      self.dual_toggle, self.secondary_device):
                w.setEnabled(editable)
            if hasattr(self, 'personal_summary'):
                self.personal_summary.edit.setEnabled(editable)
            self.usage.setEnabled(editable and self.scene not in ('bedroom_demo', 'safety_demo'))
            for w in (*self.scene_buttons.values(), self.training_nav, self.body_nav):
                w.setEnabled(available and self.state != 'SAVE_FAILED')
            self.history_nav.setEnabled(available and self.state != 'SAVE_FAILED')
            self.catalog_button.setEnabled(editable)
            self.catalog.setEnabled(editable)
            if hasattr(self, 'training_hub'):
                self.training_hub.setEnabled(editable)
            if hasattr(self, 'body_train'):
                self.body_train.setEnabled(available and bool(self.body_action.currentData()))
            self.poses.setEnabled(self.state != 'ONLINE' and available)
            self.manual.setEnabled(self.state != 'ONLINE' and available)
            self.roi_select.setEnabled(self.state == 'PREVIEW' and available)
            self.canvas.edit_roi = self.roi_select.currentData() if self.state == 'PREVIEW' else None
            self.permission.setEnabled(self.state != 'ONLINE' and available)
            self.activity_options.setEnabled(editable)
            for control in self.activity_durations.values():
                control.setEnabled(editable and not self.demo.isChecked())
            self.preview_segment_button.setEnabled(available and self.state == 'PREVIEW' and self.source_kind.currentData() == 'REPLAY_FILE')
            for button in self.task_buttons:
                button.setEnabled(available and self.state == 'ONLINE' and self.scene == 'activity')
        self._render_journey(available)
        self._refresh_guidance_visibility()

    def _poll(self):
        try:
            while True:
                message = self.runtime.messages.get_nowait()
                self._handle_message(message)
        except queue.Empty:
            pass
        try:
            view = self.runtime.views.get_nowait()
        except queue.Empty:
            self._check_view_freshness()
            return
        self._render_view(view)
        self._check_view_freshness()

    def _check_view_freshness(self, now=None):
        data = self._last_coach_view or {}
        packet = data.get('packet')
        if self.scene != 'rehab' or self.state not in ('PREVIEW', 'ONLINE') or packet is None or packet.context.source_kind != 'LIVE_CAMERA':
            return
        received = packet.received_monotonic
        if packet.paired_frame is not None:
            received = min(received, packet.paired_frame.received_monotonic)
        if (time.monotonic() if now is None else now)-received > 3:
            self.angle_card.show_value(None)
            self.timing_readout.clear()
            self.video_pair.clear()
            guidance = dict(level='critical', instruction='画面更新超时，请重新预览。', status='',
                            phase=None, measurement_valid=False, recovery='preview')
            self._last_coach_view = dict(data, guidance=guidance)
            self.exercise_guide.apply_guidance(guidance)
            self._refresh_guidance_visibility()

    def _handle_message(self, m):
        kind = m['kind']
        if kind == 'family_demo':
            if self.family_demo_dialog:
                self.family_demo_dialog.render(m['data'])
            return
        if kind == 'error' and m.get('command') == 'family_demo':
            if self.family_demo_dialog:
                self.family_demo_dialog.show_error(m['text'])
            return
        if kind == 'silver':
            if self.silver_dialog:
                if m['data']['scope'] == self._body_scope_key():
                    self.silver_dialog.render(m['data'])
                else:
                    self.silver_dialog.show_error('用户或来源已改变，请刷新当前页面')
            return
        if kind == 'error' and m.get('command') == 'silver':
            if self.silver_dialog:
                self.silver_dialog.show_error(m['text'])
            return
        if kind == 'error' and m.get('command') == 'task' and self.silver_dialog and self.silver_dialog.isVisible():
            self.silver_dialog.show_error(m['text'])
        if kind == 'command_done':
            if self.pending_commands[m['command']] > 0:
                self.pending_commands[m['command']] -= 1
                self.busy = max(0, self.busy-1)
            if self.participant_dialog:
                self.participant_dialog.set_busy(self.busy > 0)
            if self.feedback_dialog:
                self.feedback_dialog.set_busy(self.busy > 0)
            if self.batch_dialog:
                self.batch_dialog.set_busy(self.busy > 0)
            if self.plan_library_dialog:
                self.plan_library_dialog.set_busy(self.busy > 0)
            if self.automatic_dialog:
                self.automatic_dialog.set_busy(self.busy > 0)
            if not self.busy and self._automatic_to_activate:
                prepared, self._automatic_to_activate = self._automatic_to_activate, None
                if self.automatic_dialog and self.automatic_dialog.scope == self._body_scope_key():
                    self.automatic_dialog.accept()
                    self._activate_saved_plan(prepared)
            if not self.busy and self._demo_scope_to_activate:
                result, self._demo_scope_to_activate = self._demo_scope_to_activate, None
                self._activate_demo_training_plan(result)
            if not self.busy and self._plan_to_activate:
                prepared, self._plan_to_activate = self._plan_to_activate, None
                if self.plan_library_dialog:
                    self.plan_library_dialog.accept()
                    self._activate_saved_plan(prepared)
            if not self.busy and self._participant_to_activate:
                pid = self._participant_to_activate
                self._participant_to_activate = None
                if pid != self.participant_id:
                    self.participant.setText(pid)
                    self._apply_participant()
                else:
                    self.setup['plan']['training_plan_confirmed'] = False
                    if self.pages.currentIndex() == 0:
                        self._sync_scene()
                self.notice.flash('个人信息已保存。')
            self._buttons()
        elif kind == 'ready':
            if not self._camera_selection_touched:
                self._preferred_camera = m.get('preferred_camera')
                self._preferred_camera_pair = m.get('preferred_camera_pair')
                self._allow_single_camera = not m.get('camera_preference_error', False)
                if self._preferred_camera:
                    index = self.backend.findData(self._preferred_camera.get('backend'))
                    if index >= 0:
                        self.backend.blockSignals(True)
                        self.backend.setCurrentIndex(index)
                        self.backend.blockSignals(False)
            self._send('participants')
            self._send('enumerate', backend=self.backend.currentData())
        elif kind in ('error', 'fatal'):
            self.notice.setText(m['text'])
            if m.get('command') in ('automatic_proposal', 'accept_automatic_plan', 'automatic_progress', 'prepare_automatic_item') and self.automatic_dialog:
                self.automatic_dialog.error.setText(m['text'])
            if m.get('command') == 'prepare_sample':
                self.preparation_active = False
                self.preparation_cancel.hide()
            if m.get('command') in ('confirm', 'open', 'start', 'prepare_sample', 'joint_baseline', 'baseline'):
                self._journey_error = m['text']
                self._cancel_start_countdown()
                if self.state != 'ONLINE' and self.setup_tabs.currentIndex() != 1:
                    self.setup_tabs.setCurrentIndex(2)
                    self.notice.clear()
                self._buttons()
            if m.get('command') in ('longitudinal_history', 'export_longitudinal_history') and self.longitudinal_dialog:
                self.longitudinal_dialog.show_error(m['text'], m.get('request_id'))
            if self._camera_testing and self.camera_test_dialog:
                self.camera_test_dialog.show_error(m['text'])
            self._closing = False
            if m.get('command') == 'save_participant' and self.participant_dialog:
                self.participant_dialog.error.setText(m['text'])
            if m.get('command') == 'save_training_feedback' and self.feedback_dialog:
                self.feedback_dialog.error.setText(m['text'])
            if m.get('command') in ('assessment_batch', 'create_assessment_batch', 'change_assessment_batch') and self.batch_dialog:
                self.batch_dialog.error.setText(m['text'])
            if m.get('command') in ('training_plans', 'save_training_plan', 'archive_training_plan', 'prepare_training_plan') and self.plan_library_dialog:
                self.plan_library_dialog.error.setText(m['text'])
            if kind == 'fatal':
                self.preview_button.setEnabled(False)
        elif kind == 'notice':
            self.notice.flash(m['text'])
        elif kind == 'preparation':
            context = m.get('context')
            if context and (not self._accept_context_frames or context.generation < self.last_generation):
                return
            self.preparation_active = m['active']
            self.preparation_status.setText(m['text'])
            if not m['active'] and m['text'].startswith('已记录'):
                self.preparation_status.flash(m['text'])
                self._preparation_failed = False
            elif not m['active']:
                # A failed sampling is where the guided path becomes worth offering.
                self._preparation_failed = True
            self.preparation_cancel.setVisible(m['active'])
            self.preparation_retry.setVisible(not m['active'] and ('重试' in m['text'] or '再试' in m['text'] or '重新' in m['text']))
            self._buttons()
        elif kind == 'self_report':
            context = m.get('context')
            if context and (not self._accept_context_frames or context.generation < self.last_generation):
                return
            self._self_reported = m['count']
            self.notice.flash(f"已记下第 {m['count']} 次（本人记录，与自动测量分开保存）。")
            self._buttons()
        elif kind == 'camera_test_stopped':
            if not self._camera_testing:
                return
            if self.camera_test_dialog:
                self.camera_test_dialog.finish_close()
                self.camera_test_dialog.deleteLater()
                self.camera_test_dialog = None
            self._camera_testing = False
            self._accept_context_frames = False
            self._confirmed = False
            self.state = 'UNSELECTED' if self.state != 'SAVE_FAILED' else self.state
            self.status_badge.setText(STATUS[self.state])
            self.coverage.setText('当前未开始观察\n其他场景未监测')
            self._buttons()
        elif kind == 'participants':
            self.participant_records = {p['participant_id']: p for p in m['participants']}
            self._refresh_participant_controls()
        elif kind == 'demo_training_plan_created':
            self._demo_scope_to_activate = copy.deepcopy(m)
        elif kind == 'assessment_batch':
            if self.batch_dialog and m['scope'] == self.batch_dialog.scope == self._body_scope_key():
                self.batch_dialog.set_batch(m['batch'])
        elif kind == 'participant_saved':
            profile = m['profile']
            self.participant_records[profile['participant_id']] = profile
            self._refresh_participant_controls()
            self._participant_to_activate = profile['participant_id']
            if self.participant_dialog:
                self.participant_dialog.set_busy(False)
                self.participant_dialog.accept()
        elif kind == 'devices':
            if m.get('backend', self.backend.currentData()) != self.backend.currentData():
                return  # Never apply a late enumeration from another backend.
            self._last_devices = copy.deepcopy(m['devices'])
            previous = self.device.currentData() or self._preferred_camera
            selected = choose_camera(m['devices'], previous, allow_single=self._allow_single_camera)
            self.device.blockSignals(True)
            self.device.clear()
            placeholder = ('上次摄像头不可用，请重选' if previous else '请选择摄像头')
            self.device.addItem(placeholder, None)
            names = Counter(d['name'] for d in m['devices'])
            for d in m['devices']:
                title = d['name']
                if names[title] > 1:
                    title += f" · {d['index']} / {digest(d.get('path', ''))[:5]}"
                self.device.addItem(title, d)
                self.device.setItemData(self.device.count()-1, f"{d['name']} · 索引 {d['index']} · 接口 {d['backend']}", Qt.ItemDataRole.ToolTipRole)
                if d is selected:
                    self.device.setCurrentIndex(self.device.count()-1)
            self.device.blockSignals(False)
            self._fill_secondary_devices(m['devices'])
            if selected:
                self._preferred_camera = selected
                self.device.setToolTip('各模式共用此摄像头；打开预览后仍需确认机位。')
                if self.notice.text() == self._camera_notice_text:
                    self.notice.clear()
            else:
                self.device.setToolTip(placeholder)
                if self.state == 'PREVIEW':
                    self.manual.setChecked(False)
                    self._confirmed = False
                    self.runtime.command('unconfirm')
            if not m['devices']:
                self.device.setItemText(0, '未找到摄像头')
                self._camera_notice_text = '未找到摄像头。检查连接后刷新，或在输入设置中更换接口。'
                self.notice.setText(self._camera_notice_text)
            elif not selected:
                self._camera_notice_text = ('请选择一次摄像头，后续各模式会沿用。' if not previous
                                            else '上次摄像头未找到或标识不唯一，请重新选择。')
                self.notice.setText(self._camera_notice_text)
            if self.state not in ('ONLINE', 'PREVIEW', 'CONNECTING'):
                self.canvas.caption, self.canvas.subcaption, _ = self._idle_copy()
                self.canvas.update()
            self._buttons()
        elif kind == 'confirmed':
            self._journey_error = ''
            self.setup = m['setup']
            self._confirmed = True
            plan = self.setup['plan']
            training_pending = self.submode.currentData() == 'training' and not (
                plan.get('training_plan_confirmed') and (plan.get('assessment_reference') or {}).get('status') == 'ASSESSED')
            self.notice.flash('机位已确认。请先选择评估记录并确认训练计划。' if training_pending else '准备已确认，可以开始。')
        elif kind == 'joint_baseline':
            baseline = m['baseline']
            origin = baseline['provenance']
            if (not self._accept_context_frames or origin['participant_id'] != self.participant_id or
                    origin['exercise_id'] != self.exercise.currentData() or origin['side'] != self.side.currentData() or
                    m['context'].generation < self.last_generation):
                return
            self.setup['plan']['joint_baseline'] = baseline
            self._journey_error = ''
            self._confirmed = False
            self.manual.setChecked(False)
            self._sync_scene()
        elif kind == 'baseline':
            if m.get('context') and (not self._accept_context_frames or m['context'].generation < self.last_generation):
                return
            self._journey_error = ''
            self._confirmed = False
            self.runtime.command('unconfirm')
            identity = m.get('sampling_identity')
            if identity and self.setup['plan']['calibration'].get('sampling_identity') != identity:
                self.setup['plan']['calibration'] = {'sampling_identity': identity}
            self.setup['plan']['calibration'][m['position']+'_knee'] = m['knee']
            self.setup['plan']['calibration'][m['position']+'_hip_y'] = m['hip']
            self.setup['plan']['calibration']['provenance'] = m['provenance']
            self._sync_scene()
        elif kind == 'saved':
            self._journey_error = ''
            self._self_reported = 0
            self._latest_snapshot = None
            if self._feedback_after_save or self._summarize_after_save:
                self._close_distance_coach()
                self._last_coach_view = None
            self.notice.flash('已保存，可在历史记录中查看。')
            if self._feedback_after_save:
                participant_id = self._feedback_after_save
                self._feedback_after_save = None
                if participant_id == self.participant_id:
                    self._latest_report_id = m['id']
                    self._result_after_feedback = (m['id'], self._body_scope_key())
                    self._send('training_review', id=m['id'])
            if self._summarize_after_save:
                scope = self._summarize_after_save
                self._summarize_after_save = None
                if scope == self._body_scope_key():
                    # Stay on the finished task: show its summary and next steps
                    # here, and refresh the body profile without a page jump.
                    self._latest_report_id = m['id']
                    self.setup_tabs.setCurrentIndex(2)
                    self._send('report', id=m['id'])
                    self._refresh_body_profile()
        elif kind in ('automatic_proposal', 'automatic_progress', 'automatic_item_prepared'):
            if (self.automatic_dialog and m['scope'] == self._body_scope_key() == self.automatic_dialog.scope):
                if kind == 'automatic_item_prepared':
                    self._automatic_to_activate = copy.deepcopy(m)
                else:
                    self.automatic_dialog.receive(m)
                    self.automatic_dialog.set_busy(self.busy > 0)
        elif kind == 'training_plans':
            if (self.plan_library_dialog and m['scope'] == self._body_scope_key()
                    and m['scope'] == self.plan_library_dialog.scope):
                self.plan_library_dialog.populate(m['plans'], m.get('selected_id'), saved=m.get('saved', False))
        elif kind == 'training_plan_prepared':
            if (self.plan_library_dialog and m['scope'] == self._body_scope_key()
                    and m['scope'] == self.plan_library_dialog.scope):
                self._plan_to_activate = copy.deepcopy(m)
        elif kind == 'body_profile':
            profile = m['profile']
            if any(profile.get(k) != v for k, v in self._body_scope_key().items()):
                return
            self.body_profile = profile
            self.body_browser.setHtml(m['html'])
            self.body_action.clear()
            for item in profile['items']:
                if item['status'] == 'ASSESSED':
                    self.body_action.addItem(item['exercise_label']+' · '+('左侧' if item['side'] == 'left' else '右侧'), item)
            self.body_overview.set_profile(profile)
            self._buttons()
            if self.body_action.count():
                message = '评估已汇总。选择项目后可进入训练。'
                self.notice.setText(message) if self.pages.currentIndex() == 2 else self.notice.flash(message, 6000)
            elif self.pages.currentIndex() == 2:
                self.notice.clear()
        elif kind == 'longitudinal_history':
            if self.longitudinal_dialog:
                self.longitudinal_dialog.receive(m['history'], m.get('request_id'))
        elif kind == 'longitudinal_exported':
            if self.longitudinal_dialog and self.longitudinal_dialog.request_id == m.get('request_id'):
                self.longitudinal_dialog.notice.setText('纵向记录已导出：'+m['directory'])
        elif kind == 'history':
            self.sessions = m['sessions']
            self.table.setRowCount(len(self.sessions))
            for i, s in enumerate(self.sessions):
                summary = s.get('summary', {})
                ratio = summary.get('valid_ratio')
                task_name = EXERCISES.get(s.get('exercise_id'), '康复任务') if s.get('scene_id') == 'rehab' else SCENES.get(s.get('scene_id'), '任务')
                if s.get('scene_id') == 'rehab':
                    pid = s.get('participant_id')
                    person = s.get('participant_snapshot') or self.participant_records.get(pid) or {}
                    task_name += ' · '+('训练' if s.get('submode') == 'training' else '评估')+'\n'+person.get('display_name', pid or '未记录用户')
                values = [s.get('start_utc', '').replace('T', ' ')[:19]+' UTC', task_name,
                          SOURCES.get(s.get('source_kind'), '未知')+' / '+CONTEXTS.get(s.get('usage_context'), '未知'),
                          str(summary.get('completed', '—')), '—' if ratio is None else f'{ratio*100:.0f}%', s.get('stop_reason', s.get('status', '未知'))]
                for j, value in enumerate(values):
                    self.table.setItem(i, j, QTableWidgetItem(value))
                self.table.setRowHeight(i, 54)
            self.history_empty.setVisible(not self.sessions)
        elif kind == 'training_review':
            snapshot = m['snapshot']
            if snapshot.get('submode') != 'training' or snapshot.get('status') not in ('FINISHED', 'INTERRUPTED'):
                self.notice.setText('这不是已结束的训练记录。')
                return
            self.feedback_dialog = TrainingFeedbackDialog(snapshot, self)
            self.feedback_dialog.save_requested.connect(self._save_training_feedback)
            self.feedback_dialog.finished.connect(self._feedback_closed)
            self.feedback_dialog.set_busy(self.busy > 0)
            self.feedback_dialog.show()
        elif kind == 'training_feedback_saved':
            snapshot = m['snapshot']
            if self.feedback_dialog and self.feedback_dialog.snapshot['id'] == snapshot['id']:
                self.feedback_dialog.set_busy(False)
                self.feedback_dialog.accept()
            for dialog in self.report_windows:
                if dialog.snapshot['id'] == snapshot['id']:
                    dialog.snapshot = snapshot
                    dialog.browser.setHtml(m['html'])
            self.notice.flash('训练感受已保存，测量结果未改变。')
        elif kind == 'report':
            if m['snapshot'].get('id') == self._latest_report_id:
                self._latest_snapshot = m['snapshot']
                self._buttons()
            dialog = ReportDialog(m['snapshot'], m['html'], self._export, self, on_feedback=self._request_training_review)
            self.report_windows.append(dialog)
            dialog.show()
        elif kind == 'events':
            if self.events_dialog:
                self.events_dialog.populate(m['events'])
        elif kind == 'profiles':
            try:
                source = self._source()
            except ValueError as exc:
                self.notice.setText(str(exc))
                return
            candidates = [p for p in m['profiles'] if p['scene_id'] == self.scene and p.get('source_ref') == source['ref']
                          and p['plan']['exercise_id'] == self.exercise.currentData() and p['plan']['side'] == self.side.currentData()
                          and p['plan'].get('participant_id') == self.participant_id]
            if not candidates:
                self.notice.setText('当前用户、来源、场景、动作与侧别下尚无可载入机位。')
                return
            names = [f"机位 {i+1} · {p.get('setup_confirmed_at', '')[:19]}" for i, p in enumerate(candidates)]
            chosen, ok = QInputDialog.getItem(self, '载入机位候选', '载入后需要重新预览确认：', names, 0, False)
            if ok:
                self._invalidate()
                current_plan = copy.deepcopy(self.setup['plan'])
                self.setup = copy.deepcopy(candidates[names.index(chosen)])
                self.setup['plan'] = current_plan | {'calibration': copy.deepcopy(self.setup['plan'].get('calibration', {}))}
                self.setup['participant_confirmed'] = False
                self.canvas.rois = copy.deepcopy(self.setup['rois'])
                self.view.blockSignals(True)
                self.view.setCurrentIndex(self.view.findData(self.setup['view']))
                self.view.blockSignals(False)
                self._sync_scene()
        elif kind == 'shutdown_done':
            self._allow_close = True
            self.close()

    def _render_view(self, data):
        context = data.get('context')
        if context and not self._accept_context_frames:
            return
        if context and context.scene_id != self.scene and not data.get('camera_test'):
            return
        if context and context.generation < self.last_generation:
            return
        if context:
            self.last_generation = context.generation
        if self._camera_testing:
            if data.get('camera_test'):
                self.state = data['state']
                self._confirmed = False
                self.status_badge.setText('摄像头测试')
                self.coverage.setText('仅测试画面 · 未开始评估\n其他场景未监测')
                if self.camera_test_dialog:
                    self.camera_test_dialog.render(data)
                self._buttons()
            return
        if data.get('camera_test'):
            return
        previous_state = self.state
        self.state = data['state']
        if self.state != 'PREVIEW':
            self.preparation_active = False
            self.preparation_status.clear()
            self.preparation_cancel.hide()
            self.preparation_retry.hide()
        if self.state != 'PREVIEW' and self._start_countdown:
            self._cancel_start_countdown()
        self._self_reported = data.get('self_reported', 0) if self.state == 'ONLINE' else 0
        self._guided_paused = bool((data.get('guided_prompt') or {}).get('paused')) and self.state == 'ONLINE'
        self._apply_preparation_reuse(data)
        self._advance_framing(data)
        if self.scene == 'rehab' and self.state == 'ONLINE' and previous_state != 'ONLINE':
            self.setup_tabs.setCurrentIndex(0)
        if previous_state == 'ONLINE' and self.state != 'ONLINE' and self.setup_tabs.currentIndex() == 0:
            self.setup_tabs.setCurrentIndex(2)  # Come back to the step list and its next actions.
        self._training_execution = (data.get('summary') or {}).get('training') or {}
        training_stage = self._training_execution.get('stage')
        self._confirmed = data['confirmed']
        status = STATUS.get(self.state, self.state)
        if self.state == 'ONLINE' and training_stage in ('PAUSED', 'RESTING', 'COMPLETE'):
            status = TRAINING_STAGES[training_stage]+' · 相机开启'
        if self.state == 'UNSELECTED' and self.source_kind.currentData() == 'REPLAY_FILE':
            status = '视频未打开'
        self.status_badge.setText(status)
        tone = 'error' if self.state in ('ERROR', 'SAVE_FAILED', 'OFFLINE') else 'active' if self.state == 'ONLINE' else 'preview' if self.state == 'PREVIEW' else ''
        if self.status_badge.property('tone') != tone:
            self.status_badge.setProperty('tone', tone)
            self.status_badge.style().unpolish(self.status_badge)
            self.status_badge.style().polish(self.status_badge)
        self.coverage.setText(('正在观察：'+SCENES[self.scene] if self.state == 'ONLINE' else '当前未开始观察')+'\n其他场景未监测')
        if self.state == 'ONLINE' and training_stage in ('PAUSED', 'RESTING', 'COMPLETE'):
            self.coverage.setText('未计次，摄像头仍开启\n其他场景未监测')
        packet, pose = data.get('packet'), data.get('pose')
        self.video_pair.render(data, mirror=self.mirror.isChecked(), enabled=self._dual_enabled(), primary_view=self.view.currentData())
        if packet and self.state in ('PREVIEW', 'ONLINE'):
            self.source_badge.setText(SOURCES.get(packet.context.source_kind, '')+' / '+CONTEXTS.get(packet.context.usage_context, '')+(' · 演示阈值' if self.demo.isChecked() and self.scene == 'activity' else ''))
            h, w = packet.image.shape[:2]
            fps = packet.received_fps
            self.frame_info.setText(f'{w} × {h}  ·  '+('速率测量中' if fps is None else f'接收 {fps:.1f} fps')+(f' · 推理 {pose.inference_ms:.0f} ms' if pose else ''))
            if data.get('dual_camera'):
                self.frame_info.setText('双摄 · 主机位：'+VIEWS[data['dual_camera']['primary_view']])
        elif self.state not in ('PREVIEW', 'ONLINE'):
            self.canvas.set_frame(None)
            self.frame_info.clear()
            self.canvas.caption, self.canvas.subcaption, _ = self._idle_copy()
            self.canvas.update()
        summary = data.get('summary', {})
        metrics = summary.get('metrics', {})
        if pose and self.state == 'PREVIEW':
            # Preview readout only. Business processing stays in the runtime worker.
            # Use model confidence in debug without calculating a second action result.
            self.debug.setPlainText(dumps({'people': len(pose.people), 'keypoint_confidence': [p.conf for p in pose.people],
                                           'landmark_attributes': [p.attributes for p in pose.people],
                                           'schema': pose.schema_id, 'inference_ms': pose.inference_ms}, indent=2))
        if summary:
            if self.scene == 'rehab':
                self.count_card.show_value(summary.get('completed'))
                metric = metrics.get(exercise_spec(self.exercise.currentData())['metric'], {})
                angle = metric.get('value') if metric.get('valid') and data.get('current_measurement_valid', data.get('observation_status') == 'VALID') else None
                self.angle_card.show_value(None if angle is None else f'{angle:.1f}')
            elif self.scene == 'activity':
                self.count_card.show_value(f"{summary.get('totals', {}).get('SEATED', 0):.1f}")
                self.angle_card.show_value(f"{summary.get('continuous_sitting_s', 0):.1f}")
            elif self.scene == 'bedroom_demo':
                self.count_card.show_value(len(summary.get('observations', [])))
                self.angle_card.show_value(f"{summary.get('valid_s', 0):.1f}")
            else:
                self.count_card.show_value(summary.get('event_count', 0))
                self.angle_card.show_value(f"{summary.get('low_observed_s', 0):.1f}")
            ratio = summary.get('valid_ratio')
            self.valid_card.show_value(None if ratio is None else f'{ratio*100:.0f}')
            phase = PHASES.get(summary.get('phase')) or summary.get('phase') or ''
            if training_stage and training_stage != 'ACTIVE':
                phase = TRAINING_STAGES.get(training_stage, phase)
            message = summary.get('message') or ''
            self.feedback.setText(phase+' · '+message if phase else message)
            self.debug.setPlainText(dumps(summary, indent=2))
        elif self.state not in ('ONLINE',):
            for c in (self.count_card, self.angle_card, self.valid_card):
                c.show_value(None)
            self.feedback.setText('预览中。可直接确认并开始；清楚入镜后会自动记录。' if self.state == 'PREVIEW' else self._idle_copy()[2])
        if data.get('error') and not data.get('guidance'):
            self.notice.setText(data['error'])
        if self.state in ('OFFLINE', 'ERROR', 'SAVE_FAILED', 'PRIVACY_PAUSED'):
            self.feedback.setText(self._idle_copy()[2])
        observed = data.get('observation_status')
        timing_text = []
        if (self.scene == 'rehab' and self.state == 'ONLINE' and observed == 'VALID'
                and data.get('current_measurement_valid', True) and training_stage not in ('PAUSED', 'RESTING', 'FINISHED')):
            live = summary.get('movement_timing_live') or {}
            elapsed = live.get('hold_elapsed_s')
            if elapsed is not None:
                timing_text.append(f'本段连续保持 {elapsed:.1f} 秒')
            last = summary.get('last_movement_timing') or {}
            if last:
                values = []
                for key, label in (('outbound_s', '出程'), ('endpoint_dwell_s', '峰区停留'), ('return_s', '回程')):
                    metric = last.get(key) or {}
                    value = metric.get('value') if metric.get('valid') else None
                    values.append(label+' '+(f'{value:.1f} 秒' if value is not None else '—'))
                timing_text.append('最近一次记录：'+' / '.join(values))
        self.timing_readout.setText('；'.join(timing_text))
        self.timing_readout.setVisible(bool(timing_text))
        if self.scene == 'rehab':
            primary = metrics.get(exercise_spec(self.exercise.currentData())['metric'], {})
            self.exercise_guide.follow_observation(
                self.state, summary.get('phase'), training_stage=training_stage,
                valid=bool(primary.get('valid')) and observed == 'VALID')
        if (self.state in ('PREVIEW', 'ONLINE') and observed in ('NO_PERSON_DETECTED', 'MULTI_PERSON', 'UNKNOWN')
                and training_stage not in ('PAUSED', 'RESTING', 'COMPLETE')):
            self.feedback.setText({'NO_PERSON_DETECTED': '未检测到人，请调整拍摄位置。',
                                   'MULTI_PERSON': '已自动选择画面中的主要参与者。',
                                   'UNKNOWN': '暂时无法测量，请检查遮挡和拍摄位置。'}[observed])
            if pose and pose.target_kind == 'hand':
                self.feedback.setText({'NO_PERSON_DETECTED': '未检测到测试手 · 请让单只测试手清楚入镜。',
                                       'MULTI_PERSON': '已自动选择画面中最主要的测试手。',
                                       'UNKNOWN': '手部证据不足 · 请检查遮挡、距离和关节轮廓。'}[observed])
            elif pose and pose.backend == 'mediapipe_wrist' and observed == 'UNKNOWN':
                self.feedback.setText('腕部暂不能测量 · 请让所选侧肘、腕和整只手入镜，另一只手移出画面，并稳定保持。')
        if (data.get('measurement_hint') and not data.get('error') and self.state in ('PREVIEW', 'ONLINE')
                and self.scene == 'rehab' and training_stage not in ('PAUSED', 'RESTING', 'COMPLETE', 'FINISHED')):
            self.feedback.setText(data['measurement_hint'])
        guidance = data.get('guidance') if self.scene == 'rehab' else None
        if guidance:
            self.exercise_guide.apply_guidance(guidance)
            self.feedback.setText(guidance['status'])
            if guidance['level'] == 'critical' or data.get('error'):
                self.notice.clear()
                if self.state not in ('PREVIEW', 'ONLINE'):
                    self.canvas.caption, self.canvas.subcaption = '暂无实时画面', ''
                    self.canvas.update()
        self._buttons()
        if guidance:
            self.feedback.setVisible(bool(guidance['status']))

        if self.scene == 'rehab':
            self._last_coach_view = data
            self._refresh_guidance_visibility()
            if self.state == 'SAVE_FAILED':
                self._close_distance_coach()
            elif self.distance_coach is not None and self.distance_coach.isVisible():
                self._render_distance_coach()
            if (self.state == 'ONLINE' and previous_state != 'ONLINE' and context and context.run_id
                    and self.auto_distance.isChecked()):
                self._open_distance_coach()

    def _apply_preparation_reuse(self, data):
        """Tell the person once whether earlier preparation still applies."""
        reuse = data.get('preparation_reuse')
        if not reuse or self.scene != 'rehab':
            return
        signature = dumps(reuse)
        if signature == self._preparation_reuse_shown:
            return
        self._preparation_reuse_shown = signature
        parts = []
        if reuse.get('reused'):
            names = {'joint_baseline': '动作起点', 'calibration': '坐站基线'}
            parts.append('已沿用上次的'+'、'.join(names[k] for k in reuse['reused'] if k in names)+'，不用重新记录。')
        for reason in reuse.get('reasons') or []:
            parts.append(reason+'。')
        if parts:
            self.notice.flash(' '.join(parts), 7000)

    def _advance_framing(self, data):
        """Framing is acknowledged by a steady picture, not by an extra click."""
        if self.scene != 'rehab' or self.state != 'PREVIEW' or self._journey_framed:
            self._framing_valid_since = None if self.state != 'PREVIEW' else self._framing_valid_since
            return
        if not data.get('current_measurement_valid'):
            self._framing_valid_since = None
            return
        now = time.monotonic()
        if self._framing_valid_since is None:
            self._framing_valid_since = now
        elif now-self._framing_valid_since >= 1.2:
            self._journey_framed = True
            self._framing_valid_since = None

    def _refresh_guidance_visibility(self, *args):
        if not hasattr(self, 'journey'):
            return
        guidance = (self._last_coach_view or {}).get('guidance') if self.scene == 'rehab' else None
        if not guidance:
            if self.preparation_active:
                self.feedback.clear()
                self.feedback.hide()
            return
        text = guidance['status']
        on_journey = self.setup_tabs.currentIndex() == 2
        urgent = guidance['level'] in ('adjust', 'critical', 'paused')
        if on_journey and (self.state == 'ONLINE' or urgent) and not self.preparation_active:
            self.journey.instruction.setText(guidance['instruction'])
        if on_journey and not self._journey_error and not urgent and self.state != 'ONLINE':
            self.journey.instruction.setText(self._journey_step().instruction)
        if self.setup_tabs.currentIndex() == 1 and urgent:
            text = guidance['instruction']
        if on_journey and self._journey_error:
            text = ''
        if self.preparation_active:
            text = ''  # The shared sampling strip owns countdown and cancellation feedback.
        self.feedback.setText(text)
        self.feedback.setToolTip(guidance.get('detail', text))
        self.feedback.setVisible(bool(text))

    def _history(self):
        self.title.setText('历史记录')
        self.subtitle.setText('查看、导出或对照已保存的评估和训练。')
        self.pages.setCurrentIndex(1)
        self._mark_navigation()
        self.notice.clear()
        self._send('history')

    def _selected(self):
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def _open_report(self):
        rows = self._selected()
        if rows:
            self._send('report', id=self.sessions[rows[0]]['id'])

    def _export_selected(self):
        rows = self._selected()
        if rows:
            self._export(self.sessions[rows[0]]['id'])

    def _export(self, sid):
        parent = QFileDialog.getExistingDirectory(self, '选择导出文件夹')
        if parent:
            out = Path(parent)/('session-'+sid[:12])
            self._send('export', id=sid, directory=str(out))

    def _delete_report(self):
        rows = self._selected()
        if not rows:
            return
        if QMessageBox.question(self, '删除报告', '删除所选的一份本地报告？已生成的待处理事件会继续保留。') == QMessageBox.StandardButton.Yes:
            self._send('delete', id=self.sessions[rows[0]]['id'])

    def _compare(self):
        rows = self._selected()
        if len(rows) != 2:
            self.notice.setText('按住 Ctrl 选择两份报告再比较。')
            return
        a, b = (self.sessions[i] for i in rows)
        result = compare_conditions(a, b)
        if result['status'] != 'MATCH':
            keys = result['differences']+result['missing']
            QMessageBox.information(self, '比较条件需要核对', '不同或缺失的条件：'+
                '、'.join(CONDITION_LABELS.get(k, k) for k in keys)+'。可在“纵向记录”逐项查看。')
        else:
            QMessageBox.information(self, '相同条件记录对照', f"完整次数：{a['summary'].get('completed', '—')} / {b['summary'].get('completed', '—')}\n这是两次任务记录，不自动解释为康复改善。")

    def _open_longitudinal(self):
        rows = self._selected()
        if len(rows) != 1:
            self.notice.setText('请选择一份康复报告作为纵向比较基准。')
            return
        session = self.sessions[rows[0]]
        if session.get('scene_id') != 'rehab':
            self.notice.setText('纵向记录用于康复评估或训练，请选择对应报告。')
            return
        if self.longitudinal_dialog is None:
            dialog = LongitudinalDialog(self)
            self.longitudinal_dialog = dialog
            dialog.anchor_requested.connect(lambda sid, request: self._send('longitudinal_history', anchor_id=sid, request_id=request))
            dialog.report_requested.connect(lambda sid: self._send('report', id=sid))
            dialog.export_requested.connect(lambda sid, metric, folder, fingerprint: self._send('export_longitudinal_history',
                anchor_id=sid, metric=metric, directory=folder, expected_fingerprint=fingerprint, request_id=dialog.request_id))
            dialog.finished.connect(lambda: setattr(self, 'longitudinal_dialog', None))
        self.longitudinal_dialog.show()
        self.longitudinal_dialog.request(session['id'])

    def _events(self):
        if self.events_dialog is None:
            self.events_dialog = EventsDialog(self.runtime, self)
        self.events_dialog.show()
        self.events_dialog.raise_()
        self.runtime.command('events')

    def _backup_pending(self):
        directory = QFileDialog.getExistingDirectory(self, '选择可写的备份目录')
        if directory:
            self._send('backup_pending', directory=directory)

    def _discard_pending(self):
        reason, accepted = QInputDialog.getText(self, '丢弃未保存结果', '此操作会放弃本次未保存结果。建议先备份。\n输入丢弃原因以确认：')
        if accepted and reason.strip():
            self._summarize_after_save = None
            self._feedback_after_save = None
            self._send('discard_pending', reason=reason)

    def closeEvent(self, event):
        if self._allow_close:
            self._close_distance_coach()
            if self.camera_test_dialog:
                self.camera_test_dialog.finish_close()
            self.timer.stop()
            event.accept()
            return
        event.ignore()
        if not self._closing:
            self._closing = True
            self.notice.setText('正在停止采集并保存本次任务…')
            self._send('shutdown')
