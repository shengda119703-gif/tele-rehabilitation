"""Owner-scoped UI adaptation of the original rehabilitation window and command bus."""
from ..assessment import session_value
from .main_window import MainWindow
from PySide6.QtWidgets import QMessageBox


class ProductRehabWindow(MainWindow):
    def _silver_command(self, operation):
        sharing=operation.get('operation')=='consent' or operation.get('operation')=='feedback' and operation.get('share')
        if sharing and QMessageBox.question(self,'银发照护共享','确认修改共享范围或共享本条本人情况？这不会建立真实远程连接。')!=QMessageBox.Yes:
            if self.silver_dialog:
                self.silver_dialog.pending=False
                self.silver_dialog.error.setText('已取消，未保存或共享此操作。')
            return
        super()._silver_command(operation)

    def _in_product_scope(self, session):
        return all(session_value(session,key)==value for key,value in self._body_scope_key().items())

    def _handle_message(self, message):
        if message['kind']=='history':
            message=dict(message,sessions=[s for s in message['sessions'] if self._in_product_scope(s)])
        elif message['kind'] in ('report','training_review') and not self._in_product_scope(message['snapshot']):
            self.notice.setText('记录所属用户、输入来源或使用情境已变化，请重新选择当前范围的记录。')
            return
        super()._handle_message(message)

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
