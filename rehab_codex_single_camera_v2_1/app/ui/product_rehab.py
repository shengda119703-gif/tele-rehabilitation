"""Owner-scoped UI adaptation of the original rehabilitation window and command bus."""
import copy
from uuid import uuid4

from ..assessment import session_value
from ..reports import render_result_summary
from .main_window import MainWindow
from PySide6.QtWidgets import QMessageBox, QPushButton, QTableWidgetItem


class ProductRehabWindow(MainWindow):
    def __init__(self, *args, **kwargs):
        self.practice_dialog = None
        self.practice_record_dialog = None
        self.practice_saved_id = None
        self.practice_history = []
        self._practice_history_request = None
        self._practice_preparation = None
        super().__init__(*args, **kwargs)

    def _send(self, name, **kwargs):
        if name == 'history': kwargs.update(include_guided=True, scope=copy.deepcopy(self._body_scope_key()))
        super()._send(name, **kwargs)

    def _open_practice_record(self, identity):
        active = self.practice_dialog
        if active and active.record and active.scope == self._body_scope_key():
            if active.record['id'] == identity and active.record['state'] == 'PRACTICING':
                active.show(); active.raise_()
                return
            active.hide()  # Stop/persist the current practice, do not replace its controller.
        request = str(uuid4())
        self._practice_history_request = dict(request_id=request, scope=copy.deepcopy(self._body_scope_key()))
        self.runtime.command('practice_get', id=identity, request_id=request, scope=self._body_scope_key())

    def _open_plan_library(self):
        from ..guided_practice import flow_enabled
        if not flow_enabled():
            return super()._open_plan_library()
        from .guided_practice import PracticePlanLibraryDialog
        if self.state in ('ONLINE', 'SAVE_FAILED') or self.busy or self._camera_testing:
            self.notice.setText('请先结束并保存当前任务，再打开训练计划。')
            return
        self._invalidate()
        scope = self._body_scope_key()
        self.training_hub.set_plan(self.setup['plan'], scope)
        dialog = PracticePlanLibraryDialog(scope, self,
                    candidate=self.setup['plan'] if self.training_hub.has_reference else None)
        self.plan_library_dialog = dialog
        dialog.refresh_requested.connect(lambda: self._library_command('training_plans'))
        dialog.save_requested.connect(lambda plan, revision: self._library_command(
            'save_training_plan', plan=plan, expected_revision=revision))
        dialog.archive_requested.connect(lambda pid, revision, archived: self._library_command(
            'archive_training_plan', id=pid, expected_revision=revision, archived=archived))
        dialog.training_requested.connect(self._prepare_practice)
        dialog.finished.connect(lambda: setattr(self, 'plan_library_dialog', None))
        dialog.set_busy(True)
        dialog.show()
        self._send('training_plans', scope=scope, include_guided=True)

    def _library_command(self, name, **kwargs):
        super()._library_command(name, include_guided=True, **kwargs)

    def _prepare_practice(self, pid, revision, entry):
        if self.busy or self._practice_preparation or not self.plan_library_dialog:
            return
        scope = copy.deepcopy(self.plan_library_dialog.scope)
        if scope != self._body_scope_key(): return
        request = str(uuid4())
        self._practice_preparation = dict(request_id=request, scope=scope)
        self.plan_library_dialog.set_busy(True)
        self.runtime.command('practice_prepare', scope=scope, id=pid, revision=revision,
                             entry_key=entry, request_id=request)

    def _resume_training_preparation(self):
        if self.practice_dialog and self.practice_dialog.scope == self._body_scope_key() and (
                self.practice_dialog.stage != 'SUMMARY' or self.practice_dialog.sequence_end_requested):
            self.practice_dialog.show(); self.practice_dialog.raise_()
            return
        super()._resume_training_preparation()

    def _show_practice(self, prepared):
        from .guided_practice import GuidedPracticeDialog
        if self.plan_library_dialog:
            self.plan_library_dialog.set_busy(False)
            self.plan_library_dialog.accept()
        if self.practice_dialog and self.practice_dialog.record and (
                self.practice_dialog.record['state'] == 'PRACTICING' or self.practice_dialog.stage == 'REST'
                or self.practice_dialog.continue_payload or self.practice_dialog.sequence_end_requested):
            if self.practice_dialog.scope == self._body_scope_key():
                self.practice_dialog.show(); self.practice_dialog.raise_()
                return
            self.practice_dialog.hide()
        self.practice_dialog = GuidedPracticeDialog(self, prepared=prepared, record=prepared.get('open_record'))
        self.practice_dialog.show()

    def closeEvent(self, event):
        if self.practice_dialog:
            self.practice_dialog.hide()
        if self.practice_record_dialog:
            self.practice_record_dialog.hide()
        super().closeEvent(event)

    def _start_camera_test(self):
        super()._start_camera_test()
        parent=self.parentWidget()
        while parent and not hasattr(parent,'_save_camera_photo'):parent=parent.parentWidget()
        dialog=self.camera_test_dialog
        if parent and getattr(parent,'photo_requested',False) and dialog and not getattr(dialog,'photo_button',None):
            dialog.setWindowTitle('拍摄健康资料')
            dialog.details.setText('把病历或设备读数放入画面；拍摄后只保存原图，识别须另行核对。')
            item=QPushButton('拍摄并保存原图',dialog);item.setObjectName('primary')
            item.setProperty('actionId','cameraPhotoSave');item.setProperty('actionKind','A');item.setProperty('actionTarget','archive.save')
            dialog.photo_button=item
            dialog.layout().insertWidget(dialog.layout().count()-1,item)
            item.clicked.connect(lambda:parent._save_camera_photo(dialog))
            dialog.finished.connect(lambda *_:setattr(parent,'photo_requested',False))

    def _activate_saved_plan(self, prepared):
        super()._activate_saved_plan(prepared)
        parent=self.parentWidget()
        while parent and not hasattr(parent,'_show_rehab_scope'):parent=parent.parentWidget()
        if parent:parent._show_rehab_scope(True)

    def _refresh_guidance_visibility(self,*args):
        super()._refresh_guidance_visibility(*args)
        if self.scene=='rehab' and self.submode.currentData()=='training' and self.state=='ONLINE':
            guidance=(self._last_coach_view or {}).get('guidance')
            if guidance:
                values=[guidance.get('instruction',''),guidance.get('status','')]
                self.feedback.setText('\n'.join(dict.fromkeys(value for value in values if value)))
                self.feedback.setVisible(bool(self.feedback.text()))

    def _buttons(self):
        super()._buttons()
        focus=self.scene=='rehab' and self.submode.currentData()=='training' and self.state in ('ONLINE','SAVE_FAILED')
        self.setup_tabs.setVisible(not focus)
        self.device.parentWidget().setVisible(not focus)

    def _handle_message(self, message):
        if message.get('command', '').startswith('practice_') and message['kind'] in ('practice_result', 'error'):
            history = self._practice_history_request
            if history and history['request_id'] == message.get('request_id'):
                self._practice_history_request = None
                if history['scope'] != self._body_scope_key(): return
                if message['kind'] == 'error': self.notice.setText(message['text'])
                else:
                    from .guided_practice import GuidedPracticeDialog
                    active = self.practice_dialog
                    if active and active.record and active.record['state'] == 'PRACTICING':
                        if self.practice_record_dialog:
                            self.practice_record_dialog.hide(); self.practice_record_dialog.deleteLater()
                        self.practice_record_dialog = GuidedPracticeDialog(self, record=message['result'])
                        self.practice_record_dialog.show()
                    else:
                        if active:
                            active.hide(); active.deleteLater()
                        self.practice_dialog = GuidedPracticeDialog(self, record=message['result'])
                        self.practice_dialog.show()
                return
            pending = self._practice_preparation
            if pending and pending['request_id'] == message.get('request_id'):
                self._practice_preparation = None
                if self.plan_library_dialog: self.plan_library_dialog.set_busy(False)
                if pending['scope'] != self._body_scope_key(): return
                if message['kind'] == 'error':
                    if self.plan_library_dialog: self.plan_library_dialog.error.setText(message['text'])
                else:
                    self._show_practice(message['result'])
                return
            if self.practice_dialog and self.practice_dialog.receive(message): return
            return  # An old owner/request must never overwrite the current page.
        if message['kind']=='history':
            message=dict(message,sessions=[s for s in message['sessions'] if self._in_product_scope(s)])
        elif message['kind'] in ('report','training_review') and not self._in_product_scope(message['snapshot']):
            self.notice.setText('记录所属用户、输入来源或使用情境已变化，请重新选择当前范围的记录。')
            return
        super()._handle_message(message)
        if message['kind'] == 'history' and message.get('practice_scope') == self._body_scope_key():
            from ..exercises import exercise_spec
            self.practice_history = copy.deepcopy(message.get('practices', []))
            self.table.setRowCount(len(self.sessions) + len(self.practice_history))
            for row, record in enumerate(self.practice_history, start=len(self.sessions)):
                count = record.get('self_reported_count')
                values = [record['created_at'].replace('T', ' ')[:19] + ' UTC',
                          exercise_spec(record['exercise_id'])['label'] + f" · 第{record.get('set_index', 1)}组跟练",
                          '本人记录 / 本机', '本人记录 ' + str(count) if count is not None else '未填写',
                          '无自动测量', '已保存' if record['state'] == 'COMMITTED' else '练习未结束']
                for column, value in enumerate(values): self.table.setItem(row, column, QTableWidgetItem(value))
                self.table.setRowHeight(row, 54)
            self.history_empty.setVisible(not self.sessions and not self.practice_history)
        if message['kind']=='training_feedback_saved':
            for report in self.report_windows:
                if report.snapshot['id']==message['snapshot']['id'] and report.overview:
                    report.overview.setHtml(render_result_summary(message['snapshot']))
        if message['kind']=='report':
            dialog=self.report_windows[-1]
            parent=self.parentWidget()
            while parent and not hasattr(parent,'_return_recovery'):parent=parent.parentWidget()
            if parent:
                entry=QPushButton('返回康复',dialog)
                entry.clicked.connect(lambda: self._report_to_recovery(dialog,parent))
                dialog.layout().addWidget(entry)

    def _report_to_recovery(self,dialog,parent):
        if parent._rehab_locked():
            self.notice.setText('请先结束并保存当前任务，再返回康复。');return
        dialog.close()
        if parent.return_context and parent.return_context[0]=='health':parent._return_context()
        else:parent._return_recovery()

    def _silver_command(self, operation):
        sharing=operation.get('operation')=='consent' or operation.get('operation')=='feedback' and operation.get('share')
        if sharing and QMessageBox.question(self,'银发照护共享','确认修改共享范围或共享本条本人情况？这不会建立真实远程连接。')!=QMessageBox.Yes:
            if self.silver_dialog:
                self.silver_dialog.pending=False
                self.silver_dialog._restore_busy_controls()
                self.silver_dialog.error.setText('已取消，未保存或共享此操作。')
            return
        super()._silver_command(operation)

    def _in_product_scope(self, session):
        return all(session_value(session,key)==value for key,value in self._body_scope_key().items())

    def _open_report(self):
        if not self._selected():self.notice.setText('请先选择要打开的报告。');return
        row = self._selected()[0] - len(self.sessions)
        if row >= 0:
            if row < len(self.practice_history): self._open_practice_record(self.practice_history[row]['id'])
            return
        super()._open_report()

    def _open_body_report(self):
        item=self.body_overview.current_item()
        if self.busy:self.notice.setText('正在读取资料，请稍候。');return
        if not item or not item.get('session_id'):self.notice.setText('请先选择已有评估记录，再查看报告。');return
        super()._open_body_report()

    def _export_selected(self):
        if not self._selected():self.notice.setText('请先选择要导出的报告。');return
        if self._selected()[0] >= len(self.sessions):self.notice.setText('此项是独立跟练记录，可打开查看原内容。');return
        super()._export_selected()

    def _delete_report(self):
        if not self._selected():self.notice.setText('请先选择要删除的报告。');return
        if self._selected()[0] >= len(self.sessions):self.notice.setText('跟练事实保留，不按测量报告删除。');return
        super()._delete_report()

    def _open_longitudinal(self):
        if any(row >= len(self.sessions) for row in self._selected()):
            self.notice.setText('本人记录不作为自动测量趋势基准。');return
        super()._open_longitudinal()

    def _compare(self):
        if any(row >= len(self.sessions) for row in self._selected()):
            self.notice.setText('本人记录与自动测量分别保留，不直接比较。');return
        super()._compare()
