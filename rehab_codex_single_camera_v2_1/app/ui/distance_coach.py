"""Large, presentation-only guidance. All run controls delegate to existing gates."""
import math
import time

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QComboBox, QStackedWidget, QSizePolicy)

from ..domain import SOURCES, CONTEXTS
from ..exercise_instructions import exercise_instructions
from ..exercises import exercise_spec
from .exercise_guide import ExerciseGuide
from .training import TrainingControls
from .widgets import VideoCanvas
from .video_pair import VideoPairPanel


class DistanceCoach(QDialog):
    finish_requested = Signal()
    privacy_requested = Signal()
    control_requested = Signal(str, bool)
    self_report_requested = Signal()
    guided_pause_requested = Signal()

    def __init__(self, parent=None, *, root=None):
        super().__init__(parent)
        self.setWindowTitle('大字动作指导')
        self.setMinimumSize(980, 680)
        self.resize(1280, 800)
        self.state = 'UNSELECTED'
        self.countdown_seconds = 0
        self.self_reported = 0
        self.guided_mode = False
        self.guided_paused = False
        self.training_data = {}
        self.training_mode = False
        self._live_display = False
        self._frame_received = None
        self.freshness_timer = QTimer(self)
        self.freshness_timer.setInterval(250)
        self.freshness_timer.timeout.connect(self._check_freshness)
        self.setStyleSheet('''
            QLabel#coachTitle { font-size:26px; font-weight:700; }
            QLabel#coachMeta { font-size:20px; color:#675675; }
            QLabel#coachCount { font-size:42px; font-weight:700; color:#5933ab; }
            QLabel#coachFeedback { font-size:28px; color:#493356; font-weight:600; }
            QLabel#coachHold { font-size:42px; font-weight:700; color:#643f39;
                background:#fff3eb; padding:24px; border-radius:14px; }
            QLabel#coachSafety { font-size:20px; color:#81442d; }
            QPushButton { font-size:22px; min-height:38px; }
            QComboBox, QCheckBox { font-size:20px; }
        ''')
        box = QVBoxLayout(self)
        box.setContentsMargins(24, 18, 24, 16)
        box.setSpacing(12)
        top = QHBoxLayout()
        self.title = self.label('', 'coachTitle')
        top.addWidget(self.title, 1)
        top.addWidget(self.label('提示字号', 'coachMeta'))
        self.font_choice = QComboBox()
        for size in (32, 36, 40, 48):
            self.font_choice.addItem(str(size), size)
        self.font_choice.setCurrentIndex(1)
        self.font_choice.currentIndexChanged.connect(self._font_changed)
        top.addWidget(self.font_choice)
        self.back = QPushButton('返回普通界面')
        self.back.clicked.connect(self.reject)
        top.addWidget(self.back)
        box.addLayout(top)
        self.source = self.label('', 'coachMeta')
        box.addWidget(self.source)
        middle = QHBoxLayout()
        middle.setSpacing(20)
        left = QVBoxLayout()
        self.count = self.label('尚未开始', 'coachCount')
        left.addWidget(self.count)
        self.canvas = VideoCanvas()
        self.canvas.setMinimumSize(300, 170)
        self.video_pair = VideoPairPanel(self.canvas, compact=True)
        left.addWidget(self.video_pair, 1)
        self.feedback = self.label('', 'coachFeedback')
        left.addWidget(self.feedback)
        middle.addLayout(left, 4)
        self.guide = ExerciseGuide(root=root, distance=True)
        self.hold = self.label('请先完成准备', 'coachHold')
        self.hold.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hold.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.presentation = QStackedWidget()
        self.presentation.addWidget(self.guide)
        self.presentation.addWidget(self.hold)
        middle.addWidget(self.presentation, 6)
        box.addLayout(middle, 1)
        self.training = TrainingControls()
        self.training.control_requested.connect(self.control_requested)
        # Reuse the exact pause/resume/next-set checks; the large header already
        # presents progress, so hide duplicate descriptions in this view.
        self.training.label.hide()
        self.training.note.hide()
        box.addWidget(self.training)
        self.safety = self.label('', 'coachSafety')
        box.addWidget(self.safety)
        footer = QHBoxLayout()
        self.exit_hint = self.label('', 'coachMeta')
        footer.addWidget(self.exit_hint, 1)
        self.guided_pause = QPushButton('暂停提示')
        self.guided_pause.clicked.connect(self.guided_pause_requested)
        footer.addWidget(self.guided_pause)
        self.self_report = QPushButton('记一次（我完成了）')
        self.self_report.clicked.connect(self.self_report_requested)
        footer.addWidget(self.self_report)
        self.privacy = QPushButton('停止采集')
        self.privacy.setObjectName('danger')
        self.privacy.clicked.connect(self.privacy_requested)
        footer.addWidget(self.privacy)
        self.finish = QPushButton('结束并保存')
        self.finish.setObjectName('primary')
        self.finish.clicked.connect(self.finish_requested)
        footer.addWidget(self.finish)
        box.addLayout(footer)

    @staticmethod
    def label(text, name):
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def _font_changed(self):
        self.guide.set_distance_font(self.font_choice.currentData())

    def set_controls(self, available):
        self.training.setVisible(self.training_mode and self.state == 'ONLINE')
        self.training.set_execution(self.training_data, self.state == 'ONLINE', available)
        self.training.progress.hide()
        self.finish.setEnabled(self.state == 'ONLINE')
        self.privacy.setEnabled(self.state in ('ONLINE', 'PREVIEW', 'CONNECTING', 'ERROR'))
        self.guided_pause.setVisible(self.guided_mode and self.state == 'ONLINE')
        self.guided_pause.setEnabled(available and self.state == 'ONLINE')
        self.guided_pause.setText('继续提示' if self.guided_paused else '暂停提示')
        self.self_report.setVisible(self.state == 'ONLINE')
        self.self_report.setEnabled(available and self.state == 'ONLINE')
        self.self_report.setText('记一次（我完成了）' if not self.self_reported
                                 else f'记一次（已记 {self.self_reported} 次）')

    def set_countdown(self, seconds):
        """An interface wait before the run starts; it records nothing."""
        self.countdown_seconds = seconds if isinstance(seconds, int) and seconds > 0 else 0
        if self.countdown_seconds and self.state == 'PREVIEW':
            self.show_hold(f'{self.countdown_seconds} 秒后开始\n请保持起始姿势')

    def show_hold(self, text):
        self.hold.setText(text)
        self.presentation.setCurrentWidget(self.hold)

    def set_feedback(self, text):
        # Keep the full detail in the ordinary view and tooltip; a long backend
        # error must never push the large stop buttons below the screen.
        self.feedback.setToolTip(text)
        brief = text.split('；')[0] if len(text) > 46 else text
        if len(brief) > 46 or brief.count('\n') > 2:
            brief = '详细提示较长\n请返回普通界面查看'
        self.feedback.setText(brief)

    def render(self, data, plan, *, mirror, source_kind, usage_context, available=True):
        self.state = data['state']
        info = exercise_instructions(plan['exercise_id'])
        self.guide.set_exercise(plan['exercise_id'], plan['side'])
        self.training_mode = plan.get('submode') == 'training'
        mode = '训练' if self.training_mode else '评估'
        self.title.setText(info['label']+' · '+('本人左侧' if plan['side'] == 'left' else '本人右侧')+' · '+mode)
        self.canvas.mirror = mirror
        context = data.get('context')
        source_kind = context.source_kind if context else source_kind
        usage_context = context.usage_context if context else usage_context
        self._live_display = source_kind == 'LIVE_CAMERA'
        self.source.setText(SOURCES.get(source_kind, '来源未记录')+' / '+CONTEXTS.get(usage_context, '情境未记录')+
                            ' · '+info['view_label']+(' · 镜像画面' if mirror else ' · 原向画面')+
                            (' · 实验性二维观察' if info['experimental'] else ' · 二维观察'))
        if data.get('dual_camera'):
            self.source.setText(self.source.text()+' · 正侧双摄')
        summary = data.get('summary') or {}
        self.training_data = summary.get('training') or {}
        stage = self.training_data.get('stage')
        completed = summary.get('completed')
        self.self_reported = data.get('self_reported', 0) if self.state == 'ONLINE' else 0
        self.count.setText(f'已完成 {completed} 次' if completed is not None else '尚未开始' if self.state != 'ONLINE' else '等待有效动作')
        guided = data.get('continuation_mode') == 'guided'
        self.guided_mode = guided
        self.guided_paused = bool((data.get('guided_prompt') or {}).get('paused'))
        if guided:
            prompt = data.get('guided_prompt') or {}
            cycle = prompt.get('cycle')
            self.count.setText('引导计时'+(f' · 第 {cycle} 轮' if cycle else '')+
                               (f'\n自己记录 {self.self_reported} 次' if self.self_reported else '\n完成一次请点“记一次”'))
        elif self.self_reported:
            self.count.setText(self.count.text()+f'\n自己记录 {self.self_reported} 次')
        if self.training_data:
            self.count.setText(f"第 {self.training_data.get('set_number', '—')} / {self.training_data.get('target_sets', '—')} 组\n"
                               f"{self.training_data.get('set_reps', '—')} / {self.training_data.get('target_reps', '—')} 次")
        self.safety.setText(plan.get('stop_instruction') or '如有疼痛、头晕或不适，立即停止。')
        active = self.state in ('PREVIEW', 'ONLINE', 'CONNECTING')
        self.exit_hint.setText('Esc 返回普通界面，不停止采集' if active else '采集未开启 · Esc 返回普通界面')
        packet = data.get('packet')
        self._frame_received = getattr(packet, 'received_monotonic', None)
        if data.get('dual_camera'):
            secondary_received = getattr(getattr(packet, 'paired_frame', None), 'received_monotonic', None)
            self._frame_received = (min(self._frame_received, secondary_received)
                                    if all(isinstance(t, (int, float)) and math.isfinite(t) for t in (self._frame_received, secondary_received)) else None)
        fresh = (not self._live_display or (isinstance(self._frame_received, (int, float)) and
                 math.isfinite(self._frame_received) and 0 <= time.monotonic()-self._frame_received <= 3))
        if packet is not None and packet.context == context and fresh and self.state in ('PREVIEW', 'ONLINE') and not data.get('error'):
            pair_fresh = self.video_pair.render(data, mirror=mirror)
            if data.get('dual_camera'):
                fresh = fresh and pair_fresh
        else:
            self.video_pair.clear()
            self.canvas.caption = '暂无实时画面'
            self.canvas.subcaption = '请以当前输入状态为准'
        metric = (summary.get('metrics') or {}).get(exercise_spec(plan['exercise_id'])['metric'], {})
        valid = metric.get('valid') and data.get('observation_status') == 'VALID' and fresh
        phase = summary.get('phase')
        timing = summary.get('movement_timing_live') or {}
        hold_pending = (timing.get('at_target') and isinstance(timing.get('hold_elapsed_s'), (int, float))
                        and isinstance(timing.get('hold_min_s'), (int, float))
                        and timing['hold_elapsed_s']+1e-8 < timing['hold_min_s'])
        self.set_feedback('')
        guidance = data.get('guidance')
        if self.countdown_seconds and self.state == 'PREVIEW':
            self.show_hold(f'{self.countdown_seconds} 秒后开始\n请保持起始姿势')
            self.set_controls(available)
            return
        if guidance:
            self.feedback.setStyleSheet('font-size:20px; font-weight:400; color:#675675;')
            self.back.setText('返回处理并恢复' if guidance.get('recovery') else '返回普通界面')
            if self._live_display and not fresh and self.state in ('ONLINE', 'PREVIEW'):
                self.show_hold('画面更新超时，请重新预览。')
            elif guidance['level'] in ('critical', 'adjust', 'paused'):
                self.show_hold(guidance['instruction'])
                self.hold.setToolTip(guidance.get('detail', guidance['instruction']))
            else:
                self.presentation.setCurrentWidget(self.guide)
                self.guide.apply_guidance(guidance)
                self.set_feedback(guidance['status'])
            self.set_controls(available)
            return
        if data.get('error'):
            self.show_hold('请暂停动作\n检查输入或操作提示')
            self.set_feedback(data['error'])
        elif self.state in ('OFFLINE', 'ERROR', 'SAVE_FAILED', 'PRIVACY_PAUSED'):
            self.show_hold('请暂停动作\n采集已停止或中断')
            self.set_feedback('报告待保存，请返回普通界面处理。' if self.state == 'SAVE_FAILED' else '重新预览和确认后再开始。')
        elif self.state != 'ONLINE':
            self.show_hold('尚未开始\n请先完成准备确认')
            if self.state == 'PREVIEW':
                self.set_feedback(data.get('measurement_hint') or '请在普通界面记录起点，再确认准备。')
        elif stage in ('PAUSED', 'RESTING', 'COMPLETE', 'FINISHED'):
            self.show_hold({'PAUSED': '训练已暂停\n请先休息', 'RESTING': '组间休息\n准备好后再继续',
                            'COMPLETE': '本次训练已完成\n请结束并保存', 'FINISHED': '训练已结束'}[stage])
            remaining = self.training_data.get('rest_remaining_s')
            if stage == 'RESTING' and isinstance(remaining, (int, float)) and math.isfinite(remaining) and remaining > 0:
                self.show_hold(f'组间休息\n还需休息 {math.ceil(remaining)} 秒')
            self.set_feedback('摄像头仍开启；暂停和休息不计次。')
        elif self.training_mode and stage not in ('ACTIVE', 'RECOVERY'):
            self.show_hold('请暂停动作\n等待训练状态确认')
        elif not valid:
            self.show_hold('暂时看不清\n请暂停动作')
            self.set_feedback(data.get('measurement_hint') or {'NO_PERSON_DETECTED': '请让测试部位清楚入镜。', 'MULTI_PERSON': '正在自动选择主要参与者。'}
                                  .get(data.get('observation_status'), '请检查遮挡和拍摄位置。'))
        elif self.training_mode and summary.get('current_issues') and summary.get('message'):
            self.show_hold(summary['message'])
        elif self.training_mode and hold_pending and phase in ('RAISING', 'PEAK_OR_HOLD', 'RISING', 'STANDING_REACHED'):
            self.show_hold(f"本段连续保持\n{timing['hold_elapsed_s']:.1f} / {timing['hold_min_s']:g} 秒")
            self.set_feedback(summary.get('message') or '按本次人工安排保持；不适时停止。')
        elif phase not in ('REST', 'WAIT_READY', 'SEATED_READY', 'RAISING', 'RISING', 'PEAK_OR_HOLD', 'STANDING_REACHED', 'LOWERING'):
            self.show_hold('等待明确动作阶段\n请保持舒适姿势')
        else:
            self.presentation.setCurrentWidget(self.guide)
            message = summary.get('message') or ''
            returning = (stage == 'RECOVERY' or phase == 'STANDING_REACHED' or
                         (self.training_mode and (phase == 'PEAK_OR_HOLD' or message.startswith('已观察到目标范围；'))))
            self.guide.follow_observation('ONLINE', 'LOWERING' if returning else phase, valid=True, training_stage=stage)
            if returning:
                self.guide.status.setText('本组次数完成 · 按安排回位' if stage == 'RECOVERY' else '当前提示 · 缓慢回位')
            # Only present existing engine feedback, never infer a new diagnosis or dose.
            self.set_feedback(message or ('按已确认的安排练习。' if self.training_mode else '按自己的舒适幅度完成动作。'))
        self.set_controls(available)

    def _check_freshness(self, now=None):
        if (self._live_display and self.state in ('PREVIEW', 'ONLINE') and self._frame_received is not None
                and (time.monotonic() if now is None else now)-self._frame_received > 3):
            self.video_pair.clear()
            if self.training_data.get('stage') not in ('PAUSED', 'RESTING', 'COMPLETE', 'FINISHED'):
                self.show_hold('画面更新超时\n请暂停动作')
                self.set_feedback('等待新画面，或停止采集后重新预览。')

    def showEvent(self, event):
        super().showEvent(event)
        self.freshness_timer.start()

    def hideEvent(self, event):
        self.freshness_timer.stop()
        super().hideEvent(event)

    def reject(self):
        self.video_pair.clear()
        self.hide()  # Presentation only; returning must not silently stop a run.

    def closeEvent(self, event):
        self.video_pair.clear()
        event.accept()
