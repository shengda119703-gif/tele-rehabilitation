"""Owner-scoped UI adaptation of the original rehabilitation window and command bus."""
from ..assessment import session_value
from ..reports import render_result_summary
from .main_window import MainWindow
from PySide6.QtWidgets import QMessageBox, QPushButton


class ProductRehabWindow(MainWindow):
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
        if message['kind']=='history':
            message=dict(message,sessions=[s for s in message['sessions'] if self._in_product_scope(s)])
        elif message['kind'] in ('report','training_review') and not self._in_product_scope(message['snapshot']):
            self.notice.setText('记录所属用户、输入来源或使用情境已变化，请重新选择当前范围的记录。')
            return
        super()._handle_message(message)
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
        dialog.close();parent._return_recovery()

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
        super()._open_report()

    def _open_body_report(self):
        item=self.body_overview.current_item()
        if self.busy:self.notice.setText('正在读取资料，请稍候。');return
        if not item or not item.get('session_id'):self.notice.setText('请先选择已有评估记录，再查看报告。');return
        super()._open_body_report()

    def _export_selected(self):
        if not self._selected():self.notice.setText('请先选择要导出的报告。');return
        super()._export_selected()

    def _delete_report(self):
        if not self._selected():self.notice.setText('请先选择要删除的报告。');return
        super()._delete_report()
