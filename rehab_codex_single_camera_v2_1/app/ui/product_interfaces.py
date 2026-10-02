"""UI entrances to existing ProductService ports; no device or domain implementation here."""
import json
from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QFileDialog, QMessageBox, QDockWidget, QTextBrowser,
    QPlainTextEdit, QCheckBox)


class ProductInterfaces:
    def _interface_button(self, layout, key, text, callback):
        item = QPushButton(text)
        item.setObjectName(key)
        item.clicked.connect(callback)
        layout.addWidget(item)
        self.interface_buttons[key] = item
        return item

    def _build_global_assistant(self, layout):
        row = QHBoxLayout()
        row.addStretch()
        self._interface_button(row, 'globalAssistant', '问康复管家', self._open_global_assistant)
        layout.addLayout(row)
        self.assistant_shortcut = QShortcut(QKeySequence('Ctrl+J'), self)
        self.assistant_shortcut.activated.connect(self._open_global_assistant)
        self.assistant_dock = QDockWidget('AI 康复管家', self)
        self.assistant_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        self.assistant_dock.setFeatures(QDockWidget.DockWidgetClosable)
        content = QWidget()
        content.setMinimumWidth(340)
        area = QVBoxLayout(content)
        self.assistant_context = QLabel()
        self.assistant_context.setWordWrap(True)
        area.addWidget(self.assistant_context)
        self.dock_chat = QTextBrowser()
        self.dock_chat.setOpenExternalLinks(False)
        area.addWidget(self.dock_chat)
        self.dock_input = QPlainTextEdit()
        self.dock_input.setPlaceholderText('查询已保存记录，或记录今天的感受')
        self.dock_input.setMaximumHeight(100)
        area.addWidget(self.dock_input)
        self.dock_private = QCheckBox('本轮不记录')
        self.dock_private.toggled.connect(self.private_turn.setChecked)
        self.private_turn.toggled.connect(self.dock_private.setChecked)
        area.addWidget(self.dock_private)
        self._interface_button(area, 'dockSend', '发送',
                               lambda: self._send_chat(self.dock_input.toPlainText().strip(), inline=True))
        self.assistant_dock.setWidget(content)
        self.addDockWidget(Qt.RightDockWidgetArea, self.assistant_dock)
        self.assistant_dock.hide()

    def _open_global_assistant(self):
        self.assistant_context.setText('当前页面：'+self.title.text()+
            '。使用同一用户及已保存数据；页面内容尚不自动传给模型。')
        self.assistant_dock.show()
        self.resizeDocks([self.assistant_dock], [380], Qt.Horizontal)
        self.assistant_dock.raise_()
        self.dock_input.setFocus()

    def _voice_controls(self, layout):
        self.assistant_reference = QLabel('等待当前用户数据。')
        self.assistant_reference.setWordWrap(True)
        layout.addWidget(self.assistant_reference)
        note = QLabel('上传资料会保存到健康档案，不自动作为模型上下文。图片识别须许可，候选结果在健康档案中核对后确认。')
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self._interface_button(row, 'assistantAttachment', '上传资料 / 图片 / 视频', self._add_attachment)
        self._interface_button(row, 'assistantImage', '识别健康图片', self._parse_image)
        self._interface_button(row, 'voiceInput', '语音输入', self._voice_input)
        self._interface_button(row, 'voiceOutput', '朗读最近回复', self._voice_output)
        self._interface_button(row, 'voiceCancel', '停止语音', lambda: self._request('voice.cancel'))
        layout.addLayout(row)
        self.voice_status = QLabel('语音接口已保留，正在核对桌面端支持情况。')
        self.voice_status.setWordWrap(True)
        layout.addWidget(self.voice_status)

    def _voice_input(self):
        if self.private_turn.isChecked():
            self._message('当前语音接口不支持本轮不记录。请使用文字输入，隐私选项保持有效。')
            return
        if QMessageBox.question(self, '语音输入', '使用已配置的语音服务识别并发送为一轮管家对话，按现有规则处理和记录。是否继续？') == QMessageBox.Yes:
            self._request('voice.input', {})

    def _voice_output(self):
        message = next((m for m in reversed(self.snapshot.get('state', {}).get('chat', [])) if m['role']=='agent'), None)
        if message:
            self._request('voice.output', {'id': message['id']})
        else:
            self._message('暂无可朗读的管家回复。')

    def _devices_tab(self, tabs):
        page = QWidget()
        area = QVBoxLayout(page)
        self.device_status = QLabel('正在核对外部健康数据源。')
        self.device_status.setWordWrap(True)
        area.addWidget(self.device_status)
        row = QHBoxLayout()
        self._interface_button(row, 'deviceRefresh', '刷新设备与服务状态', lambda: self._request('extensions.status'))
        self._interface_button(row, 'deviceImport', '导入设备数据文件', self._import_device_file)
        self._interface_button(row, 'cameraSettings', '康复摄像头 / 回放设置', lambda: self._rehab_action('assessment'))
        area.addLayout(row)
        interval = QHBoxLayout()
        self.device_from = QDateEdit(date.today()-timedelta(days=7))
        self.device_to = QDateEdit(date.today())
        for control in (self.device_from, self.device_to):
            control.setCalendarPopup(True)
            control.setDisplayFormat('yyyy-MM-dd')
        interval.addWidget(QLabel('导入日期范围'))
        interval.addWidget(self.device_from)
        interval.addWidget(self.device_to)
        self.device_adapter = QComboBox()
        interval.addWidget(self.device_adapter)
        area.addLayout(interval)
        row = QHBoxLayout()
        self._interface_button(row, 'devicePull', '读取已配置设备',
            lambda: self._request('device.pull', dict(self._device_dates(), adapter=self.device_adapter.currentData())))
        self._interface_button(row, 'healthkitImport', '导入 Apple Health 数据',
            lambda: self._request('healthkit.import', self._device_dates()))
        self._interface_button(row, 'healthkitDiagnostics', 'Apple Health 权限 / 导入状态',
            lambda: self._request('healthkit.diagnostics'))
        area.addLayout(row)
        note = QLabel('Apple Health 权限由 iPhone 端请求，Windows 不模拟授权。通用设备可导入血压、心率、血氧、活动等既有指标。特殊硬件沿用已配置数据源；未连接设备不表示已监测。视频沿用康复摄像头与回放，无视频健康分析。')
        note.setWordWrap(True)
        area.addWidget(note)
        area.addStretch()
        tabs.addTab(page, '设备')

    def _device_dates(self):
        return {'from': self.device_from.date().toString('yyyy-MM-dd'),
                'to': self.device_to.date().toString('yyyy-MM-dd')}

    def _import_device_file(self):
        if not self.owner or self.pending:
            self._message('请先选择用户并等待当前操作完成。')
            return
        filename, _ = QFileDialog.getOpenFileName(self, '选择设备导出数据（含 ownerId、source、measurements）', '', 'JSON (*.json)')
        if not filename:
            return
        from pathlib import Path
        data = self._read_input_file(Path(filename), 2*1024*1024)
        if data is None:
            return
        try:
            payload = json.loads(data)
            if not isinstance(payload, dict) or payload.get('ownerId') != self.owner or payload.get('source') not in ('device','demo') or not isinstance(payload.get('measurements'), list):
                raise ValueError('文件用户须与当前用户一致，并包含 source 和 measurements。')
        except (ValueError, UnicodeError) as error:
            self._message('设备文件未导入：'+str(error))
            return
        if QMessageBox.question(self, '导入设备记录', f'向当前用户导入 {len(payload["measurements"])} 条设备记录？软件将验证指标、单位、来源和时间。') == QMessageBox.Yes:
            self._request('device.import', payload)

    def _sync_controls(self, layout):
        self.sync_status = QLabel('跨设备接口已保留，正在核对连接状态。')
        self.sync_status.setWordWrap(True)
        layout.addWidget(self.sync_status)
        row = QHBoxLayout()
        for key, text, operation in [('syncStart','连接同步','sync.start'),
            ('syncStatus','刷新同步状态','sync.status'),('syncPoll','接收并验证同步数据','sync.poll'),
            ('syncPublish','同步已授权通知与许可','sync.publish'),('syncClose','断开同步','sync.close')]:
            self._interface_button(row, key, text, lambda checked=False, op=operation: self._request(op))
        layout.addLayout(row)
        self.external_notification_status = QLabel('正在核对外部通知渠道。')
        self.external_notification_status.setWordWrap(True)
        layout.addWidget(self.external_notification_status)
        self._interface_button(layout, 'notificationSettings', '通知设置与发送台账', lambda: self.navigate('notifications'))
        self._interface_button(layout, 'familySettings', '家庭共享与授权', lambda: self.navigate('family'))
        layout.addWidget(QLabel('外部服务由宿主配置；未启用时显示不可用。接口已迁，外部设备 / 平台尚未验收。'))

    def _render_extensions(self, result):
        self.extension_status = result
        voice = result.get('voice', {})
        available = bool(voice.get('available'))
        self.voice_status.setText('语音：'+('已配置 · '+voice.get('phase','') if available else '当前桌面宿主未接入 ASR / TTS'))
        for key in ('voiceInput','voiceOutput','voiceCancel'):
            self.interface_buttons[key].setEnabled(available)
        devices = result.get('devices', [])
        self.device_adapter.clear()
        for name in devices:
            self.device_adapter.addItem(name, name)
        self.interface_buttons['devicePull'].setEnabled(bool(devices))
        for key in ('healthkitImport','healthkitDiagnostics'):
            self.interface_buttons[key].setEnabled(bool(result.get('healthkit')))
        self.device_status.setText('康复摄像头：请在康复输入设置中核对；此页不自动开启。\n外部设备：'+('、'.join(devices) or '未配置')+
            '\nApple Health：'+('已配置外部数据源，实机未验收' if result.get('healthkit') else '未连接 iPhone 健康数据源')+
            '\n导入文件用户编号：'+(self.owner or '请先选择用户'))
        self.external_notification_status.setText('外部通知：'+('渠道已配置；接受不等于送达，外部验收待完成' if result.get('notification') else '未配置外部渠道；本机通知台账可用'))
        self.notification_status.setText(self.external_notification_status.text())
        sync = result.get('sync', {})
        self.sync_status.setText('同步：'+{'local-only':'仅本机','connecting':'连接中','cross-device':'跨设备已连接','failed':'连接失败'}.get(sync.get('mode'),'未连接')+' · '+sync.get('detail',''))
        # A local-only host is not an available cross-device transport.
        for key in ('syncStart','syncStatus','syncPoll','syncPublish','syncClose'):
            self.interface_buttons[key].setEnabled(bool(result.get('syncAvailable')) or sync.get('mode', 'local-only') != 'local-only')

    def _interface_result(self, operation, result):
        if operation == 'extensions.status':
            self._render_extensions(result)
            return True
        if operation.startswith('sync.'):
            if operation == 'sync.poll':
                rejected = sum(not item.get('applied') for item in result.get('outcomes', []))
                self._message(f'已核对同步输入；{rejected} 条未应用。未应用的数据未视为同步成功。')
                self._request('snapshot')
            else:
                self._message('同步操作已处理；接受不代表对端收到。')
                self._request('extensions.status')
            return True
        if operation == 'healthkit.diagnostics':
            d = result.get('diagnostics', {})
            self.device_status.setText(self.device_status.text()+f'\nApple Health：授权状态 {d.get("authorizationStatus", "unknown")}；数据新鲜度 {d.get("freshness", "unknown")}；样本 {d.get("sampleCount", "未知")}。权限仍由 iPhone 端管理。')
            return True
        if operation in ('voice.output','voice.cancel'):
            self._message('语音操作已提交；不代表播放验收通过。')
            return True
        return False
