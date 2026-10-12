"""Original Qt plan-library controls and native independent-practice flow.

No new palette, QSS, icons or patient database. Replies use the existing Runtime
bus, SQLite commit authority and immutable operation identities.
"""
from __future__ import annotations

import copy
import time
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QPushButton, QCheckBox, QSpinBox, QComboBox, QAbstractSpinBox)

from ..exercises import exercise_spec
from ..exercise_instructions import exercise_instructions
from ..guided import prompt_state
from .plan_library import PlanLibraryDialog
from .participants import plain_label
from .widgets import NoticeLabel


class PracticePlanLibraryDialog(PlanLibraryDialog):
    """Same widgets/layout/signals; only the explicit manual use path changes."""
    def _can_practice(self):
        record, entry = self.current_record(), self.current_item()
        checked = (entry or {}).get('practice_decision') or {}
        return bool(record and record['status'] == 'ACTIVE' and
                    record.get('record_origin', 'manual') == 'manual' and
                    checked.get('category') in (None, 'MISSING_INPUT') and checked.get('code'))

    def _buttons(self):
        super()._buttons()
        if not self.editing:
            self.use.setEnabled(not self.pending and self._can_practice())
            entry = self.current_item()
            if entry and entry.get('practice_decision'):
                checked = entry['practice_decision']
                self.detail.setText('按已有安排跟练，次数由本人记录。' if self._can_practice() else checked['message'])
                for row, item in enumerate((self.current_record() or {}).get('items', [])):
                    decision = item.get('practice_decision') or {}
                    if decision.get('code'):
                        self.table.item(row, 4).setText('可确认后跟练' if decision.get('category') == 'MISSING_INPUT'
                                                       else '可跟练' if decision.get('allowed') else '需核对安排')
                        self.table.item(row, 4).setToolTip(decision.get('message') or '使用时复核原安排')

    def _use(self):
        if not self.pending and not self.editing and self._can_practice():
            record, entry = self.current_record(), self.current_item()
            self.training_requested.emit(record['id'], record['revision'], entry['key'])


