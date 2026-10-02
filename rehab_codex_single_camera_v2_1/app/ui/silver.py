"""Optional native silver-mode workspace. No camera or database work on UI thread."""
from uuid import uuid4
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QListWidget, QAbstractItemView, QComboBox, QLineEdit,
    QCheckBox, QScrollArea, QInputDialog, QFormLayout)

from ..silver_store import FEELINGS, CHECKLIST

STATUS = {'OPEN': '待回应', 'ACKNOWLEDGED': '已查看', 'CLAIMED': '已认领 / 已安排',
          'RESOLVED': '已处理', 'AWAITING_CONFIRMATION': '整改完成，待本人确认',
          'ACTIVE': '进行中', 'COMPLETED': '视觉核实完成', 'INTERRUPTED': '已中断',
          'DECLINED': '本轮不适合', 'SNOOZED': '已延期', 'OFFERED': '待本人选择', 'ACCEPTED': '已接受提醒'}


class SilverDialog(QDialog):
    operation = Signal(dict)
    navigate = Signal(str, str)
    privacy = Signal()
    task = Signal(str)
    family_demo_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('银发健康守护')
        self.resize(1040, 760)
        self.setMinimumSize(800, 600)
        self.setStyleSheet('QPushButton {min-height:38px;} QLabel, QComboBox, QLineEdit, QListWidget {font-size:18px;}')
        self.data, self.pending, self.items = {}, False, []
        self._help_request_id = None
        self.speech = None
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        title = QLabel('银发健康守护')
        title.setStyleSheet('font-size:28px;font-weight:600;')
        top.addWidget(title, 1)
        self.role = QComboBox()
        self.role.addItems(['本人', '本机家属（同电脑演示）'])
        self.role.currentIndexChanged.connect(self._role_changed)
        top.addWidget(self.role)
        layout.addLayout(top)
        self.scope_label = self.label('仅本人选择的内容会出现在家属角色；尚未连接手机。')
        layout.addWidget(self.scope_label)
        actions = QHBoxLayout()
        self.training = self.button('开始训练', lambda: self.navigate.emit('training', 'primary'), actions)
        self.today_button = self.button('今天的任务', lambda: self.tabs.setCurrentIndex(0), actions)
        self.help_button = self.button('我需要帮助', lambda: self.request('help', '本人主动请求帮助'), actions)
        self.stop = self.button('暂停摄像头', self.privacy.emit, actions)
        layout.addLayout(actions)
        self.error = self.label('')
        self.error.setStyleSheet('color:#9b3a24;font-weight:600;')
        layout.addWidget(self.error)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        today = self.page('今天的任务')
        self.coverage = self.label('尚无数据；未启用场景未监测。')
        today.addWidget(self.coverage)
        self.live = self.label('')
        today.addWidget(self.live)
        self.activity_tasks = QListWidget()
        today.addWidget(self.activity_tasks, 1)
        task_row = QHBoxLayout()
        self.task_buttons = []
        for label, key in (('站立任务', 'stand'), ('步行任务', 'walk'), ('稍后提醒', 'snooze'),
                           ('本轮不适合', 'skip'), ('停止任务', 'stop'), ('仅自报完成', 'self_report')):
            self.task_buttons.append(self.button(label, lambda checked=False, k=key: self.task.emit(k), task_row))
        today.addLayout(task_row)
        row = QHBoxLayout()
        self.camera_role = QComboBox()
        self.camera_role.addItem('A：当前主相机', 'primary')
        self.camera_role.addItem('B：已选第二相机', 'secondary')
        row.addWidget(self.camera_role)
        self.activity = self.button('准备活动观察', lambda: self.navigate.emit('activity', self.camera_role.currentData()), row)
        self.bedroom = self.button('床边演示', lambda: self.navigate.emit('bedroom_demo', self.camera_role.currentData()), row)
        self.safety = self.button('安全演示', lambda: self.navigate.emit('safety_demo', self.camera_role.currentData()), row)
        today.addLayout(row)
        today.addWidget(self.label('康复双摄同时观察同一人。活动 / 床边 / 安全按模式切换，不同时监测另一房间；须重新圈区与确认。'))

        changes = self.page('功能变化')
        changes.addWidget(self.label('选 3～5 次同条件报告建立固定参考期；选之后的单次报告比较。不会自动诊断或提高训练量。'))
        self.sessions = QListWidget()
        self.sessions.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.sessions.setMinimumHeight(130)
        changes.addWidget(self.sessions, 1)
        form = QFormLayout()
        self.protocol, self.chair, self.support = QLineEdit(), QLineEdit(), QLineEdit()
        for label, control, placeholder in (('任务协议', self.protocol, '例如：固定脚位，舒适速度，5 次'),
                ('椅子 / 环境', self.chair, '例如：同一把蓝椅；肩部任务可填不适用'),
                ('扶物安排', self.support, '本次实际是否扶物、使用何种支撑')):
            control.setPlaceholderText(placeholder)
            form.addRow(label, control)
        changes.addLayout(form)
        self.attest = self.button('已逐条核对：记录所选报告的实际条件', self._conditions, changes)
        row = QHBoxLayout()
        self.metric_select = QComboBox()
        for label, value in (('起立 / 出程时间', 'outbound_s'), ('完整次数', 'completed'), ('可观察幅度', 'range_deg')):
            self.metric_select.addItem(label, value)
        row.addWidget(self.metric_select)
        self.create_reference = self.button('建立新参考期', lambda: self.send('reference', ids=self.selected_ids(), metric=self.metric_select.currentData()), row)
        self.references = QComboBox()
        row.addWidget(self.references, 1)
        self.compare = self.button('比较所选单次', self._compare, row)
        changes.addLayout(row)
        self.card = self.label('建立个人参考中。没有足够记录时不显示身体下降结论。')
        changes.addWidget(self.card)
        row = QHBoxLayout()
        self.feeling = QComboBox()
        self.feeling.addItems(FEELINGS)
        row.addWidget(self.feeling)
        self.share_feeling = QCheckBox('同意分享本条感受')
        row.addWidget(self.share_feeling)
        self.feedback_button = self.button('记录本人情况', self._feedback, row)
        changes.addLayout(row)

        requests = self.page('家庭回应与安全')
        requests.addWidget(self.label('本机双角色：已查看 ≠ 已联系 / 已到场。没有网络通道时不能显示远端已收到。'))
        self.requests = QListWidget()
        requests.addWidget(self.requests, 1)
        self.detail = self.label('选择请求或事件，查看来源和真实回应。')
        requests.addWidget(self.detail)
        self.requests.currentRowChanged.connect(self._selection)
        row = QHBoxLayout()
        self.ack = self.button('我已查看', lambda: self.respond('ack'), row)
        self.claim = self.button('我来联系 / 处理', lambda: self.respond('claim'), row)
        self.resolve = self.button('记录处理结果', lambda: self.respond('resolve'), row)
        self.confirm = self.button('本人确认整改完成', lambda: self.respond('confirm'), row)
        requests.addLayout(row)
        self.contact = self.button('希望家人联系', lambda: self.request('contact', '本人希望家人联系'), requests)
        self.checklist = QComboBox()
        self.checklist.addItems(CHECKLIST)
        requests.addWidget(self.checklist)
        self.check_note = QLineEdit()
        self.check_note.setPlaceholderText('人工检查发现的问题及希望完成的整改，不用摄像头猜测环境安全')
        requests.addWidget(self.check_note)
        self.check_button = self.button('建立居家整改任务', lambda: self.request('checklist', self.checklist.currentText()+'：'+self.check_note.text()), requests)

        sharing = self.page('共享与提示设置')
        sharing.addWidget(self.label('仅在本人或获授权人员明确选择后共享；不包含视频、骨架、设备路径与完整个人档案。'))
        self.recipient = QLineEdit()
        self.recipient.setPlaceholderText('家属称呼（本机角色，不是已认证的远端身份）')
        sharing.addWidget(self.recipient)
        self.grants = {}
        for key, label in (('summary', '训练 / 活动摘要与覆盖'), ('requests', '本人联系与求助请求'),
                           ('safety', '按预设授权共享安全事件'), ('changes', '本人选择分享的情况'), ('checklist', '居家整改任务')):
            control = QCheckBox(label)
            sharing.addWidget(control)
            self.grants[key] = control
        self.save_policy = self.button('确认共享范围', lambda: self.send('consent', recipient=self.recipient.text(),
            grants=[k for k, c in self.grants.items() if c.isChecked()], revision=self.data.get('policy', {}).get('revision', 0)), sharing)
        self.revoke = self.button('撤销全部共享', lambda: self.send('consent', recipient='', grants=[],
            revision=self.data.get('policy', {}).get('revision', 0)), sharing)
        self.phone_demo = self.button('手机家属联动（仅隔离测试资料）', self.family_demo_requested.emit, sharing)
        self.voice = QCheckBox('启用本机语音（请先测试是否能听见）')
        sharing.addWidget(self.voice)
        self.voice_test = self.button('测试语音提示', lambda: self.speak('这是本机提示音测试，请确认能够听清。', force=True), sharing)
        sharing.addStretch()
        row = QHBoxLayout()
        self.updated = self.label('尚未刷新')
        row.addWidget(self.updated, 1)
        self.button('刷新', self.refresh, row)
        self.button('返回康复界面', self.close, row)
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self._last_spoken = None

    @staticmethod
    def label(value):
        label = QLabel(value)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    @staticmethod
    def button(label, callback, layout):
        button = QPushButton(label)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def page(self, name):
        host = QWidget()
        host.setObjectName('scrollContent')
        layout = QVBoxLayout(host)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(host)
        self.tabs.addTab(scroll, name)
        return layout

    def send(self, operation='refresh', **kw):
        if self.pending:
            self.error.setText('正在读取或保存，请等待当前操作完成。')
            return
        self.pending = True
        self.operation.emit(dict(operation=operation, family=self.role.currentIndex() == 1, **kw))

    def refresh(self):
        if self.isVisible():
            self.send()

    def _role_changed(self):
        self.data = {}
        self.requests.clear()
        self.activity_tasks.clear()
        self.sessions.clear()
        self.coverage.setText('等待授权检查；旧角色数据已隐藏。')
        self.detail.clear()
        self.card.setText('请返回本人角色查看未共享的变化记录。')
        self.live.clear()
        self.tabs.setTabEnabled(1, self.role.currentIndex() == 0)
        self.tabs.setTabEnabled(3, self.role.currentIndex() == 0)
        self.refresh()

    def selected_ids(self):
        return [i.data(Qt.ItemDataRole.UserRole) for i in self.sessions.selectedItems()]

    def _conditions(self):
        self.send('conditions', ids=self.selected_ids(), protocol=self.protocol.text(), chair=self.chair.text(), support=self.support.text())

    def _compare(self):
        ids = self.selected_ids()
        if len(ids) != 1:
            self.error.setText('请只选一次新报告与固定参考期比较。')
            return
        self.send('compare', current_id=ids[0], reference_id=self.references.currentData())

    def _feedback(self):
        ids = self.selected_ids()
        if len(ids) != 1:
            self.error.setText('请只选一份本次报告，再记录本人情况。')
            return
        self.send('feedback', id=ids[0], feeling=self.feeling.currentText(), share=self.share_feeling.isChecked())

    def request(self, kind, note):
        if kind == 'help':
            if self._help_request_id is None:
                self._help_request_id = uuid4().hex
            # Manual help remains available during camera failure or an in-flight refresh.
            self.operation.emit(dict(operation='request', family=False, kind=kind, note=note, request_id=self._help_request_id))
            self.error.setText('正在保存本地求助；尚未收到家属回应。')
            return
        self.send('request', kind=kind, note=note, request_id=uuid4().hex)

    def _selection(self):
        row = self.requests.currentRow()
        if not 0 <= row < len(self.items):
            for button in (self.ack, self.claim, self.resolve, self.confirm):
                button.setEnabled(False)
            return
        kind, item = self.items[row]
        history = '\n'.join(f"{h.get('actor', h.get('operator', ''))} · {h.get('action', h.get('status', ''))} · {h.get('note', '')}" for h in item.get('history', []))
        self.detail.setText((item.get('note') or item.get('message', ''))+'\n'+history)
        state = item['status']
        self.ack.setEnabled(state == 'OPEN')
        self.claim.setEnabled(state == 'ACKNOWLEDGED')
        self.resolve.setEnabled(state == 'CLAIMED')
        self.confirm.setEnabled(state == 'AWAITING_CONFIRMATION' and self.role.currentIndex() == 0)

    def respond(self, action):
        row = self.requests.currentRow()
        if not 0 <= row < len(self.items):
            self.error.setText('请先选择要回应的请求或事件。')
            return
        kind, item = self.items[row]
        note = ''
        if action in ('resolve', 'confirm'):
            note, accepted = QInputDialog.getMultiLineText(self, '人工处理记录', '记录实际做了什么 / 确认情况（不自动代表已到场）：')
            if not accepted or not note.strip():
                return
        if kind == 'event':
            self.send('event', id=item['id'], status={'ack': 'ACKNOWLEDGED', 'claim': 'CLAIMED', 'resolve': 'RESOLVED'}[action], note=note)
        else:
            if item['kind'] == 'checklist' and action == 'resolve':
                action = 'submit'
            self.send('respond', id=item['id'], action=action, note=note, revision=item['revision'])

    def show_error(self, message):
        self.pending = False
        self.error.setText(message+'（未显示成功，请核对后重试）')
        if self.role.currentIndex() == 1:
            self.data = {}
            self.requests.clear()
            self.activity_tasks.clear()
            self.detail.clear()
            self.live.clear()
            self.coverage.setText('授权或连接不可用，当前数据未知。')

    def render(self, data):
        self.pending = False
        if bool(data['family']) != (self.role.currentIndex() == 1):
            self.refresh()
            return
        self.data = data
        if data.get('operation') == 'request' and data.get('request_id') == self._help_request_id:
            self._help_request_id = None
        self.error.clear()
        family = data['family']
        self.scope_label.setText(' / '.join(data['scope'].values())+' · 本机双角色；手机未连接')
        daily = data.get('daily')
        self.coverage.setText((f"今天完成训练 {daily['training_sessions']} 次 · 有效观察 {daily['valid_s']:.1f} 秒 / 观察跨度 {daily['observed_span_s']:.1f} 秒\n"+daily['note'])
            if daily else '未共享今日摘要。')
        state = {'INACTIVE': '未监测', 'ONLINE': '观察中', 'PRIVACY_PAUSED': '本人已暂停，期间未监测',
                 'OFFLINE': '设备离线，当前未知', 'ERROR': '设备异常，当前未知', 'SAVE_FAILED': '结果待保存'}.get(data['state'], data['state'])
        summary = data.get('live_summary', {})
        self.live.setText('当前：'+state+' · 其他场景未监测\n'+summary.get('message', ''))
        self.activity_tasks.clear()
        for t in (daily or {}).get('tasks', []):
            evidence = '本人自报（不是视觉核实）' if t.get('self_reported') else '视觉核实' if t.get('visual_verified') else '尚未核实完成'
            self.activity_tasks.addItem(f"{STATUS.get(t['status'], t['status'])} · {t['kind']} · {t.get('visible_s', 0):.1f} 秒 · {evidence}"+
                (' · DEMO_THRESHOLDS' if t.get('demo_thresholds') else ''))
        selected = set(self.selected_ids())
        self.sessions.clear()
        for s in data.get('sessions', []):
            self.sessions.addItem(f"{s.get('start_utc') or '时间未知'} · {s['label']} · {s['side']} · {s['status']}")
            item = self.sessions.item(self.sessions.count()-1)
            item.setData(Qt.ItemDataRole.UserRole, s['id'])
            item.setSelected(s['id'] in selected)
        previous = self.references.currentData()
        self.references.clear()
        for r in data.get('references', []):
            self.references.addItem(f"参考期 {r['reference_revision']} · {r['metric']} · {len(r['session_ids'])} 次", r['id'])
        index = self.references.findData(previous)
        if index >= 0:
            self.references.setCurrentIndex(index)
        if 'card' in data:
            card = data['card']
            message = card['message']
            if card['status'] == 'OBSERVED':
                percent = '参考为零，不计算百分比' if card['percent'] is None else f"差异 {card['percent']:+.1f}%"
                message = f"{card['metric_label']}：参考 {card['reference']:.1f} → 本次 {card['current']:.1f}，{percent}\n"+message
            self.card.setText(message)
        last = self.requests.currentRow()
        self.requests.clear()
        self.items = [('request', r) for r in data['requests']]+[('event', e) for e in data['events']]
        for kind, item in self.items:
            self.requests.addItem(f"{STATUS.get(item['status'], item['status'])} · {item.get('origin', '未知来源')}\n"+(item.get('note') or item.get('message', '')))
        self.requests.setCurrentRow(max(0, min(last, len(self.items)-1)))
        if data.get('operation') == 'request':
            # Make the committed result visible, not a silent update in another tab.
            self.tabs.setCurrentIndex(2)
            for row, (kind, item) in enumerate(self.items):
                if kind == 'request' and item['id'] == data.get('request_id'):
                    self.requests.setCurrentRow(row)
                    break
        for f in data.get('feedback', []):
            self.activity_tasks.addItem('历史本人自报（'+f['updated_utc']+'）：'+f['feeling']+(' · 已同意分享' if f['shared'] else ' · 仅本人'))
        for card in data.get('change_cards', []):
            numbers = (f"参考 {card['reference']:.1f} → 本次 {card['current']:.1f} · " if card['status'] == 'OBSERVED' else '')
            self.activity_tasks.addItem('功能变化：'+numbers+card['message'])
        policy = data['policy']
        # Do not erase a draft while the user is editing sharing controls.
        if not hasattr(self, '_policy_revision') or self._policy_revision != policy['revision']:
            self.recipient.setText(policy['recipient'])
            for k, control in self.grants.items():
                control.setChecked(k in policy['grants'])
            self._policy_revision = policy['revision']
        self.tabs.setTabEnabled(1, not family)
        self.tabs.setTabEnabled(3, not family)
        for widget in (self.training, self.help_button, self.stop, self.activity, self.bedroom, self.safety,
                       self.contact, self.check_button, self.check_note, self.checklist):
            widget.setEnabled(not family)
        for button in self.task_buttons:
            button.setEnabled(not family and data['state'] == 'ONLINE' and data.get('active_scene') == 'activity')
        self.updated.setText('观察快照：'+data.get('observation_snapshot_utc', data['refreshed_utc'])+' · 本机回执不表示电话已接通')
        cue = summary.get('message') if summary.get('reminder_due') else None
        if cue and cue != self._last_spoken:
            self.speak(cue)
        self._last_spoken = cue

    def speak(self, message, *, force=False):
        if not force and not self.voice.isChecked():
            return
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            if not QTextToSpeech.availableEngines():
                raise RuntimeError('没有可用本机语音引擎')
            if self.speech is None:
                self.speech = QTextToSpeech(self)
            self.speech.stop()
            self.speech.say(message)
        except Exception:
            self.error.setText('语音不可用，请以文字提示为准；未下载或调用在线语音。')

    def closeEvent(self, event):
        if self.speech:
            self.speech.stop()
        super().closeEvent(event)
