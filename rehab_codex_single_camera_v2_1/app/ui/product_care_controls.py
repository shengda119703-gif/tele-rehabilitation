"""Explicit care confirmation over trusted, owner-scoped backend proposals."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QToolButton, QDialog, QComboBox, QTextBrowser, QDialogButtonBox
from .product_widgets import label, button, visual
from datetime import datetime


class CareControls(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.workflows = []
        self.scope = None
        self.busy = False
        self.result_value = None
        row = QHBoxLayout(self); row.setContentsMargins(0, 0, 0, 0)
        self.summary = visual(label(''), typography='caption'); row.addWidget(self.summary, 1)
        self.open = QToolButton(); self.open.setText('核对操作'); self.open.setAccessibleName('查看待确认操作和实际执行结果')
        self.open.setProperty('actionId', 'assistantCareReview'); self.open.setProperty('actionKind', 'B')
        self.open.setProperty('actionTarget', 'ui.care.review'); row.addWidget(self.open)
        self.dialog = QDialog(window); self.dialog.setObjectName('assistantCareDialog'); self.dialog.setWindowTitle('核对管家操作'); self.dialog.resize(640, 480)
        box = QVBoxLayout(self.dialog)
        box.addWidget(label('请核对操作与保存结果；首次确认前不会修改记录。'))
        self.select = QComboBox(); self.select.setAccessibleName('选择当前用户待确认的操作')
        self.select.setPlaceholderText('选择另一项待核对操作'); box.addWidget(self.select)
        self.detail = QTextBrowser(); self.detail.setAccessibleName('操作内容与每一步保存回执'); box.addWidget(self.detail, 1)
        actions = QHBoxLayout()
        self.confirm = visual(button('确认并执行', lambda: self.submit('care.confirm'), True), appearance='primary')
        self.cancel = visual(button('取消待执行操作', lambda: self.submit('care.cancel')), appearance='ghost')
        for control, name in ((self.confirm, 'Confirm'), (self.cancel, 'Cancel')):
            control.setObjectName('assistantCare'+name); control.setProperty('actionId', 'assistantCare'+name)
            control.setProperty('actionKind', 'A'); control.setProperty('actionTarget', 'care.'+name.lower())
            actions.addWidget(control)
        box.addLayout(actions)
        close = QDialogButtonBox(QDialogButtonBox.Close); close.button(QDialogButtonBox.Close).setText('关闭')
        close.rejected.connect(self.dialog.close); box.addWidget(close)
        self.open.clicked.connect(self.dialog.show); self.select.currentIndexChanged.connect(self.review)
        self.clear()

    def clear(self):
        self.workflows = []; self.scope = None; self.result_value = None; self.select.clear(); self.detail.clear()
        self.dialog.close(); self.summary.clear(); self.hide(); self.set_busy(False)

    def refresh(self, workflows, unavailable=False):
        current = self.select.currentData()
        self.scope = dict(self.window.legacy._body_scope_key(), participant_id=self.window.owner)
        self.workflows = workflows if isinstance(workflows, list) else []
        self.select.blockSignals(True); self.select.clear()
        for w in self.workflows:
            status = {'awaiting_confirmation':'待确认', 'failed':'失败，待核对', 'partially_succeeded':'部分已保存', 'executing':'执行待恢复'}.get(w['status'], '待核对')
            self.select.addItem(status+' · '+w.get('steps', [{}])[0].get('label', '操作'), w['id'])
        index = self.select.findData(current)
        # A completed operation's receipt remains visible. Never promote another
        # pending operation into an already-open confirmation dialog on refresh.
        self.select.setCurrentIndex(index if index >= 0 else -1 if self.result_value else 0)
        self.select.blockSignals(False)
        if unavailable:
            self.summary.setText('暂时无法读取待确认操作，请刷新后核对。');self.show()
        if self.workflows:
            if not self.result_value:self.summary.setText(f'{len(self.workflows)}项操作需要核对')
            self.show()
            if not self.result_value:self.review()
        elif not self.result_value and not unavailable:
            self.detail.clear();self.summary.clear();self.hide();self.dialog.close()
        self.open.setEnabled(bool(self.workflows or self.result_value))
        self.set_busy(self.busy)

    def selected(self):
        return next((w for w in self.workflows if w['id'] == self.select.currentData()), None)

    def review(self, *_):
        w = self.selected()
        if w:
            self.result_value = None
            self.summary.setText(f'{len(self.workflows)}项操作需要核对')
            status = {'pending':'尚未执行', 'executing':'待核对回执', 'succeeded':'已保存', 'failed':'失败' }
            deadline=datetime.fromisoformat(w['expiresAt'].replace('Z','+00:00')).astimezone().strftime('%Y-%m-%d %H:%M')
            self.detail.setPlainText(w.get('reply', '')+'\n\n'+'\n'.join(s['label']+'：'+status.get(s['status'], s['status']) for s in w['steps'])+'\n\n确认有效期至：'+deadline)
        self.set_busy(self.busy)

    def set_busy(self, busy):
        self.busy = busy; w = self.selected()
        self.confirm.setEnabled(bool(w and not busy)); self.cancel.setEnabled(bool(w and not busy and w['status']=='awaiting_confirmation'))
        self.confirm.setText('确认并执行' if not w or w['status']=='awaiting_confirmation' else '核对后重试未完成步骤')
        self.select.setEnabled(not busy)

    def submit(self, operation):
        w = self.selected()
        current = dict(self.window.legacy._body_scope_key(), participant_id=self.window.owner)
        if not w or self.busy or self.scope != current:
            return
        if self.window._request(operation, {'id':w['id'], 'confirmationToken':w['confirmationToken'], 'confirmed':True}):
            self.set_busy(True)

    def result(self, value):
        self.result_value = value
        self.select.blockSignals(True);self.select.setCurrentIndex(-1);self.select.blockSignals(False)
        self.detail.setPlainText(value.get('reply', '请核对实际记录。'))
        self.summary.setText({'succeeded':'操作已保存，可查看执行结果', 'cancelled':'已取消，未执行操作', 'expired':'确认已过期，请重新提出需求', 'partially_succeeded':'部分已保存，请核对未完成步骤', 'failed':'保存失败，请核对后重试'}.get(value.get('status'), '请核对执行结果'))
        self.show(); self.open.setEnabled(True); self.dialog.show(); self.confirm.setEnabled(False); self.cancel.setEnabled(False)