class GuidedPracticeDialog(QDialog):
    def __init__(self, window, prepared=None, record=None):
        super().__init__(window)
        self.window = window
        self.scope = copy.deepcopy(window._body_scope_key())
        self.prepared, self.record = copy.deepcopy(prepared), copy.deepcopy(record)
        self.stage = ('SUMMARY' if record['state'] == 'COMMITTED' else 'PAUSED') if record else 'SETUP'
        self.pending = None
        self.start_payload = copy.deepcopy(record['start_payload']) if record else None
        self.finish_payload = copy.deepcopy(record.get('finish_payload')) if record else None
        self.draft_payload = None
        self.elapsed_ms = (record or {}).get('draft', {}).get('elapsed_ms', 0)
        self.last_tick = None
        self.setWindowTitle('跟练')
        self.setMinimumSize(520, 440)
        self.resize(560, 530)
        box = QVBoxLayout(self); box.setContentsMargins(22, 18, 22, 18); box.setSpacing(12)
        self.title = plain_label('', 'sectionTitle'); box.addWidget(self.title)
        self.arrangement = plain_label('', 'muted'); box.addWidget(self.arrangement)
        self.instruction = plain_label('', 'sectionTitle'); box.addWidget(self.instruction, 1)
        self.status = plain_label('', 'muted'); box.addWidget(self.status)
        self.confirm = QCheckBox('采用本人的这份已有安排'); box.addWidget(self.confirm)
        self.support = QCheckBox('已按安排准备好支撑'); box.addWidget(self.support)
        self.companion = QCheckBox('陪同者已在场'); box.addWidget(self.companion)
        self.form = QFormLayout()
        self.count = QSpinBox(); self.count.setRange(-1, 10000); self.count.setSpecialValueText('未填写')
        self.count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.count.setValue((record or {}).get('draft', {}).get('count') if
                            (record or {}).get('draft', {}).get('count') is not None else -1)
        self.count.setAccessibleName('本组实际总次数'); self.form.addRow('本组实际总次数', self.count)
        self.reason = QComboBox()
        for text, key in (('结束本次', 'ended'), ('我已完成本组', 'completed_set'), ('因不适停止', 'discomfort')):
            self.reason.addItem(text, key)
        self.form.addRow('结束方式', self.reason)
        self.scores = {}
        for key, label in (('pain', '当前疼痛'), ('fatigue', '当前疲劳')):
            spin = QSpinBox(); spin.setRange(-1, 10); spin.setSpecialValueText('未填写'); spin.setValue(-1)
            spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.setSuffix(' / 10'); self.scores[key] = spin; self.form.addRow(label, spin)
        box.addLayout(self.form)
        self.notice = NoticeLabel(); self.notice.setTextFormat(Qt.TextFormat.PlainText); self.notice.clear()
        box.addWidget(self.notice)
        row = QHBoxLayout()
        self.back = QPushButton('返回康复'); self.back.clicked.connect(self.hide)
        self.pause = QPushButton('暂停'); self.pause.clicked.connect(self._pause_or_resume)
        self.end = QPushButton('结束'); self.end.clicked.connect(self._end)
        self.primary = QPushButton('开始跟练'); self.primary.setObjectName('primary'); self.primary.clicked.connect(self._primary)
        for button in (self.back, self.pause, self.end, self.primary): row.addWidget(button)
        box.addLayout(row)
        self.timer = QTimer(self); self.timer.setInterval(100); self.timer.timeout.connect(self._tick); self.timer.start()
        self.watch = QTimer(self); self.watch.setInterval(5000); self.watch.timeout.connect(self._recheck); self.watch.start()
        self._render()

    def _bound(self):
        return self.window._body_scope_key() == self.scope

    def _request(self, command, **kwargs):
        if self.pending or not self._bound():
            return
        request = str(uuid4())
        self.pending = dict(command=command, request_id=request, started=time.monotonic())
        self.window.runtime.command(command, scope=copy.deepcopy(self.scope), request_id=request, **copy.deepcopy(kwargs))
        self._render()

    def receive(self, message):
        if not self.pending or message.get('request_id') != self.pending['request_id'] or not self._bound():
            return False
        if message.get('kind') not in ('error', 'practice_result'):
            return False
        if message['kind'] == 'practice_result' and message.get('scope') != self.scope:
            return False
        command = self.pending['command']; self.pending = None
        if message['kind'] == 'error':
            self.notice.setText(message['text'])
            if command in ('practice_start', 'practice_get') and self.stage in ('SETUP', 'EXERCISING', 'PAUSED'):
                self.stage = 'PAUSED' if self.record else 'SETUP'
                self.last_tick = None
                self.resume_requested = False
            self._render(); return True
        item = message['result']; self.record = copy.deepcopy(item)
        if self.draft_payload and any(op['operation_id'] == self.draft_payload['operation_id']
                                      for op in item['draft']['operations']):
            self.draft_payload = None
        if item['state'] == 'COMMITTED':
            self.stage = 'SUMMARY'; self.finish_payload = copy.deepcopy(item['finish_payload'])
            self.notice.setText('练习记录已保存。')
            self.window.practice_saved_id = item['id']
        elif (command == 'practice_start' and self.stage == 'SETUP') or (
                command == 'practice_get' and self.stage == 'PAUSED' and getattr(self, 'resume_requested', False)):
            self.resume_requested = False
            self.stage = 'EXERCISING' if item.get('execution_allowed') and self.isVisible() else 'PAUSED'
            self.last_tick = time.monotonic() if self.stage == 'EXERCISING' else None
            if not item.get('execution_allowed'):
                self.notice.setText((item.get('execution_decision') or {}).get('message') or '请核对当前安排。')
        elif self.stage in ('EXERCISING', 'PAUSED') and not item.get('execution_allowed'):
            self.stage = 'PAUSED'; self.last_tick = None
            self.notice.setText((item.get('execution_decision') or {}).get('message') or '请核对当前安排。')
        if command == 'practice_get' and self.finish_payload and item['state'] != 'COMMITTED':
            # The original end operation was not committed; resend only that
            # immutable payload, never create another journey.
            self._request('practice_finish', id=item['id'], payload=self.finish_payload)
        self._render(); return True

    def _primary(self):
        if self.pending or not self._bound(): return
        if self.stage == 'SETUP':
            ref = self.prepared['plan_ref']
            if not self.start_payload:
                self.start_payload = dict(operation_id=str(uuid4()), plan_id=ref['id'], plan_revision=ref['revision'],
                                          entry_key=ref['entry_key'], arrangement_confirmed=self.confirm.isChecked(),
                                          support_ready=self.support.isChecked(), companion_present=self.companion.isChecked())
            self._request('practice_start', payload=self.start_payload)
        elif self.stage == 'WRAP_UP':
            if not self.finish_payload:
                self.finish_payload = dict(operation_id=str(uuid4()), count=self._count(), elapsed_ms=int(self.elapsed_ms),
                                           reason=self.reason.currentData(), feedback={k: s.value() if s.value() >= 0 else None
                                                                                     for k, s in self.scores.items()})
            self._request('practice_finish', id=self.record['id'], payload=self.finish_payload)
        elif self.stage == 'SUMMARY':
            self.hide()
        elif self.record:
            if self.draft_payload:
                self._request('practice_draft', id=self.record['id'], payload=self.draft_payload)
            else:
                self.resume_requested = True
                self._request('practice_get', id=self.record['id'])

    def _count(self):
        return self.count.value() if self.count.value() >= 0 else None

    def _pause_or_resume(self):
        if self.stage == 'EXERCISING': self._pause()
        elif self.stage == 'PAUSED': self._primary()

    def _pause(self):
        self._tick(); self.stage = 'PAUSED'; self.last_tick = None
        self._checkpoint(); self._render()

    def _checkpoint(self):
        if self.record and self.record['state'] == 'PRACTICING' and not self.pending and not self.finish_payload:
            if not self.draft_payload:
                self.draft_payload = dict(operation_id=str(uuid4()), expected_revision=self.record['draft']['revision'],
                                          elapsed_ms=int(self.elapsed_ms), count=self._count())
            self._request('practice_draft', id=self.record['id'], payload=self.draft_payload)

    def _end(self):
        if self.stage not in ('EXERCISING', 'PAUSED'): return
        self._tick(); self.stage = 'WRAP_UP'; self.last_tick = None; self.resume_requested = False
        self._render(); self.count.setFocus()

    def _tick(self):
        now = time.monotonic()
        if not self._bound():
            if self.stage == 'EXERCISING': self.stage = 'PAUSED'; self.last_tick = None
            self.hide(); return
        if self.pending and now - self.pending['started'] > 20:
            self.pending = None
            if self.stage == 'EXERCISING': self.stage = 'PAUSED'; self.last_tick = None
            self.notice.setText('当前状态待核对，原记录与输入仍保留。')
        if self.stage == 'EXERCISING' and self.isVisible():
            if self.last_tick is not None:
                gap = now - self.last_tick
                if gap <= 1.5: self.elapsed_ms += max(0, gap) * 1000
                else:
                    self.stage = 'PAUSED'; self.notice.setText('练习已暂停，准备好后继续。')
            self.last_tick = now if self.stage == 'EXERCISING' else None
        self._render()

    def _recheck(self):
        if self.stage == 'EXERCISING' and self.record and not self.pending:
            self._request('practice_get', id=self.record['id'])

    def _render(self):
        entry = self.record or (self.prepared or {}).get('entry')
        decision = (self.record or {}).get('execution_decision') or (self.prepared or {}).get('decision') or {}
        if not entry: self.primary.setEnabled(False); self.notice.setText(decision.get('message') or '请核对原安排。'); return
        eid, settings = entry['exercise_id'], entry['settings']
        self.title.setText(exercise_spec(eid)['label'] + ' · ' + ('本人左侧' if entry['side'] == 'left' else '本人右侧'))
        self.arrangement.setText(f"已有安排 {settings['target_reps']} 次 × {settings['target_sets']} 组 · 本页记录本组")
        setup = self.stage == 'SETUP'
        for check in (self.confirm, self.support): check.setVisible(setup); check.setEnabled(not self.pending and not self.start_payload)
        self.companion.setVisible(setup and decision.get('companion_required', False)); self.companion.setEnabled(not self.pending and not self.start_payload)
        wrap = self.stage == 'WRAP_UP'
        for widget in (self.count, self.reason, *self.scores.values()):
            widget.setVisible(wrap); self.form.labelForField(widget).setVisible(wrap)
            widget.setEnabled(not self.pending and not self.finish_payload)
        self.pause.setVisible(self.stage in ('EXERCISING', 'PAUSED')); self.pause.setText('继续' if self.stage == 'PAUSED' else '暂停')
        self.pause.setEnabled(not self.pending and self._bound())
        self.end.setVisible(self.stage in ('EXERCISING', 'PAUSED')); self.end.setEnabled(self._bound())
        self.primary.setVisible(self.stage in ('SETUP', 'WRAP_UP', 'SUMMARY'))
        self.primary.setText('开始跟练' if setup else '保存记录' if wrap else '返回康复')
        eligible_setup = decision.get('category') == 'MISSING_INPUT' and self.confirm.isChecked() and self.support.isChecked()
        if decision.get('companion_required'): eligible_setup = eligible_setup and self.companion.isChecked()
        self.primary.setEnabled(not self.pending and self._bound() and (not setup or eligible_setup))
        self.back.setEnabled(True)
        self.back.setVisible(self.stage != 'SUMMARY')
        info = exercise_instructions(eid)
        if self.stage == 'EXERCISING':
            prompt = prompt_state(self.elapsed_ms / 1000, eid)
            self.instruction.setText(prompt['instruction'] if prompt else info['start'])
            self.status.setText(f'正在跟练 · {int(self.elapsed_ms / 1000)} 秒')
        elif self.stage == 'SUMMARY':
            value = self.record.get('self_reported_count')
            self.instruction.setText('本组记录已保存')
            self.status.setText(('本人记录 ' + str(value) + ' 次' if value is not None else '次数未填写') + ' · 无自动测量结果')
        else:
            self.instruction.setText(info['start'] if setup else '填写本组完成情况' if wrap else '练习已暂停')
            self.status.setText('按已有安排练习，完成后记录本组次数。' if setup else
                                f'页面练习时间 {int(self.elapsed_ms / 1000)} 秒')

    def hideEvent(self, event):
        if self.stage == 'EXERCISING': self._pause()
        super().hideEvent(event)

    def closeEvent(self, event):
        if self.stage == 'EXERCISING': self._pause()
        event.ignore(); self.hide()
