"""Assessment -> suggestion -> sequential practice, with no prescription form."""
from __future__ import annotations

import copy
import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QCheckBox, QTextBrowser, QWidget)

from ..domain import SOURCES, CONTEXTS
from ..exercises import exercise_spec


class AutomaticPlanDialog(QDialog):
    requested = Signal(str, dict)
    feedback_requested = Signal(str)

    def __init__(self, scope, parent=None):
        super().__init__(parent)
        self.scope = copy.deepcopy(scope)
        self.demo_only = scope['source_kind'] == 'SYNTHETIC'
        self.proposal = self.record = self.progress = None
        self.pending = False
        self.setWindowTitle('根据评估自动安排训练')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(900, 720)
        box = QVBoxLayout(self)
        self.title = QLabel('评估完成后，不用再填动作、次数和组数')
        self.title.setStyleSheet('font-size:24px;font-weight:600;')
        self.title.setWordWrap(True)
        box.addWidget(self.title)
        scope_label = QLabel(SOURCES[scope['source_kind']]+' / '+CONTEXTS[scope['usage_context']])
        if self.demo_only:
            scope_label.setText(scope_label.text()+' · 临时演示数据，不用于真人训练')
        box.addWidget(scope_label)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        box.addWidget(self.browser, 1)
        self.checks = QWidget()
        checks = QVBoxLayout(self.checks)
        self.general = QCheckBox('测试中和现在没有疼痛、头晕等不适；\n没有医嘱、疾病或术后活动限制，适合一般轻缓练习')
        self.standing = QCheckBox('可稳定站立，已备好稳固无轮椅或固定扶手（否则只安排坐位动作）')
        self.companion = QCheckBox('如需他人协助，陪同者已在场')
        for control in (self.general, self.standing, self.companion):
            control.setStyleSheet('font-size:16px;')
            checks.addWidget(control)
        box.addWidget(self.checks)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setObjectName('error')
        box.addWidget(self.error)
        self.feedback_button = QPushButton('补记上一项训练感受')
        self.feedback_button.clicked.connect(self._feedback)
        self.feedback_button.hide()
        box.addWidget(self.feedback_button)
        row = QHBoxLayout()
        self.refresh = QPushButton('重新读取评估')
        self.refresh.clicked.connect(lambda: self._request('automatic_proposal'))
        self.new = QPushButton('重新安排本次计划')
        self.new.clicked.connect(self.show_proposal)
        self.primary = QPushButton('使用这个安排')
        self.primary.setObjectName('primary')
        self.primary.clicked.connect(self._primary)
        self.close_button = QPushButton('暂不训练')
        self.close_button.clicked.connect(self.reject)
        for button in (self.refresh, self.new, self.close_button, self.primary):
            row.addWidget(button)
        box.addLayout(row)
        self.set_busy(True)

    def _request(self, name, **kwargs):
        if self.pending:
            return
        self.error.clear()
        self.set_busy(True)
        self.requested.emit(name, kwargs)

    def receive(self, message):
        self.set_busy(False)
        if message['kind'] == 'automatic_proposal':
            self.proposal = copy.deepcopy(message['proposal'])
        self.record, self.progress = copy.deepcopy(message.get('record')), copy.deepcopy(message.get('progress'))
        if self.record:
            self.show_progress()
        else:
            self.show_proposal()

    def show_proposal(self):
        if self.pending or not self.proposal:
            return
        self.mode = 'proposal'
        self.general.setChecked(False)
        self.standing.setChecked(False)
        self.companion.setChecked(False)
        self.checks.show()
        self.feedback_button.hide()
        self.new.hide()
        p = self.proposal
        self.title.setText('系统已读取评估，为你安排基础练习')
        lines = ['<h3>1 · 你的测试情况</h3>']
        for row in p['body']:
            span = row['motion_range']
            detail = (f"{span['min_deg']:.0f}°–{span['max_deg']:.0f}°，完整动作 {row['completed']} 次"
                      if span else '本次没有取得可用幅度')
            lines.append('<p>'+html.escape(row['label']+'：'+detail)+'</p>')
        if not p['body']:
            lines.append('<p>还没有已保存的评估。先在身体评估中完成一个动作。</p>')
        lines.append('<h3>2 · 可以安排的项目</h3>')
        for entry in p['candidates'][:8]:
            suffix = '（需要稳固站立支撑）' if entry['standing'] else '（坐位）'
            basis = '官方动作条目匹配' if entry['evidence_kind'] == 'matched' else '本人评估适配，指南仅支持从少量开始'
            lines.append('<p>'+html.escape(entry['label']+suffix+'：'+entry['rationale']+' · '+basis)+'</p>')
        if len(p['candidates']) > 8:
            lines.append(f'<p>共 {len(p["candidates"])} 项评估达到自动安排门槛；本页先显示优先级最高的 8 项，本次实际安排前 4 项。</p>')
        lines.append('<p>按列表顺序，每次最多 4 项。角度目标来自本次测量范围的适度缩减，不是正常值；舒适程度优先。</p>')
        lines.append('<h3>3 · 确认今天适合，再按顺序练习</h3><p>上面的身体信息和练习参数自动生成。下方仅确认摄像头无法判断的情况；不确定时暂不使用自动安排。</p>')
        for entry in p['excluded'][:6]:
            lines.append('<p>'+html.escape(entry['label']+'：'+entry['reason'])+'</p>')
        if len(p['excluded']) > 6:
            lines.append(f'<p>另有 {len(p["excluded"])-6} 项暂不自动安排，可在身体档案查看各项状态。</p>')
        lines.append('<p>'+html.escape(p['note'])+'</p>')
        self.browser.setHtml(''.join(lines))
        self.error.setText('\n'.join(p['blockers']))
        self.primary.setText('使用这个安排')
        self.primary.setEnabled(bool(p['candidates']) and not p['blockers'])

    def show_progress(self):
        self.mode = 'progress'
        self.checks.hide()
        self.new.setVisible(self.proposal is not None)
        record, progress = self.record, self.progress
        self.title.setText(f"本次训练 · 已完成 {progress['completed']} / {progress['total']} 项")
        meta = record['automatic']
        rows = []
        for index, entry in enumerate(meta['entries']):
            state = next(i for i in progress['items'] if i['key'] == entry['key'])
            settings, source = entry['settings'], entry['source']
            marker = '已完成' if state['done'] else '下一项' if entry['key'] == progress['next_key'] else '稍后'
            rows.append(f'<h3>{index+1} · {html.escape(entry["label"])} · {marker}</h3>')
            target = settings['target_angle_deg']
            text = f"{settings['target_reps']} 次 × {settings['target_sets']} 组"
            direction = '≤' if exercise_spec(entry['exercise_id'])['target_direction'] == 'decrease' else '≥'
            text += '；只记录幅度，不追角度目标' if target is None else f'；本次投影角目标 {direction}{target:g}°（舒适优先）'
            rows.append('<p>'+html.escape(text)+'</p><p>'+html.escape(entry['instruction'])+'</p>')
            if state['quality']:
                q = state['quality']
                rows.append(f"<p>已观察目标达成 {q['observed_goals_met']} 次；需调整 {q['needs_adjustment']} 次；未能核实 {q['unassessable']} 次。不是整体动作合格率。</p>")
            basis = '动作条目匹配' if entry['evidence_kind'] == 'matched' else '一般活动原则；动作与参数由本软件按评估适配'
            rows.append('<p>参考：<a href="'+html.escape(source['url'], quote=True)+'">'+html.escape(source['title'])+'</a> · '+html.escape(source['section'])+' · '+basis+'</p>')
        rows.append('<p>动作选择参考官方公开运动指导；次数上限、角度缩减和复核窗口是本软件的初始适配规则，尚未经过临床验证。项目之间充分休息，准备好再继续。</p>')
        self.browser.setHtml(''.join(rows))
        self.error.setText(progress['blocked'])
        self.feedback_button.setVisible(bool(progress['blocked']) and '记录疼痛' in progress['blocked'])
        self.primary.setText('准备下一项' if progress['next_key'] else '本次安排已完成')
        if self.demo_only:
            self.primary.setText('演示计划仅供查看')
        self.primary.setEnabled(bool(progress['next_key']) and not progress['blocked'] and not self.demo_only)

    def _primary(self):
        if self.mode == 'proposal':
            self._request('accept_automatic_plan', fingerprint=self.proposal['fingerprint'], screening={
                'general_activity_ok': self.general.isChecked(), 'standing_support_ok': self.standing.isChecked(),
                'companion_present': self.companion.isChecked()})
        else:
            self._request('prepare_automatic_item', id=self.record['id'], revision=self.record['revision'],
                          entry_key=self.progress['next_key'])

    def _feedback(self):
        if not self.pending and self.progress:
            sid = next((i['session_id'] for i in reversed(self.progress['items']) if i['session_id']), None)
            if sid:
                self.feedback_requested.emit(sid)

    def set_busy(self, pending):
        self.pending = pending
        for control in (self.primary, self.refresh, self.new, self.close_button, self.checks, self.feedback_button):
            control.setEnabled(not pending)
        if not pending and self.record and getattr(self, 'mode', '') == 'progress':
            self.primary.setEnabled(bool(self.progress['next_key']) and not self.progress['blocked'] and not self.demo_only)
        elif not pending and self.proposal:
            self.primary.setEnabled(bool(self.proposal['candidates']) and not self.proposal['blockers'])

    def reject(self):
        if not self.pending:
            super().reject()
