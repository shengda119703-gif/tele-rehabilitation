"""Native editor for versioned, explicitly entered local training plans."""
from __future__ import annotations

import copy
from datetime import datetime
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QComboBox, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QWidget)

from ..domain import SOURCES, CONTEXTS
from ..exercises import EXERCISE_IDS, exercise_spec
from ..settings import default_plan
from ..training_plans import item_from_plan, validate_training_plan
from .dialogs import PlanDialog


class PlanLibraryDialog(QDialog):
    refresh_requested = Signal()
    save_requested = Signal(dict, int)
    archive_requested = Signal(str, int, bool)
    training_requested = Signal(str, int, str)

    def __init__(self, scope, parent=None, candidate=None):
        super().__init__(parent)
        self.setWindowTitle('我的训练计划')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumSize(780, 540)
        self.resize(980, 660)
        self.scope = copy.deepcopy(scope)
        self.participant_records = getattr(parent, 'participant_records', {})
        self.candidate = copy.deepcopy(candidate)
        self.records = []
        self.draft = None
        self.editing = self.pending = False
        box = QVBoxLayout(self)
        box.setContentsMargins(22, 18, 22, 18)
        box.setSpacing(12)
        title = QLabel('我的训练计划')
        title.setObjectName('sectionTitle')
        box.addWidget(title)
        person = self.participant_records.get(scope['participant_id'], {}).get('display_name', scope['participant_id'])
        self.scope_label = QLabel(f"{person} · {SOURCES[scope['source_kind']]} / {CONTEXTS[scope['usage_context']]}")
        self.scope_label.setTextFormat(Qt.TextFormat.PlainText)
        self.scope_label.setWordWrap(True)
        box.addWidget(self.scope_label)
        selector = QHBoxLayout()
        self.selector = QComboBox()
        self.selector.currentIndexChanged.connect(self._select_record)
        selector.addWidget(self.selector, 1)
        self.refresh = QPushButton('刷新')
        self.refresh.clicked.connect(self.refresh_requested.emit)
        self.new = QPushButton('新建计划')
        self.new.clicked.connect(self._new)
        self.edit = QPushButton('编辑计划')
        self.edit.clicked.connect(self._edit)
        self.archive = QPushButton('归档计划')
        self.archive.clicked.connect(self._archive)
        for button in (self.refresh, self.new, self.edit, self.archive):
            selector.addWidget(button)
        box.addLayout(selector)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setMaxLength(80)
        self.name.setPlaceholderText('例如：日常肩部练习')
        form.addRow('计划名称', self.name)
        box.addLayout(form)
        self.version = QLabel()
        self.version.setObjectName('muted')
        box.addWidget(self.version)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['动作 / 侧别', '次数 × 组数', '角度安排', '组间休息', '当前评估'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 118), (2, 125), (3, 105), (4, 148)):
            self.table.setColumnWidth(column, width)
        self.table.itemSelectionChanged.connect(self._buttons)
        box.addWidget(self.table, 1)
        self.item_editor = QWidget()
        row = QHBoxLayout(self.item_editor)
        row.setContentsMargins(0, 0, 0, 0)
        self.exercise = QComboBox()
        for eid in EXERCISE_IDS:
            self.exercise.addItem(exercise_spec(eid)['label'], eid)
        self.side = QComboBox()
        self.side.addItem('本人左侧', 'left')
        self.side.addItem('本人右侧', 'right')
        self.add_item = QPushButton('添加项目')
        self.add_item.clicked.connect(self._add_item)
        self.edit_item = QPushButton('修改项目')
        self.edit_item.clicked.connect(self._edit_item)
        self.remove_item = QPushButton('移除项目')
        self.remove_item.clicked.connect(self._remove_item)
        self.up = QPushButton('上移')
        self.up.clicked.connect(lambda: self._move(-1))
        self.down = QPushButton('下移')
        self.down.clicked.connect(lambda: self._move(1))
        for widget in (self.exercise, self.side, self.add_item, self.edit_item, self.remove_item, self.up, self.down):
            row.addWidget(widget)
        box.addWidget(self.item_editor)
        self.add_current = QPushButton('添加当前准备的训练项目')
        self.add_current.clicked.connect(self._add_current)
        box.addWidget(self.add_current)
        self.detail = QLabel('新建计划并逐项填写；使用时会检查当前有效评估。')
        self.detail.setWordWrap(True)
        box.addWidget(self.detail)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setObjectName('error')
        self.error.setWordWrap(True)
        box.addWidget(self.error)
        note = QLabel('每次只准备一个项目；完成并保存后，再选择下一项。计划不会自动开启相机或开始训练。')
        note.setObjectName('muted')
        note.setWordWrap(True)
        box.addWidget(note)
        actions = QHBoxLayout()
        self.save = QPushButton('保存到计划库')
        self.save.setObjectName('primary')
        self.save.clicked.connect(self._save)
        self.cancel_edit = QPushButton('放弃修改')
        self.cancel_edit.clicked.connect(self._cancel_edit)
        self.use = QPushButton('使用所选项目')
        self.use.setObjectName('primary')
        self.use.clicked.connect(self._use)
        self.close_button = QPushButton('关闭')
        self.close_button.clicked.connect(self.reject)
        for button in (self.save, self.cancel_edit, self.use):
            actions.addWidget(button)
        actions.addStretch()
        actions.addWidget(self.close_button)
        box.addLayout(actions)
        self.populate([])

    def current_record(self):
        pid = self.selector.currentData()
        return next((p for p in self.records if p['id'] == pid), None)

    def current_item(self):
        value = self.draft if self.editing else self.current_record()
        row = self.table.currentRow()
        return value['items'][row] if value and 0 <= row < len(value['items']) else None

    def populate(self, plans, selected_id=None, *, saved=False):
        if self.editing and not saved:
            return  # A stale read must not replace an unsaved draft.
        selected_id = selected_id or self.selector.currentData()
        self.records = copy.deepcopy(plans)
        self.editing = False
        self.draft = None
        self.selector.blockSignals(True)
        self.selector.clear()
        for record in self.records:
            suffix = ' · 已归档' if record['status'] == 'ARCHIVED' else ''
            self.selector.addItem(f"{record['name']} · v{record['revision']}{suffix}", record['id'])
        if selected_id is not None:
            index = self.selector.findData(selected_id)
            if index >= 0:
                self.selector.setCurrentIndex(index)
        self.selector.blockSignals(False)
        self._select_record()
        self.error.setText('已保存，可在下次启动后继续使用。' if saved else '')

    def _select_record(self):
        if self.editing:
            return
        self._render(self.current_record())

    def _render(self, record, selected_row=0):
        self.name.setText(record['name'] if record else '')
        try:
            updated = datetime.fromisoformat(record['updated_utc'].replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%d %H:%M')
        except (TypeError, KeyError, ValueError):
            updated = '未记录'
        self.version.setText(('未保存的计划草稿' if not record.get('revision') else
                             f"保存版本 {record['revision']} · 修改时间 {updated}") if record else
                             '当前用户与来源下还没有保存的计划')
        entries = record['items'] if record else []
        self.table.setRowCount(len(entries))
        for i, entry in enumerate(entries):
            spec, settings = exercise_spec(entry['exercise_id']), entry['settings']
            angle = settings['target_angle_deg']
            target = '未设置' if angle is None else ('≤ ' if spec['target_direction'] == 'decrease' else '≥ ')+f'{angle:g}°'
            rest = settings['rest_between_sets_s']
            values = [spec['label']+' · '+('左侧' if entry['side'] == 'left' else '右侧'),
                      f"{settings['target_reps']} 次 × {settings['target_sets']} 组", target,
                      '手动继续' if rest is None else f'{rest:g} 秒',
                      '保存后检查' if self.editing else ('可准备' if entry.get('available') else '需核对 / 评估')]
            for j, text in enumerate(values):
                cell = QTableWidgetItem(text)
                cell.setToolTip(entry.get('availability_reason', '使用时重新检查评估与本次准备'))
                self.table.setItem(i, j, cell)
            self.table.setRowHeight(i, 44)
        if entries:
            self.table.selectRow(min(selected_row, len(entries)-1))
        self._buttons()

    def _new(self):
        if self.pending or self.editing:
            return
        self.draft = dict(self.scope, id=uuid4().hex, schema_version=1, revision=0,
                          status='ACTIVE', name='', items=[])
        self.editing = True
        self.error.clear()
        self._render(self.draft)
        self.name.setFocus()

    def _edit(self):
        record = self.current_record()
        if self.pending or self.editing or not record or record['status'] != 'ACTIVE':
            return
        if record.get('record_origin') == 'assessment_rules':
            self.error.setText('自动计划请从训练中心重新安排；人工修改请另建计划。')
            return
        self.draft = copy.deepcopy(record)
        self.editing = True
        self.error.clear()
        self._render(self.draft)

    def _candidate_plan(self, eid, side, settings=None):
        plan = default_plan(eid)
        plan.update(settings or {})
        plan.update(participant_id=self.scope['participant_id'], submode='training', side=side)
        return plan

    def _add_item(self):
        if self.pending or not self.editing:
            return
        dialog = PlanDialog(self._candidate_plan(self.exercise.currentData(), self.side.currentData()),
                            self, template_mode=True)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._append_item(dialog.plan)

    def _append_item(self, plan):
        if not self.editing:
            return
        try:
            entry = item_from_plan(plan)
            if any(i['key'] == entry['key'] for i in self.draft['items']):
                raise ValueError('计划已有此动作与侧别，请选中后修改')
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.draft['name'] = self.name.text()
        self.draft['items'].append(entry)
        self._render(self.draft, len(self.draft['items'])-1)
        self.error.clear()

    def _add_current(self):
        if self.candidate and not self.pending:
            self._append_item(self.candidate)

    def _edit_item(self):
        entry = self.current_item()
        if self.pending or not self.editing or not entry:
            return
        selected = self.table.currentRow()
        dialog = PlanDialog(self._candidate_plan(entry['exercise_id'], entry['side'], entry['settings']),
                            self, template_mode=True)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.draft['items'][selected] = item_from_plan(dialog.plan)
            self.draft['name'] = self.name.text()
            self._render(self.draft, selected)

    def _remove_item(self):
        if self.editing and not self.pending and self.current_item():
            self.draft['name'] = self.name.text()
            row = self.table.currentRow()
            self.draft['items'].pop(row)
            self._render(self.draft, max(0, row-1))

    def _move(self, delta):
        if not self.editing or self.pending or not self.current_item():
            return
        row, entries = self.table.currentRow(), self.draft['items']
        if 0 <= row+delta < len(entries):
            self.draft['name'] = self.name.text()
            entries[row], entries[row+delta] = entries[row+delta], entries[row]
            self._render(self.draft, row+delta)

    def _save(self):
        if not self.editing or self.pending:
            return
        self.draft['name'] = self.name.text()
        try:
            value = validate_training_plan(self.draft)
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.save_requested.emit(value, self.draft['revision'])

    def _cancel_edit(self):
        if self.pending:
            return
        self.editing = False
        self.draft = None
        self.error.clear()
        self._select_record()

    def _archive(self):
        record = self.current_record()
        if record and not self.editing and not self.pending:
            self.archive_requested.emit(record['id'], record['revision'], record['status'] != 'ARCHIVED')

    def _use(self):
        record, entry = self.current_record(), self.current_item()
        if record and entry and entry.get('available') and not self.editing and not self.pending:
            self.training_requested.emit(record['id'], record['revision'], entry['key'])

    def _buttons(self):
        record, entry = self.current_record(), self.current_item()
        free = not self.pending
        self.selector.setEnabled(free and not self.editing)
        self.refresh.setEnabled(free and not self.editing)
        self.new.setEnabled(free and not self.editing)
        automatic = bool(record) and record.get('record_origin') == 'assessment_rules'
        self.edit.setEnabled(free and not self.editing and bool(record) and record['status'] == 'ACTIVE' and not automatic)
        self.archive.setEnabled(free and not self.editing and bool(record))
        self.archive.setText('恢复计划' if record and record['status'] == 'ARCHIVED' else '归档计划')
        self.name.setReadOnly(not self.editing or self.pending)
        self.table.setEnabled(free)
        self.item_editor.setVisible(self.editing)
        self.item_editor.setEnabled(free)
        self.add_current.setVisible(self.editing and self.candidate is not None)
        self.add_current.setEnabled(free)
        for button in (self.edit_item, self.remove_item):
            button.setEnabled(free and bool(entry))
        self.up.setEnabled(free and self.table.currentRow() > 0)
        self.down.setEnabled(free and bool(entry) and self.table.currentRow() < self.table.rowCount()-1)
        self.save.setVisible(self.editing)
        self.save.setEnabled(free)
        self.cancel_edit.setVisible(self.editing)
        self.cancel_edit.setEnabled(free)
        self.use.setVisible(not self.editing)
        self.use.setEnabled(free and bool(entry) and bool(entry.get('available')) and bool(record)
                            and record['status'] == 'ACTIVE' and not automatic)
        self.close_button.setEnabled(free and not self.editing)
        self.detail.setText('按已确认的安排逐项填写；目标不由评估结果自动生成。' if self.editing else
                            (entry.get('availability_reason', '使用时重新检查评估') if entry else
                             '新建计划并逐项填写；使用时会检查当前有效评估。'))
        if automatic:
            self.detail.setText('这是根据评估生成的自动安排。请从训练中心“自动安排 / 继续训练”按顺序执行；此处可以查看和归档。')

    def set_busy(self, busy):
        self.pending = bool(busy)
        self._buttons()

    def reject(self):
        if self.pending:
            return
        if self.editing:
            self.error.setText('草稿尚未保存，请先保存或点击“放弃修改”。')
            return
        super().reject()

    def closeEvent(self, event):
        if self.pending or self.editing:
            event.ignore()
            if self.editing:
                self.error.setText('草稿尚未保存，请先保存或点击“放弃修改”。')
        else:
            super().closeEvent(event)
